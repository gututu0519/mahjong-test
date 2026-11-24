import { existsSync, readFileSync, realpathSync, statSync } from "node:fs";
import { basename, extname, isAbsolute, relative, resolve } from "node:path";
import * as p from "../../../../other/shared/compat/runtime.js";
import { BytesIO } from "../../../../other/shared/compat/platform.js";
import { ServiceError, check } from "../../../../other/shared/core.js";
import { GameService } from "../../../../other/shared/migrated/py/core/service.js";
import { create_registry } from "../../../../other/shared/migrated/py/games/catalog.js";
import { PlatformRoutes } from "../../../../other/shared/migrated/py/transport/http.js";
import { createAdapter } from "../adapters/cash_mania.js";
import { normalRtp } from "../engine/engine.js";

const CLIENT = p.sourcePath("clients/cash-mania");
const Base = p.modules["http.server"].SimpleHTTPRequestHandler;
const method = (object: any, name: string, ...args: any[]) => p.call(p.attr(object, name), args);
const fn = (name: string, names: string[], impl: (...args: any[]) => any) => p.fn(name, { names, kwonly: [], defaults: {}, vararg: null, kwarg: null }, impl);

// 只保留启动所需的静态选项。令牌、用户与余额均由本地会话生成。
export const authMetadata = {
  oj: { jid: 0 }, st: 1, cc: "PGC", cs: "", gm: [{ gid: 1682240, msdt: 0, medt: 0, st: 1, amsg: "" }],
  uiogc: { bb: 1, gec: 1, cbu: 0, cl: 0, mr: 0, phtr: 0, vc: 0, il: 0, rp: 0, gc: 0, ign: 0, tsn: 0, we: 0, gsc: 1, bu: 0, pwr: 0, hd: 0, igv: 0, grt: 0, ivs: 0, ir: 0, gvs: 0, hn: 1, fbrc: 1, grtp: 0, bf: 1, et: 0, np: 0, as: 1000, asc: 1, std: 0, hnp: 0, ts: 1, smpo: 0, swf: 0, sp: 0, rcf: 0, sbb: 0, hwl: 0 },
  ec: [], gcv: "2.0.0.3", sdn: "", jc: { grtp: 0, bf: 1, et: 0, np: 0, as: 1000, asc: 1, std: 0, hnp: 0, ts: 1, smpo: 0, swf: 0, sp: 0, rcf: 0, sbb: 0, hwl: 0 },
  geu: "game-api/cash-mania/", bau: "web-api/game-proxy/", lau: "game-api/lobby/", nkn: "本地玩家", ioph: "local",
  occ: { tcm: "", tlb: "", trb: "", tsc: 0, ttp: 0, rurl: "" },
};

