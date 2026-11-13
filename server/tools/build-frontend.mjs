import {
  readFileSync,
  writeFileSync,
  mkdirSync,
  readdirSync,
  statSync,
  copyFileSync,
} from "node:fs";
import { resolve, dirname, relative, extname, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { randomBytes } from "node:crypto";
import { execFileSync } from "node:child_process";
import { sha, encode } from "../dist/shared/core.js";
import { repairModule } from "../dist/gateway/assets.js";
import { GAME_CODES } from "../dist/gateway/catalog.js";
const repo = resolve(dirname(fileURLToPath(import.meta.url)), "../.."),
  args = process.argv.slice(2);
const option = (key, fallback) =>
  args.includes(key) ? args[args.indexOf(key) + 1] : fallback;
const game = option("--game");
if (!GAME_CODES.includes(game))
  throw Error("Supply --game with a supported game code");
if (args.includes("--version") || args.includes("--release"))
  throw Error("Frontend versions are generated automatically");
const source = resolve(option("--source", resolve(repo, "clients", game))),
  output = resolve(option("--output", resolve(repo, "diagnostics/releases")));
const roots = {
  "buffalo-win": ["assets", "shared"],
  "mahjong-ways2": ["assets", "shared", "loader", "shell-res"],
  "captains-bounty": ["54", "loader", "shared", "favicon"],
  "fortune-rabbit": ["1543462", "loader", "shared"],
  "wild-bandito": ["104", "loader", "shared"],
  "big-bass-bonanza": ["hub-demo"],
  "sweet-bonanza-pop": ["hub-demo"],
  "gates-of-olympus": ["hub-demo"],
  "super-ace": ["astarte2", "fullhouse", "smallicon", "static"],
  "fortune-gems2": ["astarte2", "fgp", "smallicon", "static"],
  "roma-x-10000": ["astarte2", "rx10000", "smallicon", "static"],
  "money-pot-deluxe": ["astarte2", "mpt2", "smallicon", "static"],
  "3-billion-vaults": ["astarte4", "sss-tbv", "smallicon", "static"],
  "jokers-fortune-winx": ["astarte4", "sss-jf2", "smallicon", "static"],
  "wicked-grin": ["2347", "integrations"],
  "le-vampire": ["2582", "integrations"],
  "dr-zappo": ["2253", "integrations"],
  "great-game-serengeti": ["2620", "integrations"],
  "tower-run-treasure-steps": ["cdn", "platform"],
};
const mime = {
  ".js": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".avif": "image/avif",
  ".gif": "image/gif",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".mp3": "audio/mpeg",
  ".ogg": "audio/ogg",
  ".wav": "audio/wav",
  ".m4a": "audio/mp4",
  ".mp4": "video/mp4",
  ".webm": "video/webm",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".otf": "font/otf",
  ".wasm": "application/wasm",
  ".bin": "application/octet-stream",
  ".atlas": "text/plain; charset=utf-8",
  ".skel": "application/octet-stream",
};
const fixtures = new Set([
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
const publicFiles = [],
  privateFiles = [];
function walk(at, visit) {
  for (const entry of readdirSync(at, { withFileTypes: true }).sort((a, b) =>
    a.name.localeCompare(b.name),
  )) {
    if (entry.isSymbolicLink())
      throw Error("Symlinks are not allowed in frontend builds");
    const path = resolve(at, entry.name);
    if (entry.isDirectory()) walk(path, visit);
    else visit(path);
  }
}
const entry = (path, data, type) => ({
  path,
  size: data.length,
  sha256: sha(data),
  type,
});
walk(source, (path) => {
  const rel = relative(source, path).split(sep).join("/"),
    parts = rel.split("/"),
    ext = extname(path).toLowerCase();
  if (
    parts.some((p) =>
      [
        "diagnostics",
        "data",
        "logs",
        "api-documents",
        "node_modules",
        ".git",
        "__pycache__",
      ].includes(p),
    )
  )
    return;
  const rootStatic =
    parts.length === 1 &&
    (/^[a-f0-9]{6,}\.[a-f0-9]{3,}\.[a-z0-9]+$/i.test(rel) ||
      /^local-[a-z0-9-]+\.js$/i.test(rel) ||
      /^favicon\.(ico|png)$/i.test(rel));
  const allowed = rootStatic || roots[game].includes(parts[0]);
  const fixture =
    parts[0] === "fixtures" && parts.length === 2 && fixtures.has(parts[1]);
  if (!allowed && !fixture && !(parts.length === 1 && ext === ".html")) return;
  let bytes = readFileSync(path);
  const source_sha256 = sha(bytes);
  if (
    allowed &&
    mime[ext] &&
    !/^(resource-index|missing-references|cover-evidence|rules-evidence)\.json$/.test(
      rel,
    )
  ) {
    if (rel.startsWith("shared/") && rel.endsWith("/index.js"))
      bytes = Buffer.from(repairModule(bytes.toString("utf8")));
    publicFiles.push({
      row: {
        ...entry(rel, bytes, mime[ext]),
        source_sha256,
        processed: sha(bytes) !== source_sha256,
      },
      bytes,
    });
  }
  if (
    fixture ||
    ext === ".html" ||
    (parts.length === 1 && [".js", ".css"].includes(ext))
  ) {
    const name = `resources/clients/${game}/${rel}`;
    privateFiles.push({
      row: entry(
        name,
        bytes,
        ext === ".html"
          ? "text/html; charset=utf-8"
          : (mime[ext] ?? "text/plain"),
      ),
      bytes,
    });
  }
});
for (const name of ["service.json", `config/${game}.json`]) {
  const bytes = readFileSync(resolve(repo, "services", game, name));
  privateFiles.push({
    row: entry(`resources/services/${game}/${name}`, bytes, "application/json"),
    bytes,
  });
}
walk(resolve(repo, "py"), (path) => {
  const rel = relative(resolve(repo, "py"), path).split(sep).join("/");
  if (
    rel
      .split("/")
      .some((p) => ["tests", "data", "logs", "__pycache__"].includes(p)) ||
    !/[.](json|sql)$/.test(path)
  )
    return;
  const bytes = readFileSync(path);
  privateFiles.push({
    row: entry("resources/py/" + rel, bytes, "application/octet-stream"),
    bytes,
  });
});
publicFiles.sort((a, b) => a.row.path.localeCompare(b.row.path));
privateFiles.sort((a, b) => a.row.path.localeCompare(b.row.path));
if (
  !publicFiles.length ||
  !privateFiles.some((f) => f.row.path.endsWith(".html"))
)
  throw Error("Client bootstrap/static files are missing");
const profile = JSON.parse(
  readFileSync(resolve(repo, "services", game, "service.json"), "utf8"),
);
const client_contract = profile.client_contract ?? game + ":original-v1";
const content_hash = sha(
  encode({
    game,
    client_contract,
    files: publicFiles.map((f) => f.row),
    bootstrap: privateFiles.map((f) => f.row),
  }),
);
const release = `fe-${new Date().toISOString().replace(/\D/g, "")}-${content_hash.slice(0, 8)}-${randomBytes(3).toString("hex")}`;
mkdirSync(output, { recursive: true });
const bundle = resolve(output, `frontend-${game}-${release}`);
mkdirSync(bundle, { recursive: false });
for (const [group, files] of [
  ["objects", publicFiles],
  ["bootstrap", privateFiles],
])
  for (const file of files) {
    const target = resolve(bundle, group, file.row.path);
    mkdirSync(dirname(target), { recursive: true });
    writeFileSync(target, file.bytes, { flag: "wx" });
  }
const manifest = {
  format: 3,
  kind: "game-client",
  game,
  release,
  created_at: new Date().toISOString(),
  client_contract,
  prefix: `releases/${game}/${release}`,
  content_hash,
  source: {
    commit: execFileSync("git", ["rev-parse", "HEAD"], {
      cwd: repo,
      encoding: "utf8",
      windowsHide: true,
    }).trim(),
    dirty: !!execFileSync("git", ["status", "--porcelain"], {
      cwd: repo,
      encoding: "utf8",
      windowsHide: true,
    }).trim(),
  },
  files: publicFiles.map((f) => f.row),
  bootstrap: privateFiles.map((f) => f.row),
};
writeFileSync(
  resolve(bundle, "manifest.json"),
  JSON.stringify(manifest, null, 2) + "\n",
  { flag: "wx" },
);
writeFileSync(
  resolve(bundle, "DEPLOY.txt"),
  "objects/ -> private S3 at " +
    manifest.prefix +
    "/\nbootstrap/ and manifest.json stay on backend. Install this bundle before registering it in the platform frontend-version page.\n",
);
console.log(
  JSON.stringify({
    bundle,
    game,
    release,
    files: manifest.files.length,
    private_files: manifest.bootstrap.length,
    content_hash,
  }),
);
