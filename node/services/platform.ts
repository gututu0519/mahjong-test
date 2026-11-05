import { readFileSync } from "node:fs";
import {
  server,
  body,
  send,
  success,
  fetchBounded,
  utf8,
} from "../shared/http.js";
import { check, object, encode, signedHeaders, DB } from "../shared/core.js";
import { Control } from "../gateway/control.js";
import { MockWallet } from "../migrated/server/merchant/mock_wallet.js";
import * as p from "../compat/runtime.js";
import { method } from "./local.js";

export function platformServer(config: any, control: Control) {
  check(config.environment !== "production", "SANDBOX_FORBIDDEN");
  const mid = config.sandbox_merchant,
    player = config.sandbox_player;
  check(
    typeof mid === "string" && typeof player === "string",
    "SANDBOX_CONFIG_REQUIRED",
  );
  const directory = () =>
    p.from(
      Object.fromEntries(
        control.merchants().map((m) => [m.id, control.merchant(m.id, true)]),
      ),
    );
  const wallet = p.call(MockWallet, [config.platform_database, directory()]);
  wallet.snapshot = p.native(([row]) =>
    p.from({
      player_id: p.item(row, "player_id"),
      currency: p.item(row, "currency"),
      balance_minor: p.item(row, "balance_minor"),
      minor_unit: control.merchant(p.item(row, "merchant_id"), true).minor_unit,
    }),
  );
  const auth = new DB(config.platform_database);
  method(wallet, "seed", mid, player, config.sandbox_balance_minor ?? 200000);
  if (config.sandbox_external_username)
    method(
      wallet,
      "bind_prebet_player",
      mid,
      player,
      config.sandbox_external_username,
    );
  const postGateway = async (path: string, payload: any) => {
    const merchant = control.merchant(mid, true);
    check(merchant, "MERCHANT_NOT_FOUND");
    const raw = encode(payload);
    const response = await fetchBounded(
      config.gateway_origin + path,
      {
        method: "POST",
        headers: signedHeaders(mid, merchant.merchant_secret, path, raw),
        body: raw,
        timeout: 10000,
      },
      1048576,
    );
    const result = object(response.body);
    check(
      response.status < 300 && !result.error,
      result.error?.code ?? "GATEWAY_UNAVAILABLE",
      result.error?.message ?? "Gateway unavailable",
      response.status,
    );
    return result.data;
  };
  const http = server(async (req, res) => {
    const host = req.headers.host;
    check(
      host === `localhost:${req.socket.localPort}` ||
        host === `127.0.0.1:${req.socket.localPort}`,
      "HOST_REJECTED",
      "Unexpected host",
      403,
    );
    check(
      !req.headers.origin || req.headers.origin === "http://" + host,
      "ORIGIN_REJECTED",
      "Unexpected origin",
      403,
    );
    const path = new URL(req.url!, "http://local").pathname;
    p.setattr(wallet, "merchants", directory());
    if (req.method === "GET") {
      if (path === "/health")
        return success(res, { status: "ok", service_id: "gtt-mock-platform" });
      if (path === "/")
        return send(
          res,
          200,
          readFileSync(
            new URL("../../frontend/platform/index.html", import.meta.url),
            "utf8",
          ),
          { "Content-Type": "text/html; charset=utf-8" },
        );
      if (path === "/sandbox/status" || path === "/sandbox/snapshot") {
        const merchant = control.merchant(mid, true);
        return success(res, {
          merchant_id: mid,
          ...p.plain(
            method(
              wallet,
              "call",
              mid,
              "transactions/list",
              p.from({
                player_id: player,
                currency: merchant.currency,
                minor_unit: merchant.minor_unit,
              }),
            ),
          ),
        });
      }
      if (path === "/sandbox/games")
        return success(res, await postGateway("/gtt/v1/games/list", {}));
      if (path === "/sandbox/prebet-policy")
        return success(res, {
          maxWinMulti: p.plain(method(wallet, "prebet_policy", mid)),
        });
    }
    check(req.method === "POST", "NOT_FOUND", "Not found", 404);
    check(
      !new URL(req.url!, "http://local").search,
      "BAD_REQUEST",
      "Signed routes do not accept query parameters.",
    );
    check(
      req.headers["content-type"]?.split(";")[0] === "application/json",
      "CONTENT_TYPE",
      "Use application/json.",
      415,
    );
    const raw = await body(req);
    check(
      raw.length > 0,
      "BODY_TOO_LARGE",
      "Request must contain 1..16384 bytes.",
      413,
    );
    const payload = object(utf8(raw));
    if (path === "/sandbox/prebet-policy")
      return success(res, {
        maxWinMulti: p.plain(
          method(wallet, "prebet_policy", mid, p.from(payload.maxWinMulti)),
        ),
      });
    if (path === "/sandbox/launch") {
      const result = await postGateway("/gtt/v1/games/launch", {
        player_id: player,
        game_id: payload.game_id ?? 1,
        language: payload.language ?? "en",
        ...(config.sandbox_external_username
          ? { external_username: config.sandbox_external_username }
          : {}),
      });
      result.launch_url = new URL(
        result.launch_url,
        config.gateway_origin,
      ).href;
      return success(res, result, 201);
    }
    check(
      path.startsWith("/wallet/v1/") ||
        path === "/api/v1/callbacks/gtt/preBetDecision",
      "NOT_FOUND",
      "Not found",
      404,
    );
    const merchant = control.merchant(
      String(req.headers["x-gtt-merchant"] ?? ""),
      true,
    );
    check(merchant, "AUTH_INVALID", "Unknown merchant", 401);
    auth.authenticate(req.headers, path, raw, { ...merchant, enabled: true });
    if (path === "/api/v1/callbacks/gtt/preBetDecision")
      return send(
        res,
        200,
        p.plain(
          method(wallet, "prebet_decision", merchant.id, p.from(payload)),
        ),
      );
    return success(
      res,
      p.plain(
        method(
          wallet,
          "call",
          merchant.id,
          path.slice("/wallet/v1/".length),
          p.from(payload),
        ),
      ),
    );
  });
  http.once("close", () => auth.close());
  return { server: http, wallet };
}