const Handler = p.cls("CashManiaHandler", [PlatformRoutes, Base], {
  launch_game: fn("launch_game", ["self", "game_id", "language"], (self, gameId, language) => {
    method(self.server.service.registry, "get", gameId);
    check(["zh", "en"].includes(language), "LANGUAGE_INVALID");
    const session = p.plain(method(self.server.service, "create_session"));
    const query = new URLSearchParams({ mock: "1", l: "en", ops: session.token, btt: "2" });
    const config = p.plain(method(self.server.service.registry, "get", gameId).config);
    return p.from({ game_id: gameId, language, client_language: "en", launch_url: "/?" + query, mode: "generated", supported_features: config.supported_features, expires_at: session.expires_at, balance_minor: session.balance_minor, currency: "DEMO", minor_unit: 100 });
  }),
  compatibility_post: fn("compatibility_post", ["self", "path", "body"], (self, path: string, body: Buffer) => {
    const app = self.server, form = path.startsWith("/web-api/") ? new URLSearchParams(body.toString("utf8")) : new URLSearchParams();
    const token = self.headers.get("X-Local-Game-Session") || form.get("atk");
    const wallet = p.plain(method(app.service, "wallet", token));
    const json = (value: any) => method(self, "_json", 200, p.from(value));
    if (["/web-api/auth/session/v2/verifySession", "/web-api/auth/session/v2/verifyOperatorPlayerSession"].includes(path)) {
      return json({ dt: { ...p.plain(app.auth), tk: token, pid: wallet.player_id, pcd: wallet.player_id, bl: wallet.balance_minor / 100 }, err: null });
    }
    if (path === "/game-api/cash-mania/v4/GameInfo/Get") return method(self, "_response", 200, app.pg.game_info(body, token), "application/octet-stream");
    if (path === "/game-api/cash-mania/v4/Spin") return method(self, "_response", 200, app.pg.spin(body, token), "application/octet-stream");
    if (path === "/web-api/game-proxy/v2/GameWallet/Get") return json(app.pg.wallet(token));
    if (["/web-api/game-proxy/v2/BetSummary/Get", "/web-api/game-proxy/v2/BetHistory/Get"].includes(path)) return json(app.pg.history(token, form, path.includes("/BetSummary/")));
    if (path === "/web-api/game-proxy/v2/GameName/Get") return json({ dt: { "1682240": "Cash Mania" }, err: null });
    if (path === "/web-api/game-proxy/v2/GameRule/Get") {
      check(!form.has("gid") || form.get("gid") === "1682240", "GAME_NOT_FOUND", "未知游戏。", 404);
      return json(p.plain(app.game_rule));
    }
    if (path === "/web-api/game-proxy/v2/Resources/GetByResourcesTypeIds") return json({ dt: [], err: null });
    if (path === "/web-api/game-proxy/ServerManager/RefreshWallet") return json({ dt: null, err: null });
    throw new ServiceError("NOT_IMPLEMENTED", "当前本地版本未实现此接口。", 501);
  }),
  serve_assets: fn("serve_assets", ["self"], self => p.call(p.attr(Base, "do_GET"), [self])),
  send_head: fn("send_head", ["self"], self => {
    const url = new URL(self.path, "http://local");
    if (url.pathname === "/") {
      method(self, "send_response", 302); method(self, "send_header", "Location", "/1682240/index.html" + url.search); method(self, "end_headers"); return null;
    }
    const path = method(self, "translate_path", self.path), rel = relative(resolve(CLIENT), path);
    if (rel.startsWith("..") || isAbsolute(rel) || rel.split(/[\\/]/).includes("fixtures") || [".py", ".pyc", ".md", ".bat", ".har", ".txt", ".map"].includes(extname(path).toLowerCase())) { method(self, "send_error", 404); return null; }
    if (!existsSync(path) || !statSync(path).isFile()) { method(self, "send_error", 404); return null; }
    const actual = relative(realpathSync(CLIENT), realpathSync(path));
    if (actual.startsWith("..") || isAbsolute(actual)) { method(self, "send_error", 404); return null; }
    if (basename(path) === "index.js" && rel.split(/[\\/]/).includes("shared")) {
      const [bytes] = p.call(p.modules["py.adapters.pg.client_modules"].prepare_module, [readFileSync(path)]);
      method(self, "send_response", 200); method(self, "send_header", "Content-Type", "application/javascript; charset=utf-8");
      method(self, "send_header", "Content-Length", String(bytes.length)); method(self, "send_header", "Cache-Control", "no-store"); method(self, "end_headers");
      return new BytesIO(bytes);
    }
    return p.call(p.attr(Base, "send_head"), [self]);
  }),
});

export const build_server = p.native(([port = 8103, database = null, configuration = null]) => {
  const registry = p.call(create_registry, [["cash-mania"], p.from({ "cash-mania": configuration ?? p.sourcePath("services/cash-mania/config/cash-mania.json") })]);
  const service = p.call(GameService, [database ?? p.sourcePath("services/cash-mania/data/games.sqlite3"), registry]);
  method(service, "ensure_local_demo");
  const game = method(registry, "get", "cash-mania"), config = p.plain(game.config), rtp = Number((normalRtp(config) * 100).toFixed(6));
  return {
    server_address: p.tuple(["127.0.0.1", port]), server_port: port, service_id: "cash-mania", engine_mode: config.presentation_model ? "generated-normal-features" : "generated-normal-only",
    handler: p.native(([context]) => p.call(Handler, [context, CLIENT])), service, pg: createAdapter(service), auth: p.from(authMetadata),
    game_rule: p.from({ dt: { rtp: { Default: { min: rtp, max: rtp } }, grtpi: [], ows: { itare: false, tart: 0, igare: false, gart: 0 }, jws: null, model: config.probability_model, supported_features: config.supported_features,
      ...(config.presentation_model ? { presentation_model: config.presentation_model, presentation_weights: config.presentation_weights } : {}) }, err: null }),
  };
});
