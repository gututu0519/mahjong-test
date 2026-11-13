import { websocket } from "../../other/shared/services/websocket.js";
import * as py from "../../other/shared/compat/runtime.js";
import type { Duplex } from "node:stream";
import { Worker } from "node:worker_threads";
import { resolve, dirname } from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import { body } from "../../other/shared/http.js";
import { check, ServiceError } from "../../other/shared/core.js";
import { GAME_CODES } from "./catalog.js";
import type { MerchantGames } from "./merchant-games.js";
import { merchantClientHTML, merchantClientJSON, merchantClientText, merchantClientURL, type MerchantClient } from "./merchant-client.js";

// Script/image requests in a cross-site iframe may have no third-party cookie.
// Only client asset files are public; HTML and every protocol route still need
// a signed launch session. The original asset handler also checks file access.
function clientAsset(req: IncomingMessage, url: URL) {
  if (req.method !== "GET" && req.method !== "HEAD") return false;
  let path: string;
  try {
    path = decodeURIComponent(url.pathname);
  } catch {
    return false;
  }
  if (/[\\\x00-\x1f%]/.test(path)) return false;
  const parts = path.toLowerCase().split("/").slice(1);
  if (
    parts.some(
      (part) =>
        !part ||
        part === "." ||
        part === ".." ||
        [
          "api",
          "game-api",
          "web-api",
          "gtt",
          "fixtures",
          "diagnostics",
          "data",
          "config",
          "api-documents",
        ].includes(part),
    )
  )
    return false;
  return /\.(?:js|css|json|png|jpe?g|webp|avif|gif|svg|ico|mp3|wav|ogg|m4a|mp4|webm|woff2?|ttf|otf|wasm|bin|atlas|skel)$/i.test(
    path,
  );
}

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
    const raw=this.games.initial(s.merchant_id,s.player_id,s.game_id);
    const release=this.games.remote?.select(s.merchant_id,s.player_id,s.game_id,raw);
    return {
      mirror,
      snapshot: {
        expires_at: s.expires_at,
        state,
        raw_state: this.games.initial(s.merchant_id, s.player_id, s.game_id),
        ...(release?{engine:{config:release.descriptor.config,version:release.descriptor.version,ruleset_id:release.descriptor.ruleset_id}}:{}),
        wallet: {
          player_id: mirror.player_id,
          balance_minor: state.balance_minor,
          currency: m.currency,
          minor_unit: this.games.descriptor(s.game_id).minor_unit,
        },
      },
    };
  }
  async worker(code: string, frontend?:any) {
    const key=code+(frontend?":"+frontend.id:"");
    let entry = this.workers.get(key);
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
              code + (frontend?"-"+frontend.id:"") + ".sqlite3",
            ),
          },
          ...(frontend?{env:{...process.env,GTT_RESOURCE_ROOT:this.games.frontends.resources(frontend)}}:{}),
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
        this.workers.delete(key);
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
    this.workers.set(key, entry);
    return entry.ready;
  }
  host(req: IncomingMessage) {
    const host = String(req.headers.host ?? "");
    const frontend=this.games.frontends.host(host);
    if(frontend)return frontend.code;
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
        (req.headers.authorization
          ? String(req.headers.authorization).replace(/^Bearer /, "")
          : String(req.headers["x-local-game-session"] || cookie || ""));
    this.games.session(token, code);
    return token;
  }
  guard(req: IncomingMessage, code: string) {
    const frontend=this.games.frontends.host(String(req.headers.host??""));
    check(!frontend||frontend.code===code,"HOST_REJECTED");
    const origin = frontend?.origin??this.games.origin(code);
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
    const frontend=this.games.frontends.host(String(req.headers.host??""));
    if(frontend&&["GET","HEAD"].includes(req.method??"")&&this.games.frontends.asset(frontend,req,res))return;
    const url = new URL(req.url!, "http://local"),
      isAsset = clientAsset(req, url),
      token = isAsset ? "" : this.token(req, code);
    if(frontend) {
      check(!isAsset,"NOT_FOUND","版本清单中不存在该素材",404);
      this.games.frontends.session(token,frontend);
      if(["GET","HEAD"].includes(req.method??""))this.games.frontends.verifyPrivate(frontend);
    }
    const session = isAsset ? null : this.games.session(token, code);
    const client: MerchantClient | undefined = session ? {
      code, token, operator:session.merchant_id, player_id:session.player_id,
      currency:this.games.p.control.merchant(session.merchant_id).currency,
    } : undefined;
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
    const worker = await this.worker(code,frontend),
      id = ++this.sequence,
      bytes = await body(req, 131072),
      reply: any = await new Promise((resolve, reject) => {
        worker.pending.set(id, { resolve, reject });
        worker.instance.postMessage({
          id,
          request: {
            token,
            merchant: client,
            url: req.url,
            method: req.method,
            headers: {
              ...req.headers,
              authorization: "Bearer " + token,
              "x-local-game-session": token,
            },
            port: req.socket.localPort,
            body: bytes,
          },
        });
      });
    let data = Buffer.from(reply.body);
    const type = String(Object.entries(reply.headers).find(([key]) => key.toLowerCase() === "content-type")?.[1] ?? "");
    if (client) {
      const origin = frontend?.origin??this.games.origin(code);
      for (const key of Object.keys(reply.headers)) {
        if (key.toLowerCase() === "location")
          reply.headers[key] = merchantClientURL(String(reply.headers[key]), origin, client);
      }
      if (type.includes("text/html")) data = Buffer.from(merchantClientHTML(data.toString(), req.url!, origin, client));
      else if (type.includes("application/json") && data.length > 0) data = Buffer.from(JSON.stringify(merchantClientJSON(JSON.parse(data.toString()), client)));
      else if (type.includes("text/plain")) data = Buffer.from(merchantClientText(data.toString(), client));
    }
    for (const key of Object.keys(reply.headers)) if (key.toLowerCase() === "content-length") delete reply.headers[key];
    const
      cookies = reply.headers["Set-Cookie"] ?? reply.headers["set-cookie"];
    delete reply.headers["Set-Cookie"];
    delete reply.headers["set-cookie"];
    res.writeHead(reply.status, {
      ...reply.headers,
      "Content-Length": data.length,
      "Cache-Control": "no-store",
      "Referrer-Policy": "no-referrer",
      ...(!isAsset
        ? {
            "Set-Cookie": [
              `gtt-session=${token}; Path=/; HttpOnly; SameSite=Lax${this.config.environment === "production" ? "; Secure" : ""}`,
              ...(cookies ? [cookies] : []),
            ],
          }
        : {}),
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
    const frontend=this.games.frontends.host(String(req.headers.host??""));
    if(frontend)this.games.frontends.session(token,frontend);
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
      frontend?.origin??this.games.origin(code),
    );
  }
  async close() {
    await Promise.all(
      [...this.workers.values()].map((v) => v.instance.terminate()),
    );
    this.workers.clear();
  }
}
