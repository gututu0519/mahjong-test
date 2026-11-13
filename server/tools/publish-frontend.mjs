import { readFileSync, writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { resolve, join } from "node:path";
import { tmpdir } from "node:os";
import { pathToFileURL } from "node:url";
import { execFileSync } from "node:child_process";
import { sha } from "../dist/shared/core.js";
import {
  verifyFrontendBundle,
  frontendFile,
} from "../dist/shared/frontend-manifest.js";

export function aws(operation, args) {
  return JSON.parse(
    execFileSync(
      "aws",
      ["s3api", operation, ...args, "--output", "json", "--no-cli-pager"],
      {
        encoding: "utf8",
        windowsHide: true,
        env: { ...process.env, AWS_CLI_AUTO_PROMPT: "off" },
      },
    ) || "{}",
  );
}
const missing = (e) =>
  /NotFound|NoSuchKey|\(404\)|Not Found/.test(String(e.stderr ?? e.message));
const race = (e) =>
  /PreconditionFailed|\(412\)|ConditionalRequestConflict|\(409\)/.test(
    String(e.stderr ?? e.message),
  );
export function publishFrontend({ bundle, bucket, owner, run = aws }) {
  if (
    !/^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$/.test(bucket ?? "") ||
    !/^\d{12}$/.test(owner ?? "")
  )
    throw Error("Supply the private bucket and expected AWS account owner");
  const m = verifyFrontendBundle(bundle),
    scope = ["--bucket", bucket, "--expected-bucket-owner", owner];
  const block = run(
    "get-public-access-block",
    scope,
  ).PublicAccessBlockConfiguration;
  if (
    ![
      "BlockPublicAcls",
      "IgnorePublicAcls",
      "BlockPublicPolicy",
      "RestrictPublicBuckets",
    ].every((k) => block?.[k] === true)
  )
    throw Error("Private bucket protections are required");
  const ownership = run(
    "get-bucket-ownership-controls",
    scope,
  ).OwnershipControls;
  if (
    !ownership?.Rules?.some((r) => r.ObjectOwnership === "BucketOwnerEnforced")
  )
    throw Error("Bucket owner enforced ownership is required");
  if (run("get-bucket-versioning", scope).Status !== "Enabled")
    throw Error("Bucket versioning is required");
  const encryption = run(
    "get-bucket-encryption",
    scope,
  ).ServerSideEncryptionConfiguration;
  if (
    !encryption?.Rules?.some((r) =>
      ["AES256", "aws:kms"].includes(
        r.ApplyServerSideEncryptionByDefault?.SSEAlgorithm,
      ),
    )
  )
    throw Error("Encrypted private bucket is required");
  const cache = "public, max-age=31536000, immutable";
  const put = (key, path, bytes, type) => {
    const checksum = Buffer.from(sha(bytes), "hex").toString("base64");
    const verify = (head) => {
      if (
        head.ContentLength !== bytes.length ||
        head.ChecksumSHA256 !== checksum ||
        head.ContentType !== type ||
        head.CacheControl !== cache ||
        head.Metadata?.["gtt-release"] !== m.release ||
        head.Metadata?.["gtt-sha256"] !== sha(bytes)
      )
        throw Error("Existing object differs; refusing overwrite: " + key);
    };
    const head = () =>
      run("head-object", [
        ...scope,
        "--key",
        key,
        "--checksum-mode",
        "ENABLED",
      ]);
    try {
      verify(head());
      return;
    } catch (error) {
      if (!missing(error)) throw error;
    }
    try {
      run("put-object", [
        ...scope,
        "--key",
        key,
        "--body",
        path,
        "--content-type",
        type,
        "--cache-control",
        cache,
        "--checksum-algorithm",
        "SHA256",
        "--checksum-sha256",
        checksum,
        "--metadata",
        JSON.stringify({ "gtt-release": m.release, "gtt-sha256": sha(bytes) }),
        "--if-none-match",
        "*",
      ]);
    } catch (error) {
      if (!race(error)) throw error;
    }
    verify(head());
  };
  for (const file of m.files) {
    const bytes = frontendFile(bundle, "objects", file);
    put(
      m.prefix + "/" + file.path,
      resolve(bundle, "objects", file.path),
      bytes,
      file.type,
    );
  }
  const manifest_sha256 = sha(readFileSync(resolve(bundle, "manifest.json")));
  const publicManifest = Buffer.from(
    JSON.stringify(
      {
        format: 3,
        kind: m.kind,
        game: m.game,
        release: m.release,
        prefix: m.prefix,
        manifest_sha256,
        files: m.files,
      },
      null,
      2,
    ) + "\n",
  );
  const temp = mkdtempSync(join(tmpdir(), "gtt-frontend-publish-"));
  try {
    const path = join(temp, "public-manifest.json");
    writeFileSync(path, publicManifest);
    put(
      m.prefix + "/_gtt-manifest.json",
      path,
      publicManifest,
      "application/json; charset=utf-8",
    );
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
  return {
    status: "passed",
    game: m.game,
    release: m.release,
    bucket,
    prefix: m.prefix,
    verified_objects: m.files.length,
    manifest_sha256,
    cloudfront_modified: false,
    bootstrap_uploaded: false,
  };
}
if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(resolve(process.argv[1])).href
) {
  const args = process.argv.slice(2),
    option = (name) => args[args.indexOf(name) + 1];
  if (!args.includes("--bucket") || !args.includes("--owner") || !args[0])
    throw Error(
      "Usage: publish-frontend.mjs <bundle> --bucket <private-bucket> --owner <account-id>",
    );
  const report = publishFrontend({
    bundle: resolve(args[0]),
    bucket: option("--bucket"),
    owner: option("--owner"),
  });
  const receipt = resolve(args[0], "publication-" + Date.now() + ".json");
  writeFileSync(receipt, JSON.stringify(report, null, 2) + "\n", {
    flag: "wx",
  });
  console.log(JSON.stringify({ ...report, receipt }));
}
