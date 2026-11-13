import { check, sha, pythonJSON } from "../../other/shared/core.js";
const PAYTABLE: Record<string, number> = {
  "3": 5,
  "4": 4,
  "5": 3,
  "6": 3,
  "7": 2,
  "8": 2,
  "9": 2,
  "10": 1,
  "11": 1,
  "12": 1,
};
import type { Provider } from "./provider.js";
import * as py from "../../other/shared/compat/runtime.js";
const PHASES: any = {
  ready: 1,
  paid_extension: 4,
  free_start: 21,
  free_extension: 22,
};
const nullable = (v: any) => (Object.keys(v).length ? v : null);
export function transaction(e: any, w: any, t: any) {
  const wp = e.positions,
    cells = new Set<number>((Object.values(wp) as number[][]).flat()),
    blocks: any = Object.fromEntries(
      (Object.entries(e.expanded) as [string, number[]][]).filter(([, ps]) =>
        ps.every((p) => cells.has(p)),
      ),
    ),
    long: any = {};
  for (const col of new Set(
    (Object.values(blocks) as number[][]).map((ps) => Math.floor(ps[0] / 4)),
  )) {
    const reel: number[] = [];
    let p = col * 4;
    while (p < (col + 1) * 4) {
      const b = Object.keys(blocks).find((k) => blocks[k][0] === p);
      if (b) {
        reel.push(...Array(e.block_counts[b]).fill(e.board[p]));
        p += blocks[b].length;
      } else reel.push(e.board[p++]);
    }
    long[col] = reel;
  }
  let rs: any = null;
  if (e.extension) {
    const wins = Object.fromEntries(
        (Object.entries(wp) as [string, number[]][])
          .map(([k, ps]) => [k, ps.filter((p) => p >= e.board.length - 4)])
          .filter(([, ps]) => (ps as number[]).length),
      ),
      newBlocks = e.new_blocks ?? {},
      winning = Object.fromEntries(
        Object.entries(blocks).filter(([k]) => k in newBlocks),
      );
    rs = {
      ecrl: e.board.slice(-4),
      oecrl: e.original_column ?? e.board.slice(-4),
      pr: null,
      sr: Number(Object.keys(e.previous_positions).sort()[0] ?? "3"),
      ewp: nullable(wins),
      ebwp: nullable(winning),
      ebwsc: nullable(
        Object.fromEntries(
          Object.keys(winning).map((k) => [k, e.block_counts[k]]),
        ),
      ),
      nes: nullable(newBlocks),
    };
  }
  const f = e.free,
    fs = f
      ? {
          s: f.remaining,
          ts: f.total,
          as: f.added,
          aw: f.award_minor / 100,
          rc: f.rc,
        }
      : null,
    settled = !e.extend,
    ratio = e.base_bet_minor ? e.win_minor / e.base_bet_minor : 0;
  let gwt = -1;
  ["mw", "bw", "mgw", "smgw"].forEach((k, i) => {
    if (ratio >= t[k]) gwt = i + 1;
  });
  let hash =
    e.extension_index +
    ":" +
    Array.from({ length: 4 }, (_, r) =>
      [0, 1, 2].map((c) => e.board[c * 4 + r]).join(";"),
    ).join("#");
  for (const k of Object.keys(wp).sort())
    hash +=
      "#R#" +
      k +
      "#" +
      wp[k].map((p) => "" + Math.floor(p / 4) + (p % 4)).join("");
  const float = (n: number) => (Number.isInteger(n) ? n + ".0" : String(n));
  hash += `#MV#${float(e.debit_minor / 100)}#MT#1#MG#${float(e.win_minor / 100)}#`;
  return {
    sid: e.sid,
    psid: e.round_id,
    st: PHASES[e.phase],
    nst: PHASES[e.next_phase],
    pf: 1,
    ml: e.bet.level,
    cs: e.bet.coin_minor / 100,
    rl: e.board,
    orl: e.original,
    s: e.special,
    ix: e.extend,
    sc: e.scatter_count,
    gm: e.multiplier,
    wp: nullable(wp),
    lw: null,
    sw:
      settled && Object.keys(wp).length
        ? Object.fromEntries(
            Object.entries(e.awards_minor).map(([k, v]) => [
              k,
              [PAYTABLE[k], Number(v) / 100],
            ]),
          )
        : null,
    scs: e.counts_eval,
    wpl: cells.size ? [...cells].sort((a, b) => a - b) : null,
    bwp: nullable(blocks),
    bwsc: nullable(
      Object.fromEntries(
        Object.keys(blocks).map((k) => [k, e.block_counts[k]]),
      ),
    ),
    es: nullable(e.expanded),
    bsc: nullable(e.block_counts),
    lrs: nullable(long),
    rs,
    fs,
    twbm: settled ? e.base_minor / 100 : 0,
    acw: e.accumulated_minor / 100,
    ctw: e.display_delta_minor / 100,
    tw: e.win_minor / 100,
    aw: e.round_award_minor / 100,
    tb: e.debit_minor / 100,
    tbb: e.debit_minor / 100,
    np: (e.win_minor - e.debit_minor) / 100,
    gwt,
    cwc: Number(e.win_minor > 0),
    pcwc: 0,
    fstc: nullable(
      Object.fromEntries(
        Object.entries(e.phase_counts).map(([k, v]) => [PHASES[k], v]),
      ),
    ),
    rwsp: null,
    hashr: hash,
    fb: null,
    pmt: null,
    ab: null,
    wid: 0,
    wt: "C",
    wk: "0_C",
    wbn: null,
    wfg: null,
    ocr: null,
    mr: null,
    ge: [
      e.extend && Object.keys(wp).length
        ? 3
        : f && f.remaining > 0
          ? 2
          : e.base_bet_minor && e.win_minor >= e.base_bet_minor * 3
            ? 3
            : 1,
      11,
    ],
    blb: w.before_minor / 100,
    blab: (w.before_minor - w.debit_minor) / 100,
    bl: w.after_minor / 100,
  };
}
export function idle(s: any) {
  return {
    sid: s.sid,
    round_id: "0",
    phase: "ready",
    next_phase: "ready",
    bet: s.bet,
    board: s.board,
    original: null,
    expanded: {},
    block_counts: {},
    positions: {},
    counts_eval: null,
    phase_counts: {},
    special: 10,
    multiplier: 1,
    extension_index: 0,
    extension: false,
    extend: false,
    previous_positions: {},
    free: null,
    scatter_count: 0,
    base_bet_minor: 0,
    debit_minor: 0,
    win_minor: 0,
    round_award_minor: 0,
    accumulated_minor: 0,
    display_delta_minor: 0,
    base_minor: 0,
    awards_minor: {},
  };
}
export class PG {
  constructor(public service: Provider) {}
  async runtime(tok: string) {
    const games=this.service.multi;
    if(!games?.remote)return null;
    const s=this.service.session(tok),raw=await games.ensureInitial(s.merchant_id,s.player_id,s.game_id);
    return games.handle(games.remote.select(s.merchant_id,s.player_id,s.game_id,raw));
  }
  async spin(form: URLSearchParams, tok: string) {
    for (const k of form.keys())
      check(form.getAll(k).length === 1, "SPIN_INVALID");
    check(
      form.get("wk") === "0_C" &&
        form.get("btt") === "1" &&
        form.get("pf") === "1",
      "SPIN_INVALID",
    );
    const feature = form.get("fb") ?? "0";
    check(
      ["", "0", "false", "2"].includes(feature) &&
        ["", "0", "false"].includes(form.get("ab") ?? "0"),
      "BET_INVALID",
    );
    check(/^[+-]?\d+$/.test(form.get("ml") ?? ""), "BET_INVALID");
    const engine=await this.runtime(tok);
    const payload={
          cs: form.get("cs"),
          ml: Number(form.get("ml")),
          buy_free: feature === "2",
        };
    const bet = engine?await this.service.multi!.invoke(engine,"normalize_bet",payload):await this.service.game.call("normalize", {bet:payload}),
      previous = form.get("id"),
      key = "pg:" + sha(pythonJSON({ previous, bet }));
    check(previous !== null, "PREVIOUS_SID_INVALID");
    const r = await this.service.spin(tok, key, previous, bet);
    return {
      dt: {
        si: transaction(
          r.outcome,
          r.wallet,
          engine?py.plain(engine.config).win_thresholds:this.service.description.config.win_thresholds,
        ),
      },
      err: null,
    };
  }
  async info(tok: string) {
    const engine=await this.runtime(tok);
    const r = await this.service.state(tok),
      s = r.state,
      e = s.last_event ?? idle(s),
      c = engine?py.plain(engine.config):this.service.description.config,
      w = {
        before_minor: r.balance_minor + e.debit_minor - e.win_minor,
        after_minor: r.balance_minor,
        debit_minor: e.debit_minor,
      };
    return {
      dt: {
        cs: c.coin_sizes_minor.map((v) => v / 100),
        ml: c.bet_levels,
        mxl: 10,
        maxwm: null,
        wt: c.win_thresholds,
        fb: c.feature_buy,
        gcs: { bf: c.feature_buy_game_config },
        bl: r.balance_minor / 100,
        inwe: false,
        iuwe: false,
        ls: { si: transaction(e, w, c.win_thresholds) },
        cc: (await this.service.wallet(tok)).currency,
      },
      err: null,
    };
  }
  async wallet(tok: string) {
    const wallet = await this.service.wallet(tok), balance = wallet.balance_minor / 100;
    return {
      dt: {
        cc: wallet.currency,
        tb: balance,
        pb: 0,
        cb: balance,
        tbb: 0,
        tfgb: 0,
        rfgc: 0,
        inbe: false,
        infge: false,
        iebe: false,
        iefge: false,
        ch: { k: "0_C", cid: 0, cb: balance },
        p: null,
        ocr: null,
        bwc: 0,
        fgwc: 0,
      },
      err: null,
    };
  }
}
