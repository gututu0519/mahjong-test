import { isIP } from "node:net";
import { check, encode, hex, now, ServiceError } from "../../other/shared/core.js";
import { fetchBounded } from "../../other/shared/http.js";
import { GAME_CODES, gameNumber, gameUnit } from "./catalog.js";
import type { Provider } from "./provider.js";

export type GameRelease = {
  id: string;
  code: string;
  release: string;
  origin: string;
  secret: string;
  descriptor: any;
  status: string;
};

// Registry lives in the shared control DB; round and retry bindings live with
// settlement state. Gateway and admin processes observe changes without restart.
export class GameServices {
  constructor(
    public p: Provider,
    public config: any = {},
  ) {
    p.control.db.exec(`
      CREATE TABLE IF NOT EXISTS game_service_releases (
        id TEXT PRIMARY KEY,code TEXT NOT NULL,release TEXT NOT NULL,origin TEXT NOT NULL,
        secret TEXT NOT NULL,descriptor_json TEXT NOT NULL,status TEXT NOT NULL,created_at INTEGER NOT NULL,
        UNIQUE(code,release));
      CREATE TABLE IF NOT EXISTS game_service_routes (
        code TEXT PRIMARY KEY,release_id TEXT NOT NULL,revision INTEGER NOT NULL,updated_at INTEGER NOT NULL);`);
    p.db.exec(`
      CREATE TABLE IF NOT EXISTS game_release_rounds (
        id TEXT PRIMARY KEY,merchant_id TEXT NOT NULL,player_id TEXT NOT NULL,game_id TEXT NOT NULL,
        release_id TEXT NOT NULL,round_id TEXT,closed INTEGER NOT NULL DEFAULT 0,created_at INTEGER NOT NULL);
      CREATE UNIQUE INDEX IF NOT EXISTS game_release_active_round ON game_release_rounds(merchant_id,player_id,game_id) WHERE closed=0;
      CREATE TABLE IF NOT EXISTS game_release_calculations (calculation_id TEXT PRIMARY KEY,release_id TEXT NOT NULL,round_key TEXT NOT NULL);`);
  }
  validateOrigin(value: string) {
    let u: URL;
    try {
      u = new URL(value);
    } catch {
      throw new ServiceError(
        "GAME_SERVICE_URL_INVALID",
        "请输入有效的内部服务地址",
      );
    }
    const host = u.hostname.replace(/^\[|\]$/g, "");
    const internal =
      host === "localhost" ||
      host === "::1" ||
      (isIP(host) === 4 && /^127\./.test(host)) ||
      (isIP(host) === 4 &&
        (/^10\./.test(host) ||
          /^192\.168\./.test(host) ||
          /^172\.(1[6-9]|2\d|3[01])\./.test(host))) ||
      (this.config.game_service_hosts ?? []).includes(host);
    check(
      internal &&
        ["http:", "https:"].includes(u.protocol) &&
        u.pathname === "/" &&
        !u.username &&
        !u.password &&
        !u.search &&
        !u.hash,
      "GAME_SERVICE_URL_INVALID",
      "使用回环或私网地址；其他内部主机须加入 game_service_hosts",
    );
    return u.origin;
  }
  row(row: any): GameRelease {
    check(row, "GAME_SERVICE_REQUIRED", "请在平台后台注册对应游戏版本", 503);
    const { descriptor_json, ...rest } = row;
    return { ...rest, descriptor: JSON.parse(descriptor_json) };
  }
  release(id: string) {
    return this.row(
      this.p.control.get("SELECT * FROM game_service_releases WHERE id=?", id),
    );
  }
  active(code: string) {
    const route = this.p.control.get(
      "SELECT * FROM game_service_routes WHERE code=?",
      code,
    );
    check(route, "GAME_SERVICE_REQUIRED", "游戏尚未配置运行版本", 503);
    return this.release(route.release_id);
  }
  async request(release: GameRelease, action: string, value: any = {}) {
    try {
      const response = await fetchBounded(
        release.origin + "/v1/" + action,
        {
          method: "POST",
          headers: {
            "content-type": "application/json",
            authorization: "Bearer " + release.secret,
          },
          body: encode(
            JSON.parse(
              JSON.stringify({
                ...value,
                expected_release: release.release,
                ...(release.descriptor
                  ? { expected_ruleset: release.descriptor.ruleset_id }
                  : {}),
              }),
            ),
          ),
          timeout: ["prebet-plan", "rtp-plan"].includes(action)
            ? 120000
            : 10000,
        },
        16 * 1024 * 1024,
      );
      const reply = JSON.parse(response.body);
      if (reply.error)
        throw new ServiceError(
          reply.error.code,
          reply.error.message,
          response.status,
        );
      check(
        response.status === 200 && reply.data != null,
        "GAME_UNAVAILABLE",
        "游戏计算服务暂不可用，请重试原操作",
        503,
      );
      check(
        reply.service?.game_id === release.code &&
          (!release.release || reply.service?.release === release.release) &&
          (release.release || action!=="describe" || reply.service?.release===reply.data?.release) &&
          (!release.descriptor ||
            reply.service.ruleset_id === release.descriptor.ruleset_id),
        "GAME_RELEASE_CHANGED",
        "服务响应与绑定版本不匹配",
        409,
      );
      return reply.data;
    } catch (error) {
      if (error instanceof ServiceError) throw error;
      throw new ServiceError(
        "GAME_UNAVAILABLE",
        "游戏计算服务暂不可用，请重试原操作",
        503,
      );
    }
  }
  async register(actor: string, q: any) {
    check(
      GAME_CODES.includes(q.code) &&
        (q.release == null || (typeof q.release === "string" &&
        /^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$/.test(q.release))),
      "INVALID_ARGUMENT",
    );
    check(
      typeof q.secret === "string" &&
        q.secret.length >= 32 &&
        q.secret.length <= 512,
      "INTERNAL_KEY_INVALID",
    );
    const origin = this.validateOrigin(q.origin);
    const temporary = {
      id: "",
      code: q.code,
      release: q.release??"",
      origin,
      secret: q.secret,
      status: "ready",
      descriptor: null,
    };
    const descriptor = await this.request(temporary, "describe");
    check(
      descriptor.game_id === q.code &&
        (!q.release || descriptor.release === q.release) &&
        typeof descriptor.release === "string" && /^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$/.test(descriptor.release) &&
        descriptor.protocol_version === 1 &&
        descriptor.minor_unit === gameUnit(q.code) &&
        typeof descriptor.ruleset_id === "string" &&
        typeof descriptor.version === "string" &&
        typeof descriptor.title === "string" &&
        descriptor.config &&
        typeof descriptor.config === "object" &&
        !Array.isArray(descriptor.config) &&
        typeof descriptor.client_contract === "string" &&
        descriptor.client_contract.length > 0 &&
        descriptor.client_contract.length <= 128 &&
        typeof descriptor.state_contract === "string" &&
        descriptor.state_contract.length > 0 &&
        descriptor.state_contract.length <= 128,
      "GAME_SERVICE_MISMATCH",
      "服务标识、版本或接口契约不匹配",
    );
    q={...q,release:descriptor.release};
    return this.p.control.tx(() => {
      check(
        !this.p.control.get(
          "SELECT 1 FROM game_service_releases WHERE code=? AND release=?",
          q.code,
          q.release,
        ),
        "GAME_RELEASE_EXISTS",
        "该构建已登记，请部署新的构建后再登记",
        409,
      );
      const id = "gs-" + hex();
      this.p.control.run(
        "INSERT INTO game_service_releases VALUES(?,?,?,?,?,?,?,?)",
        id,
        q.code,
        q.release,
        origin,
        q.secret,
        encode(descriptor),
        "ready",
        now(),
      );
      this.p.control.audit(actor, "game-service.register", id, "success", {
        game_id: gameNumber(q.code),
        release: q.release,
      });
      return { id, code: q.code, release: q.release };
    });
  }
  async activate(actor: string, q: any) {
    check(Number.isInteger(q.revision) && q.revision >= 0, "INVALID_ARGUMENT");
    const selected = this.release(q.id);
    check(selected.status === "ready", "GAME_RELEASE_RETIRED");
    const live = await this.request(selected, "describe");
    check(
      encode(live) === encode(selected.descriptor),
      "GAME_RELEASE_CHANGED",
      "已注册版本发生变化，请注册新版本",
      409,
    );
    return this.p.control.tx(() => {
      check(
        this.release(selected.id).status === "ready",
        "GAME_RELEASE_RETIRED",
      );
      const old = this.p.control.get(
        "SELECT * FROM game_service_routes WHERE code=?",
        selected.code,
      );
      check(
        (old?.revision ?? 0) === q.revision,
        "VERSION_CONFLICT",
        "运行版本已变化，请刷新后重试",
        409,
      );
      if (old) {
        const prior = this.release(old.release_id);
        check(
          prior.descriptor.client_contract === live.client_contract &&
            prior.descriptor.state_contract === live.state_contract,
          "GAME_CONTRACT_MISMATCH",
          "前端或状态契约不兼容，不能执行无感切换",
          409,
        );
      }
      this.p.control.run(
        "INSERT INTO game_service_routes VALUES(?,?,?,?) ON CONFLICT(code) DO UPDATE SET release_id=excluded.release_id,revision=excluded.revision,updated_at=excluded.updated_at",
        selected.code,
        selected.id,
        q.revision + 1,
        now(),
      );
      this.p.control.audit(
        actor,
        "game-service.activate",
        selected.id,
        "success",
        {
          game_id: gameNumber(selected.code),
          previous: old?.release_id ?? null,
          revision: q.revision + 1,
        },
      );
      return {
        code: selected.code,
        release_id: selected.id,
        revision: q.revision + 1,
      };
    });
  }
  retire(actor: string, q: any) {
    const release = this.release(q.id);
    return this.p.control.tx(() => {
      check(
        !this.p.control.get(
          "SELECT 1 FROM game_service_routes WHERE release_id=?",
          release.id,
        ),
        "GAME_RELEASE_ACTIVE",
        "先切换当前运行版本",
        409,
      );
      this.p.control.run(
        "UPDATE game_service_releases SET status='retired' WHERE id=?",
        release.id,
      );
      this.p.control.audit(actor, "game-service.retire", release.id);
      return { id: release.id, status: "retired" };
    });
  }
  list() {
    return GAME_CODES.map((code) => {
      const route = this.p.control.get(
        "SELECT * FROM game_service_routes WHERE code=?",
        code,
      );
      const releases = this.p.control
        .all(
          "SELECT * FROM game_service_releases WHERE code=? ORDER BY created_at,id",
          code,
        )
        .map((row) => {
          const { secret, descriptor, ...publicRelease } = this.row(row);
          return {
            ...publicRelease,
            engine_version: descriptor.version,
            ruleset_id: descriptor.ruleset_id,
            client_contract: descriptor.client_contract,
            state_contract: descriptor.state_contract,
            open_rounds: this.p.get(
              "SELECT COUNT(*) AS n FROM game_release_rounds WHERE release_id=? AND closed=0",
              row.id,
            ).n,
            pending_calculations: this.p.get(
              "SELECT COUNT(*) AS n FROM game_release_calculations b JOIN node_calculations c ON c.id=b.calculation_id WHERE b.release_id=? AND c.status='pending'",
              row.id,
            ).n,
          };
        });
      return {
        code,
        game_id: gameNumber(code),
        active_id: route?.release_id ?? null,
        revision: route?.revision ?? 0,
        releases,
      };
    });
  }
  select(
    mid: string,
    pid: string,
    code: string,
    state: any,
    requestKey?: string,
  ) {
    if (requestKey) {
      const calc = this.p.get(
        "SELECT b.release_id FROM game_release_calculations b JOIN node_calculations c ON c.id=b.calculation_id WHERE c.merchant_id=? AND c.player_id=? AND c.game_id=? AND c.request_key=?",
        mid,
        pid,
        code,
        requestKey,
      );
      if (calc) return this.release(calc.release_id);
      const legacy = this.p.get(
        "SELECT state_json FROM node_calculations WHERE merchant_id=? AND player_id=? AND game_id=? AND request_key=? AND status='pending'",
        mid,
        pid,
        code,
        requestKey,
      );
      if (legacy) {
        const ruleset = JSON.parse(legacy.state_json).ruleset_id;
        const original = this.p.control.get(
          "SELECT * FROM game_service_releases WHERE code=? AND json_extract(descriptor_json,'$.ruleset_id')=? ORDER BY created_at LIMIT 1",
          code,
          ruleset ?? "",
        );
        check(
          original,
          "GAME_VERSION_REQUIRED",
          "旧待计算操作需要先注册其原游戏版本",
          503,
        );
        return this.row(original);
      }
    }
    const round = this.p.get(
      "SELECT release_id FROM game_release_rounds WHERE merchant_id=? AND player_id=? AND game_id=? AND closed=0",
      mid,
      pid,
      code,
    );
    if (round) return this.release(round.release_id);
    if (state.phase !== "ready") {
      const old = this.p.control.get(
        "SELECT * FROM game_service_releases WHERE code=? AND json_extract(descriptor_json,'$.ruleset_id')=? ORDER BY created_at LIMIT 1",
        code,
        state.ruleset_id ?? "",
      );
      check(
        old,
        "GAME_VERSION_REQUIRED",
        "请先注册当前未结束回合对应的旧版本",
        503,
      );
      return this.row(old);
    }
    return this.active(code);
  }
  bind(calc: any, release: GameRelease) {
    const old = this.p.get(
      "SELECT * FROM game_release_calculations WHERE calculation_id=?",
      calc.id,
    );
    if (old) {
      check(old.release_id === release.id, "GAME_VERSION_CONFLICT");
      return;
    }
    const state = JSON.parse(calc.state_json);
    let round = this.p.get(
      "SELECT * FROM game_release_rounds WHERE merchant_id=? AND player_id=? AND game_id=? AND closed=0",
      calc.merchant_id,
      calc.player_id,
      calc.game_id,
    );
    if (!round) {
      const id = calc.engine_sid;
      this.p.run(
        "INSERT INTO game_release_rounds VALUES(?,?,?,?,?,?,0,?)",
        id,
        calc.merchant_id,
        calc.player_id,
        calc.game_id,
        release.id,
        state.phase === "ready"
          ? null
          : (state.round_id ?? state.pending?.round_id),
        now(),
      );
      round = { id, release_id: release.id };
    }
    check(round.release_id === release.id, "GAME_VERSION_CONFLICT");
    this.p.run(
      "INSERT INTO game_release_calculations VALUES(?,?,?)",
      calc.id,
      release.id,
      round.id,
    );
  }
  settle(calculation: string, outcome: any) {
    const binding = this.p.get(
      "SELECT * FROM game_release_calculations WHERE calculation_id=?",
      calculation,
    );
    if (binding)
      this.p.run(
        "UPDATE game_release_rounds SET round_id=?,closed=? WHERE id=?",
        outcome.event.round_id,
        outcome.state.phase === "ready" ? 1 : 0,
        binding.round_key,
      );
  }
  reject(calculation: string) {
    const row = this.p.get(
      "SELECT b.round_key,c.state_json FROM game_release_calculations b JOIN node_calculations c ON c.id=b.calculation_id WHERE calculation_id=?",
      calculation,
    );
    if (row && JSON.parse(row.state_json).phase === "ready")
      this.p.run(
        "UPDATE game_release_rounds SET closed=1 WHERE id=?",
        row.round_key,
      );
  }
}
