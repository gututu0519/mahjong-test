import { websocket } from "../services/websocket.js";
import * as py from "../compat/runtime.js";
import type { Duplex } from "node:stream";
import { Worker } from "node:worker_threads";
import { resolve, dirname } from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import { body } from "../shared/http.js";
import { check, ServiceError } from "../shared/core.js";
import { GAME_CODES } from "./catalog.js";
import type { MerchantGames } from "./merchant-games.js";

export class ProtocolPool {
  workers = new Map<string, any>();
  sequence = 0;
  constructor(
    public games: MerchantGames,
    public config: any,
  ) {}
  async snapshot(token: string, after = 0) {
    const s = this.games.session(token),
      state = await this.games.state(token),
      m = this.games.merchant(s.merchant_id, s.game_id);
    const mirror = this.games.mirror(token, after);
    return {
      mirror,
      snapshot: {
        expires_at: s.expires_at,
        state,
        raw_state: this.games.initial(s.merchant_id, s.player_id, s.game_id),
        wallet: {
          player_id: mirror.player_id,
          balance_minor: state.balance_minor,
          currency: m.currency,
          minor_unit: this.games.descriptor(s.game_id).minor_unit,
        },
      },
    };
  }
  async worker(code: string) {
    let entry = this.workers.get(code);
    if (entry) return entry.ready;
    const instance = new Worker(
        new URL("./protocol-worker.js", import.meta.url),
        {
          workerData: {
            code,
            database: resolve(
              this.config.protocol_directory ??
                resolve(
                  dirname(this.config.game_database),
                  "merchant-protocols",
                ),
              code + ".sqlite3",
            ),
          },
        },
      ),
      pending = new Map<number, any>();
    entry = { instance, pending };
    entry.ready = new Promise((ok, fail) => {
      instance.on("message", async (value) => {
        if (value.ready) return ok(entry);
        if (value.rpc) {
          let reply: any;
          try {
            const [token, ...args] = value.args;
            this.games.session(token, code);
            if (value.command === "sync")
              reply = { data: await this.snapshot(token, args[0]) };
            else if (value.command === "history")
              reply = { data: this.games.history(token, args[0]) };
            else if (value.command === "spin") {
              const result = await this.games.spin(
                token,
                args[0],
                args[1],
                args[2],
              );
              reply = {
                data: { result, ...(await this.snapshot(token, args[3])) },
              };
            } else throw new ServiceError("NOT_FOUND");
          } catch (e) {
            reply = {
              error: {
                code: (e as any).code ?? "GAME_UNAVAILABLE",
                message: (e as any).message,
                status: (e as any).status ?? 503,
              },
            };
          }
          let bytes = Buffer.from(JSON.stringify(reply));
          if (bytes.length > value.memory.byteLength - 8)
            bytes = Buffer.from(
              JSON.stringify({
                error: {
                  code: "RESPONSE_TOO_LARGE",
                  message: "Protocol snapshot too large",
                  status: 503,
                },
              }),
            );
          Buffer.from(value.memory, 8, bytes.length).set(bytes);
          const flag = new Int32Array(value.memory, 0, 2);
          Atomics.store(flag, 1, bytes.length);
          Atomics.store(flag, 0, 1);
          Atomics.notify(flag, 0);
          return;
        }
        const call = pending.get(value.id);
        if (!call) return;
        pending.delete(value.id);
        value.error
          ? call.reject(
              new ServiceError(
                value.error.code,
                value.error.message,
                value.error.status,
              ),
            )
          : call.resolve(value);
      });
      instance.on("error", (e) => {
        fail(e);
        for (const v of pending.values()) v.reject(e);
        pending.clear();
      });
      instance.on("exit", () => {
        fail(
          new ServiceError("GAME_UNAVAILABLE", "Protocol worker stopped", 503),
        );
        this.workers.delete(code);
        for (const v of pending.values())
          v.reject(
            new ServiceError(
              "GAME_UNAVAILABLE",
              "Protocol worker stopped",
              503,
            ),
          );
        pending.clear();
      });
    });
    this.workers.set(code, entry);
    return entry.ready;
  }
  host(req: IncomingMessage) {
    const host = String(req.headers.host ?? "");
    return GAME_CODES.find(
      (code) =>
        (this.config.environment !== "production" ||
          this.config.game_origins?.[code]) &&
        new URL(this.games.origin(code)).host === host,
    );
  }
  token(req: IncomingMessage, code: string) {
    const url = new URL(req.url!, "http://local"),
      cookie = String(req.headers.cookie ?? "")
        .split(";")
        .map((v) => v.trim())
        .find((v) => v.startsWith("gtt-session="))
        ?.slice(12),
      token =
        url.searchParams.get("ops") ??
        cookie ??
        String(
          req.headers.authorization ??
            req.headers["x-local-game-session"] ??
            "",
        ).replace(/^Bearer /, "");
    this.games.session(token, code);
    return token;
  }
  guard(req: IncomingMessage, code: string) {
    const origin = this.games.origin(code);
    check(
      req.headers.host === new URL(origin).host,
      "HOST_REJECTED",
      "Unexpected host",
      403,
    );
    check(
      !req.headers.origin || req.headers.origin === origin,
      "ORIGIN_REJECTED",
      "Unexpected origin",
      403,
    );
    if (this.config.environment === "production") {
      check(
        (this.config.trusted_proxy_ips ?? []).includes(
          req.socket.remoteAddress,
        ) && req.headers["x-forwarded-proto"] === "https",
        "PROXY_REJECTED",
        "Trusted HTTPS proxy required",
        403,
      );
    }
  }
  async handle(code: string, req: IncomingMessage, res: ServerResponse) {
    this.guard(req, code);
    const token = this.token(req, code),
      url = new URL(req.url!, "http://local");
    check(
      !url.pathname.startsWith("/gtt/") &&
        url.pathname !== "/api/v1/sessions" &&
        !url.pathname.endsWith("/launch"),
      "MERCHANT_AUTH_REQUIRED",
      "Use the signed merchant launch API",
      401,
    );
    check(
      ["GET", "POST", "HEAD"].includes(req.method ?? ""),
      "METHOD_NOT_ALLOWED",
      "Method not allowed",
      405,
    );
    const worker = await this.worker(code),
      id = ++this.sequence,
      bytes = await body(req, 131072),
      reply: any = await new Promise((resolve, reject) => {
        worker.pending.set(id, { resolve, reject });
        worker.instance.postMessage({
          id,
          request: {
            token,
            url: req.url,
            method: req.method,
            headers: req.headers,
            port: req.socket.localPort,
            body: bytes,
          },
        });
      });
    const data = Buffer.from(reply.body),
      cookies = reply.headers["Set-Cookie"] ?? reply.headers["set-cookie"];
    delete reply.headers["Set-Cookie"];
    delete reply.headers["set-cookie"];
    res.writeHead(reply.status, {
      ...reply.headers,
      "Content-Length": data.length,
      "Cache-Control": "no-store",
      "Referrer-Policy": "no-referrer",
      "Set-Cookie": [
        `gtt-session=${token}; Path=/; HttpOnly; SameSite=Lax${this.config.environment === "production" ? "; Secure" : ""}`,
        ...(cookies ? [cookies] : []),
      ],
    });
    res.end(req.method === "HEAD" ? undefined : data);
  }
  async upgrade(
    code: string,
    req: IncomingMessage,
    socket: Duplex,
    head: Buffer,
  ) {
    this.guard(req, code);
    const token = this.token(req, code),
      path = new URL(req.url!, "http://local").pathname;
    check(
      (path === "/lifeservice/ws2" &&
        this.games.descriptor(code).minor_unit === 10000) ||
        (path === "/platform/player-events" &&
          code === "tower-run-treasure-steps"),
      "NOT_FOUND",
    );
    await this.games.wallet(token, code);
    const handler = { token: py.native(() => token) };
    websocket(
      path.includes("player-events") ? "player_events" : "life_service",
      handler,
      req,
      socket,
      head,
      async (supplied) => {
        check(supplied === token, "SESSION_INVALID");
        return this.games.wallet(token, code);
      },
      this.games.origin(code),
    );
  }
  async close() {
    await Promise.all(
      [...this.workers.values()].map((v) => v.instance.terminate()),
    );
    this.workers.clear();
  }
}
