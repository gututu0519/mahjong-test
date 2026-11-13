import { existsSync, readdirSync, readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { Provider } from "./provider.js";
import { GAME_CODES, gameNumber } from "./catalog.js";
import { check, encode, now, sha } from "../shared/core.js";
import {
  readFrontendManifest,
  verifyFrontendBundle,
  frontendFile,
  FRONTEND_VERSION,
  type FrontendManifest,
} from "../shared/frontend-manifest.js";

export class FrontendVersions {
  root: string;
  constructor(
    public p: Provider,
    public config: any,
  ) {
    this.root = resolve(
      config.frontend_releases_directory ??
        resolve(dirname(p.control.path), "frontend-releases"),
    );
    p.control.db.exec(`CREATE TABLE IF NOT EXISTS frontend_releases (
      id TEXT PRIMARY KEY,code TEXT NOT NULL,bundle TEXT NOT NULL,origin TEXT NOT NULL UNIQUE,
      manifest_json TEXT NOT NULL,manifest_sha256 TEXT NOT NULL,status TEXT NOT NULL,created_at INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS frontend_routes(code TEXT PRIMARY KEY,release_id TEXT NOT NULL,revision INTEGER NOT NULL,updated_at INTEGER NOT NULL);`);
    p.db.exec(
      "CREATE TABLE IF NOT EXISTS frontend_sessions(token_hash TEXT PRIMARY KEY,release_id TEXT NOT NULL,expires_at INTEGER NOT NULL);",
    );
  }
  bundle(name: string) {
    check(
      typeof name === "string" &&
        /^[a-zA-Z0-9._-]+$/.test(name) &&
        name !== "." &&
        name !== "..",
      "FRONTEND_BUNDLE_INVALID",
    );
    return resolve(this.root, name);
  }
  candidates() {
    if (!existsSync(this.root)) return [];
    return readdirSync(this.root, { withFileTypes: true })
      .filter((f) => f.isDirectory() && !f.isSymbolicLink())
      .flatMap((f) => {
        try {
          const m = readFrontendManifest(this.bundle(f.name));
          return [
            {
              bundle: f.name,
              code: m.game,
              release: m.release,
              created_at: m.created_at,
              files: m.files.length,
              registered: !!this.p.control.get(
                "SELECT 1 FROM frontend_releases WHERE id=?",
                m.release,
              ),
            },
          ];
        } catch {
          return [];
        }
      });
  }
  release(id: string) {
    const row = this.p.control.get(
      "SELECT * FROM frontend_releases WHERE id=?",
      id,
    );
    check(row, "FRONTEND_VERSION_REQUIRED", "前端构建版本不存在", 404);
    return {
      ...row,
      manifest: JSON.parse(row.manifest_json) as FrontendManifest,
    };
  }
  origin(manifest: FrontendManifest) {
    const template = this.config.frontend_origin_template;
    let value: string;
    if (template) {
      check(
        typeof template === "string" && template.includes("{release}"),
        "FRONTEND_ORIGIN_TEMPLATE_INVALID",
      );
      value = template
        .replaceAll("{release}", manifest.release)
        .replaceAll("{game}", manifest.game)
        .replaceAll("{game_id}", String(gameNumber(manifest.game)));
    } else {
      check(
        this.config.environment !== "production",
        "FRONTEND_ORIGIN_TEMPLATE_REQUIRED",
        "生产环境须先配置版本域名、TLS 和 CDN 路由",
        409,
      );
      const base = new URL(this.p.multi!.origin(manifest.game));
      base.hostname = manifest.release + "." + base.hostname;
      value = base.origin;
    }
    const url = new URL(value);
    check(
      ["http:", "https:"].includes(url.protocol) &&
        url.pathname === "/" &&
        !url.username &&
        !url.password &&
        !url.search &&
        !url.hash &&
        url.hostname.includes(manifest.release) &&
        (this.config.environment !== "production" || url.protocol === "https:"),
      "FRONTEND_ORIGIN_TEMPLATE_INVALID",
    );
    return url.origin;
  }
  register(actor: string, q: any) {
    const path = this.bundle(q.bundle),
      manifest = verifyFrontendBundle(path),
      origin = this.origin(manifest);
    return this.p.control.tx(() => {
      check(
        !this.p.control.get(
          "SELECT 1 FROM frontend_releases WHERE id=?",
          manifest.release,
        ),
        "FRONTEND_VERSION_EXISTS",
        "构建版本已登记",
        409,
      );
      this.p.control.run(
        "INSERT INTO frontend_releases VALUES(?,?,?,?,?,?,?,?)",
        manifest.release,
        manifest.game,
        q.bundle,
        origin,
        encode(manifest),
        sha(readFileSync(resolve(path, "manifest.json"))),
        "staged",
        now(),
      );
      this.p.control.audit(
        actor,
        "frontend.register",
        manifest.release,
        "success",
        { game_id: gameNumber(manifest.game) },
      );
      return { id: manifest.release, code: manifest.game, origin };
    });
  }
  verify(id: string) {
    const release = this.release(id),
      path = this.bundle(release.bundle);
    check(
      sha(readFileSync(resolve(path, "manifest.json"))) ===
        release.manifest_sha256,
      "FRONTEND_MANIFEST_CHANGED",
      "前端清单已变化，请重新构建",
      409,
    );
    verifyFrontendBundle(path);
    return release;
  }
  verifyPrivate(release: any) {
    const bundle = this.bundle(release.bundle);
    check(
      sha(readFileSync(resolve(bundle, "manifest.json"))) ===
        release.manifest_sha256,
      "FRONTEND_MANIFEST_CHANGED",
      "前端清单已变化",
      409,
    );
    for (const file of release.manifest.bootstrap)
      frontendFile(bundle, "bootstrap", file);
  }
  async probe(actor: string, id: string) {
    const release = this.verify(id);
    check(release.status !== "retired", "FRONTEND_VERSION_RETIRED");
    if (this.config.environment === "production")
      for (const file of release.manifest.files) {
        const response = await fetch(
          release.origin +
            "/" +
            file.path.split("/").map(encodeURIComponent).join("/"),
          {
            redirect: "manual",
            credentials: "omit",
            signal: AbortSignal.timeout(15000),
          },
        );
        check(
          response.status === 200,
          "FRONTEND_CDN_UNAVAILABLE",
          "版本 CDN 文件尚未正确发布",
          409,
        );
        const reader = response.body!.getReader(),
          chunks: Buffer[] = [];
        let size = 0;
        try {
          while (true) {
            const r = await reader.read();
            if (r.done) break;
            size += r.value.byteLength;
            check(size <= file.size, "FRONTEND_CDN_CHANGED");
            chunks.push(Buffer.from(r.value));
          }
        } finally {
          await reader.cancel();
        }
        check(
          size === file.size && sha(Buffer.concat(chunks)) === file.sha256,
          "FRONTEND_CDN_CHANGED",
          "版本 CDN 文件与清单不一致",
          409,
        );
      }
    this.p.control.run(
      "UPDATE frontend_releases SET status='verified' WHERE id=? AND status<>'retired'",
      id,
    );
    this.p.control.audit(actor, "frontend.verify", id, "success", {
      mode: this.config.environment === "production" ? "cdn" : "local",
    });
    return {
      id,
      status: "verified",
      mode: this.config.environment === "production" ? "cdn" : "local",
    };
  }
  activate(actor: string, q: any) {
    const selected = this.verify(q.id);
    check(
      selected.status === "verified",
      "FRONTEND_NOT_VERIFIED",
      "请先检查构建和 CDN 文件",
      409,
    );
    check(Number.isInteger(q.revision) && q.revision >= 0, "INVALID_ARGUMENT");
    return this.p.control.tx(() => {
      check(
        this.release(selected.id).status === "verified",
        "FRONTEND_NOT_VERIFIED",
      );
      const route = this.p.control.get(
        "SELECT * FROM frontend_routes WHERE code=?",
        selected.code,
      );
      check(
        (route?.revision ?? 0) === q.revision,
        "VERSION_CONFLICT",
        "前端版本已变化，请刷新后重试",
        409,
      );
      const hasServices = this.p.control.get(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='game_service_releases'",
      );
      const service = hasServices
        ? this.p.control.get(
            "SELECT r.descriptor_json FROM game_service_routes a JOIN game_service_releases r ON r.id=a.release_id WHERE a.code=?",
            selected.code,
          )
        : null;
      if (service)
        check(
          JSON.parse(service.descriptor_json).client_contract ===
            selected.manifest.client_contract,
          "FRONTEND_CONTRACT_MISMATCH",
          "前端与当前游戏服务的协议契约不匹配",
          409,
        );
      if (route)
        check(
          this.release(route.release_id).manifest.client_contract ===
            selected.manifest.client_contract,
          "FRONTEND_CONTRACT_MISMATCH",
          "不兼容的前端不能直接切换",
          409,
        );
      this.p.control.run(
        "INSERT INTO frontend_routes VALUES(?,?,?,?) ON CONFLICT(code) DO UPDATE SET release_id=excluded.release_id,revision=excluded.revision,updated_at=excluded.updated_at",
        selected.code,
        selected.id,
        q.revision + 1,
        now(),
      );
      this.p.control.audit(actor, "frontend.activate", selected.id, "success", {
        previous: route?.release_id ?? null,
        revision: q.revision + 1,
      });
      return { id: selected.id, revision: q.revision + 1 };
    });
  }
  retire(actor: string, id: string) {
    return this.p.control.tx(() => {
      check(
        !this.p.control.get(
          "SELECT 1 FROM frontend_routes WHERE release_id=?",
          id,
        ),
        "FRONTEND_VERSION_ACTIVE",
        "先切换新会话使用的版本",
        409,
      );
      this.release(id);
      this.p.control.run(
        "UPDATE frontend_releases SET status='retired' WHERE id=?",
        id,
      );
      this.p.control.audit(actor, "frontend.retire", id);
      return { id, status: "retired" };
    });
  }
  list() {
    return GAME_CODES.map((code) => {
      const route = this.p.control.get(
        "SELECT * FROM frontend_routes WHERE code=?",
        code,
      );
      const releases = this.p.control
        .all(
          "SELECT id,origin,status,created_at,manifest_sha256 FROM frontend_releases WHERE code=? ORDER BY created_at DESC,id",
          code,
        )
        .map((row) => ({
          ...row,
          sessions: this.p.get(
            "SELECT COUNT(*) AS n FROM frontend_sessions WHERE release_id=? AND expires_at>?",
            row.id,
            now(),
          ).n,
        }));
      return {
        code,
        game_id: gameNumber(code),
        active_id: route?.release_id ?? null,
        revision: route?.revision ?? 0,
        releases,
      };
    });
  }
  bind(tokenHash: string, code: string, expiry: number) {
    const route = this.p.control.get(
      "SELECT release_id FROM frontend_routes WHERE code=?",
      code,
    );
    if (!route) return null;
    const release = this.release(route.release_id);
    this.p.run(
      "INSERT INTO frontend_sessions VALUES(?,?,?)",
      tokenHash,
      release.id,
      expiry,
    );
    return release;
  }
  host(host: string) {
    const row = this.p.control.get(
      "SELECT id FROM frontend_releases WHERE origin IN (?,?)",
      "http://" + host,
      "https://" + host,
    );
    return row ? this.release(row.id) : null;
  }
  session(token: string, release: any) {
    const binding = this.p.get(
      "SELECT release_id FROM frontend_sessions WHERE token_hash=? AND expires_at>?",
      sha(token),
      now(),
    );
    check(
      binding && binding.release_id === release.id,
      "FRONTEND_SESSION_MISMATCH",
      "请使用原游戏启动链接",
      403,
    );
  }
  asset(release: any, req: IncomingMessage, res: ServerResponse) {
    const path = decodeURIComponent(
      new URL(req.url!, "http://local").pathname,
    ).slice(1);
    const file = release.manifest.files.find((f: any) => f.path === path);
    if (!file) return false;
    check(
      this.config.environment !== "production",
      "FRONTEND_CDN_REQUIRED",
      "生产素材应由私有 S3 / CloudFront 提供",
      503,
    );
    const bytes = frontendFile(this.bundle(release.bundle), "objects", file);
    res.writeHead(200, {
      "Content-Type": file.type,
      "Content-Length": bytes.length,
      "Cache-Control": "public, max-age=31536000, immutable",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
    });
    res.end(req.method === "HEAD" ? undefined : bytes);
    return true;
  }
  resources(release: any) {
    return resolve(this.bundle(release.bundle), "bootstrap/resources");
  }
}
