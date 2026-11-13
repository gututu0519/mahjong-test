import { check } from "../../other/shared/core.js";
import type { IncomingMessage } from "node:http";
export class Deployment {
  production: boolean;
  origins: any;
  proxies: string[];
  constructor(c: any) {
    check(
      ["development", "production"].includes(c.environment ?? "development"),
      "CONFIG_INVALID",
    );
    this.production = c.environment === "production";
    this.origins = c.public_origins ?? {};
    this.proxies = c.trusted_proxy_ips ?? ["127.0.0.1", "::1"];
    if (this.production) {
      check(
        Object.keys(this.origins).sort().join(",") ===
          "admin,api,merchant,play,site",
        "CONFIG_INVALID",
      );
      for (const v of Object.values(this.origins)) {
        const u = new URL(String(v));
        check(
          typeof v === "string" &&
            u.protocol === "https:" &&
            !u.username &&
            !u.password &&
            !u.search &&
            !u.hash &&
            u.pathname === "/" &&
            u.origin === v,
          "CONFIG_INVALID",
        );
      }
      check(
        new Set(Object.values(this.origins)).size === 5 &&
          this.proxies.length > 0 &&
          this.proxies.every((x) => ["127.0.0.1", "::1"].includes(x)),
        "CONFIG_INVALID",
      );
    }
  }
  role(req: IncomingMessage) {
    return Object.keys(this.origins).find(
      (k) => new URL(this.origins[k]).host === req.headers.host,
    );
  }
  guard(req: IncomingMessage, type: "gateway" | "admin") {
    const host = req.headers.host,
      origin = req.headers.origin,
      local = [
        `127.0.0.1:${req.socket.localPort}`,
        `localhost:${req.socket.localPort}`,
      ],
      path = new URL(req.url!, "http://local").pathname;
    if (!this.production) {
      check(
        local.includes(host ?? ""),
        "HOST_REJECTED",
        "Unexpected host",
        403,
      );
      check(
        !origin || origin === "http://" + host,
        "ORIGIN_REJECTED",
        "Unexpected origin",
        403,
      );
      return;
    }
    if (
      req.method === "GET" &&
      req.url === "/health" &&
      local.includes(host ?? "") &&
      !origin
    )
      return;
    check(
      this.proxies.includes(req.socket.remoteAddress ?? ""),
      "PROXY_REJECTED",
      "Trusted proxy required",
      403,
    );
    const role = this.role(req);
    check(
      (type === "gateway" ? ["api", "play"] : ["merchant", "admin"]).includes(
        role ?? "",
      ),
      "HOST_REJECTED",
      "Unexpected host",
      403,
    );
    check(
      req.headers["x-forwarded-proto"] === "https",
      "HTTPS_REQUIRED",
      "HTTPS required",
      403,
    );
    check(
      !origin || origin === this.origins[role!],
      "ORIGIN_REJECTED",
      "Unexpected origin",
      403,
    );
    check(
      type === "gateway"
        ? (role === "api") === path.startsWith("/gtt/")
        : !path.startsWith("/api/") || path.startsWith("/api/" + role + "/"),
      "NOT_FOUND",
      "Not found",
      404,
    );
  }
  browser(req: IncomingMessage) {
    return {
      portal: this.role(req) ?? null,
      merchant_url: this.production
        ? this.origins.merchant + "/"
        : "/merchant/",
      admin_url: this.production ? this.origins.admin + "/" : "/",
      home_url: this.production ? this.origins.site + "/" : "/",
    };
  }
  remote(req: IncomingMessage) {
    return this.production
      ? String(req.headers["x-real-ip"] ?? req.socket.remoteAddress)
      : (req.socket.remoteAddress ?? "");
  }
}
