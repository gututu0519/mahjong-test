import { readFileSync } from "node:fs";
import { server, body, success, utf8 } from "../shared/http.js";
import { check, equal, ServiceError } from "../shared/core.js";
import { definitions } from "../migrated/server/games/catalog.js";
import * as p from "../compat/runtime.js";
import { method } from "./local.js";

// One game per process. State and settlement belong to the caller, never here.
export function computeServer(
  id: string,
  configuration: string,
  secret: string,
) {
  check(Object.hasOwn(definitions, id), "GAME_NOT_FOUND");
  check(secret.length >= 32, "INTERNAL_KEY_INVALID");
  const config = p.jsonLoads(readFileSync(configuration)),
    game = p.call(definitions[id].factory, [config]);
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
    let result: any;
    switch (req.url) {
      case "/v1/describe":
        result = p.from({
          game_id: id,
          title: p.attr(game, "title"),
          version: p.attr(game, "version"),
          ruleset_id: p.attr(game, "ruleset_id"),
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
      default:
        throw new ServiceError("NOT_FOUND", "Not found", 404);
    }
    success(res, p.plain(result));
  });
}
