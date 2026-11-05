import { createServer, IncomingMessage, ServerResponse } from "node:http";
import { readFileSync } from "node:fs";
import { resolve, basename } from "node:path";
import { pathToFileURL } from "node:url";
import * as p from "../compat/runtime.js";
import { BytesIO } from "../compat/platform.js";
import { body, fetchBounded, send } from "../shared/http.js";
import { ServiceError, check } from "../shared/core.js";
import { websocket } from "./websocket.js";

export const ENTRIES: Record<string, string> = {
  mahjong_client: "local_demo",
  buffalo_client: "buffalo_demo",
  json_api: "game_api",
  olympus_client: "olympus_demo",
  olympus_preview: "olympus_preview",
  sweet_bonanza_pop_client: "sweet_bonanza_pop_demo",
  big_bass_bonanza_client: "big_bass_bonanza_demo",
  super_ace_client: "super_ace_demo",
  fortune_gems2_client: "fortune_gems2_demo",
  jokers_fortune_winx_client: "jokers_fortune_winx_demo",
  three_billion_vaults_client: "three_billion_vaults_demo",
  money_pot_deluxe_client: "money_pot_deluxe_demo",
  roma_x_10000_client: "roma_x_10000_demo",
  wicked_grin_client: "wicked_grin_demo",
  le_vampire_client: "le_vampire_demo",
  dr_zappo_client: "dr_zappo_demo",
  great_game_serengeti_client: "great_game_serengeti_demo",
  tower_run_treasure_steps_client: "tower_run_treasure_steps_demo",
  wild_bandito_client: "wild_bandito_demo",
  fortune_rabbit_client: "fortune_rabbit_demo",
  captains_bounty_client: "captains_bounty_demo",
};
export function method(object: any, name: string, ...args: any[]) {
  return p.call(p.attr(object, name), args);
}
export function profile(directory: string) {
  const dir = resolve(directory),
    spec = JSON.parse(readFileSync(resolve(dir, "service.json"), "utf8"));
  check(
    /^[a-z0-9][a-z0-9-]*$/.test(spec.id) && Object.hasOwn(ENTRIES, spec.entry),
    "SERVICE_INVALID",
  );
  check(
    Number.isInteger(spec.port) && spec.port > 0 && spec.port <= 65535,
    "PORT_INVALID",
  );
  if (spec.entry === "olympus_preview") {
    check(
      Array.isArray(spec.games) && spec.games.length === 0,
      "GAMES_INVALID",
    );
    return { dir, spec };
  }
  check(
    Array.isArray(spec.games) &&
      spec.games.length > 0 &&
      new Set(spec.games).size === spec.games.length,
    "GAMES_INVALID",
  );
  if (spec.entry !== "json_api")
    check(
      spec.games.length === 1 &&
        ({
          mahjong_client: "mahjong-ways2",
          buffalo_client: "buffalo-win",
          olympus_client: "gates-of-olympus",
          three_billion_vaults_client: "3-billion-vaults",
        }[spec.entry] ??
          spec.entry.replace(/_client$/, "").replaceAll("_", "-")) ===
          spec.games[0],
      "GAME_ISOLATION_REQUIRED",
    );
  return { dir, spec };
}
export async function buildLocal(
  directory: string,
  options: {
    database?: string;
    port?: number;
    launchPorts?: Record<string, number>;
  } = {},
) {
  const { dir, spec } = profile(directory),
    mod = await import(
      new URL(
        "../migrated/server/services/" + ENTRIES[spec.entry] + ".js",
        import.meta.url,
      ).href
    );
  const configs = p.from(
    Object.fromEntries(
      spec.games.map((id: string) => {
        check(/^[a-z0-9-]+$/.test(id), "GAME_ID_INVALID");
        const path = resolve(dir, "config", id + ".json");
        readFileSync(path);
        return [id, path];
      }),
    ),
  );
  const args: any[] = [
    options.port ?? spec.port,
    options.database ?? resolve(dir, "data/games.sqlite3"),
  ];
  if (spec.entry === "olympus_preview") args.splice(1);
  else if (spec.entry === "json_api") args.push(spec.games, configs);
  else args.push(p.item(configs, spec.games[0]));
  const app = p.call(mod.build_server, args);
  app.service_id = spec.id;
  const server = createServer(async (req, res) => {
    try {
      check(
        req.headers.host === `127.0.0.1:${app.server_port}` ||
          req.headers.host === `localhost:${app.server_port}`,
        "HOST_REJECTED",
        "Unexpected host",
        403,
      );
      const bytes = await body(req, 131072);
      const url = new URL(req.url!, "http://local");
      // The lobby forwards launch requests asynchronously; no sync networking or
      // Python helper process is used inside the Node event loop.
      const match = /^\/api\/v1\/games\/([a-z0-9-]+)\/launch$/.exec(
        url.pathname,
      );
      if (
        spec.id === "mahjong-ways2" &&
        req.method === "POST" &&
        match &&
        match[1] !== "mahjong-ways2"
      ) {
        check(
          !req.headers.origin ||
            req.headers.origin === "http://" + req.headers.host,
          "ORIGIN_REJECTED",
          "Cross-origin writes rejected",
          403,
        );
        const target = profile(p.sourcePath("services/" + match[1])).spec;
        const payload = p.plain(p.jsonLoads(bytes));
        check(
          ["zh", "en"].includes(payload.language ?? "zh"),
          "LANGUAGE_INVALID",
        );
        const origin =
          "http://127.0.0.1:" +
          (options.launchPorts?.[target.id] ?? target.port);
        try {
          const result = await fetchBounded(
            origin + url.pathname,
            {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify(payload),
              timeout: 5000,
            },
            1048576,
          );
          check(result.status === 201, "GAME_UNAVAILABLE");
          const value = JSON.parse(result.body);
          const link = new URL(value.launch_url, origin);
          check(
            link.origin === origin &&
              link.pathname === "/" &&
              link.searchParams.get("mock") === "1" &&
              link.searchParams.has("ops"),
            "GAME_UNAVAILABLE",
          );
          value.launch_url = link.href;
          send(res, 201, value);
          return;
        } catch {
          throw new ServiceError(
            "GAME_UNAVAILABLE",
            target.id + " service unavailable",
            503,
          );
        }
      }
      dispatch(app, req, res, bytes);
    } catch (e) {
      const safe =
        e instanceof ServiceError
          ? e
          : new ServiceError(
              "INVALID_REQUEST",
              e instanceof Error ? e.message : "Invalid request",
              400,
            );
      if (!res.headersSent)
        send(res, safe.status, {
          dt: null,
          err: { cd: safe.code, msg: safe.message },
        });
      else res.destroy();
    }
  });
  server.on("upgrade", (req, socket, head) => {
    try {
      check(
        req.headers.host === `127.0.0.1:${app.server_port}` ||
          req.headers.host === `localhost:${app.server_port}`,
        "HOST_REJECTED",
      );
      const handler = handlerFor(app, req, Buffer.alloc(0));
      let upgraded = false;
      handler.__websocket = (kind: string) => {
        websocket(kind, handler, req, socket, head);
        upgraded = true;
      };
      method(handler, "do_GET");
      if (!upgraded)
        socket.end(
          `HTTP/1.1 ${handler.__status >= 400 ? handler.__status : 400} Bad Request\r\nContent-Length: 0\r\n\r\n`,
        );
    } catch {
      socket.end("HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n");
    }
  });
  server.once("listening", () => {
    app.server_port = (server.address() as any).port;
    app.server_address = p.tuple(["127.0.0.1", app.server_port]);
  });
  return { server, app, spec };
}
export function handlerFor(app: any, req: IncomingMessage, bytes: Buffer) {
  class Headers extends p.Dict {
    has(k: any) {
      return super.has(String(k).toLowerCase());
    }
    get(k: any) {
      return super.get(String(k).toLowerCase());
    }
    set(k: any, v: any) {
      return super.set(String(k).toLowerCase(), v);
    }
    get_content_type = () =>
      String(req.headers["content-type"] ?? "text/plain").split(";")[0];
  }
  const headers = new Headers(
    Object.entries(req.headers).map(([k, v]) => [
      k,
      Array.isArray(v) ? v.join(", ") : String(v),
    ]),
  );
  const chunks: Buffer[] = [],
    context: any = {
      server: app,
      path: req.url,
      command: req.method,
      headers,
      directory: p.sourcePath("clients"),
      rfile: new BytesIO(bytes),
      wfile: {
        write: (v: any) => {
          chunks.push(Buffer.from(v));
        },
        flush: () => null,
      },
      __status: 200,
      __headers: {},
      __chunks: chunks,
      __remote: req.socket.remoteAddress,
      __websocket: () => {
        throw new ServiceError("INVALID_REQUEST", "WebSocket upgrade required");
      },
    };
  return p.call(app.handler, [context]);
}
export function dispatch(
  app: any,
  req: IncomingMessage,
  res: ServerResponse,
  bytes: Buffer,
) {
  const handler = handlerFor(app, req, bytes);
  method(
    handler,
    req.method === "GET"
      ? "do_GET"
      : req.method === "HEAD"
        ? "do_HEAD"
        : req.method === "POST"
          ? "do_POST"
          : "unsupported_method",
  );
  const payload = Buffer.concat(handler.__chunks);
  res.writeHead(handler.__status, {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Content-Length": payload.length,
    ...handler.__headers,
  });
  res.end(req.method === "HEAD" ? undefined : payload);
}
