import {
  readFileSync,
  writeFileSync,
  mkdirSync,
  readdirSync,
  copyFileSync,
  statSync,
  existsSync,
} from "node:fs";
import { resolve, dirname, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { repairModule } from "../dist/gateway/assets.js";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repo = resolve(root, "..");
const args = process.argv.slice(2);
function option(name, fallback) {
  const at = args.indexOf(name);
  if (at < 0) return fallback;
  if (!args[at + 1] || args[at + 1].startsWith("--"))
    throw new Error(`Missing ${name}`);
  return args[at + 1];
}
const sha = (data) => createHash("sha256").update(data).digest("hex");
const write = (path, data) => {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(
    path,
    typeof data === "string" ? data : JSON.stringify(data, null, 2) + "\n",
    { flag: "wx" },
  );
};
const buildId = option(
  "--build-id",
  `gtt-node-${new Date().toISOString().replace(/[-:.]/g, "")}`,
);
if (!/^gtt-node-[A-Za-z0-9_-]+$/.test(buildId))
  throw new Error("Invalid build id");
const manifestPath = option("--assets-manifest");
if (!manifestPath)
  throw new Error(
    "Supply --assets-manifest with the verified Buffalo S3 manifest",
  );
const raw = readFileSync(resolve(manifestPath));
const assets = JSON.parse(raw);
if (
  assets.game !== "buffalo-win" ||
  !/^[a-f0-9]{20}$/.test(assets.release) ||
  !assets.files?.length ||
  assets.prefix !== `releases/buffalo-win/${assets.release}`
)
  throw new Error("Invalid S3 manifest");
const client = resolve(repo, "clients/buffalo-win");
const seen = new Set();
// Check actual Node-prepared bytes against the existing published asset version.
// This reads local assets only; packaging never uploads or changes S3.
for (const file of assets.files) {
  if (
    typeof file.path !== "string" ||
    file.path.includes("\\") ||
    file.path.split("/").some((x) => !x || x === ".." || x === ".") ||
    seen.has(file.path)
  )
    throw new Error("Unsafe or duplicate asset path");
  seen.add(file.path);
  let data = readFileSync(resolve(client, file.path));
  if (file.path.startsWith("shared/") && file.path.endsWith("/index.js"))
    data = Buffer.from(repairModule(data.toString("utf8")));
  if (data.length !== file.size || sha(data) !== file.sha256)
    throw new Error(`Asset version is incompatible: ${file.path}`);
}
const output = resolve(repo, "diagnostics/releases", buildId);
if (existsSync(output))
  throw new Error("Build directory exists; choose a new build id");
mkdirSync(output, { recursive: true });
function copy(src, dest, filter = () => true) {
  if (statSync(src).isDirectory()) {
    for (const name of readdirSync(src).sort())
      copy(resolve(src, name), resolve(dest, name), filter);
  } else if (filter(src)) {
    mkdirSync(dirname(dest), { recursive: true });
    copyFileSync(src, dest);
  }
}
const pkg = JSON.parse(readFileSync(resolve(root, "package.json"), "utf8"));
function runtime(name, gameFiles) {
  const dest = resolve(output, name);
  write(resolve(dest, "package.json"), {
    name: `gtt-${name}`,
    version: pkg.version,
    private: true,
    type: "module",
    engines: pkg.engines,
  });
  copy(resolve(root, "dist/cli.js"), resolve(dest, "dist/cli.js"));
  copy(resolve(root, "dist/shared"), resolve(dest, "dist/shared"), (p) =>
    p.endsWith(".js"),
  );
  for (const name of gameFiles)
    copy(
      resolve(root, `dist/games/buffalo-win/${name}.js`),
      resolve(dest, `dist/games/buffalo-win/${name}.js`),
    );
  copy(
    resolve(root, "config/buffalo-win.json"),
    resolve(dest, "config/buffalo-win.json"),
  );
  return dest;
}
const gateway = runtime("gateway", [
  "engine",
  "random",
  "calibration",
  "worker",
]);
copy(resolve(root, "dist/gateway"), resolve(gateway, "dist/gateway"), (p) =>
  p.endsWith(".js"),
);
copy(
  resolve(root, "config"),
  resolve(gateway, "config"),
  (p) => !p.endsWith("buffalo-win.json"),
);
copy(resolve(root, "frontend/admin"), resolve(gateway, "frontend/admin"));
for (const path of [
  "index.html",
  "local-auth-bootstrap.js",
  "local-frame-clock.js",
  "fixtures/auth-metadata.json",
  "fixtures/game-rule.json",
])
  copy(resolve(client, path), resolve(gateway, "clients/buffalo-win", path));
runtime("buffalo-win", ["engine", "random", "service"]);
copy(resolve(root, "frontend/admin"), resolve(output, "frontend/admin"));
// All migrated services, with private protocol/bootstrap resources. Large
// client assets remain an independently mounted/published frontend artifact.
const all = resolve(output, "all-services");
write(resolve(all, "package.json"), {
  name: "gtt-all-services",
  version: pkg.version,
  private: true,
  type: "module",
  engines: pkg.engines,
});
for (const name of [
  "cli.js",
  "shared",
  "gateway",
  "games",
  "compat",
  "migrated",
  "services",
])
  copy(resolve(root, "dist", name), resolve(all, "dist", name), (p) =>
    p.endsWith(".js"),
  );
copy(resolve(root, "config"), resolve(all, "config"));
copy(resolve(root, "frontend"), resolve(all, "frontend"));
copy(
  resolve(root, "migrated/sources.json"),
  resolve(all, "migration-sources.json"),
);
const resources = resolve(all, "resources");
copy(
  resolve(repo, "server"),
  resolve(resources, "server"),
  (p) =>
    /\.(json|sql)$/.test(p) &&
    !relative(resolve(repo, "server"), p).startsWith("tests"),
);
copy(
  resolve(repo, "server/merchant/sandbox.html"),
  resolve(resources, "server/merchant/sandbox.html"),
);
const profiles = [];
for (const id of readdirSync(resolve(repo, "services")).sort()) {
  const service = resolve(repo, "services", id);
  if (!existsSync(resolve(service, "service.json"))) continue;
  profiles.push(
    JSON.parse(readFileSync(resolve(service, "service.json"), "utf8")),
  );
  copy(
    resolve(service, "service.json"),
    resolve(resources, "services", id, "service.json"),
  );
  copy(
    resolve(service, "config"),
    resolve(resources, "services", id, "config"),
    (p) => p.endsWith(".json"),
  );
}
const fixtureNames = new Set([
  "auth-metadata.json",
  "game-rule.json",
  "game-info.json",
  "game-names.en.json",
  "init.txt",
  "login.json",
  "info.json",
  "authenticate.json",
  "partner-settings.json",
  "launcher.html",
  "game.json",
  "prelaunch.json",
  "configuration.json",
  "help.html",
  "help-zh.html",
]);
for (const id of profiles.filter((s) => s.id !== "game-api").map((s) => s.id)) {
  const src = resolve(repo, "clients", id);
  copy(src, resolve(resources, "clients", id), (p) => {
    const parts = relative(src, p).split(sep);
    return (
      (parts.length === 1 && /\.(html|js|css)$/.test(p)) ||
      (!parts.includes("fixtures") && p.endsWith(".html")) ||
      (parts.length === 2 &&
        parts[0] === "fixtures" &&
        fixtureNames.has(parts[1]))
    );
  });
}
copy(
  resolve(repo, "demo"),
  resolve(resources, "demo"),
  (p) => !/(?:\.py|\.bat|\.md|\.har)$/.test(p),
);
write(resolve(all, "SERVICES.json"), profiles);
write(
  resolve(all, "ASSETS.md"),
  "# Client resources\n\nThis package contains runtime bootstrap metadata, not the full game assets. Mount the matching complete resource tree with GTT_RESOURCE_ROOT, or merge the existing clients/ assets into resources/clients/. Do not publish private fixtures. Existing Buffalo S3 deployment continues to use gateway.tar.gz and the bound asset manifest. Other games require their own verified CDN routing before production publication.\n",
);
// Unified gateway loads all engines and protocol workers. Keep its artifact self-contained.
for (const name of ["compat", "migrated", "services"])
  copy(resolve(root, "dist", name), resolve(gateway, "dist", name), (p) =>
    p.endsWith(".js"),
  );
copy(resources, resolve(gateway, "resources"));
copy(resolve(root, "frontend/platform"), resolve(gateway, "frontend/platform"));
copy(resolve(root, "deploy"), resolve(output, "infra"));
copy(resolve(root, "README.md"), resolve(output, "README.md"));
copy(resolve(repo, "docs/node-migration.md"), resolve(output, "MIGRATION.md"));
copy(resolve(repo, "docs/unified-merchant-games.md"), resolve(output, "UNIFIED-MERCHANT.md"));
copy(resolve(manifestPath), resolve(output, "assets-manifest.json"));
const git = (...params) =>
  execFileSync("git", params, { cwd: repo, encoding: "utf8" }).trim();
function inventory(dir) {
  const files = [];
  function walk(at) {
    for (const name of readdirSync(at).sort()) {
      const path = resolve(at, name);
      if (statSync(path).isDirectory()) walk(path);
      else {
        const bytes = readFileSync(path);
        files.push({
          path: relative(dir, path).split(sep).join("/"),
          size: bytes.length,
          sha256: sha(bytes),
        });
      }
    }
  }
  walk(dir);
  return files;
}
const artifacts = [];
for (const name of [
  "gateway",
  "buffalo-win",
  "all-services",
  "frontend",
  "infra",
]) {
  const dir = resolve(output, name);
  write(resolve(dir, "release-manifest.json"), {
    build_id: buildId,
    files: inventory(dir),
  });
  const filename = `${name}.tar.gz`;
  execFileSync("tar", ["-czf", resolve(output, filename), "-C", output, name], {
    stdio: "pipe",
  });
  const bytes = readFileSync(resolve(output, filename));
  artifacts.push({
    name,
    file: filename,
    size: bytes.length,
    sha256: sha(bytes),
  });
}
// This is the completion marker. A failed build leaves no release.json.
write(resolve(output, "release.json"), {
  format: 1,
  build_id: buildId,
  built_at: new Date().toISOString(),
  node: process.version,
  source: {
    commit: git("rev-parse", "HEAD"),
    dirty: !!git("status", "--porcelain"),
    checksums: "Each artifact contains release-manifest.json",
  },
  services: [
    "gateway",
    "admin",
    "buffalo-win-compute",
    "rtp-worker",
    "mock-platform",
    ...profiles.map((s) => s.id),
  ],
  artifacts,
  assets: {
    game: assets.game,
    release: assets.release,
    prefix: assets.prefix,
    manifest_sha256: sha(raw),
    files: assets.files.length,
  },
  validation: {
    asset_bytes: "verified",
    tests:
      "Run npm test; packaging does not imply test or production acceptance",
    clean_unpack: "Run tools/smoke-release.mjs against this directory",
  },
});
console.log(output);
