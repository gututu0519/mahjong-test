import { readFileSync, realpathSync, statSync } from "node:fs";
import { resolve, relative, isAbsolute, sep } from "node:path";
import { check, sha, encode } from "./core.js";
import { GAME_CODES } from "../../gateway/src/catalog.js";

export const FRONTEND_VERSION = /^fe-(?:\d{17}-[a-f0-9]{8}-[a-f0-9]{6}|v[1-9]\d{0,7}-(?:0|[1-9]\d{0,7})-g[1-9]\d*)$/;
export const COMPONENT_VERSION = /^v([1-9]\d*)\.(0|[1-9]\d*)$/;
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
  component_version?: string;
  entry_mode?: "cdn-html";
  source?: {commit:string;dirty:boolean};
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
    !/[\\:]/.test(path) && !path.includes("//") &&
    !/[\x00-\x1f%?#]/.test(path) &&
    !path.startsWith("/") &&
    !path.split("/").some((v) => !v || v === "." || v === "..")
  );
}
/** 浏览器入口和同层脚本样式可独立升级；适配器所需 fixtures 和规则必须匹配。 */
export function adapterFiles(m:FrontendManifest){
  const prefix=`resources/clients/${m.game}/`;
  return m.bootstrap.filter(f=>!(f.path.startsWith(prefix)&&/^(index\.html|[^/]+\.(js|css))$/.test(f.path.slice(prefix.length))));
}
/** 构造可公开校验的版本标记，仅包含适配器资料摘要，不包含私有配置内容。 */
export function frontendMarker(m:FrontendManifest,manifest_sha256:string){
  return {format:3,kind:m.kind,game:m.game,release:m.release,...(m.release.startsWith('fe-v')?{component_version:m.component_version}:{}),prefix:m.prefix,manifest_sha256,files:m.files,
    ...(m.entry_mode==='cdn-html'?{entry:{mode:m.entry_mode,created_at:m.created_at,client_contract:m.client_contract,source:m.source,runtime_sha256:sha(encode(adapterFiles(m)))}}:{})};
}
export function readFrontendManifest(bundle: string): FrontendManifest {
  const m = JSON.parse(readFileSync(resolve(bundle, "manifest.json"), "utf8"));
  check(
    m.format === 3 &&
      m.kind === "game-client" &&
      GAME_CODES.includes(m.game) &&
      (m.component_version === undefined || (typeof m.component_version === "string" && COMPONENT_VERSION.test(m.component_version))) &&
      FRONTEND_VERSION.test(m.release),
    "FRONTEND_MANIFEST_INVALID",
  );
  check(
    (m.release.startsWith('fe-v')
      ? !!m.component_version && m.release===`fe-${m.component_version.replace('.','-')}-g${GAME_CODES.indexOf(m.game)+1}` && m.prefix===`releases/${m.game}/${m.component_version}`
      : m.prefix === `releases/${m.game}/${m.release}`) &&
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
          ) && (!/\.(html?|py|sqlite3?|db|har|log)$/i.test(f.path)||(m.entry_mode==='cdn-html'&&m.game==='buffalo-win'&&f.path==='index.html'&&f.type==='text/html; charset=utf-8'&&f.size>0&&f.size<=4*1024*1024)),
    ),
    "FRONTEND_PRIVATE_FILE",
  );
  if(m.entry_mode!==undefined)check(m.entry_mode==='cdn-html'&&m.release.startsWith('fe-v')&&m.files.some((f:FrontendFile)=>f.path==='index.html')&&adapterFiles(m).length===m.bootstrap.length,'FRONTEND_MANIFEST_INVALID');
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
