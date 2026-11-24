import { readFileSync, writeFileSync, mkdtempSync, rmSync, existsSync, mkdirSync } from "node:fs";
import { resolve, join, dirname } from "node:path";
import { tmpdir } from "node:os";
import { pathToFileURL } from "node:url";
import { execFileSync, execFile } from "node:child_process";
import {promisify} from 'node:util';
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
async function awsAsync(operation,args) {
  const result=await promisify(execFile)('aws',['s3api',operation,...args,'--output','json','--no-cli-pager'],{encoding:'utf8',windowsHide:true,timeout:120000,maxBuffer:1024*1024,env:{...process.env,AWS_CLI_AUTO_PROMPT:'off'}});
  return JSON.parse(result.stdout||'{}');
}
export async function publishFrontend({ bundle, bucket, owner, run = awsAsync, concurrency = 6, onProgress = () => {} }) {
  if(!Number.isInteger(concurrency)||concurrency<1||concurrency>8)throw Error('Concurrency must be between 1 and 8');
  if (
    !/^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$/.test(bucket ?? "") ||
    !/^\d{12}$/.test(owner ?? "")
  )
    throw Error("Supply the private bucket and expected AWS account owner");
  const m = verifyFrontendBundle(bundle),
    scope = ["--bucket", bucket, "--expected-bucket-owner", owner];
  const block = (await run(
    "get-public-access-block",
    scope,
  )).PublicAccessBlockConfiguration;
  if (
    ![
      "BlockPublicAcls",
      "IgnorePublicAcls",
      "BlockPublicPolicy",
      "RestrictPublicBuckets",
    ].every((k) => block?.[k] === true)
  )
    throw Error("Private bucket protections are required");
  const ownership = (await run(
    "get-bucket-ownership-controls",
    scope,
  )).OwnershipControls;
  if (
    !ownership?.Rules?.some((r) => r.ObjectOwnership === "BucketOwnerEnforced")
  )
    throw Error("Bucket owner enforced ownership is required");
  if ((await run("get-bucket-versioning", scope)).Status !== "Enabled")
    throw Error("Bucket versioning is required");
  const encryption = (await run(
    "get-bucket-encryption",
    scope,
  )).ServerSideEncryptionConfiguration;
  if (
    !encryption?.Rules?.some((r) =>
      ["AES256", "aws:kms"].includes(
        r.ApplyServerSideEncryptionByDefault?.SSEAlgorithm,
      ),
    )
  )
    throw Error("Encrypted private bucket is required");
  const cache = "public, max-age=31536000, immutable";
  const put = async (key, path, bytes, type) => {
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
      verify(await head());
      return;
    } catch (error) {
      if (!missing(error)) throw error;
    }
    try {
      await run("put-object", [
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
    verify(await head());
  };
  let index=0,completed=0,failure;
  await Promise.all(Array.from({length:Math.min(concurrency,m.files.length)},async()=>{
  while(index<m.files.length&&!failure) {
    const file=m.files[index++];
    try {
    const bytes = frontendFile(bundle, "objects", file);
    await put(
      m.prefix + "/" + file.path,
      resolve(bundle, "objects", file.path),
      bytes,
      file.type,
    );
    onProgress(++completed,m.files.length);
    } catch(error) {failure??=error;}
  }
  }));
  if(failure)throw failure;
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
    await put(
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
  const receipt=args.includes('--receipt')?resolve(option('--receipt')):resolve(process.env.GTT_WORKSPACE_ROOT??process.cwd(),'other/diagnostics/releases','frontend-publication-'+Date.now(),'publication.json');
  if(existsSync(receipt))throw Error('Publication receipt already exists: '+receipt);
  const report = await publishFrontend({
    bundle: resolve(args[0]),
    bucket: option("--bucket"),
    owner: option("--owner"),
    onProgress:(completed,total)=>{if(completed%25===0||completed===total)console.error(`Verified S3 objects: ${completed}/${total}`);},
  });
  mkdirSync(dirname(receipt),{recursive:true});
  writeFileSync(receipt, JSON.stringify(report, null, 2) + "\n", {
    flag: "wx",
  });
  console.log(JSON.stringify({ ...report, receipt }));
}
