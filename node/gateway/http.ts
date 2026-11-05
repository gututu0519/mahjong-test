import { readFileSync } from "node:fs";
import { join } from "node:path";
import { server, body, send, success, utf8 } from "../shared/http.js";
import { object, check, clone, limit, ServiceError } from "../shared/core.js";
import type { Provider } from "./provider.js";
import { PG } from "./pg.js";
import { Deployment } from "./deployment.js";
import { asset } from "./assets.js";
export function gatewayServer(p: Provider, config: any, clientRoot: string) {
  const deployment = new Deployment(config),
    pg = new PG(p),
    auth = JSON.parse(
      readFileSync(join(clientRoot, "fixtures/auth-metadata.json"), "utf8"),
    ),
    rule = JSON.parse(
      readFileSync(join(clientRoot, "fixtures/game-rule.json"), "utf8"),
    );
  return server(async (req, res) => {
    const url = new URL(req.url!, "http://local"),
      path = url.pathname;
    try {
      deployment.guard(req, "gateway");
      if (req.method === "GET") {
        const tok = String(req.headers.authorization ?? "").replace(
          /^Bearer /,
          "",
        );
        if (path === "/health")
          return send(res, 200, {
            status: "ok",
            service_id: "gtt-gateway-node",
            api_version: 1,
            games: p.catalog(),
          });
        if (path === "/api/v1/games")
          return send(res, 200, { games: p.catalog() });
        if (path === "/api/v1/wallet")
          return send(res, 200, await p.wallet(tok));
        if (path === "/api/v1/games/buffalo-win/state")
          return send(res, 200, await p.state(tok));
        if (path === "/api/v1/history") {
          const s = p.session(tok);
          return send(res, 200, {
            spins: p
              .all(
                "SELECT response_json FROM game_operations WHERE merchant_id=? AND player_id=? AND status='settled' ORDER BY seq DESC LIMIT ?",
                s.merchant_id,
                s.player_id,
                limit(Number(url.searchParams.get("limit") ?? 20)),
              )
              .map((r) => JSON.parse(r.response_json)),
          });
        }
        check(
          !path.startsWith("/api/") &&
            !path.startsWith("/game-api/") &&
            !path.startsWith("/web-api/") &&
            !path.startsWith("/gtt/"),
          "NOT_FOUND",
          "Not found",
          404,
        );
        const a = asset(clientRoot, req.url!);
        res.writeHead(200, {
          "Content-Type": a.type,
          "Content-Length": a.data.length,
          "Cache-Control": "no-store",
          "X-Content-Type-Options": "nosniff",
          "Referrer-Policy": "no-referrer",
        });
        return res.end(a.data);
      }
      check(req.method === "POST", "NOT_FOUND", "Not found", 404);
      const raw = await body(req);
      if (path.startsWith("/gtt/")) {
        check(
          !url.search &&
            req.headers["content-type"]?.split(";")[0] === "application/json",
          "BAD_REQUEST",
        );
        const mid = String(req.headers["x-gtt-merchant"] ?? "");
        p.authenticate(req.headers, path, raw, p.control.merchant(mid, true));
        const q = object(utf8(raw));
        if (path === "/gtt/v1/games/list")
          return success(res, { games: p.catalog(mid) });
        if (path === "/gtt/v1/games/launch")
          return success(res, await p.launch(mid, q), 201);
        if (path === "/gtt/v1/transactions/list")
          return success(res, p.operations(mid, q));
        if (path === "/gtt/v1/transactions/retry")
          return success(res, await p.retry(mid, q.operation_id));
        throw new ServiceError("NOT_FOUND", "Not found", 404);
      }
      if (path.startsWith("/api/")) {
        check(
          req.headers["content-type"]?.split(";")[0] === "application/json",
          "CONTENT_TYPE",
        );
        const q = object(utf8(raw)),
          tok = String(req.headers.authorization ?? "").replace(/^Bearer /, "");
        if (path === "/api/v1/games/buffalo-win/spin")
          return send(
            res,
            200,
            await p.spin(
              tok,
              String(req.headers["idempotency-key"] ?? ""),
              q.previous_sid,
              q.bet ?? {},
            ),
          );
        if (path === "/api/v1/sessions" || path.endsWith("/launch"))
          throw new ServiceError(
            "MERCHANT_AUTH_REQUIRED",
            "Use signed merchant launch",
            401,
          );
        throw new ServiceError("NOT_FOUND", "Not found", 404);
      }
      const form = new URLSearchParams(raw.toString("utf8")),
        tok = String(
          req.headers["x-local-game-session"] ?? form.get("atk") ?? "",
        );
      const wallet = await p.wallet(tok);
      let result: any;
      if (
        [
          "/web-api/auth/session/v2/verifySession",
          "/web-api/auth/session/v2/verifyOperatorPlayerSession",
        ].includes(path)
      ) {
        const d = clone(auth);
        Object.assign(d, {
          tk: tok,
          pid: wallet.player_id,
          pcd: wallet.player_id,
          nkn: "Local demo",
          ioph: "local-demo",
          oj: { jid: 1 },
          bl: wallet.balance_minor / 100,
        });
        d.uiogc.bf = 1;
        result = { dt: d, err: null };
      } else if (path === "/game-api/buffalo-win/v2/GameInfo/Get")
        result = await pg.info(tok);
      else if (path === "/game-api/buffalo-win/v2/Spin")
        result = await pg.spin(form, tok);
      else if (path === "/web-api/game-proxy/v2/GameWallet/Get")
        result = await pg.wallet(tok);
      else if (path === "/web-api/game-proxy/v2/GameName/Get")
        result = {
          dt: { "108": form.get("lang") === "en" ? "Buffalo Win" : "美洲野牛" },
          err: null,
        };
      else if (
        path === "/web-api/game-proxy/v2/Resources/GetByResourcesTypeIds"
      )
        result = { dt: [], err: null };
      else if (path === "/web-api/game-proxy/ServerManager/RefreshWallet")
        result = { dt: null, err: null };
      else if (path === "/web-api/game-proxy/v2/GameRule/Get") {
        check((form.get("gid") ?? "108") === "108", "GAME_NOT_FOUND");
        const snap = await p.state(tok),
          d = clone(rule),
          target = snap.rtp.target_rtp;
        if (target != null) {
          Object.assign(d.dt.rtp.Default, { min: target, max: target });
          for (const g of d.dt.grtpi ?? [])
            for (const v of g.grtps ?? [])
              Object.assign(v, { min: target, max: target });
        }
        result = d;
      } else throw new ServiceError("NOT_FOUND", "Not found", 404);
      return send(res, 200, result);
    } catch (e) {
      if (path.startsWith("/gtt/")) throw e;
      if (e instanceof ServiceError)
        return send(res, e.status, {
          dt: null,
          err: { cd: e.code, msg: e.message },
        });
      throw e;
    }
  });
}
