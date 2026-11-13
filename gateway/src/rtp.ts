import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
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
} from "../../other/shared/core.js";
import { reason, prebetURL } from "../../other/shared/control.js";
import type { Provider } from "./provider.js";
import * as py from "../../other/shared/compat/runtime.js";
import { GAME_CODES, gameCode, gameNumber, gameUnit } from "./catalog.js";
import {
  ROUND_MODEL_VERSION,
  createEngine,
  invoke,
  modePayloads,
  modeKey,
} from "../../other/shared/games/round-model.js";
export class RTP {
  legacy = "";
  constructor(
    public p: Provider,
    private modelFile?: string,
  ) {
    p.run("ATTACH DATABASE ? AS control", p.control.path);
    p.tx(() => p.column("rtp_jobs", "game_id", "INTEGER NOT NULL DEFAULT 1"));
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
    const extra =
      this.modelFile && join(dirname(this.modelFile), "rtp-round-models.json");
    if (extra && existsSync(extra))
      for (const r of JSON.parse(readFileSync(extra, "utf8")).models)
        this.importModel(r, true);
    this.p.tx(() => {
      for (const r of this.p.all(
        "SELECT * FROM game_operations WHERE status='settled' AND id NOT IN (SELECT operation_id FROM rtp_accounted_ops) ORDER BY seq",
      ))
        this.record(r);
    });
  }
  importModel(r: any, publish = false) {
    if (r.format === 2) return this.importRoundModel(r, publish);
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
        game_id: JSON.parse(r.report_json).game_id ?? 1,
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
      enabled = !!this.p.control.merchant(mid, true)?.pre_payout.url;
    const mode = enabled ? "prebet" : "rtp";
    return { mode, revision: r?.revision ?? 0 };
  }
  resolve(mid: string, pid = "", gameId = 1, includeGame = true) {
    gameCode(gameId);
    let selected: any;
    for (const [scope, m, p] of [
      ["player", mid, pid],
      ["game", mid, ""],
      ["merchant", mid, ""],
      ["platform", "", ""],
    ]) {
      if (scope === "player" && !pid) continue;
      if (scope === "game" && !includeGame) continue;
      const r = this.p.get(
        "SELECT p.*,m.target_bp FROM rtp_policies p JOIN rtp_models m ON m.id=p.model_id WHERE scope=? AND merchant_id=? AND player_id=? AND game_id=?",
        scope,
        m,
        p,
        scope === "player" || scope === "game" ? gameId : 1,
      );
      if (r) {
        selected = r;
        break;
      }
    }
    selected ??= { target_bp: 9600, scope: "default", revision: 0 };
    const model = this.p.get(
      "SELECT * FROM rtp_models WHERE published=1 AND target_bp=? AND COALESCE(json_extract(report_json,'$.game_id'),1)=? ORDER BY (id=?) DESC,created_at DESC,id DESC LIMIT 1",
      selected.target_bp,
      gameId,
      selected.model_id ?? "",
    );
    return {
      ...selected,
      model_id: model?.id ?? (gameId === 1 ? this.legacy : null),
      game_id: gameId,
      calibrated: !!model,
    };
  }
  importRoundModel(r: any, publish = false) {
    gameCode(r.game_id);
    check(
      r.game_id !== 1 &&
        r.algorithm === ROUND_MODEL_VERSION &&
        Number.isInteger(r.target_bp) &&
        r.target_bp >= 8000 &&
        r.target_bp <= 9900,
      "RTP_MODEL_INVALID",
    );
    check(
      r.model_hash === sha(encode(r.modes)) && Object.keys(r.modes).length > 0,
      "RTP_MODEL_INVALID",
    );
    const engine = createEngine(gameCode(r.game_id));
    check(
      r.engine_version === py.attr(engine, "version") &&
        r.ruleset_id === py.attr(engine, "ruleset_id"),
      "RTP_MODEL_INVALID",
    );
    check(
      encode(Object.keys(r.modes).sort()) ===
        encode(
          modePayloads(gameCode(r.game_id))
            .map((payload) => modeKey(invoke(engine, "normalize_bet", payload)))
            .sort(),
        ),
      "RTP_MODEL_INVALID",
    );
    for (const [key, mode] of Object.entries(r.modes) as any[]) {
      check(
        mode &&
          mode.validation &&
          modeKey(invoke(engine, "normalize_bet", mode.payload)) === key,
        "RTP_MODEL_INVALID",
      );
      const v = mode.validation,
        target = r.target_bp / 10000;
      const batches = v.rounds / 100,
        variance =
          Math.max(
            0,
            (v.batch_squares - v.batch_sum ** 2 / batches) / (batches - 1),
          ) * 100;
      check(
        v.confidence === 0.99 &&
          Number.isInteger(v.rounds) &&
          v.rounds % 100 === 0 &&
          v.batch_size === 100 &&
          [
            v.rtp,
            v.variance,
            v.ci_half,
            v.sum,
            v.squares,
            v.batch_sum,
            v.batch_squares,
          ].every(Number.isFinite) &&
          Math.abs(v.rtp - v.sum / v.rounds) < 1e-10 &&
          Math.abs(v.variance - variance) < 1e-8 &&
          Math.abs(v.ci_low - (v.rtp - v.ci_half)) < 1e-8 &&
          Math.abs(v.ci_high - (v.rtp + v.ci_half)) < 1e-8,
        "RTP_MODEL_INVALID",
      );
      check(
        [2, 4, 8, 16].includes(mode.candidates) &&
          Number.isFinite(mode.upper_probability) &&
          mode.upper_probability >= 0 &&
          mode.upper_probability <= 1 &&
          v.rounds >= 20000 &&
          v.unfinished_rounds === 0 &&
          v.ci_half <= 0.015 &&
          v.ci_low <= target &&
          target <= v.ci_high &&
          Math.abs(v.ci_half - 2.576 * Math.sqrt(v.variance / v.rounds)) <
            1e-10,
        "RTP_MODEL_INVALID",
      );
    }
    const id = `round-${r.game_id}-${r.target_bp}-${r.model_hash.slice(0, 16)}`;
    this.p.run(
      "INSERT OR IGNORE INTO rtp_models VALUES(?,?,?,?,?,?)",
      id,
      r.target_bp,
      r.model_hash,
      encode(r),
      publish,
      now(),
    );
    return id;
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
          "SELECT 1 FROM prebet_rounds WHERE game_id='buffalo-win' AND merchant_id=? AND player_id=? AND error_code IS NULL AND " +
            (legacy ? "id=?" : "initial_sid=?"),
          mid,
          pid,
          legacy ? state.round_id : state.sid,
        )
      )
        mode = "prebet";
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
  // Caller persists this change with the callback failure in one transaction.
  fallback(b: any, error: string) {
      if (b.mode !== "prebet") return b;
      check(!b.round_id, "ROUND_ALREADY_STARTED");
      const policy = this.resolve(b.merchant_id, b.player_id);
      const settings = {...JSON.parse(b.settings_json), enabled:false, fallback_reason:error};
      this.p.run("UPDATE rtp_bindings SET mode='rtp',model_id=?,source=?,revision=?,settings_json=? WHERE merchant_id=? AND player_id=? AND game_id=? AND initial_sid=? AND round_id IS NULL",
        policy.model_id, policy.scope, policy.revision, encode(settings), b.merchant_id, b.player_id, b.game_id, b.initial_sid);
      Object.assign(b,{mode:"rtp",model_id:policy.model_id,source:policy.scope,revision:policy.revision,settings_json:encode(settings)});
      this.event("system","prebet.fallback",b.merchant_id,{game_id:b.game_id,error});
      return b;
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
  changeMode(
    actor: string,
    mid: string,
    mode: string,
    url?: string,
    why = "",
    touchMerchant = true,
  ) {
    const old = this.mode(mid),
      settings = this.p.control.merchant(mid, true).pre_payout;
    url ??= settings.url;
    check(typeof url === "string", "PREBET_CONFIG_INVALID");
    url = (url ?? "").trim();
    mode = url ? "prebet" : "rtp";
    if (url) prebetURL(url);
    this.p.run(
      "INSERT OR REPLACE INTO control.merchant_prebet_settings VALUES(?,?,?,?,?)",
      mid,
      mode === "prebet",
      url,
      "",
      "",
    );
    if (touchMerchant)
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
  updateMerchant(actor: string, q: any, profileOnly = false) {
    const mid = identifier(q.id),
      control = this.p.control;
    return this.p.tx(() => {
      const edit = control.prepareMerchantUpdate(mid, q, profileOnly),
        before = control.merchant(mid),
        settings = q.pre_payout;
      let transition = false;
      if (settings !== undefined) {
        check(
          settings &&
            typeof settings.url === "string" &&
            !("operator_token" in settings) &&
            !("secret_key" in settings),
          "PREBET_CONFIG_INVALID",
        );
        settings.url = settings.url.trim();
        settings.enabled = !!settings.url;
        if (settings.url) prebetURL(settings.url);
        const next = settings.url ? "prebet" : "rtp";
        transition = this.mode(mid).mode !== next;
        if (
          transition ||
          before.pre_payout.enabled !== settings.enabled ||
          before.pre_payout.url !== settings.url
        )
          this.changeMode(
            actor,
            mid,
            next,
            settings.url,
            profileOnly
              ? "商户资料保存预派彩设置"
              : "平台商户编辑保存预派彩设置",
            false,
          );
      }
      const updated = now();
      this.p.run(
        "INSERT INTO control.merchant_wallet_endpoints VALUES(?,?) ON CONFLICT(merchant_id) DO UPDATE SET endpoints_json=excluded.endpoints_json",
        mid,
        encode(edit.wallet_endpoints),
      );
      this.p.run(
        "UPDATE control.merchants SET name=?,wallet_url=?,enabled=?,games_json=?,version=version+1,updated_at=? WHERE id=?",
        edit.name,
        edit.wallet_url,
        edit.enabled,
        edit.games_json,
        updated,
        mid,
      );
      // Compose the public response from validated values; the control connection
      // cannot see these uncommitted updates yet.
      const merchant = {
        ...before,
        name: edit.name,
        wallet_url: edit.wallet_url,
        wallet_endpoints: edit.wallet_endpoints,
        enabled: !!edit.enabled,
        games: JSON.parse(edit.games_json).map(gameNumber),
        version: before.version + 1,
        updated_at: updated,
        ...(settings !== undefined
          ? { pre_payout: { enabled: settings.enabled, url: settings.url } }
          : {}),
      };
      this.p.run(
        "INSERT INTO control.admin_audit(created_at,actor,action,target,outcome,details_json,merchant_id) VALUES(?,?,?,?,?,?,?)",
        now(),
        actor,
        profileOnly ? "merchant.profile.update" : "merchant.update",
        mid,
        "success",
        encode({ before, after: merchant }),
        mid,
      );
      return {
        merchant,
        mode_changed: transition,
        effective: "next_paid_round",
      };
    });
  }
  setMode(actor: string, p: any) {
    const mid = identifier(p.merchant_id),
      why = reason(p);
    check(
      (p.mode === undefined || ["rtp", "prebet"].includes(p.mode)) && this.p.control.merchant(mid),
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
        mode: (p.url ?? this.p.control.merchant(mid).pre_payout.url).trim() ? "prebet" : "rtp",
        revision: old.revision + 1,
        effective: "next_paid_round",
      };
    });
  }
  policy(actor: string, p: any, platform: boolean) {
    const gameId = p.game_id ?? 1;
    gameCode(gameId);
    const why = reason(p),
      scope = p.scope ?? "merchant";
    check(
      ["platform", "merchant", "player", "game"].includes(scope) &&
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
          "SELECT * FROM rtp_policies WHERE scope=? AND merchant_id=? AND player_id=? AND game_id=?",
          scope,
          mid,
          pid,
          scope === "game" || scope === "player" ? gameId : 1,
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
          // RTP remains configurable as the fallback even with a decision URL.
          if (activate) check(p.mode_revision === mode.revision, "VERSION_CONFLICT");
        }
      }
      this.p.run(
        "INSERT INTO rtp_policies VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(scope,merchant_id,player_id,game_id) DO UPDATE SET model_id=excluded.model_id,revision=excluded.revision,actor=excluded.actor,updated_at=excluded.updated_at",
        scope,
        mid,
        pid,
        scope === "game" || scope === "player" ? gameId : 1,
        model,
        rev + 1,
        actor,
        now(),
      );
      this.event(actor, "rtp.policy.publish", mid, {
        game_id: gameId,
        player_id: pid,
        scope,
        before: old ?? null,
        model_id: model,
        revision: rev + 1,
        reason: why,
      });
      const affected =
        scope === "platform"
          ? GAME_CODES.map((_, i) => i + 1)
          : scope === "merchant"
            ? this.p.control.merchant(mid, true).games.map(gameNumber)
            : [gameId];
      for (const id of affected) {
        if (id === 1) continue;
        const target = this.resolve(mid, pid, id);
        if (
          target.calibrated ||
          this.p.get(
            "SELECT 1 FROM rtp_jobs WHERE game_id=? AND target_bp=? AND status IN ('queued','running')",
            id,
            target.target_bp,
          )
        )
          continue;
        const jobId = hex();
        this.p.run(
          "INSERT INTO rtp_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)",
          jobId,
          target.target_bp,
          "queued",
          actor,
          "{}",
          null,
          null,
          null,
          now(),
          now(),
          id,
        );
        this.event(actor, "rtp.calibration.queue", mid, {
          game_id: id,
          target_bp: target.target_bp,
          job_id: jobId,
          reason: "Target inheritance requires a calibrated game model",
        });
      }
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
      gid = gameNumber(o.game_id),
      rid = e.round_id,
      context = JSON.parse(o.candidate_json).rtp,
      b =
        o.game_id !== "buffalo-win"
          ? context
            ? {
                ...context,
                target_bp:
                  context.target_rtp == null
                    ? null
                    : Math.round(context.target_rtp * 100),
              }
            : null
          : this.p.get(
              "SELECT b.*,m.target_bp FROM rtp_bindings b JOIN rtp_models m ON m.id=b.model_id WHERE b.merchant_id=? AND b.player_id=? AND b.game_id=? AND b.round_id=?",
              mid,
              pid,
              o.game_id,
              rid,
            ),
      old = this.p.get(
        "SELECT * FROM rtp_facts WHERE merchant_id=? AND player_id=? AND game_id=? AND round_id=?",
        mid,
        pid,
        gid,
        rid,
      );
    let mode =
      b?.mode ??
      (this.p.get("SELECT 1 FROM prebet_rounds WHERE id=?", rid)
        ? "prebet"
        : "legacy");
    if (mode !== "prebet" && b?.target_bp == null) mode = "legacy";
    const closed = JSON.parse(o.candidate_json).state?.phase === "ready",
      debit = BigInt(old?.debit_minor ?? 0) + BigInt(w.debit_minor),
      credit = BigInt(old?.credit_minor ?? 0) + BigInt(w.credit_minor);
    this.p.run(
      "INSERT INTO rtp_facts(merchant_id,player_id,game_id,round_id,play_mode,mode,target_bp,model_id,debit_minor,credit_minor,closed,started_at,closed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(merchant_id,player_id,game_id,round_id) DO UPDATE SET debit_minor=excluded.debit_minor,credit_minor=excluded.credit_minor,closed=excluded.closed,closed_at=excluded.closed_at",
      mid,
      pid,
      gid,
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
    const why = reason(p),
      gameId = p.game_id ?? 1;
    gameCode(gameId);
    return this.p.tx(() => {
      check(
        !this.p.get(
          "SELECT 1 FROM rtp_jobs WHERE target_bp=? AND game_id=? AND status IN ('queued','running')",
          p.target_bp,
          gameId,
        ),
        "RTP_JOB_EXISTS",
      );
      const id = hex();
      this.p.run(
        "INSERT INTO rtp_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)",
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
        gameId,
      );
      this.event(actor, "rtp.calibration.queue", "", {
        game_id: gameId,
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
    const gameId = p.game_id ?? 1;
    check(
      Number.isInteger(gameId) && gameId >= 0 && gameId <= 19,
      "GAME_ID_INVALID",
    );
    const code = gameId ? gameCode(gameId) : "",
      unit = gameId ? gameUnit(code) : 10000;
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
    const clauses = [gameId ? "game_id=?" : "1=1"],
      args: any[] = gameId ? [gameId] : [];
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
    const facts = this.p
        .all("SELECT * FROM rtp_facts WHERE " + clauses.join(" AND "), ...args)
        .map((r) =>
          gameId
            ? r
            : {
                ...r,
                debit_minor: String(
                  (BigInt(r.debit_minor) * 10000n) /
                    BigInt(gameUnit(gameCode(r.game_id))),
                ),
                credit_minor: String(
                  (BigInt(r.credit_minor) * 10000n) /
                    BigInt(gameUnit(gameCode(r.game_id))),
                ),
              },
        ),
      where =
        (mid ? " AND merchant_id=?" : "") + (pid ? " AND player_id=?" : ""),
      values = [...(mid ? [mid] : []), ...(pid ? [pid] : [])],
      ops = this.p.all(
        "SELECT * FROM game_operations WHERE " +
          (gameId ? "game_id='" + code + "' AND " : "") +
          "status IN ('prepared','debited')" +
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
      minor_unit: unit,
      ...aggregate(rows.filter((r) => r.merchant_id === m.id)),
      ...this.mode(m.id),
      default: this.resolve(m.id, "", 1, false),
    }));
    const keys = new Set(
        [
          ...facts,
          ...ops,
          ...policies.filter(
            (r) => r.scope === "player" && (!gameId || r.game_id === gameId),
          ),
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
          minor_unit: unit,
          ...aggregate(
            rows.filter((r) => r.merchant_id === m && r.player_id === p),
          ),
          effective: gameId
            ? this.resolve(m, p, gameId)
            : { target_bp: null, scope: "mixed" },
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
            .all(
              "SELECT * FROM rtp_jobs ORDER BY CASE status WHEN 'running' THEN 0 WHEN 'queued' THEN 1 ELSE 2 END,created_at DESC LIMIT 100",
            )
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
      game_id: gameId,
      summary: currencies.map((c) => ({
        currency: c,
        minor_unit: unit,
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
          minor_unit: unit,
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
      reserved_rounds:
        this.p.get(
          "SELECT COUNT(*) AS n FROM rtp_bindings WHERE " +
            (gameId ? "game_id='" + code + "' AND " : "") +
            "round_id IS NULL" +
            where,
          ...values,
        ).n +
        (this.p.multi
          ? this.p.get(
              "SELECT COUNT(*) AS n FROM round_model_bindings WHERE " +
                (gameId ? "game_id='" + code + "' AND " : "") +
                "round_id IS NULL" +
                where,
              ...values,
            ).n
          : 0),
      worker_online:
        (this.p.get("SELECT MAX(updated_at) AS t FROM rtp_workers").t ?? 0) >=
        now() - 120,
      historical_unknown_time: facts.filter(
        (r) => r.closed && r.closed_at == null,
      ).length,
      voided_rounds: facts.filter((r) => r.voided).length,
      timezone: "UTC",
      definition:
        "确认结算且已完成整局的派彩 / 实际投注；免费及续列计入原付费整局。" +
        (gameId
          ? "金额字段为对应游戏原生精度的整数字符串。"
          : "跨游戏金额统一换算为 10000 精度后汇总。"),
    };
  }
}
