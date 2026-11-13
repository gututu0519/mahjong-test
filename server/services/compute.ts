import { readFileSync } from "node:fs";
import { server, body, success, send, utf8 } from "../shared/http.js";
import { check, equal, ServiceError } from "../shared/core.js";
import { definitions } from "../migrated/py/games/catalog.js";
import * as p from "../compat/runtime.js";
import { method } from "./local.js";
import { gameUnit } from "../gateway/catalog.js";
import { invokeEngine, prebetPlan, rtpPlan } from "./game-planning.js";

// One game per process. State and settlement belong to the caller, never here.
export function computeServer(
  id: string,
  configuration: string,
  secret: string,
  options: {
    release?: string;
    clientContract?: string;
    stateContract?: string;
  } = {},
) {
  check(Object.hasOwn(definitions, id), "GAME_NOT_FOUND");
  check(secret.length >= 32, "INTERNAL_KEY_INVALID");
  const config = p.jsonLoads(readFileSync(configuration)),
    base = p.call(definitions[id].factory, [config]);
  const release = options.release ?? p.attr(base, "version");
  return server(async (req, res) => {
    check(
      equal(String(req.headers.authorization ?? ""), "Bearer " + secret),
      "AUTH_INVALID",
      "Internal authentication required",
      401,
    );
    if (req.method === "GET" && req.url === "/health")
      return success(res, { status: "ok", service_id: id + "-compute-node" });
    check(req.method === "POST", "NOT_FOUND", "Not found", 404);
    check(
      req.headers["content-type"]?.split(";")[0] === "application/json",
      "CONTENT_TYPE",
    );
    const value = p.jsonLoads(utf8(await body(req, 4 * 1024 * 1024)));
    check(value instanceof p.Dict, "INVALID_ARGUMENT");
    const q = p.plain(value);
    check(
      !q.expected_release || q.expected_release === release,
      "GAME_RELEASE_CHANGED",
      "游戏服务版本发生变化，请恢复原版本",
      409,
    );
    check(
      !q.expected_ruleset || q.expected_ruleset === p.attr(base, "ruleset_id"),
      "GAME_RELEASE_CHANGED",
      "游戏配置发生变化，请恢复原版本",
      409,
    );
    const game = q.configuration
      ? p.call(definitions[id].factory, [p.from(q.configuration)])
      : base;
    let result: any;
    switch (req.url) {
      case "/v1/describe":
        result = p.from({
          game_id: id,
          title: p.attr(game, "title"),
          version: p.attr(game, "version"),
          ruleset_id: p.attr(game, "ruleset_id"),
          config: p.plain(p.attr(game, "config")),
          release,
          protocol_version: 1,
          minor_unit: gameUnit(id),
          client_contract: options.clientContract ?? id + ":original-v1",
          state_contract: options.stateContract ?? id + ":state-v1",
        });
        break;
      case "/v1/initial":
        result = method(
          game,
          "initial_state",
          ...(value.has("seed") ? [value.get("seed")] : []),
        );
        break;
      case "/v1/normalize":
        result = method(game, "normalize_bet", p.item(value, "bet"));
        break;
      case "/v1/step":
        check(
          typeof value.get("seed") === "string" &&
            typeof value.get("operation_id") === "string",
          "INVALID_ARGUMENT",
        );
        result = method(
          game,
          "step",
          p.item(value, "state"),
          method(game, "normalize_bet", p.item(value, "bet")),
          value.get("seed"),
          value.get("operation_id"),
        );
        break;
      case "/v1/invoke":
        check(
          ["initial_state", "public_state", "normalize_bet", "step"].includes(
            q.method,
          ) && Array.isArray(q.args),
          "INVALID_ARGUMENT",
        );
        result = p.from(invokeEngine(game, q.method, ...q.args));
        break;
      case "/v1/prebet-plan":
        result = p.from(prebetPlan(id, game, q));
        break;
      case "/v1/rtp-plan":
        result = p.from(rtpPlan(id, game, q));
        break;
      default:
        throw new ServiceError("NOT_FOUND", "Not found", 404);
    }
    send(res, 200, {
      data: p.plain(result),
      error: null,
      service: { game_id: id, release, ruleset_id: p.attr(base, "ruleset_id") },
    });
  });
}
