import { roundSummary, roundChanges } from "./rounds.js";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { server, body, send, success, utf8 } from "../../other/shared/http.js";
import { object, check, clone, limit, ServiceError } from "../../other/shared/core.js";
import type { Provider } from "./provider.js";
import { PG } from "./pg.js";
import { Deployment } from "./deployment.js";
import { asset, gatewayClientRoot } from "./assets.js";
import { ProtocolPool } from "./protocol-pool.js";
import { merchantClientHTML } from "./merchant-client.js";
import { merchantLaunch, merchantGameResult, merchantOperations, merchantRoundSummary } from "./merchant-money.js";
export function gatewayServer(p: Provider, config: any, clientRoot: string) {
  clientRoot=gatewayClientRoot(clientRoot);
  const pool = new ProtocolPool(p.enableGames(config), config);
  const deployment = new Deployment(config),
    pg = new PG(p),
    auth = JSON.parse(
      readFileSync(join(clientRoot, "fixtures/auth-metadata.json"), "utf8"),
    ),
    rule = JSON.parse(
      readFileSync(join(clientRoot, "fixtures/game-rule.json"), "utf8"),
    );
  const http = server(async (req, res) => {
    const url = new URL(req.url!, "http://local"),
      path = url.pathname;
    try {
      const game = pool.host(req);
      if (game) return await pool.handle(game, req, res);
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
          return send(res, 200, { games: p.merchantCatalog() });
        if (path === "/api/v1/wallet")
          return send(res, 200, await p.wallet(tok));
        if (/^\/api\/v1\/games\/[^/]+\/state$/.test(path)) {
          check(
            p.session(tok).game_id === path.split("/")[4],
            "SESSION_GAME_MISMATCH",
            "Session belongs to another game",
            403,
          );
          return send(res, 200, await p.state(tok));
        }
        if (path === "/api/v1/history") {
          const s = p.session(tok);
          return send(res, 200, {
            spins: p
              .all(
                "SELECT response_json FROM game_operations WHERE merchant_id=? AND player_id=? AND game_id=? AND status='settled' ORDER BY seq DESC LIMIT ?",
                s.merchant_id,
                s.player_id,
                s.game_id,
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
        if (a.type.startsWith("text/html") && url.searchParams.has("ops")) {
          const token = url.searchParams.get("ops")!, session = p.session(token);
          check(session.game_id === "buffalo-win", "SESSION_GAME_MISMATCH");
          a.data = Buffer.from(merchantClientHTML(a.data.toString(), req.url!, "http://" + req.headers.host, {
            code:"buffalo-win",token,operator:session.merchant_id,player_id:session.player_id,
            currency:p.control.merchant(session.merchant_id).currency,
          }));
        }
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
          return success(res, { games: p.merchantCatalog(mid) });
        if (path === "/gtt/v1/games/launch")
          return success(res, merchantLaunch(await p.launch(mid, q)), 201);
        if (path === "/gtt/v1/rounds/get")
          return success(res, merchantRoundSummary(p.tx(() => roundSummary(p,mid,q))));
        if (path === "/gtt/v1/rounds/changes")
          return success(res, p.tx(() => {
            const result = roundChanges(p,mid,q);
            return {...result, changes: result.changes.map((change: any) => ({...change, round: merchantRoundSummary(change.round)}))};
          }));
        if (path === "/gtt/v1/transactions/list")
          return success(res, merchantOperations(p.operations(mid, q)));
        if (path === "/gtt/v1/transactions/retry")
          return success(res, merchantGameResult(await p.retry(mid, q.operation_id)));
        throw new ServiceError("NOT_FOUND", "Not found", 404);
      }
      if (path.startsWith("/api/")) {
        check(
          req.headers["content-type"]?.split(";")[0] === "application/json",
          "CONTENT_TYPE",
        );
        const q = object(utf8(raw)),
          tok = String(req.headers.authorization ?? "").replace(/^Bearer /, "");
        if (/^\/api\/v1\/games\/[^/]+\/spin$/.test(path)) {
          check(
            p.session(tok).game_id === path.split("/")[4],
            "SESSION_GAME_MISMATCH",
            "Session belongs to another game",
            403,
          );
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
        }
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
      check(
        p.session(tok).game_id === "buffalo-win",
        "SESSION_GAME_MISMATCH",
        "Session belongs to another game",
        403,
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
          nkn: wallet.player_id,
          ioph: p.session(tok).merchant_id,
          cc: wallet.currency,
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
  http.on("upgrade", (req, socket, head) => {
    const code = pool.host(req);
    if (!code) {
      socket.end("HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n");
      return;
    }
    void pool
      .upgrade(code, req, socket, head)
      .catch(() =>
        socket.end("HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n"),
      );
  });
  http.once("close", () => {
    void pool.close();
  });
  return Object.assign(http, { protocolPool: pool });
}
