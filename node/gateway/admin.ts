import { readFileSync } from "node:fs";
import { join } from "node:path";
import { server, success, send, jsonBody } from "../shared/http.js";
import {
  check,
  identifier,
  limit,
  amount,
  now,
  ServiceError,
} from "../shared/core.js";
import { reason } from "./control.js";
import { Deployment } from "./deployment.js";
import type { Provider } from "./provider.js";
export function transactions(p: Provider, q: any, detail = false) {
  const clauses: string[] = [],
    args: any[] = [];
  for (const k of ["merchant_id", "player_id", "game_id", "status"])
    if (q[k]) {
      let v = q[k];
      if (k === "game_id") {
        check(v === 1, "GAME_ID_INVALID");
        v = "buffalo-win";
      }
      identifier(v);
      if (k === "status")
        check(
          ["prepared", "debited", "settled", "rejected"].includes(v),
          "INVALID_ARGUMENT",
        );
      clauses.push(k + "=?");
      args.push(v);
    }
  if (q.operation_id) {
    clauses.push("id=?");
    args.push(identifier(q.operation_id).replace(/:(debit|credit)$/, ""));
  }
  check(!detail || q.operation_id, "INVALID_ARGUMENT");
  if (q.before_seq) {
    amount(q.before_seq);
    clauses.push("seq<?");
    args.push(q.before_seq);
  }
  const rows = p.all(
    "SELECT * FROM game_operations" +
      (clauses.length ? " WHERE " + clauses.join(" AND ") : "") +
      " ORDER BY seq DESC LIMIT ?",
    ...args,
    detail ? 1 : limit(q.limit ?? 25),
  );
  const entries = rows.map((r) => {
    const c = JSON.parse(r.candidate_json),
      m = p.control.merchant(r.merchant_id);
    return {
      seq: r.seq,
      id: r.id,
      merchant_id: r.merchant_id,
      player_id: r.player_id,
      game_id: 1,
      status: r.status,
      error_code: r.error_code,
      created_at: r.created_at,
      debit_minor: c.debit_minor,
      credit_minor: c.credit_minor,
      round_id: c.event.round_id,
      ruleset_id: c.ruleset_id,
      currency: m?.currency ?? null,
      minor_unit: m?.minor_unit ?? null,
      ...(detail
        ? {
            request: JSON.parse(r.request_json),
            result: r.response_json ? JSON.parse(r.response_json) : null,
          }
        : {}),
    };
  });
  if (detail) {
    check(entries.length, "NOT_FOUND", "Transaction not found", 404);
    return entries[0];
  }
  return entries;
}
function overview(p: Provider, mid?: string) {
  const merchants = mid ? [p.control.merchant(mid)] : p.control.merchants(),
    rows = p.all(
      "SELECT * FROM game_operations" + (mid ? " WHERE merchant_id=?" : ""),
      ...(mid ? [mid] : []),
    ),
    counts: any = {},
    totals: any = {},
    players = new Set(),
    daily = Array.from({ length: 7 }, (_, i) => ({
      date: new Date((now() - (6 - i) * 86400) * 1000)
        .toISOString()
        .slice(0, 10),
      settled: 0,
    }));
  for (const r of rows) {
    counts[r.status] = (counts[r.status] ?? 0) + 1;
    if (r.status !== "settled") continue;
    const m = p.control.merchant(r.merchant_id);
    if (!m) continue;
    const c = JSON.parse(r.candidate_json),
      t = (totals[m.currency] ??= {
        currency: m.currency,
        minor_unit: 100,
        debit_minor: 0,
        credit_minor: 0,
      });
    t.debit_minor += c.debit_minor;
    t.credit_minor += c.credit_minor;
    players.add(r.merchant_id + ":" + r.player_id);
    const day = daily.find(
      (d) =>
        d.date === new Date(r.created_at * 1000).toISOString().slice(0, 10),
    );
    if (day) day.settled++;
  }
  return {
    merchants: merchants.length,
    active_merchants: merchants.filter((m) => m.enabled).length,
    games: mid ? p.catalog(mid).length : 1,
    settled: counts.settled ?? 0,
    pending: (counts.prepared ?? 0) + (counts.debited ?? 0),
    rejected: counts.rejected ?? 0,
    players: players.size,
    totals: Object.values(totals),
    daily,
    recent: transactions(p, { limit: 5, ...(mid ? { merchant_id: mid } : {}) }),
  };
}
function prebetDecisions(p: Provider, q: any) {
  const clauses: string[] = [],
    args: any[] = [];
  for (const k of ["merchant_id", "player_id"])
    if (q[k]) {
      clauses.push(k + "=?");
      args.push(identifier(q[k]));
    }
  return p
    .all(
      "SELECT * FROM prebet_rounds" +
        (clauses.length ? " WHERE " + clauses.join(" AND ") : "") +
        " ORDER BY created_at DESC,rowid DESC LIMIT ?",
      ...args,
      limit(q.limit ?? 25),
    )
    .map((r) => ({
      id: r.id,
      merchant_id: r.merchant_id,
      player_id: r.player_id,
      game_id: 1,
      error_code: r.error_code,
      created_at: r.created_at,
      request: JSON.parse(r.prebet_request_json),
      policy: r.policy_json ? JSON.parse(r.policy_json) : null,
      status: r.error_code ? "rejected" : r.plan_json ? "planned" : "pending",
    }));
}
const permissions: any = {
  "rtp/read": "rtp.read",
  "rtp/policy": "rtp.write",
  "rtp/mode": "rtp.write",
  "rtp/job": "rtp.manage",
  "rtp/publish": "rtp.manage",
  "integration/docs": "merchants.read",
  overview: "merchants.read",
  "merchants/list": "merchants.read",
  "merchants/create": "merchants.write",
  "merchants/update": "merchants.write",
  "merchants/rotate": "keys.rotate",
  games: "games.read",
  "transactions/list": "transactions.read",
  "transactions/detail": "transactions.read",
  "transactions/retry": "transactions.retry",
  audit: "audit.read",
  "prebet/list": "transactions.read",
  "merchants/profile": "profile.write",
  "merchants/signing/view": "keys.rotate",
  "merchants/signing/rotate": "keys.rotate",
  "users/list": "users.manage",
  "users/create": "users.manage",
  "users/update": "users.manage",
  "users/reset": "users.manage",
  password: null,
  logout: null,
};
export function adminServer(
  p: Provider,
  config: any,
  frontend: string,
  configDir: string,
) {
  const deployment = new Deployment(config),
    control = p.control,
    headers = {
      "X-Frame-Options": "DENY",
      "Content-Security-Policy":
        "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
    };
  const integration = (name: string) =>
    readFileSync(join(configDir, name), "utf8")
      .replaceAll(
        "https://api.gttgames.com",
        deployment.origins.api ?? config.gateway_origin,
      )
      .replaceAll(
        "https://play.gttgames.com",
        deployment.origins.play ?? config.gateway_origin,
      );
  return server(async (req, res) => {
    for (const [k, v] of Object.entries(headers)) res.setHeader(k, v);
    deployment.guard(req, "admin");
    const path = req.url!;
    check(!path.includes("?"), "BAD_REQUEST");
    const merchantAPI = path.startsWith("/api/merchant/"),
      cookieName =
        (deployment.production ? "__Host-" : "") +
        (merchantAPI ? "gtt_merchant_session" : "gtt_admin_session"),
      cookies = Object.fromEntries(
        String(req.headers.cookie ?? "")
          .split(";")
          .map((v) => v.trim().split("=")),
      ),
      tok = cookies[cookieName] ?? "",
      cookie = (t: string, age = 28800) =>
        `${cookieName}=${t}; HttpOnly; SameSite=Strict; Path=/; Max-Age=${age}` +
        (deployment.production ? "; Secure" : "");
    const session = (permission?: string | null, csrf?: string) => {
      const s = control.session(tok, permission, csrf);
      check(
        !merchantAPI || s.user.merchant_id,
        "MERCHANT_LOGIN_REQUIRED",
        "Use merchant account",
        403,
      );
      return s;
    };
    if (req.method === "GET") {
      if (path === "/health")
        return success(res, { status: "ok", service_id: "gtt-admin-node" });
      if (path === "/deployment.json")
        return success(res, deployment.browser(req));
      if (["/api/admin/me", "/api/merchant/me"].includes(path))
        return success(res, session());
      if (deployment.production && path === "/merchant/") {
        res.writeHead(308, { Location: deployment.origins.merchant + "/" });
        return res.end();
      }
      if (
        /^\/api\/(admin|merchant)\/integration\/(guide.md|openapi.json)$/.test(
          path,
        )
      ) {
        session("merchants.read");
        const md = path.endsWith("guide.md"),
          body = integration(md ? "guide.md" : "openapi.json");
        return send(res, 200, body, {
          "Content-Type": md
            ? "text/markdown; charset=utf-8"
            : "application/json",
          "Content-Disposition":
            'attachment; filename="' +
            (md ? "GTT-Integration-v1.md" : "GTT-OpenAPI-v1.json") +
            '"',
        });
      }
      const files: any = {
        "/": "admin.html",
        "/merchant/": "admin.html",
        "/admin.js": "admin.js",
        "/admin.css": "admin.css",
      };
      check(files[path], "NOT_FOUND", "Not found", 404);
      return send(res, 200, readFileSync(join(frontend, files[path]), "utf8"), {
        "Content-Type": path.endsWith(".js")
          ? "application/javascript; charset=utf-8"
          : path.endsWith(".css")
            ? "text/css; charset=utf-8"
            : "text/html; charset=utf-8",
      });
    }
    check(
      req.method === "POST" && /^\/api\/(admin|merchant)\//.test(path),
      "NOT_FOUND",
      "Not found",
      404,
    );
    const q = await jsonBody(req),
      action = path.replace(/^\/api\/(admin|merchant)\//, "");
    if (action === "login") {
      const r = control.login(
        q.username,
        q.password,
        deployment.remote(req),
        merchantAPI,
      );
      check(
        !merchantAPI || r.data.user.merchant_id,
        "MERCHANT_LOGIN_REQUIRED",
        "Use merchant account",
        403,
      );
      return success(res, r.data, 200, { "Set-Cookie": cookie(r.token) });
    }
    check(Object.hasOwn(permissions, action), "NOT_FOUND", "Not found", 404);
    const s = session(
        permissions[action],
        String(req.headers["x-gtt-csrf"] ?? ""),
      ),
      actor = s.user.username,
      scope = s.user.merchant_id ?? undefined;
    if (scope) {
      check(
        [undefined, null, "", scope].includes(q.merchant_id),
        "FORBIDDEN",
        "Tenant mismatch",
        403,
      );
      if (
        ["merchants/profile", "merchants/rotate"].includes(action) ||
        action.startsWith("merchants/signing/")
      ) {
        check((q.id ?? scope) === scope, "FORBIDDEN", "Tenant mismatch", 403);
        q.id = scope;
      }
      q.merchant_id = scope;
    }
    let result: any;
    switch (action) {
      case "logout":
        control.logout(tok, actor);
        res.setHeader("Set-Cookie", cookie("", 0));
        result = { logged_out: true };
        break;
      case "password":
        control.changePassword(actor, q.current_password, q.new_password);
        res.setHeader("Set-Cookie", cookie("", 0));
        result = { changed: true };
        break;
      case "overview":
        result = overview(p, scope);
        break;
      case "integration/docs":
        result = JSON.parse(integration("integration.json"));
        break;
      case "merchants/list":
        result = {
          merchants: scope ? [control.merchant(scope)] : control.merchants(),
        };
        break;
      case "merchants/create":
        result = control.saveMerchant(actor, q, true);
        break;
      case "merchants/update":
        result = control.saveMerchant(actor, q);
        break;
      case "merchants/profile": {
        const { merchant_id, ...profile } = q;
        check(scope, "FORBIDDEN", "Merchant profile required", 403);
        result = control.profile(actor, scope, profile);
        break;
      }
      case "merchants/rotate":
      case "merchants/signing/rotate":
        result = control.signing(actor, q, "rotate");
        break;
      case "merchants/signing/view":
        result = control.signing(actor, q, "view");
        break;
      case "games":
        result = { games: p.catalog(scope) };
        break;
      case "transactions/list":
        result = { transactions: transactions(p, q) };
        break;
      case "transactions/detail":
        result = transactions(p, q, true);
        break;
      case "transactions/retry": {
        const mid = identifier(q.merchant_id),
          id = identifier(q.operation_id),
          why = reason(q),
          o = p.get(
            "SELECT status FROM game_operations WHERE merchant_id=? AND id=?",
            mid,
            id,
          );
        check(o, "NOT_FOUND", "Operation not found", 404);
        check(
          ["prepared", "debited"].includes(o.status),
          "NOT_PENDING",
          "Operation is not pending",
          409,
        );
        control.audit(actor, "transaction.retry.request", id, "success", {
          merchant_id: mid,
          reason: why,
          status: o.status,
        });
        try {
          result = await p.retry(mid, id, true);
          control.audit(actor, "transaction.retry.result", id, "success", {
            merchant_id: mid,
            status: "settled",
          });
        } catch (e) {
          control.audit(actor, "transaction.retry.result", id, "failed", {
            merchant_id: mid,
            code: e instanceof ServiceError ? e.code : "SERVICE_UNAVAILABLE",
          });
          throw e;
        }
        break;
      }
      case "prebet/list":
        result = { decisions: prebetDecisions(p, q) };
        break;
      case "audit":
        result = { audit: control.audits(q, scope) };
        break;
      case "users/list":
        result = { users: control.users(scope) };
        break;
      case "users/create":
        result = control.createUser(
          actor,
          q.username,
          q.role,
          undefined,
          q.merchant_id || null,
          scope,
        );
        break;
      case "users/update":
      case "users/reset":
        result = control.updateUser(actor, q, action === "users/reset", scope);
        break;
      case "rtp/read":
        result = p.rtp.snapshot(q, scope);
        break;
      case "rtp/policy":
        result = p.rtp.policy(actor, q, s.permissions.includes("rtp.manage"));
        break;
      case "rtp/mode":
        result = p.rtp.setMode(actor, q);
        break;
      case "rtp/job":
        result = p.rtp.createJob(actor, q);
        break;
      case "rtp/publish":
        result = p.rtp.publish(actor, q);
        break;
      default:
        throw new ServiceError("NOT_FOUND", "Not found", 404);
    }
    return success(res, result, action.endsWith("/create") ? 201 : 200);
  });
}
