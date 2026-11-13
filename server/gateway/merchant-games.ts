import { roundMetadata, walletRound } from "./rounds.js";
import { decision } from "./prebet-decision.js";
import { merchantLaunchQuery } from "./merchant-client.js";
import { RoundChoice } from "../shared/prebet.js";
import {
  extremes,
  selectRound,
  modeKey,
  ROUND_MODEL_VERSION,
} from "../games/round-model.js";
import { readFileSync } from "node:fs";
import { setImmediate as nextTurn } from "node:timers/promises";
import * as py from "../compat/runtime.js";
import { definitions } from "../migrated/py/games/catalog.js";
import { method } from "../services/local.js";
import {
  GAME_CODES,
  gameCode,
  gameNumber,
  gameUnit,
  units,
  displayUnits,
  multiplier,
} from "./catalog.js";
import {
  check,
  encode,
  hex,
  sha,
  now,
  token,
  identifier,
  amount,
  ServiceError,
} from "../shared/core.js";
import type { Provider } from "./provider.js";
import { GameServices, type GameRelease } from "./game-services.js";
import {FrontendVersions} from "./frontend-versions.js";

export class MerchantGames {
  engines = new Map<string, any>();
  models = new Map<string, any>();
  remote?: GameServices;
  frontends:FrontendVersions;
  constructor(
    public p: Provider,
    public config: any,
  ) {
    this.frontends=new FrontendVersions(p,config);
    p.db.exec(
      "CREATE TABLE IF NOT EXISTS merchant_game_counter(id INTEGER PRIMARY KEY CHECK(id=1),value INTEGER NOT NULL); INSERT OR IGNORE INTO merchant_game_counter VALUES(1,0);",
    );
    p.column("node_calculations", "engine_sid", "TEXT");
    p.column("node_calculations","runtime_payload_json","TEXT");
    p.db.exec(
      "CREATE TABLE IF NOT EXISTS round_model_bindings(id TEXT PRIMARY KEY,merchant_id TEXT NOT NULL,player_id TEXT NOT NULL,game_id TEXT NOT NULL,initial_sid TEXT NOT NULL,round_id TEXT,context_json TEXT NOT NULL,plan_json TEXT,created_at INTEGER NOT NULL); CREATE INDEX IF NOT EXISTS round_model_round ON round_model_bindings(merchant_id,player_id,game_id,round_id);",
    );
    if (config.game_services_mode === "remote") {
      this.remote = new GameServices(p,config);
      for (const code of GAME_CODES) this.engines.set(code,null);
      return;
    }
    for (const code of GAME_CODES) {
      const cfg = py.jsonLoads(
        readFileSync(py.sourcePath(`services/${code}/config/${code}.json`)),
      );
      this.engines.set(code, py.call(definitions[code].factory, [cfg]));
    }
  }
  game(code: string) {
    if (this.remote) return this.handle(this.remote.active(code));
    const g = this.engines.get(code);
    check(g, "GAME_ID_INVALID");
    return g;
  }
  call(code: string, name: string, ...args: any[]) {
    if (this.remote) return this.invoke(this.game(code),name,...args);
    return py.plain(method(this.game(code), name, ...args.map(py.from)));
  }
  handle(release: GameRelease, configuration?: any, descriptor = release.descriptor) {
    return {remote:release,configuration,version:descriptor.version,ruleset_id:descriptor.ruleset_id,config:py.from(descriptor.config)};
  }
  async invoke(engine: any, name: string, ...args: any[]) {
    if (engine.remote) return this.remote!.request(engine.remote,"invoke",{method:name,args,configuration:engine.configuration});
    return py.plain(method(engine,name,...args.map(py.from)));
  }
  descriptor(code: string) {
    if (this.remote) {
      const row=this.p.control.get("SELECT r.descriptor_json FROM game_service_routes a JOIN game_service_releases r ON r.id=a.release_id WHERE a.code=?",code);
      const d=row?JSON.parse(row.descriptor_json):null;
      return {id:gameNumber(code),code,title:d?.title??code,engine_version:d?.version??null,ruleset_id:d?.ruleset_id??null,minor_unit:gameUnit(code),target_rtp:null,rtp_status:"not_calibrated"};
    }
    const g = this.game(code);
    return {
      id: gameNumber(code),
      code,
      title: py.attr(g, "title"),
      engine_version: py.attr(g, "version"),
      ruleset_id: py.attr(g, "ruleset_id"),
      minor_unit: gameUnit(code),
      target_rtp: null,
      rtp_status: "not_calibrated",
    };
  }
  merchant(mid: string, code: string, disabled = false) {
    const m = this.p.merchant(mid, false, disabled);
    check(
      m.games.includes(code) || disabled,
      "GAME_FORBIDDEN",
      "Game not authorized",
      403,
    );
    check(
      m.minor_unit >= gameUnit(code),
      "WALLET_PRECISION_REQUIRED",
      "This game requires minor_unit=10000. Create a merchant wallet with matching precision.",
    );
    return m;
  }
  generic(s: any) {
    return (
      !!this.remote || s.game_id !== "buffalo-win" ||
      this.p.control.merchant(s.merchant_id, true).minor_unit !== 100
    );
  }
  session(tok: string, code?: string) {
    const s = this.p.session(tok);
    if (code)
      check(
        s.game_id === code,
        "SESSION_GAME_MISMATCH",
        "Session belongs to another game",
        403,
      );
    this.merchant(s.merchant_id, s.game_id);
    return s;
  }
  origin(code: string) {
    const supplied = this.config.game_origins?.[code];
    if (supplied) return new URL(supplied).origin;
    const u = new URL(this.p.playOrigin);
    check(
      this.config.environment !== "production",
      "GAME_ORIGIN_REQUIRED",
      "Configure a verified game origin for each game.",
    );
    return `http://g${gameNumber(code)}.localhost:${u.port}`;
  }
  initial(mid: string, pid: string, code: string) {
    let row = this.p.get(
      "SELECT state_json FROM merchant_states WHERE merchant_id=? AND player_id=? AND game_id=?",
      mid,
      pid,
      code,
    );
    if (!row) {
      check(!this.remote,"GAME_STATE_REQUIRED","请重新打开游戏会话",409);
      const value = this.call(code, "initial_state", hex(32));
      this.p.run(
        "INSERT OR IGNORE INTO merchant_states VALUES(?,?,?,?)",
        mid,
        pid,
        code,
        encode(value),
      );
      row = this.p.get(
        "SELECT state_json FROM merchant_states WHERE merchant_id=? AND player_id=? AND game_id=?",
        mid,
        pid,
        code,
      );
    }
    return JSON.parse(row.state_json);
  }
  async ensureInitial(mid: string, pid: string, code: string) {
    if (!this.remote) return this.initial(mid,pid,code);
    let row=this.p.get("SELECT state_json FROM merchant_states WHERE merchant_id=? AND player_id=? AND game_id=?",mid,pid,code);
    if (!row) {
      const release=this.remote.active(code);
      const state=await this.remote.request(release,"invoke",{method:"initial_state",args:[hex(32)]});
      this.p.run("INSERT OR IGNORE INTO merchant_states VALUES(?,?,?,?)",mid,pid,code,encode(state));
    }
    return this.initial(mid,pid,code);
  }
  async launch(mid: string, q: any) {
    const code = gameCode(q.game_id ?? 1),
      m = this.merchant(mid, code),
      pid = identifier(q.player_id);
    this.p.assertLaunchReady(mid, pid, code);
    check(["en", "zh"].includes(q.language ?? "en"), "LANGUAGE_INVALID");
    if (q.external_username !== undefined) {
      const name = q.external_username;
      check(
        typeof name === "string" &&
          name.trim() === name &&
          name.length > 0 &&
          name.length <= 128 &&
          !/[\x00-\x1f]/.test(name),
        "PREBET_PLAYER_REQUIRED",
      );
      check(
        ["NORMAL", "SURE_WIN"].includes(q.prebet_type ?? "NORMAL"),
        "PREBET_TYPE_INVALID",
      );
      this.p.tx(() => {
        const old = this.p.get(
            "SELECT * FROM merchant_players WHERE merchant_id=? AND player_id=?",
            mid,
            pid,
          ),
          other = this.p.get(
            "SELECT * FROM merchant_players WHERE merchant_id=? AND external_username=?",
            mid,
            name,
          );
        check(
          (!old || old.external_username === name) &&
            (!other || other.player_id === pid),
          "PREBET_PLAYER_CONFLICT",
        );
        this.p.run(
          "INSERT OR IGNORE INTO merchant_players VALUES(?,?,?,?)",
          mid,
          pid,
          name,
          q.prebet_type ?? "NORMAL",
        );
        this.p.run(
          "UPDATE merchant_players SET prebet_type=? WHERE merchant_id=? AND player_id=?",
          q.prebet_type ?? "NORMAL",
          mid,
          pid,
        );
      });
    } else check(q.prebet_type === undefined, "PREBET_PLAYER_REQUIRED");
    check(
      !m.pre_payout.enabled ||
        this.p.get(
          "SELECT 1 FROM merchant_players WHERE merchant_id=? AND player_id=?",
          mid,
          pid,
        ),
      "PREBET_PLAYER_REQUIRED",
    );
    const w = await this.p.walletClient.call(mid, "balance", {
        player_id: pid,
        currency: m.currency,
        minor_unit: m.minor_unit,
      }),
      tk = token(),
      expiry = now() + 86400;
    await this.ensureInitial(mid, pid, code);
    this.p.run(
      "INSERT INTO merchant_sessions VALUES(?,?,?,?,?)",
      sha(tk),
      mid,
      pid,
      code,
      expiry,
    );
    const frontend=this.frontends.bind(sha(tk),code,expiry);
    return {
      game_id: gameNumber(code),
      launch_url:
        (frontend?.origin??this.origin(code)) +
        "/?" +
        merchantLaunchQuery(code, tk, q.language ?? "en", mid),
      expires_at: expiry,
      balance_minor: w.balance_minor,
      currency: w.currency,
      minor_unit: m.minor_unit,
    };
  }
  async wallet(tok: string, code?: string) {
    const s = this.session(tok, code),
      m = this.merchant(s.merchant_id, s.game_id),
      w = await this.p.walletClient.call(m.id, "balance", {
        player_id: s.player_id,
        currency: m.currency,
        minor_unit: m.minor_unit,
      });
    return {
      ...w,
      player_id: sha(m.id + ":" + s.player_id),
      balance_minor: displayUnits(
        w.balance_minor,
        m.minor_unit,
        gameUnit(s.game_id),
      ),
      minor_unit: gameUnit(s.game_id),
    };
  }
  async state(tok: string, code?: string) {
    const s = this.session(tok, code),
      pending = this.p.get(
        "SELECT id FROM game_operations WHERE merchant_id=? AND player_id=? AND game_id=? AND status IN ('prepared','debited')",
        s.merchant_id,
        s.player_id,
        s.game_id,
      );
    if (pending) await this.retry(s.merchant_id, pending.id);
    const raw = await this.ensureInitial(s.merchant_id, s.player_id, s.game_id),
      wallet = await this.wallet(tok);
    const engine=this.remote?this.handle(this.remote.select(s.merchant_id,s.player_id,s.game_id,raw)):this.game(s.game_id);
    return {
      game_id: s.game_id,
      engine_version: py.attr(engine, "version"),
      ruleset_id: py.attr(engine, "ruleset_id"),
      state: await this.invoke(engine,"public_state",raw),
      ...(s.game_id === "buffalo-win"
        ? { rtp: this.p.rtp.context(s.merchant_id, s.player_id, raw) }
        : {}),
      balance_minor: wallet.balance_minor,
    };
  }
  history(tok: string, limit = 20) {
    const s = this.session(tok);
    check(
      Number.isInteger(limit) && limit >= 1 && limit <= 100,
      "LIMIT_INVALID",
    );
    return this.p
      .all(
        "SELECT response_json FROM game_operations WHERE merchant_id=? AND player_id=? AND game_id=? AND status='settled' ORDER BY seq DESC LIMIT ?",
        s.merchant_id,
        s.player_id,
        s.game_id,
        limit,
      )
      .map((r) => JSON.parse(r.response_json));
  }
  mirror(tok: string, after = 0) {
    const s = this.session(tok);
    return {
      player_id: sha(s.merchant_id + ":" + s.player_id),
      expires_at: s.expires_at,
      operations: this.p.all(
        "SELECT seq,id,request_key,request_json,response_json,candidate_json,created_at FROM game_operations WHERE merchant_id=? AND player_id=? AND game_id=? AND status='settled' AND seq>? ORDER BY seq",
        s.merchant_id,
        s.player_id,
        s.game_id,
        after,
      ),
    };
  }
  async configured(calc: any, selected?: GameRelease) {
    if (this.remote) {
      const stored=this.p.get("SELECT release_id FROM game_release_calculations WHERE calculation_id=?",calc.id??"");
      const release=selected??(stored?this.remote.release(stored.release_id):this.remote.select(calc.merchant_id,calc.player_id,calc.game_id,JSON.parse(calc.state_json)));
      if (calc.game_id !== "buffalo-win") return {engine:this.handle(release),binding:null};
      const binding=this.p.rtp.bind(calc.merchant_id,calc.player_id,JSON.parse(calc.state_json),JSON.parse(calc.bet_json));
      const model=JSON.parse(this.p.get("SELECT report_json FROM rtp_models WHERE id=?",binding.model_id).report_json);
      if ((model.legacy&&model.ruleset_id!==release.descriptor.ruleset_id)||(!model.legacy&&model.engine_version!==release.descriptor.version)) {
        const id="legacy:"+release.descriptor.ruleset_id;
        this.p.tx(()=>{
          this.p.run("INSERT OR IGNORE INTO rtp_models VALUES(?,?,?,?,?,?)",id,null,release.descriptor.ruleset_id,encode({legacy:true,config:release.descriptor.config,ruleset_id:release.descriptor.ruleset_id}),0,now());
          this.p.run("UPDATE rtp_bindings SET model_id=? WHERE merchant_id=? AND player_id=? AND game_id=? AND initial_sid=?",id,binding.merchant_id,binding.player_id,binding.game_id,binding.initial_sid);
        });
        binding.model_id=id;
      }
      const configuration=this.p.rtp.configuration(binding);
      const descriptor=await this.remote.request(release,"describe",{configuration});
      return {engine:this.handle(release,configuration,descriptor),binding};
    }
    if (calc.game_id !== "buffalo-win")
      return { engine: this.game(calc.game_id), binding: null };
    const binding = this.p.rtp.bind(
        calc.merchant_id,
        calc.player_id,
        JSON.parse(calc.state_json),
        JSON.parse(calc.bet_json),
      ),
      key = binding.model_id + ":" + binding.play_mode;
    let engine = this.models.get(key);
    if (!engine) {
      engine = py.call(definitions["buffalo-win"].factory, [
        py.from(this.p.rtp.configuration(binding)),
      ]);
      this.models.set(key, engine);
    }
    return { engine, binding };
  }
  async spin(tok: string, key: string, previous: string, payload: any) {
    const s = this.session(tok),
      code = s.game_id,
      mid = s.merchant_id,
      pid = s.player_id;
    check(
      typeof key === "string" &&
        key.length > 0 &&
        key.length <= 128 &&
        typeof previous === "string" &&
        previous.length <= 64,
      "REQUEST_KEY_INVALID",
    );
    return this.p.serial.run(mid + ":" + pid, async () => {
      const recorded=this.remote?this.p.get("SELECT o.*,c.runtime_payload_json FROM game_operations o LEFT JOIN node_calculations c ON c.id=o.id WHERE o.merchant_id=? AND o.player_id=? AND o.game_id=? AND o.request_key=?",mid,pid,code,key):null;
      if(recorded?.runtime_payload_json===encode(payload)) {
        check(JSON.parse(recorded.request_json).previous_sid===previous,"IDEMPOTENCY_CONFLICT","Different request",409);
        return this.retry(mid,recorded.id);
      }
      const state = await this.ensureInitial(mid,pid,code);
      const release=this.remote?.select(mid,pid,code,state,key);
      const bet = await this.invoke(release?this.handle(release):this.game(code),"normalize_bet",payload),
        canonical = encode({ previous_sid: previous, bet });
      let old = this.p.get(
        "SELECT * FROM game_operations WHERE merchant_id=? AND player_id=? AND game_id=? AND request_key=?",
        mid,
        pid,
        code,
        key,
      );
      if (old) {
        check(
          old.request_json === canonical,
          "IDEMPOTENCY_CONFLICT",
          "Different request",
          409,
        );
        return this.retry(mid, old.id);
      }
      check(state.sid === previous, "STALE_STATE", "Refresh game state", 409);
      // Validate the actual game transition before reserving an operation. This
      // candidate is discarded; committed calculation always uses its stored seed.
      const validationGame =
        code === "buffalo-win" && state.phase !== "ready"
          ? (await this.configured({
              game_id: code,
              merchant_id: mid,
              player_id: pid,
              state_json: encode(state),
              bet_json: encode(bet),
            },release)).engine
          : release?this.handle(release):this.game(code);
      await this.invoke(
        validationGame,
        "step",
        state,
        bet,
        "validation-only",
        "0",
      );
      let calc = this.p.tx(() => {
        check(
          !this.p.get(
            "SELECT 1 FROM game_operations WHERE merchant_id=? AND player_id=? AND status IN ('prepared','debited')",
            mid,
            pid,
          ),
          "OPERATION_PENDING",
          "Recover pending transaction",
          409,
        );
        const prior = this.p.get(
          "SELECT * FROM node_calculations WHERE merchant_id=? AND player_id=? AND game_id=? AND request_key=?",
          mid,
          pid,
          code,
          key,
        );
        if (prior) {
          check(prior.request_json === canonical, "IDEMPOTENCY_CONFLICT");
          return prior;
        }
        if (state.phase === "ready") this.p.assertGameAvailable(code);
        check(
          !this.p.get(
            "SELECT 1 FROM node_calculations WHERE merchant_id=? AND player_id=? AND status='pending'",
            mid,
            pid,
          ),
          "OPERATION_PENDING",
          "Retry original calculation",
          409,
        );
        this.p.run(
          "UPDATE merchant_game_counter SET value=value+4096 WHERE id=1",
        );
        const sid = String(
            this.p.get("SELECT value FROM merchant_game_counter WHERE id=1")
              .value,
          ),
          id = "mg-" + hex();
        this.p.run(
          "INSERT INTO node_calculations(id,merchant_id,player_id,game_id,request_key,request_json,state_json,bet_json,seed,status,created_at,engine_sid) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
          id,
          mid,
          pid,
          code,
          key,
          canonical,
          encode(state),
          encode(bet),
          hex(32),
          "pending",
          now(),
          sid,
        );
        const result=this.p.get("SELECT * FROM node_calculations WHERE id=?", id);
        this.p.run("UPDATE node_calculations SET runtime_payload_json=? WHERE id=?",encode(payload),id);
        if (release) this.remote!.bind(result,release);
        return result;
      });
      if (release && !this.p.get("SELECT 1 FROM game_release_calculations WHERE calculation_id=?",calc.id))
        this.p.tx(()=>this.remote!.bind(calc,release));
      let configured = await this.configured(calc);
      let seed = calc.seed;
      try {
        seed = await this.prebet(
          calc,
          payload,
          configured.engine,
          configured.binding,
        );
      } catch (e) {
        if (e instanceof ServiceError && e.code === "PREBET_3202")
          this.remote?.reject(calc.id);
        if (e instanceof ServiceError && e.code === "PREBET_3202")
          this.p.run(
            "DELETE FROM node_calculations WHERE id=? AND status='pending'",
            calc.id,
          );
        throw e;
      }
      // A failed callback may have rebound Buffalo to its RTP configuration.
      configured = await this.configured(calc);
      const probability = configured.binding
        ? null
        : await this.rtpSeed(calc, payload, seed);
      if (probability) seed = probability.seed;
      const outcome = await this.invoke(
            configured.engine,
            "step",
            JSON.parse(calc.state_json),
            bet,
            seed,
            calc.engine_sid,
          ),
        m = this.merchant(mid, code);
      amount(outcome.debit_minor);
      amount(outcome.credit_minor);
      const candidate = {
        ...outcome,
        ...roundMetadata(this.p,mid,code,outcome),
        multigame: true,
        ...(release?{service_release_id:release.id}:{}),
        engine_version: py.attr(configured.engine, "version"),
        ruleset_id: py.attr(configured.engine, "ruleset_id"),
        ...(configured.binding
          ? { rtp: this.p.rtp.bindingContext(configured.binding) }
          : probability
            ? { rtp: probability.context }
            : {}),
        minor_unit: gameUnit(code),
        wallet_minor_unit: m.minor_unit,
        wallet_debit_minor: units(
          outcome.debit_minor,
          gameUnit(code),
          m.minor_unit,
        ),
        wallet_credit_minor: units(
          outcome.credit_minor,
          gameUnit(code),
          m.minor_unit,
        ),
      };
      this.p.tx(() => {
        if (probability)
          this.p.run(
            "UPDATE round_model_bindings SET round_id=? WHERE id=?",
            outcome.event.round_id,
            calc.engine_sid,
          );
        if (configured.binding)
          this.p.run(
            "UPDATE rtp_bindings SET round_id=? WHERE merchant_id=? AND player_id=? AND game_id='buffalo-win' AND initial_sid=?",
            outcome.event.round_id,
            mid,
            pid,
            configured.binding.initial_sid,
          );
        check(this.initial(mid, pid, code).sid === previous, "STALE_STATE");
        this.p.run(
          "INSERT INTO game_operations(id,merchant_id,player_id,game_id,request_key,request_json,status,candidate_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
          calc.id,
          mid,
          pid,
          code,
          key,
          canonical,
          "prepared",
          encode(candidate),
          now(),
        );
        this.p.run(
          "UPDATE node_calculations SET status='prepared' WHERE id=?",
          calc.id,
        );
      });
      return this.retry(mid, calc.id);
    });
  }
  async rtpSeed(calc: any, payload: any, originalSeed: string) {
    const { merchant_id: mid, player_id: pid, game_id: code } = calc;
    const state = JSON.parse(calc.state_json);
    const roundId = state.round_id ?? state.pending?.round_id ?? "";
    if (
      this.p.get(
        "SELECT 1 FROM prebet_rounds WHERE merchant_id=? AND player_id=? AND game_id=? AND id=? AND error_code IS NULL AND plan_json IS NOT NULL",
        mid,
        pid,
        code,
        state.phase === "ready" ? calc.engine_sid : roundId,
      )
    )
      return {
        seed: originalSeed,
        context: { mode: "prebet", target_rtp: null },
      };
    let binding = this.p.get(
      "SELECT * FROM round_model_bindings WHERE merchant_id=? AND player_id=? AND game_id=? AND " +
        (state.phase === "ready" ? "id=?" : "round_id=?"),
      mid,
      pid,
      code,
      state.phase === "ready" ? calc.engine_sid : roundId,
    );
    if (!binding && state.phase !== "ready")
      return {
        seed: originalSeed,
        context: { mode: "legacy", target_rtp: null },
      };
    if (!binding) {
      const policy = this.p.rtp.resolve(mid, pid, gameNumber(code));
      const descriptor=this.remote?this.handle(this.remote.select(mid,pid,code,state,calc.request_key)):null;
      const report=policy.calibrated&&descriptor?JSON.parse(this.p.get("SELECT report_json FROM rtp_models WHERE id=?",policy.model_id).report_json):null;
      const calibrated=policy.calibrated&&(!descriptor||report.ruleset_id===descriptor.ruleset_id);
      const context = {
        model_id: calibrated ? policy.model_id : null,
        mode: calibrated ? "rtp" : "legacy",
        target_rtp: calibrated ? policy.target_bp / 100 : null,
        requested_target_rtp: policy.target_bp / 100,
        source: policy.scope,
        revision: policy.revision,
        status: calibrated ? "active" : "not_calibrated",
        ...(policy.calibrated&&!calibrated?{fallback_reason:"GAME_VERSION_CHANGED"}:{}),
      };
      this.p.run(
        "INSERT INTO round_model_bindings VALUES(?,?,?,?,?,?,?,NULL,?)",
        calc.engine_sid,
        mid,
        pid,
        code,
        state.sid,
        null,
        encode(context),
        now(),
      );
      binding = this.p.get(
        "SELECT * FROM round_model_bindings WHERE id=?",
        calc.engine_sid,
      );
    }
    const context = JSON.parse(binding.context_json);
    if (!context.model_id) return { seed: originalSeed, context };
    let plan = binding.plan_json ? JSON.parse(binding.plan_json) : null;
    if (!plan) {
      const report = JSON.parse(
        this.p.get(
          "SELECT report_json FROM rtp_models WHERE id=?",
          context.model_id,
        ).report_json,
      );
      const game = (await this.configured(calc)).engine,
        mode = report.modes[modeKey(JSON.parse(calc.bet_json))];
      check(
        report.algorithm === ROUND_MODEL_VERSION &&
          report.ruleset_id === py.attr(game, "ruleset_id") &&
          mode,
        "RTP_MODEL_MISMATCH",
      );
      await nextTurn();
      if (this.remote) plan=await this.remote.request(game.remote,"rtp-plan",{state,payload,seed:calc.seed,sid:calc.engine_sid,candidates:mode.candidates,upper_probability:mode.upper_probability,configuration:game.configuration});
      else {
      const pair = extremes(
        code,
        game,
        state,
        payload,
        calc.seed,
        calc.engine_sid,
        mode.candidates,
      );
      plan = selectRound(pair, mode.upper_probability, calc.seed);
      delete plan.terminal_state;
      }
      this.p.run(
        "UPDATE round_model_bindings SET plan_json=? WHERE id=?",
        encode(plan),
        binding.id,
      );
    }
    const index =
      state.phase === "ready"
        ? 0
        : this.p.get(
            "SELECT COUNT(*) AS n FROM game_operations WHERE merchant_id=? AND player_id=? AND game_id=? AND status='settled' AND json_extract(candidate_json,'$.event.round_id')=?",
            mid,
            pid,
            code,
            roundId,
          ).n;
    return { seed: sha(plan.seed + ":" + index), context };
  }
  async retry(mid: string, id: string, disabled = false) {
    return this.p.serial.run("operation:" + mid + ":" + id, async () => {
      let o = this.p.get(
        "SELECT * FROM game_operations WHERE merchant_id=? AND id=?",
        mid,
        id,
      );
      check(o, "NOT_FOUND", "Operation not found", 404);
      const m = this.merchant(mid, o.game_id, disabled);
      if (o.status === "settled") return JSON.parse(o.response_json);
      check(
        o.status !== "rejected",
        o.error_code ?? "OPERATION_REJECTED",
        "Operation rejected",
        409,
      );
      const c = JSON.parse(o.candidate_json),
        base = {
          player_id: o.player_id,
          currency: m.currency,
          minor_unit: m.minor_unit,
          round_id: c.event.round_id,
          ...walletRound(c),
        };
      let debit = o.debit_json ? JSON.parse(o.debit_json) : null,
        final: any;
      try {
        if (c.wallet_debit_minor && !debit) {
          try {
            debit = await this.p.walletClient.call(mid, "debit", {
              ...base,
              transaction_id: id + ":debit",
              amount_minor: c.wallet_debit_minor,
            });
          } catch (e) {
            if (
              e instanceof ServiceError &&
              [
                "INSUFFICIENT_BALANCE",
                "TRANSACTION_CANCELED",
                "ACCOUNT_NOT_FOUND",
                "CURRENCY_MISMATCH",
              ].includes(e.code)
            )
              this.p.tx(() => {
                this.p.run("UPDATE game_operations SET status='rejected',error_code=? WHERE id=?",e.code,id);
                this.remote?.reject(id);
                this.p.run("UPDATE prebet_rounds SET error_code=COALESCE(error_code,?) WHERE merchant_id=? AND game_id=? AND id=?",e.code,mid,o.game_id,c.event.round_id);
              });
            throw e;
          }
          this.p.run(
            "UPDATE game_operations SET status='debited',debit_json=? WHERE id=?",
            encode(debit),
            id,
          );
        }
        if (c.wallet_credit_minor) {
          const anchor = c.wallet_debit_minor
            ? id
            : this.p.get(
                "SELECT id FROM game_operations WHERE merchant_id=? AND player_id=? AND game_id=? AND json_extract(candidate_json,'$.event.round_id')=? AND json_extract(candidate_json,'$.wallet_debit_minor')>0 AND status='settled' ORDER BY seq LIMIT 1",
                mid,
                o.player_id,
                o.game_id,
                c.event.round_id,
              )?.id;
          check(anchor, "ROUND_DEBIT_REQUIRED");
          final = await this.p.walletClient.call(mid, "credit", {
            ...base,
            transaction_id: id + ":credit",
            reference_id: anchor + ":debit",
            amount_minor: c.wallet_credit_minor,
          });
        } else
          final =
            debit ?? (await this.p.walletClient.call(mid, "balance", base));
      } catch (e) {
        if (
          this.p.get("SELECT status FROM game_operations WHERE id=?", id)
            .status === "rejected"
        )
          throw e;
        throw new ServiceError(
          "WALLET_UNCERTAIN",
          "Settlement pending; retry operation " + id,
          503,
        );
      }
      const scale = (n: number) =>
          displayUnits(n, c.wallet_minor_unit, c.minor_unit),
        response = {
          ...walletRound(c),
          game_id: gameNumber(o.game_id),
          ...(c.rtp ? { rtp: c.rtp } : {}),
          sid: c.state.sid,
          round_id: c.event.round_id,
          engine_version: c.engine_version,
          ruleset_id: c.ruleset_id,
          minor_unit: c.minor_unit,
          wallet: {
            before_minor: scale(
              debit?.balance_before_minor ??
                final.balance_before_minor ??
                final.balance_minor,
            ),
            debit_minor: c.debit_minor,
            credit_minor: c.credit_minor,
            after_minor: scale(final.balance_minor),
          },
          settlement: {
            minor_unit: c.wallet_minor_unit,
            before_minor: debit?.balance_before_minor ?? final.balance_before_minor ?? final.balance_minor,
            debit_minor: c.wallet_debit_minor,
            credit_minor: c.wallet_credit_minor,
            balance_minor: final.balance_minor,
          },
          outcome: c.event,
        };
      return this.p.tx(() => {
        o = this.p.get("SELECT * FROM game_operations WHERE id=?", id);
        if (o.status === "settled") return JSON.parse(o.response_json);
        this.p.run(
          "UPDATE merchant_states SET state_json=? WHERE merchant_id=? AND player_id=? AND game_id=?",
          encode(c.state),
          mid,
          o.player_id,
          o.game_id,
        );
        this.p.run(
          "UPDATE game_operations SET status='settled',response_json=?,settled_at=? WHERE id=?",
          encode(response),
          now(),
          id,
        );
        this.p.rtp.record(
          this.p.get("SELECT * FROM game_operations WHERE id=?", id),
        );
        this.remote?.settle(id,c);
        return response;
      });
    });
  }
  async prebet(calc: any, payload: any, engine: any, binding: any) {
    const calculate = (...args: any[]) => this.invoke(engine,"step",...args);
    const { merchant_id: mid, player_id: pid, game_id: code } = calc,
      state = JSON.parse(calc.state_json),
      m = this.merchant(mid, code);
    let round = this.p.get(
      "SELECT * FROM prebet_rounds WHERE merchant_id=? AND player_id=? AND game_id=? AND id=?",
      mid,
      pid,
      code,
      state.round_id ?? "",
    );
    if (state.phase !== "ready") {
      if (!round?.plan_json) return calc.seed;
      const index = this.p.get(
        "SELECT COUNT(*) AS n FROM game_operations WHERE merchant_id=? AND player_id=? AND game_id=? AND status='settled' AND json_extract(candidate_json,'$.event.round_id')=?",
        mid,
        pid,
        code,
        state.round_id,
      ).n;
      return sha(JSON.parse(round.plan_json).seed + ":" + index);
    }
    round = this.p.get("SELECT * FROM prebet_rounds WHERE id=?", calc.engine_sid);
    if (!round && this.p.get("SELECT 1 FROM round_model_bindings WHERE id=?",calc.engine_sid)) return calc.seed;
    if (!round && !(binding ? binding.mode === "prebet" : !!m.pre_payout.url)) return calc.seed;
    const bet = JSON.parse(calc.bet_json),
      first = await calculate(state, bet, calc.seed, calc.engine_sid);
    if (!first.debit_minor) return calc.seed;
    round = this.p.get(
      "SELECT * FROM prebet_rounds WHERE id=?",
      calc.engine_sid,
    );
    if (!round) {
      const player = this.p.get(
        "SELECT * FROM merchant_players WHERE merchant_id=? AND player_id=?",
        mid,
        pid,
      );
      check(player, "PREBET_PLAYER_REQUIRED");
      const unit = m.minor_unit,
        debit = units(first.debit_minor, gameUnit(code), unit),
        purchase = !!(
          bet.buy_free ||
          bet.buy_bonus ||
          bet.buy != null ||
          bet.action === "buy" ||
          (bet.mode && bet.mode !== "base")
        );
      const q = {
        decision_id: calc.engine_sid, game_id: gameNumber(code), round_id: calc.engine_sid,
        player_name: player.external_username,
        timestamp: Date.now(),
        bet_amount: `${BigInt(debit) / BigInt(unit)}.${(BigInt(debit) % BigInt(unit)).toString().padStart(unit === 10000 ? 4 : 2, "0")}`,
        type: purchase ? "BUY_FREE_SPIN" : player.prebet_type,
      };
      this.p.run(
        "INSERT INTO prebet_rounds(id,merchant_id,player_id,game_id,initial_sid,request_json,initial_state_json,bet_json,prebet_request_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        calc.engine_sid,
        mid,
        pid,
        code,
        state.sid,
        calc.request_json,
        calc.state_json,
        calc.bet_json,
        encode(q),
        now(),
      );
      round = this.p.get(
        "SELECT * FROM prebet_rounds WHERE id=?",
        calc.engine_sid,
      );
    }
    if (round.error_code && !round.policy_json) {
      if (binding) this.p.tx(() => this.p.rtp.fallback(binding,round.error_code));
      return calc.seed;
    }
    if (!round.policy_json) {
      const url = binding ? JSON.parse(binding.settings_json).url : m.pre_payout.url;
      const result = await decision(url,mid,m.merchant_secret,round.prebet_request_json);
      if (result.error) {
        this.p.tx(() => {
          this.p.run("UPDATE prebet_rounds SET error_code=? WHERE id=? AND policy_json IS NULL",result.error,round.id);
          if (binding) this.p.rtp.fallback(binding,result.error);
          else this.p.rtp.event("system","prebet.fallback",mid,{game_id:code,round_id:round.id,error:result.error});
        });
        return calc.seed;
      }
      round.policy_json = encode(result.policy);
      this.p.run(
        "UPDATE prebet_rounds SET policy_json=? WHERE id=?",
        round.policy_json,
        round.id,
      );
    }
    if (round.plan_json) return sha(JSON.parse(round.plan_json).seed + ":0");
    if (this.remote) {
      const plan=await this.remote.request(engine.remote,"prebet-plan",{state,bet,payload,seed:calc.seed,sid:calc.engine_sid,range:JSON.parse(round.policy_json).maxWinMulti,configuration:engine.configuration});
      this.p.run("UPDATE prebet_rounds SET plan_json=? WHERE id=?",encode(plan),round.id);
      return sha(plan.seed+":0");
    }
    const range = JSON.parse(round.policy_json).maxWinMulti,
      lo = multiplier(range[0]),
      hi = multiplier(range[1]);
    const choice = new RoundChoice<{
      seed: string;
      total_credit_minor: number;
      basis_minor: number;
    }>(range, first.debit_minor, lo, hi);
    const save = (attempts: number) => {
      const selected = choice.finish(attempts);
      this.p.run(
        "UPDATE prebet_rounds SET plan_json=? WHERE id=?",
        encode(selected),
        round.id,
      );
      return sha(selected.seed + ":0");
    };
    for (let attempt = 0; attempt < 3000; attempt++) {
      if (attempt % 20 === 0) await nextTurn();
      const root = sha(calc.seed + ":plan:" + attempt);
      let current = structuredClone(state),
        total = 0,
        done = false;
      for (let i = 0; i < 4096; i++) {
        let command = { ...payload };
        if (current.phase !== "ready") {
          if (code === "tower-run-treasure-steps")
            command = {
              action: current.phase === "collect" ? "collect" : "continue",
            };
          else if (
            Object.hasOwn(py.plain(py.attr(this.game(code), "config")), "costs")
          )
            command = { action: "confirm", round_id: current.pending.round_id };
          else if (
            [
              "gates-of-olympus",
              "sweet-bonanza-pop",
              "big-bass-bonanza",
            ].includes(code)
          )
            command = {
              ...payload,
              action: current.phase === "collect" ? "collect" : "spin",
              request_index: (payload.request_index ?? 0) + i,
            };
          else delete command.buy_free;
        }
        const out = await calculate(
          current,
          this.call(code, "normalize_bet", command),
          sha(root + ":" + i),
          String(Number(calc.engine_sid) + i),
        );
        total += out.credit_minor;
        current = out.state;
        if (choice.above(total)) break;
        if (current.phase === "ready") {
          done = true;
          break;
        }
      }
      if (
        done &&
        choice.consider(
          {
            seed: root,
            total_credit_minor: total,
            basis_minor: first.debit_minor,
          },
          total,
          attempt + 1,
        )
      )
        return save(attempt + 1);
    }
    return save(3000);
  }
}
