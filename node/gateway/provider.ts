import { readFileSync } from "node:fs";
import {
  DB,
  check,
  encode,
  sha,
  hex,
  token,
  now,
  identifier,
  limit,
  amount,
  Serial,
  ServiceError,
  signedHeaders,
  object,
} from "../shared/core.js";
import { Control, prebetURL } from "./control.js";
import { Wallet } from "./wallet.js";
import { GameClient } from "./game-client.js";
import { fetchBounded } from "../shared/http.js";
import { RTP } from "./rtp.js";
import { MerchantGames } from "./merchant-games.js";
import { gameNumber } from "./catalog.js";
export class Provider extends DB {
  multi?: MerchantGames;
  enableGames(config: any) {
    return (this.multi ??= new MerchantGames(this, config));
  }
  walletClient: Wallet;
  serial = new Serial();
  rtp: RTP;
  description: any;
  constructor(
    path: string,
    public control: Control,
    public game: GameClient,
    schema: string,
    public playOrigin = "",
    modelFile?: string,
  ) {
    super(path);
    this.db.exec(readFileSync(schema, "utf8"));
    this.column("game_operations", "settled_at", "INTEGER");
    this.db.exec(
      `CREATE TABLE IF NOT EXISTS node_calculations(id TEXT PRIMARY KEY,merchant_id TEXT NOT NULL,player_id TEXT NOT NULL,game_id TEXT NOT NULL,request_key TEXT NOT NULL,request_json TEXT NOT NULL,state_json TEXT NOT NULL,bet_json TEXT NOT NULL,seed TEXT NOT NULL,status TEXT NOT NULL,created_at INTEGER NOT NULL,UNIQUE(merchant_id,player_id,game_id,request_key));CREATE UNIQUE INDEX IF NOT EXISTS node_pending_calculation ON node_calculations(merchant_id,player_id,game_id) WHERE status='pending';`,
    );
    this.walletClient = new Wallet(control);
    this.rtp = new RTP(this, modelFile);
    control.rtpDB = this;
  }
  async initialize() {
    this.description = await this.game.call("describe");
    this.rtp.initialize(this.description);
    return this;
  }
  merchant(id: string, game = true, disabled = false) {
    const m = this.control.merchant(id, true);
    check(
      m && (m.enabled || disabled),
      "MERCHANT_DISABLED",
      "Merchant unavailable",
      403,
    );
    check(
      !game || m.games.includes("buffalo-win"),
      "GAME_FORBIDDEN",
      "Game unavailable",
      403,
    );
    check([100, 10000].includes(m.minor_unit), "MERCHANT_CONFIG_INVALID");
    return m;
  }
  catalog(mid?: string) {
    if (this.multi) {
      const m = mid ? this.merchant(mid, false) : null;
      return [...this.multi.engines.keys()]
        .filter((code) => !m || m.games.includes(code))
        .map((code) => ({
          ...this.multi!.descriptor(code),
          ...(code === "buffalo-win"
            ? {
                target_rtp:
                  this.rtp.mode(mid ?? "").mode === "rtp"
                    ? (this.rtp.resolve(mid ?? "").target_bp ?? 0) / 100 || null
                    : null,
                rtp_status:
                  this.rtp.mode(mid ?? "").mode === "prebet"
                    ? "prebet"
                    : this.rtp.resolve(mid ?? "").target_bp != null
                      ? "active"
                      : "not_calibrated",
              }
            : m?.pre_payout.enabled
              ? { rtp_status: "prebet" }
              : {}),
          wallet_compatible:
            !m || m.minor_unit >= this.multi!.descriptor(code).minor_unit,
        }));
    }
    if (mid) this.merchant(mid, false);
    const p = this.rtp.resolve(mid ?? ""),
      mode = mid ? this.rtp.mode(mid).mode : "rtp";
    return [
      {
        id: 1,
        title: this.description.title,
        engine_version: this.description.version,
        ruleset_id: this.description.ruleset_id,
        target_rtp:
          mode === "rtp" && p.target_bp != null ? p.target_bp / 100 : null,
        rtp_status:
          mode === "prebet"
            ? "prebet"
            : p.target_bp != null
              ? "active"
              : "not_calibrated",
      },
    ].filter(
      () =>
        !mid || this.control.merchant(mid, true).games.includes("buffalo-win"),
    );
  }
  base(mid: string, pid: string) {
    const m = this.control.merchant(mid, true);
    return { player_id: pid, currency: m.currency, minor_unit: 100 };
  }
  async initial(mid: string, pid: string) {
    let r = this.get(
      "SELECT state_json FROM merchant_states WHERE merchant_id=? AND player_id=? AND game_id=?",
      mid,
      pid,
      "buffalo-win",
    );
    if (!r) {
      const initial = await this.game.call("initial");
      this.run(
        "INSERT OR IGNORE INTO merchant_states VALUES(?,?,?,?)",
        mid,
        pid,
        "buffalo-win",
        encode(initial),
      );
      r = this.get(
        "SELECT state_json FROM merchant_states WHERE merchant_id=? AND player_id=? AND game_id=?",
        mid,
        pid,
        "buffalo-win",
      );
    }
    return JSON.parse(r.state_json);
  }
  async launch(mid: string, p: any) {
    if (
      this.multi &&
      ((p.game_id ?? 1) !== 1 ||
        this.control.merchant(mid, true)?.minor_unit !== 100)
    )
      return this.multi.launch(mid, p);
    check((p.game_id ?? 1) === 1, "GAME_ID_INVALID");
    const pid = identifier(p.player_id),
      m = this.merchant(mid);
    check(["zh", "en"].includes(p.language ?? "en"), "LANGUAGE_INVALID");
    if (p.external_username !== undefined) {
      const name = p.external_username,
        kind = p.prebet_type ?? "NORMAL";
      check(
        typeof name === "string" &&
          name.length >= 1 &&
          name.length <= 128 &&
          name.trim() === name &&
          !/[\x00-\x1f]/.test(name),
        "PREBET_PLAYER_REQUIRED",
      );
      check(["NORMAL", "SURE_WIN"].includes(kind), "PREBET_TYPE_INVALID");
      this.tx(() => {
        const old = this.get(
            "SELECT * FROM merchant_players WHERE merchant_id=? AND player_id=?",
            mid,
            pid,
          ),
          other = this.get(
            "SELECT * FROM merchant_players WHERE merchant_id=? AND external_username=?",
            mid,
            name,
          );
        check(
          (!old || old.external_username === name) &&
            (!other || other.player_id === pid),
          "PREBET_PLAYER_CONFLICT",
          "Player mapping conflict",
          409,
        );
        this.run(
          "INSERT OR IGNORE INTO merchant_players VALUES(?,?,?,?)",
          mid,
          pid,
          name,
          kind,
        );
        this.run(
          "UPDATE merchant_players SET prebet_type=? WHERE merchant_id=? AND player_id=?",
          kind,
          mid,
          pid,
        );
      });
    } else check(p.prebet_type === undefined, "PREBET_PLAYER_REQUIRED");
    check(
      !m.pre_payout.enabled ||
        this.get(
          "SELECT 1 FROM merchant_players WHERE merchant_id=? AND player_id=?",
          mid,
          pid,
        ),
      "PREBET_PLAYER_REQUIRED",
    );
    const w = await this.walletClient.call(mid, "balance", this.base(mid, pid)),
      tok = token(),
      expiry = now() + 86400;
    await this.initial(mid, pid);
    this.run(
      "INSERT INTO merchant_sessions VALUES(?,?,?,?,?)",
      sha(tok),
      mid,
      pid,
      "buffalo-win",
      expiry,
    );
    return {
      game_id: 1,
      launch_url:
        this.playOrigin +
        "/?" +
        new URLSearchParams({
          mock: "1",
          l: p.language ?? "en",
          ops: tok,
          btt: "2",
        }),
      expires_at: expiry,
      balance_minor: w.balance_minor,
      currency: w.currency,
      minor_unit: 100,
    };
  }
  session(tok: string) {
    check(
      typeof tok === "string" && tok.length <= 256,
      "SESSION_INVALID",
      "Invalid session",
      401,
    );
    const s = this.get(
      "SELECT * FROM merchant_sessions WHERE token_hash=? AND expires_at>?",
      sha(tok),
      now(),
    );
    check(s, "SESSION_INVALID", "Session expired", 401);
    const m = this.merchant(s.merchant_id, false);
    check(
      m.games.includes(s.game_id),
      "GAME_FORBIDDEN",
      "Game not authorized",
      403,
    );
    return s;
  }
  async wallet(tok: string) {
    const s = this.session(tok);
    if (this.multi?.generic(s)) return this.multi.wallet(tok);
    return this.walletClient.call(
      s.merchant_id,
      "balance",
      this.base(s.merchant_id, s.player_id),
    );
  }
  async state(tok: string): Promise<any> {
    if (this.multi?.generic(this.session(tok))) return this.multi.state(tok);
    const s = this.session(tok),
      pending = this.get(
        "SELECT id FROM game_operations WHERE merchant_id=? AND player_id=? AND game_id='buffalo-win' AND status IN ('prepared','debited')",
        s.merchant_id,
        s.player_id,
      );
    if (pending) await this.retry(s.merchant_id, pending.id);
    const state = await this.initial(s.merchant_id, s.player_id),
      wallet = await this.wallet(tok);
    return {
      game_id: 1,
      engine_version: this.description.version,
      ruleset_id: state.ruleset_id,
      state,
      balance_minor: wallet.balance_minor,
      rtp: this.rtp.context(s.merchant_id, s.player_id, state),
    };
  }
  async spin(tok: string, key: string, previous: string, p: any) {
    const s = this.session(tok);
    if (this.multi?.generic(s)) return this.multi.spin(tok, key, previous, p);
    check(
      typeof key === "string" &&
        key.length >= 1 &&
        key.length <= 128 &&
        typeof previous === "string" &&
        previous.length <= 64,
      "REQUEST_KEY_INVALID",
    );
    return this.serial.run(s.merchant_id + ":" + s.player_id, async () => {
      const bet = await this.game.call("normalize", { bet: p }),
        canonical = encode({ previous_sid: previous, bet }),
        mid = s.merchant_id,
        pid = s.player_id;
      let existing = this.get(
        "SELECT * FROM game_operations WHERE merchant_id=? AND player_id=? AND game_id='buffalo-win' AND request_key=?",
        mid,
        pid,
        key,
      );
      if (existing) {
        check(
          existing.request_json === canonical,
          "IDEMPOTENCY_CONFLICT",
          "Different request parameters",
          409,
        );
        return this.retry(mid, existing.id);
      }
      const state = await this.initial(mid, pid);
      // Reject a locked bet before reserving a durable operation. Invalid input
      // must not strand a player's existing free/extension round.
      await this.game.call("validate", { state, bet });
      const calc = this.tx(() => {
        check(
          !this.get(
            "SELECT 1 FROM game_operations WHERE merchant_id=? AND player_id=? AND status IN ('prepared','debited')",
            mid,
            pid,
          ),
          "OPERATION_PENDING",
          "Recover pending transaction",
          409,
        );
        check(state.sid === previous, "STALE_STATE", "Refresh game state", 409);
        let row = this.get(
          "SELECT * FROM node_calculations WHERE merchant_id=? AND player_id=? AND game_id='buffalo-win' AND request_key=?",
          mid,
          pid,
          key,
        );
        if (row) {
          check(
            row.request_json === canonical,
            "IDEMPOTENCY_CONFLICT",
            "Different request parameters",
            409,
          );
          return row;
        }
        check(
          !this.get(
            "SELECT 1 FROM node_calculations WHERE merchant_id=? AND player_id=? AND status='pending'",
            mid,
            pid,
          ),
          "OPERATION_PENDING",
          "Retry original calculation",
          409,
        );
        row = {
          id: hex(),
          merchant_id: mid,
          player_id: pid,
          game_id: "buffalo-win",
          request_key: key,
          request_json: canonical,
          state_json: encode(state),
          bet_json: encode(bet),
          seed: hex(32),
          status: "pending",
          created_at: now(),
        };
        this.run(
          "INSERT INTO node_calculations(id,merchant_id,player_id,game_id,request_key,request_json,state_json,bet_json,seed,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
          ...Object.values(row),
        );
        return row;
      });
      const binding = this.rtp.bind(mid, pid, state, bet),
        configuration = this.rtp.configuration(binding);
      let planned: any;
      try {
        planned = await this.prebet(
          mid,
          pid,
          state,
          bet,
          canonical,
          binding,
          calc.seed,
        );
      } catch (e) {
        if (e instanceof ServiceError && e.code === "PREBET_3202") {
          this.tx(() => {
            this.run(
              "DELETE FROM node_calculations WHERE id=? AND status='pending'",
              calc.id,
            );
            this.run(
              "DELETE FROM rtp_bindings WHERE merchant_id=? AND player_id=? AND initial_sid=? AND round_id IS NULL",
              mid,
              pid,
              state.sid,
            );
          });
        }
        throw e;
      }
      const outcome =
        planned ??
        (await this.game.call(
          "step",
          { state, bet, seed: calc.seed, operation_id: calc.id },
          configuration,
        ));
      amount(outcome.debit_minor);
      amount(outcome.credit_minor);
      const op = outcome.state.sid;
      const descriptor = await this.game.call("describe", {}, configuration),
        candidate = {
          ...outcome,
          engine_version: descriptor.version,
          ruleset_id: descriptor.ruleset_id,
          rtp: this.rtp.bindingContext(binding),
        };
      this.tx(() => {
        const current = JSON.parse(
          this.get(
            "SELECT state_json FROM merchant_states WHERE merchant_id=? AND player_id=? AND game_id='buffalo-win'",
            mid,
            pid,
          ).state_json,
        );
        existing = this.get(
          "SELECT * FROM game_operations WHERE merchant_id=? AND player_id=? AND request_key=?",
          mid,
          pid,
          key,
        );
        if (existing) {
          check(existing.request_json === canonical, "IDEMPOTENCY_CONFLICT");
          return;
        }
        check(current.sid === previous, "STALE_STATE", "State changed", 409);
        this.run(
          "INSERT INTO game_operations(id,merchant_id,player_id,game_id,request_key,request_json,status,candidate_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
          op,
          mid,
          pid,
          "buffalo-win",
          key,
          canonical,
          "prepared",
          encode(candidate),
          now(),
        );
        this.run(
          "UPDATE node_calculations SET status='prepared' WHERE id=?",
          calc.id,
        );
        this.run(
          "UPDATE rtp_bindings SET round_id=? WHERE merchant_id=? AND player_id=? AND initial_sid=?",
          outcome.event.round_id,
          mid,
          pid,
          binding.initial_sid,
        );
      });
      return this.retry(mid, existing?.id ?? op);
    });
  }
  async retry(mid: string, id: string, disabled = false) {
    identifier(id);
    const generic = this.get(
      "SELECT candidate_json FROM game_operations WHERE merchant_id=? AND id=?",
      mid,
      id,
    );
    if (this.multi && generic && JSON.parse(generic.candidate_json).multigame)
      return this.multi.retry(mid, id, disabled);
    return this.serial.run("operation:" + mid + ":" + id, async () => {
      let o = this.get(
        "SELECT * FROM game_operations WHERE id=? AND merchant_id=?",
        id,
        mid,
      );
      check(o, "NOT_FOUND", "Operation not found", 404);
      this.merchant(mid, false, disabled);
      if (o.status === "settled") return JSON.parse(o.response_json);
      check(
        o.status !== "rejected",
        o.error_code ?? "OPERATION_REJECTED",
        "Operation rejected",
        409,
      );
      const c = JSON.parse(o.candidate_json),
        base = { ...this.base(mid, o.player_id), round_id: c.event.round_id };
      let debit = o.debit_json ? JSON.parse(o.debit_json) : null,
        final: any;
      try {
        if (c.debit_minor && !debit) {
          try {
            debit = await this.walletClient.call(mid, "debit", {
              ...base,
              transaction_id: id + ":debit",
              amount_minor: c.debit_minor,
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
            ) {
              this.tx(() => {
                this.run(
                  "UPDATE game_operations SET status='rejected',error_code=? WHERE id=? AND status='prepared'",
                  e.code,
                  id,
                );
                this.run(
                  "UPDATE prebet_rounds SET error_code=? WHERE id=?",
                  e.code,
                  c.event.round_id,
                );
              });
              throw e;
            }
            throw e;
          }
          this.run(
            "UPDATE game_operations SET status='debited',debit_json=? WHERE id=? AND status='prepared'",
            encode(debit),
            id,
          );
        }
        final = c.credit_minor
          ? await this.walletClient.call(mid, "credit", {
              ...base,
              transaction_id: id + ":credit",
              amount_minor: c.credit_minor,
              reference_id: c.event.round_id + ":debit",
            })
          : (debit ??
            (await this.walletClient.call(
              mid,
              "balance",
              this.base(mid, o.player_id),
            )));
      } catch (e) {
        if (
          this.get("SELECT status FROM game_operations WHERE id=?", id)
            .status === "rejected"
        )
          throw e;
        throw new ServiceError(
          "WALLET_UNCERTAIN",
          "Settlement pending; retry operation " + id,
          503,
        );
      }
      const response = {
        game_id: 1,
        sid: id,
        round_id: c.event.round_id,
        engine_version: c.engine_version,
        ruleset_id: c.ruleset_id,
        wallet: {
          before_minor:
            debit?.balance_before_minor ??
            final.balance_before_minor ??
            final.balance_minor,
          debit_minor: c.debit_minor,
          credit_minor: c.credit_minor,
          after_minor: final.balance_minor,
        },
        outcome: c.event,
        ...(c.rtp ? { rtp: c.rtp } : {}),
      };
      return this.tx(() => {
        o = this.get("SELECT * FROM game_operations WHERE id=?", id);
        if (o.status === "settled") return JSON.parse(o.response_json);
        check(o.status !== "rejected", "OPERATION_REJECTED");
        this.run(
          "UPDATE merchant_states SET state_json=? WHERE merchant_id=? AND player_id=? AND game_id=?",
          encode(c.state),
          mid,
          o.player_id,
          o.game_id,
        );
        this.run(
          "UPDATE game_operations SET status='settled',response_json=?,settled_at=? WHERE id=?",
          encode(response),
          now(),
          id,
        );
        this.rtp.record(
          this.get("SELECT * FROM game_operations WHERE id=?", id),
        );
        return response;
      });
    });
  }
  operations(mid: string, p: any) {
    this.merchant(mid, false);
    const after = p.after_seq ?? 0;
    amount(after);
    return {
      operations: this.all(
        "SELECT * FROM game_operations WHERE merchant_id=? AND seq>? ORDER BY seq LIMIT ?",
        mid,
        after,
        limit(p.limit ?? 20),
      ).map((r) => ({
        seq: r.seq,
        operation_id: r.id,
        player_id: r.player_id,
        game_id: gameNumber(r.game_id),
        status: r.status,
        error_code: r.error_code,
        debit_transaction_id: JSON.parse(r.candidate_json).debit_minor
          ? r.id + ":debit"
          : null,
        credit_transaction_id: JSON.parse(r.candidate_json).credit_minor
          ? r.id + ":credit"
          : null,
        result: r.response_json ? JSON.parse(r.response_json) : null,
      })),
    };
  }
  async prebet(
    mid: string,
    pid: string,
    state: any,
    bet: any,
    canonical: string,
    binding: any,
    seed: string,
  ) {
    const settings = JSON.parse(binding.settings_json);
    let r = this.get(
      state.phase === "ready"
        ? "SELECT * FROM prebet_rounds WHERE game_id='buffalo-win' AND merchant_id=? AND player_id=? AND initial_sid=? AND error_code IS NULL"
        : "SELECT * FROM prebet_rounds WHERE game_id='buffalo-win' AND merchant_id=? AND player_id=? AND id=?",
      mid,
      pid,
      state.phase === "ready" ? state.sid : state.round_id,
    );
    if (!r && (!settings.enabled || state.phase !== "ready")) return null;
    if (!r)
      r = this.tx(() => {
        const old = this.get(
          "SELECT * FROM prebet_rounds WHERE game_id='buffalo-win' AND merchant_id=? AND player_id=? AND initial_sid=? AND error_code IS NULL",
          mid,
          pid,
          state.sid,
        );
        if (old) return old;
        const player = this.get(
          "SELECT * FROM merchant_players WHERE merchant_id=? AND player_id=?",
          mid,
          pid,
        );
        check(player, "PREBET_PLAYER_REQUIRED");
        const debit = bet.coin_minor * bet.level * 10 * (bet.buy_free ? 75 : 1),
          stamp = Math.max(
            Date.now(),
            this.get(
              "SELECT COALESCE(MAX(CAST(json_extract(prebet_request_json,'$.timestamp') AS INTEGER)),0)+1 AS n FROM prebet_rounds",
            ).n,
          ),
          payload = {
            player_name: player.external_username,
            timestamp: stamp,
            bet_amount:
              Math.floor(debit / 100) +
              "." +
              String(debit % 100).padStart(2, "0"),
            type: bet.buy_free ? "BUY_FREE_SPIN" : player.prebet_type,
          },
          id = hex();
        this.run(
          "INSERT INTO prebet_rounds VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
          id,
          mid,
          pid,
          "buffalo-win",
          state.sid,
          canonical,
          encode(state),
          encode(bet),
          encode(payload),
          null,
          null,
          now(),
          null,
        );
        return this.get("SELECT * FROM prebet_rounds WHERE id=?", id);
      });
    if (state.phase === "ready")
      check(
        r.request_json === canonical,
        "PREBET_PENDING",
        "Retry original bet",
        409,
      );
    else
      check(
        !bet.buy_free && encode(bet) === encode(state.bet),
        "BET_LOCKED",
        "Continue original bet",
        409,
      );
    if (!r.policy_json) {
      const url = prebetURL(settings.url),
        body = r.prebet_request_json,
        m = this.control.merchant(mid, true);
      let policy: any;
      try {
        const resp = await fetchBounded(
          url,
          {
            method: "POST",
            headers: signedHeaders(
              mid,
              m.merchant_secret,
              new URL(url).pathname,
              body,
            ),
            body,
          },
          16384,
        );
        check(resp.status === 200, "PREBET_UNCERTAIN");
        const v = object(resp.body);
        check(Number.isInteger(v.code), "PREBET_UNCERTAIN");
        if (v.code !== 0)
          throw new ServiceError(
            "PREBET_" + v.code,
            "Platform decision rejected",
            v.code === 3202 ? 409 : 503,
          );
        const range = v.data?.maxWinMulti;
        check(
          Array.isArray(range) &&
            range.length === 2 &&
            range.every(
              (v) =>
                ["number", "string"].includes(typeof v) &&
                Number.isFinite(Number(v)),
            ),
          "PREBET_RANGE_INVALID",
        );
        const [lo, hi] = range.map(Number);
        check(
          (lo === -1 || lo >= 0) &&
            hi >= 0 &&
            (lo < 0 || hi >= lo) &&
            Math.max(Math.abs(lo), hi) <= 1000000,
          "PREBET_RANGE_INVALID",
        );
        policy = encode({ maxWinMulti: range.map(String) });
      } catch (e) {
        if (e instanceof ServiceError && e.code === "PREBET_3202")
          this.run(
            "UPDATE prebet_rounds SET error_code=? WHERE id=? AND policy_json IS NULL",
            e.code,
            r.id,
          );
        if (e instanceof ServiceError) throw e;
        throw new ServiceError("PREBET_UNCERTAIN", "Decision unavailable", 503);
      }
      this.tx(() => {
        const current = this.get(
          "SELECT policy_json FROM prebet_rounds WHERE id=?",
          r.id,
        ).policy_json;
        check(!current || current === policy, "PREBET_DECISION_CONFLICT");
        this.run(
          "UPDATE prebet_rounds SET policy_json=COALESCE(policy_json,?) WHERE id=?",
          policy,
          r.id,
        );
      });
      r.policy_json = policy;
    }
    if (!r.plan_json) {
      const plan = await this.game.call(
        "plan",
        {
          state: JSON.parse(r.initial_state_json),
          bet: JSON.parse(r.bet_json),
          range: JSON.parse(r.policy_json).maxWinMulti,
          round_id: r.id,
          seed,
        },
        this.rtp.configuration(binding),
      );
      this.run(
        "UPDATE prebet_rounds SET plan_json=COALESCE(plan_json,?) WHERE id=?",
        encode(plan),
        r.id,
      );
      r.plan_json = this.get(
        "SELECT plan_json FROM prebet_rounds WHERE id=?",
        r.id,
      ).plan_json;
    }
    const step = JSON.parse(r.plan_json).steps.find(
      (s) => s.previous_sid === state.sid,
    );
    check(step, "PREBET_PLAN_CONFLICT");
    return step.candidate;
  }
}
