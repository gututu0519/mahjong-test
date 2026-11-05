import { readFileSync, existsSync } from "node:fs";
import {
  check,
  encode,
  pythonJSON,
  sha,
  hex,
  now,
  identifier,
  amount,
  clone,
} from "../shared/core.js";
import { reason, prebetURL } from "./control.js";
import type { Provider } from "./provider.js";
export class RTP {
  legacy = "";
  constructor(
    public p: Provider,
    private modelFile?: string,
  ) {
    p.run("ATTACH DATABASE ? AS control", p.control.path);
  }
  initialize(d: any) {
    this.legacy = "legacy:" + d.ruleset_id;
    this.p.run(
      "INSERT OR IGNORE INTO rtp_models VALUES(?,?,?,?,?,?)",
      this.legacy,
      null,
      d.ruleset_id,
      encode({ legacy: true, config: d.config, ruleset_id: d.ruleset_id }),
      0,
      now(),
    );
    if (this.modelFile && existsSync(this.modelFile))
      for (const r of JSON.parse(readFileSync(this.modelFile, "utf8")).models)
        this.importModel(r, true);
    this.p.tx(() => {
      for (const r of this.p.all(
        "SELECT * FROM game_operations WHERE status='settled' AND id NOT IN (SELECT operation_id FROM rtp_accounted_ops) ORDER BY seq",
      ))
        this.record(r);
    });
  }
  importModel(r: any, publish = false) {
    check(
      r.engine_version === "1.2.0" &&
        r.game_id === 1 &&
        Number.isInteger(r.target_bp) &&
        r.target_bp >= 8000 &&
        r.target_bp <= 9900,
      "RTP_MODEL_INVALID",
    );
    check(
      encode(Object.keys(r.modes).sort()) === encode(["buy_free", "normal"]),
      "RTP_MODEL_INVALID",
    );
    for (const [mode, data] of Object.entries(r.modes) as any) {
      const v = data.validation,
        n = v.rounds,
        cost = v.cost;
      check(
        Number.isInteger(n) &&
          n >= (mode === "buy_free" ? 200000 : 2000000) &&
          cost === (mode === "buy_free" ? 1500 : 20),
        "RTP_MODEL_INVALID",
      );
      const mean = v.credit / (n * cost),
        variance =
          Math.max(0, (v.credit_squared - v.credit ** 2 / n) / (n - 1)) /
          cost ** 2,
        half = 2.576 * Math.sqrt(variance / n);
      check(
        v.unfinished_rounds === 0 &&
          half <= 0.015 &&
          mean - half <= r.target_bp / 10000 &&
          r.target_bp / 10000 <= mean + half &&
          Math.abs(v.rtp - mean) < 1e-10 &&
          Math.abs(v.ci_half - half) < 1e-10,
        "RTP_MODEL_INVALID",
      );
    }
    const hash = sha(
      pythonJSON(
        Object.fromEntries(
          Object.entries(r.modes).map(([k, v]: any) => [k, v.config]),
        ),
      ),
    );
    check(hash === r.model_hash, "RTP_MODEL_INVALID");
    const id = "bw-" + r.target_bp + "-" + hash.slice(0, 16);
    this.p.run(
      "INSERT OR IGNORE INTO rtp_models VALUES(?,?,?,?,?,?)",
      id,
      r.target_bp,
      hash,
      encode(r),
      publish,
      now(),
    );
    return id;
  }
  models() {
    return this.p
      .all(
        "SELECT * FROM rtp_models WHERE target_bp IS NOT NULL ORDER BY target_bp,created_at",
      )
      .map((r) => ({
        id: r.id,
        target_bp: r.target_bp,
        model_hash: r.model_hash,
        published: !!r.published,
        created_at: r.created_at,
        validation: Object.fromEntries(
          Object.entries(JSON.parse(r.report_json).modes).map(([k, v]: any) => [
            k,
            v.validation,
          ]),
        ),
        certified_theoretical: false,
      }));
  }
  mode(mid: string) {
    const r = this.p.get("SELECT * FROM rtp_modes WHERE merchant_id=?", mid),
      enabled = this.p.control.merchant(mid, true)?.pre_payout.enabled;
    let mode = r?.mode ?? (enabled ? "prebet" : "rtp");
    if (mode === "prebet" && !enabled) mode = "rtp";
    return { mode, revision: r?.revision ?? 0 };
  }
  resolve(mid: string, pid = "") {
    for (const [scope, m, p] of [
      ["player", mid, pid],
      ["merchant", mid, ""],
      ["platform", "", ""],
    ]) {
      if (scope === "player" && !pid) continue;
      const r = this.p.get(
        "SELECT p.*,m.target_bp FROM rtp_policies p JOIN rtp_models m ON m.id=p.model_id WHERE scope=? AND merchant_id=? AND player_id=? AND game_id=1",
        scope,
        m,
        p,
      );
      if (r) return r;
    }
    return {
      model_id: this.legacy,
      target_bp: null,
      scope: "legacy",
      revision: 0,
    };
  }
  bind(mid: string, pid: string, state: any, bet: any) {
    return this.p.tx(() => {
      let r = this.p.get(
        "SELECT * FROM rtp_bindings WHERE merchant_id=? AND player_id=? AND game_id='buffalo-win' AND " +
          (state.phase === "ready" ? "initial_sid=?" : "round_id=?"),
        mid,
        pid,
        state.phase === "ready" ? state.sid : state.round_id,
      );
      if (r) {
        const initial = JSON.parse(r.settings_json)._initial_bet;
        check(
          state.phase !== "ready" ||
            initial == null ||
            encode(initial) === encode(bet),
          "ROUND_PREPARING",
          "Retry original bet",
          409,
        );
        return r;
      }
      const legacy = state.phase !== "ready",
        settings = this.p.control.merchant(mid, true).pre_payout;
      let { mode } = this.mode(mid);
      if (
        this.p.get(
          "SELECT 1 FROM prebet_rounds WHERE merchant_id=? AND player_id=? AND error_code IS NULL AND " +
            (legacy ? "id=?" : "initial_sid=?"),
          mid,
          pid,
          legacy ? state.round_id : state.sid,
        )
      )
        mode = "prebet";
      check(!(mode === "rtp" && settings.enabled), "RTP_MODE_CONFLICT");
      const policy =
        mode === "rtp" && !legacy
          ? this.resolve(mid, pid)
          : { model_id: this.legacy, scope: "legacy", revision: 0 };
      const initial = legacy ? "legacy:" + state.round_id : state.sid;
      this.p.run(
        "INSERT INTO rtp_bindings VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        mid,
        pid,
        "buffalo-win",
        initial,
        legacy ? state.round_id : null,
        policy.model_id,
        (legacy ? state.bought_feature : bet.buy_free) ? "buy_free" : "normal",
        mode,
        policy.scope,
        policy.revision,
        encode({
          ...settings,
          enabled: mode === "prebet",
          _initial_bet: legacy ? null : bet,
        }),
        now(),
      );
      return this.p.get(
        "SELECT * FROM rtp_bindings WHERE merchant_id=? AND player_id=? AND game_id='buffalo-win' AND initial_sid=?",
        mid,
        pid,
        initial,
      );
    });
  }
  configuration(b: any) {
    const row = this.p.get("SELECT * FROM rtp_models WHERE id=?", b.model_id);
    check(row, "RTP_MODEL_MISSING");
    const r = JSON.parse(row.report_json);
    return r.legacy ? r.config : r.modes[b.play_mode].config;
  }
  bindingContext(b: any) {
    const target = this.p.get(
      "SELECT target_bp FROM rtp_models WHERE id=?",
      b.model_id,
    ).target_bp;
    return {
      model_id: b.model_id,
      mode: b.mode,
      source: b.source,
      revision: b.revision,
      target_rtp: b.mode === "rtp" && target != null ? target / 100 : null,
    };
  }
  context(mid: string, pid: string, state: any) {
    const b = this.p.get(
      "SELECT * FROM rtp_bindings WHERE merchant_id=? AND player_id=? AND game_id='buffalo-win' AND " +
        (state.phase === "ready"
          ? "initial_sid=? AND round_id IS NULL"
          : "round_id=?"),
      mid,
      pid,
      state.phase === "ready" ? state.sid : state.round_id,
    );
    let c;
    if (b) c = this.bindingContext(b);
    else if (state.phase !== "ready")
      c = {
        mode: this.p.get(
          "SELECT 1 FROM prebet_rounds WHERE id=?",
          state.round_id,
        )
          ? "prebet"
          : "legacy",
        target_rtp: null,
        model_id: this.legacy,
        source: "legacy",
      };
    else {
      const p = this.resolve(mid, pid),
        { mode } = this.mode(mid);
      c = {
        mode,
        target_rtp:
          mode === "rtp" && p.target_bp != null ? p.target_bp / 100 : null,
        model_id: p.model_id,
        source: p.scope,
      };
    }
    return {
      ...c,
      status:
        c.mode === "prebet"
          ? "prebet"
          : c.target_rtp != null
            ? "active"
            : "not_calibrated",
    };
  }
  event(actor: string, action: string, mid = "", details: any = {}) {
    this.p.run(
      "INSERT INTO rtp_events(merchant_id,actor,action,details_json,created_at) VALUES(?,?,?,?,?)",
      mid,
      actor,
      action,
      encode(details),
      now(),
    );
    if (actor !== "system")
      this.p.run(
        "INSERT INTO control.admin_audit(created_at,actor,action,target,outcome,details_json,merchant_id) VALUES(?,?,?,?,?,?,?)",
        now(),
        actor,
        action,
        mid || "platform",
        "success",
        encode({ merchant_id: mid || null, ...details }),
        mid || null,
      );
  }
  changeMode(actor: string, mid: string, mode: string, url?: string, why = "") {
    const old = this.mode(mid),
      settings = this.p.control.merchant(mid, true).pre_payout;
    url ??= settings.url;
    check(
      mode === "rtp" || (mode === "prebet" && !!url),
      "PREBET_CONFIG_INVALID",
    );
    if (url) prebetURL(url);
    this.p.run(
      "INSERT OR REPLACE INTO control.merchant_prebet_settings VALUES(?,?,?,?,?)",
      mid,
      mode === "prebet",
      url,
      "",
      "",
    );
    this.p.run(
      "UPDATE control.merchants SET version=version+1,updated_at=? WHERE id=?",
      now(),
      mid,
    );
    this.p.run(
      "INSERT INTO rtp_modes VALUES(?,?,?) ON CONFLICT(merchant_id) DO UPDATE SET mode=excluded.mode,revision=excluded.revision",
      mid,
      mode,
      old.revision + 1,
    );
    this.event(actor, "rtp.mode.change", mid, {
      before: old.mode,
      mode,
      reason: why,
    });
  }
  setMode(actor: string, p: any) {
    const mid = identifier(p.merchant_id),
      why = reason(p);
    check(
      ["rtp", "prebet"].includes(p.mode) && this.p.control.merchant(mid),
      "RTP_MODE_INVALID",
    );
    return this.p.tx(() => {
      const old = this.mode(mid);
      check(
        p.revision === old.revision,
        "VERSION_CONFLICT",
        "Mode changed",
        409,
      );
      this.changeMode(actor, mid, p.mode, p.url, why);
      return {
        mode: p.mode,
        revision: old.revision + 1,
        effective: "next_paid_round",
      };
    });
  }
  policy(actor: string, p: any, platform: boolean) {
    check((p.game_id ?? 1) === 1, "RTP_GAME_UNAVAILABLE");
    const why = reason(p),
      scope = p.scope ?? "merchant";
    check(
      ["platform", "merchant", "player"].includes(scope) &&
        (scope !== "platform" || platform),
      "FORBIDDEN",
      "Cannot change platform policy",
      403,
    );
    const mid = scope === "platform" ? "" : identifier(p.merchant_id),
      pid = scope === "player" ? identifier(p.player_id) : "",
      model = p.model_id || null,
      activate = p.activate_rtp ?? false;
    check(!mid || this.p.control.merchant(mid), "NOT_FOUND");
    check(
      typeof activate === "boolean" &&
        (!activate || (scope === "merchant" && model)),
      "INVALID_ARGUMENT",
    );
    return this.p.tx(() => {
      const old = this.p.get(
          "SELECT * FROM rtp_policies WHERE scope=? AND merchant_id=? AND player_id=? AND game_id=1",
          scope,
          mid,
          pid,
        ),
        rev = old?.revision ?? 0;
      check(p.revision === rev, "VERSION_CONFLICT", "Policy changed", 409);
      if (model) {
        check(
          this.p.get(
            "SELECT 1 FROM rtp_models WHERE id=? AND published=1 AND target_bp IS NOT NULL",
            model,
          ),
          "RTP_MODEL_UNAVAILABLE",
        );
        if (mid) {
          const mode = this.mode(mid);
          if (activate) {
            check(p.mode_revision === mode.revision, "VERSION_CONFLICT");
            this.changeMode(actor, mid, "rtp", undefined, why);
          } else
            check(
              mode.mode === "rtp" &&
                !this.p.control.merchant(mid, true).pre_payout.enabled,
              "RTP_MODE_CONFLICT",
            );
        }
      }
      this.p.run(
        "INSERT INTO rtp_policies VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(scope,merchant_id,player_id,game_id) DO UPDATE SET model_id=excluded.model_id,revision=excluded.revision,actor=excluded.actor,updated_at=excluded.updated_at",
        scope,
        mid,
        pid,
        1,
        model,
        rev + 1,
        actor,
        now(),
      );
      this.event(actor, "rtp.policy.publish", mid, {
        player_id: pid,
        scope,
        before: old ?? null,
        model_id: model,
        revision: rev + 1,
        reason: why,
      });
      return { revision: rev + 1, effective: "next_paid_round" };
    });
  }
  record(o: any) {
    if (o.status !== "settled" || !o.response_json) return;
    if (
      !this.p.run("INSERT OR IGNORE INTO rtp_accounted_ops VALUES(?)", o.id)
        .changes
    )
      return;
    const r = JSON.parse(o.response_json),
      e = r.outcome,
      w = r.wallet,
      mid = o.merchant_id,
      pid = o.player_id,
      rid = e.round_id,
      b = this.p.get(
        "SELECT b.*,m.target_bp FROM rtp_bindings b JOIN rtp_models m ON m.id=b.model_id WHERE b.merchant_id=? AND b.player_id=? AND b.game_id=? AND b.round_id=?",
        mid,
        pid,
        o.game_id,
        rid,
      ),
      old = this.p.get(
        "SELECT * FROM rtp_facts WHERE merchant_id=? AND player_id=? AND game_id=1 AND round_id=?",
        mid,
        pid,
        rid,
      );
    let mode =
      b?.mode ??
      (this.p.get("SELECT 1 FROM prebet_rounds WHERE id=?", rid)
        ? "prebet"
        : "legacy");
    if (mode !== "prebet" && b?.target_bp == null) mode = "legacy";
    const closed = e.next_phase === "ready",
      debit = BigInt(old?.debit_minor ?? 0) + BigInt(w.debit_minor),
      credit = BigInt(old?.credit_minor ?? 0) + BigInt(w.credit_minor);
    this.p.run(
      "INSERT INTO rtp_facts(merchant_id,player_id,game_id,round_id,play_mode,mode,target_bp,model_id,debit_minor,credit_minor,closed,started_at,closed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(merchant_id,player_id,game_id,round_id) DO UPDATE SET debit_minor=excluded.debit_minor,credit_minor=excluded.credit_minor,closed=excluded.closed,closed_at=excluded.closed_at",
      mid,
      pid,
      1,
      rid,
      e.bought_feature ? "buy_free" : "normal",
      mode,
      mode === "rtp" ? (b?.target_bp ?? null) : null,
      b?.model_id ?? null,
      String(debit),
      String(credit),
      closed,
      old?.started_at ?? o.created_at,
      closed ? o.settled_at : null,
    );
  }
  createJob(actor: string, p: any) {
    check(
      Number.isInteger(p.target_bp) &&
        p.target_bp >= 8000 &&
        p.target_bp <= 9900,
      "RTP_TARGET_INVALID",
    );
    const why = reason(p);
    return this.p.tx(() => {
      check(
        !this.p.get(
          "SELECT 1 FROM rtp_jobs WHERE target_bp=? AND status IN ('queued','running')",
          p.target_bp,
        ),
        "RTP_JOB_EXISTS",
      );
      const id = hex();
      this.p.run(
        "INSERT INTO rtp_jobs VALUES(?,?,?,?,?,?,?,?,?,?)",
        id,
        p.target_bp,
        "queued",
        actor,
        "{}",
        null,
        null,
        null,
        now(),
        now(),
      );
      this.event(actor, "rtp.calibration.queue", "", {
        target_bp: p.target_bp,
        reason: why,
        job_id: id,
      });
      return { id, status: "queued" };
    });
  }
  publish(actor: string, p: any) {
    const why = reason(p);
    return this.p.tx(() => {
      const row = this.p.get(
        "SELECT * FROM rtp_models WHERE id=? AND target_bp IS NOT NULL",
        p.model_id,
      );
      check(row, "NOT_FOUND");
      if (!row.published) {
        this.p.run("UPDATE rtp_models SET published=1 WHERE id=?", row.id);
        this.event(actor, "rtp.model.publish", "", {
          model_id: row.id,
          reason: why,
        });
      }
      return { published: true };
    });
  }
  snapshot(p: any, scope?: string) {
    check((p.game_id ?? 1) === 1, "RTP_GAME_UNAVAILABLE");
    const mid = scope || p.merchant_id || "",
      pid = p.player_id || "",
      start = p.from_at ?? 0,
      end = p.to_at ?? 0;
    amount(start);
    amount(end);
    check(!end || end > start, "INVALID_ARGUMENT");
    if (mid) check(this.p.control.merchant(identifier(mid)), "NOT_FOUND");
    if (pid) {
      identifier(pid);
      check(mid, "INVALID_ARGUMENT");
    }
    const clauses = ["game_id=1"],
      args: any[] = [];
    for (const [key, value] of [
      ["merchant_id", mid],
      ["player_id", pid],
      ["play_mode", p.play_mode],
      ["mode", p.mode],
    ])
      if (value) {
        if (key === "play_mode")
          check(["normal", "buy_free"].includes(value), "INVALID_ARGUMENT");
        if (key === "mode")
          check(
            ["rtp", "prebet", "legacy"].includes(value),
            "INVALID_ARGUMENT",
          );
        clauses.push(key + "=?");
        args.push(value);
      }
    const facts = this.p.all(
        "SELECT * FROM rtp_facts WHERE " + clauses.join(" AND "),
        ...args,
      ),
      where =
        (mid ? " AND merchant_id=?" : "") + (pid ? " AND player_id=?" : ""),
      values = [...(mid ? [mid] : []), ...(pid ? [pid] : [])],
      ops = this.p.all(
        "SELECT * FROM game_operations WHERE status IN ('prepared','debited')" +
          where,
        ...values,
      ),
      policies = this.p.all(
        "SELECT * FROM rtp_policies" +
          (mid ? " WHERE merchant_id IN (?,?)" : ""),
        ...(mid ? [mid, ""] : []),
      ),
      names = new Map(
        this.p.control
          .merchants()
          .filter((m) => !mid || m.id === mid)
          .map((m) => [m.id, m]),
      );
    const rows = facts.filter(
      (r) =>
        names.has(r.merchant_id) &&
        r.closed &&
        !r.voided &&
        BigInt(r.debit_minor) > 0n &&
        (!start || (r.closed_at != null && r.closed_at >= start)) &&
        (!end || (r.closed_at != null && r.closed_at < end)),
    );
    const aggregate = (rs: any[]) => {
      let d = 0n,
        c = 0n,
        known = 0n,
        expected = 0n;
      for (const r of rs) {
        const v = BigInt(r.debit_minor);
        d += v;
        c += BigInt(r.credit_minor);
        if (r.target_bp != null) {
          known += v;
          expected += v * BigInt(r.target_bp);
        }
      }
      return {
        debit_minor: String(d),
        credit_minor: String(c),
        rounds: rs.length,
        actual_rtp: d ? (Number(c) / Number(d)) * 100 : null,
        weighted_target: known ? Number(expected) / Number(known) / 100 : null,
        target_coverage: d ? (Number(known) / Number(d)) * 100 : 0,
        sample_note:
          rs.length < 10000 ? "少量回合波动较大" : "实际返还率，非理论证明",
      };
    };
    const merchants = Array.from(names.values()).map((m: any) => ({
      merchant_id: m.id,
      name: m.name,
      currency: m.currency,
      minor_unit: 100,
      ...aggregate(rows.filter((r) => r.merchant_id === m.id)),
      ...this.mode(m.id),
      default: this.resolve(m.id),
    }));
    const keys = new Set(
        [
          ...facts,
          ...ops,
          ...policies.filter((r) => r.scope === "player"),
          ...(mid && pid ? [{ merchant_id: mid, player_id: pid }] : []),
        ].map((r) => encode([r.merchant_id, r.player_id])),
      ),
      players = Array.from(keys)
        .sort()
        .map((s) => JSON.parse(s))
        .filter(([m, p]) => names.has(m) && (!pid || pid === p))
        .map(([m, p]) => ({
          merchant_id: m,
          player_id: p,
          currency: (names.get(m) as any).currency,
          minor_unit: 100,
          ...aggregate(
            rows.filter((r) => r.merchant_id === m && r.player_id === p),
          ),
          effective: this.resolve(m, p),
        }));
    const currencies = [
        ...new Set(Array.from(names.values()).map((m: any) => m.currency)),
      ],
      events = this.p
        .all(
          "SELECT * FROM rtp_events" +
            (mid ? " WHERE merchant_id=?" : "") +
            " ORDER BY seq DESC LIMIT 100",
          ...(mid ? [mid] : []),
        )
        .map(({ details_json, ...r }) => ({
          ...r,
          details: JSON.parse(details_json),
        })),
      jobs = scope
        ? []
        : this.p
            .all("SELECT * FROM rtp_jobs ORDER BY created_at DESC LIMIT 30")
            .map(({ progress_json, lease, ...r }) => ({
              ...r,
              progress: JSON.parse(progress_json),
            }));
    const days = [
      ...new Set(
        rows
          .filter((r) => r.closed_at)
          .map((r) => new Date(r.closed_at * 1000).toISOString().slice(0, 10)),
      ),
    ]
      .sort()
      .slice(-90);
    return {
      summary: currencies.map((c) => ({
        currency: c,
        minor_unit: 100,
        ...aggregate(
          rows.filter((r) => (names.get(r.merchant_id) as any).currency === c),
        ),
      })),
      merchants,
      players: players.slice(0, 200),
      players_total: players.length,
      daily: days.flatMap((d) =>
        currencies.map((c) => ({
          date: d,
          currency: c,
          minor_unit: 100,
          ...aggregate(
            rows.filter(
              (r) =>
                r.closed_at &&
                new Date(r.closed_at * 1000).toISOString().slice(0, 10) === d &&
                (names.get(r.merchant_id) as any).currency === c,
            ),
          ),
        })),
      ),
      policies,
      models: this.models(),
      events,
      jobs,
      pending_operations: ops.length,
      open_rounds: facts.filter((r) => !r.closed).length,
      reserved_rounds: this.p.get(
        "SELECT COUNT(*) AS n FROM rtp_bindings WHERE round_id IS NULL" + where,
        ...values,
      ).n,
      worker_online:
        (this.p.get("SELECT MAX(updated_at) AS t FROM rtp_workers").t ?? 0) >=
        now() - 120,
      historical_unknown_time: facts.filter(
        (r) => r.closed && r.closed_at == null,
      ).length,
      voided_rounds: facts.filter((r) => r.voided).length,
      timezone: "UTC",
      definition:
        "确认结算且已完成整局的派彩 / 实际投注；免费及续列计入原付费整局。金额字段为整数美分字符串。",
    };
  }
}
