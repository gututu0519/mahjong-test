import { readFileSync, realpathSync, statSync } from "node:fs";
import { resolve, relative, isAbsolute, sep } from "node:path";
import { check, sha, encode } from "./core.js";
import { GAME_CODES } from "../gateway/catalog.js";

export const FRONTEND_VERSION = /^fe-\d{17}-[a-f0-9]{8}-[a-f0-9]{6}$/;
export type FrontendFile = {
  path: string;
  size: number;
  sha256: string;
  type: string;
  source_sha256?: string;
  processed?: boolean;
};
export type FrontendManifest = {
  format: 3;
  kind: "game-client";
  game: string;
  release: string;
  created_at: string;
  client_contract: string;
  prefix: string;
  content_hash: string;
  files: FrontendFile[];
  bootstrap: FrontendFile[];
};
export function safeFrontendPath(path: string) {
  return (
    typeof path === "string" &&
    path.length > 0 &&
    !path.includes("\\") &&
    !/[\x00-\x1f%?#]/.test(path) &&
    !path.startsWith("/") &&
    !path.split("/").some((v) => !v || v === "." || v === "..")
  );
}
export function readFrontendManifest(bundle: string): FrontendManifest {
  const m = JSON.parse(readFileSync(resolve(bundle, "manifest.json"), "utf8"));
  check(
    m.format === 3 &&
      m.kind === "game-client" &&
      GAME_CODES.includes(m.game) &&
      FRONTEND_VERSION.test(m.release),
    "FRONTEND_MANIFEST_INVALID",
  );
  check(
    m.prefix === `releases/${m.game}/${m.release}` &&
      typeof m.client_contract === "string" &&
      m.client_contract.length > 0 &&
      m.client_contract.length <= 128,
    "FRONTEND_MANIFEST_INVALID",
  );
  for (const group of [m.files, m.bootstrap]) {
    check(
      Array.isArray(group) && group.length > 0 && group.length <= 100000,
      "FRONTEND_MANIFEST_INVALID",
    );
    const seen = new Set();
    for (const f of group) {
      check(
        safeFrontendPath(f.path) &&
          !seen.has(f.path) &&
          Number.isSafeInteger(f.size) &&
          f.size >= 0 &&
          /^[a-f0-9]{64}$/.test(f.sha256) &&
          typeof f.type === "string",
        "FRONTEND_MANIFEST_INVALID",
      );
      seen.add(f.path);
    }
  }
  check(
    m.files.every(
      (f: FrontendFile) =>
        !f.path
          .split("/")
          .some((p) =>
            [
              "fixtures",
              "diagnostics",
              "data",
              "logs",
              "api-documents",
            ].includes(p),
          ) && !/\.(html?|py|sqlite3?|db|har|log)$/i.test(f.path),
    ),
    "FRONTEND_PRIVATE_FILE",
  );
  check(
    m.content_hash ===
      sha(
        encode({
          game: m.game,
          client_contract: m.client_contract,
          files: m.files,
          bootstrap: m.bootstrap,
        }),
      ),
    "FRONTEND_MANIFEST_INVALID",
  );
  return m;
}
export function frontendFile(
  bundle: string,
  group: "objects" | "bootstrap",
  file: FrontendFile,
) {
  check(safeFrontendPath(file.path), "FRONTEND_PATH_INVALID");
  const bundleRoot = realpathSync(bundle);
  const root = realpathSync(resolve(bundle, group)),
    path = realpathSync(resolve(root, file.path)),
    rel = relative(root, path);
  const groupRelative = relative(bundleRoot, root);
  check(
    groupRelative &&
      !isAbsolute(groupRelative) &&
      groupRelative !== ".." &&
      !groupRelative.startsWith(".." + sep),
    "FRONTEND_PATH_INVALID",
  );
  check(
    rel &&
      !isAbsolute(rel) &&
      rel !== ".." &&
      !rel.startsWith(".." + sep) &&
      statSync(path).isFile(),
    "FRONTEND_PATH_INVALID",
  );
  const bytes = readFileSync(path);
  check(
    bytes.length === file.size && sha(bytes) === file.sha256,
    "FRONTEND_FILE_CHANGED",
    "前端文件与构建清单不一致",
    409,
  );
  return bytes;
}
export function verifyFrontendBundle(bundle: string) {
  const manifest = readFrontendManifest(bundle);
  for (const f of manifest.files) frontendFile(bundle, "objects", f);
  for (const f of manifest.bootstrap) frontendFile(bundle, "bootstrap", f);
  return manifest;
}
