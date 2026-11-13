import {
  check,
  clone,
  encode,
  pythonJSON,
  sha,
  amount,
} from "../../shared/core.js";
import { PythonRandom } from "./random.js";
export const PAYTABLE: Record<string, number> = {
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
export function evaluate(
  board: number[],
  expanded: any,
  blockCounts: any,
  coin: number,
  level: number,
) {
  check(
    board.length >= 12 &&
      board.length % 4 === 0 &&
      board.every((v) => Number.isInteger(v) && v >= 0 && v < 13),
    "BOARD_INVALID",
  );
  const positions: any = {},
    counts: any = {},
    awards: any = {};
  for (const [symbol, rate] of Object.entries(PAYTABLE)) {
    const hits: number[] = [];
    for (let off = 0; off < board.length; off += 4) {
      const col = board
        .slice(off, off + 4)
        .flatMap((v, i) => (v === 0 || v === Number(symbol) ? [off + i] : []));
      if (!col.length) break;
      hits.push(...col);
    }
    if (new Set(hits.map((p) => Math.floor(p / 4))).size < 3) continue;
    positions[symbol] = hits;
    let count = hits.length;
    for (const [id, cells] of Object.entries(expanded) as [string, number[]][])
      if (cells.every((p) => hits.includes(p)))
        count += blockCounts[id] - cells.length;
    counts[symbol] = count;
    awards[symbol] = amount(coin * level * rate * count);
  }
  return {
    positions,
    counts,
    awards_minor: awards,
    base_minor: amount(
      (Object.values(awards) as number[]).reduce((a, b) => a + b, 0),
    ),
    extend:
      board.slice(-4).includes(1) ||
      (Object.values(positions) as number[][]).some((h) =>
        h.some((p) => p >= board.length - 4),
      ),
  };
}
export class BuffaloWin {
  game_id = "buffalo-win";
  title = "美洲野牛";
  version = "1.2.0";
  ruleset_id: string;
  compatible_ruleset_id: string;
  config: any;
  constructor(configuration: any) {
    this.config = clone(configuration);
    const c = this.config;
    check(
      encode(c.coin_sizes_minor) === encode([2, 3, 10, 20, 30, 90, 200]) &&
        encode(c.bet_levels) === encode([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]) &&
        c.base_bet_factor === 10 &&
        c.free_trigger === 3 &&
        c.free_spins === 10 &&
        c.free_extra_spins === 2 &&
        c.free_retrigger === true &&
        encode(c.feature_buy) ===
          encode({ t: 0.5, bms: null, is: true, bm: 75 }) &&
        encode(c.feature_buy_game_config) ===
          encode({ t: 40, bms: null, is: true, bm: 75 }),
      "CONFIG_INVALID",
    );
    check(
      encode(Object.keys(c.symbol_weights).sort()) ===
        encode(Array.from({ length: 13 }, (_, i) => String(i)).sort()) &&
        Object.values(c.symbol_weights).every(
          (v) => Number.isInteger(v) && Number(v) >= 0 && Number(v) <= 10000,
        ) &&
        c.symbol_weights["2"] > 0 &&
        ["stack_probability", "expanded_probability"].every(
          (k) => typeof c[k] === "number" && c[k] >= 0 && c[k] <= 1,
        ) &&
        encode(c.win_thresholds) ===
          encode({ mw: 3, bw: 5, mgw: 15, smgw: 35 }),
      "CONFIG_INVALID",
    );
    this.ruleset_id = this.version + ":" + sha(pythonJSON(c)).slice(0, 16);
    const legacy = clone(c);
    legacy.coin_sizes_minor = [3, 10, 30, 90];
    delete legacy.feature_buy;
    delete legacy.feature_buy_game_config;
    this.compatible_ruleset_id =
      "1.1.0:" + sha(pythonJSON(legacy)).slice(0, 16);
  }
  normalize_bet(p: any) {
    check(
      p &&
        typeof p === "object" &&
        !Array.isArray(p) &&
        Object.keys(p).every((k) =>
          ["coin_minor", "level", "cs", "ml", "buy_free"].includes(k),
        ),
      "BET_INVALID",
    );
    const buy = p.buy_free ?? false;
    check(typeof buy === "boolean", "BET_INVALID");
    let coin = p.coin_minor;
    if (coin == null) {
      const s = String(p.cs ?? "0.3");
      check(/^\d+(?:\.\d+)?$/.test(s), "BET_INVALID");
      const [a, b = ""] = s.split(".");
      check(!/[1-9]/.test(b.slice(2)), "BET_INVALID");
      coin = Number(BigInt(a) * 100n + BigInt((b + "00").slice(0, 2)));
    }
    const level = p.level ?? p.ml ?? 2;
    check(
      Number.isInteger(coin) &&
        Number.isInteger(level) &&
        this.config.coin_sizes_minor.includes(coin) &&
        this.config.bet_levels.includes(level),
      "BET_INVALID",
    );
    return { coin_minor: coin, level, ...(buy ? { buy_free: true } : {}) };
  }
  private column(rng: PythonRandom, first = false) {
    const out: number[] = [],
      symbols = Array.from(
        { length: first ? 12 : 13 },
        (_, i) => i + (first ? 1 : 0),
      );
    while (out.length < 4) {
      const s = rng.choice(
        symbols,
        symbols.map((n) => this.config.symbol_weights[n]),
      );
      const size =
        s >= 3 && rng.random() < this.config.stack_probability
          ? rng.int(2, 4)
          : 1;
      out.push(...Array(Math.min(size, 4 - out.length)).fill(s));
    }
    return out;
  }
  private blocks(board: number[], rng: PythonRandom, offset = 0, first = 1) {
    const expanded: any = {},
      counts: any = {};
    for (let col = 0; col < board.length / 4; col++) {
      let start = col * 4;
      while (start < col * 4 + 4) {
        let end = start + 1;
        while (end < col * 4 + 4 && board[end] === board[start]) end++;
        if (
          end - start >= 2 &&
          board[start] >= 3 &&
          rng.random() < this.config.expanded_probability
        ) {
          const key = String(first + Object.keys(expanded).length);
          expanded[key] = Array.from(
            { length: end - start },
            (_, i) => offset + start + i,
          );
          counts[key] = end - start + rng.int(1, end - start);
        }
        start = end;
      }
    }
    return [expanded, counts];
  }
  private start(rng: PythonRandom, free: boolean, buy: boolean) {
    let board = Array.from({ length: 3 }, (_, col) =>
      this.column(rng, col === 0),
    ).flat();
    if (buy) {
      board = board.map((s) => (s === 1 ? 2 : s));
      for (const p of [rng.range(8), rng.int(8, 11)]) board[p] = 1;
    }
    const special = rng.int(3, 12);
    const [expanded, counts] = this.blocks(
      free ? board.slice(4) : board,
      rng,
      free ? 4 : 0,
    );
    return { board, special, expanded, counts };
  }
  private freeAward(n: number) {
    return n < 3 ? 0 : 10 + (n - 3) * 2;
  }
  initial_state(_seed = "") {
    return {
      sid: "0",
      round_id: "0",
      phase: "ready",
      ruleset_id: this.ruleset_id,
      bet: { coin_minor: 30, level: 2 },
      board: [3, 2, 4, 2, 5, 2, 6, 2, 7, 2, 8, 2],
      expanded: {},
      block_counts: {},
      special: 10,
      multiplier: 1,
      free: null,
      counts: {},
      round_award_minor: 0,
      base_minor: 0,
      extension_index: 0,
      last_event: null,
    };
  }
  step(input: any, inputBet: any, seed: string, sid: string) {
    const state: any = clone(input),
      phase = state.phase,
      start = phase === "ready",
      buy = inputBet.buy_free ?? false;
    check(!buy || start, "FEATURE_LOCKED", "Finish current round", 409);
    const bet = { coin_minor: inputBet.coin_minor, level: inputBet.level },
      freeMode = ["free_start", "free_extension"].includes(phase),
      extension = ["paid_extension", "free_extension"].includes(phase);
    check(
      start ||
        [this.ruleset_id, this.compatible_ruleset_id].includes(
          state.ruleset_id,
        ),
      "RULESET_CHANGED",
      "Finish round with original rules",
      409,
    );
    check(
      start || encode(bet) === encode(state.bet),
      "BET_LOCKED",
      "Finish current round",
      409,
    );
    if (start)
      Object.assign(state, {
        round_id: sid,
        bet,
        ruleset_id: this.ruleset_id,
        multiplier: 1,
        free: null,
        counts: {},
        round_award_minor: 0,
        base_minor: 0,
        bought_feature: buy,
      });
    const rng = new PythonRandom(seed),
      priorBase = state.base_minor,
      previousBoard = [...state.board],
      previousPositions = extension
        ? evaluate(
            previousBoard,
            state.expanded,
            state.block_counts,
            bet.coin_minor,
            bet.level,
          ).positions
        : {};
    let newBlocks: any = {},
      originalColumn: any = null,
      original: any;
    if (freeMode) state.free.added = 0;
    if (extension) {
      let col = this.column(rng);
      if (!freeMode && state.bought_feature) {
        col = col.map((s) => (s === 1 ? 2 : s));
        if (previousBoard.filter((v) => v === 1).length < 3)
          col[rng.range(4)] = 1;
      }
      originalColumn = [...col];
      let counts;
      [newBlocks, counts] = this.blocks(
        col,
        rng,
        previousBoard.length,
        Math.max(0, ...Object.keys(state.expanded).map(Number)) + 1,
      );
      Object.assign(state.expanded, newBlocks);
      Object.assign(state.block_counts, counts);
      state.board.push(...col);
      original = previousBoard;
      state.multiplier++;
      state.extension_index++;
      if (freeMode) state.free.rc++;
    } else {
      const s = this.start(rng, freeMode, buy);
      original = s.board;
      state.expanded = s.expanded;
      state.block_counts = s.counts;
      if (!freeMode) state.special = s.special;
      state.board = [...original];
      state.extension_index = 0;
      if (freeMode) {
        state.free.remaining--;
        state.free.rc = 0;
      }
    }
    for (const cells of Object.values(state.expanded) as number[][])
      for (const p of cells) state.board[p] = freeMode ? 0 : state.special;
    if (phase !== "ready") state.counts[phase] = (state.counts[phase] ?? 0) + 1;
    const board = state.board,
      result = evaluate(
        board,
        state.expanded,
        state.block_counts,
        bet.coin_minor,
        bet.level,
      ),
      multiplier = state.multiplier,
      base = result.base_minor,
      debit = amount(
        start ? bet.coin_minor * bet.level * 10 * (buy ? 75 : 1) : 0,
      ),
      credit = amount(result.extend ? 0 : base * multiplier);
    state.round_award_minor = amount(state.round_award_minor + credit);
    if (freeMode)
      state.free.award_minor = amount(state.free.award_minor + credit);
    let nextPhase: string;
    const scatters = board.filter((v) => v === 1).length;
    if (result.extend)
      nextPhase = freeMode ? "free_extension" : "paid_extension";
    else if (freeMode) {
      const added = this.freeAward(scatters);
      state.free.remaining += added;
      state.free.total += added;
      state.free.added = added;
      nextPhase = state.free.remaining > 0 ? "free_start" : "ready";
    } else {
      const awarded = this.freeAward(scatters);
      if (awarded) {
        state.free = {
          remaining: awarded,
          total: awarded,
          award_minor: 0,
          added: 0,
          rc: 0,
        };
        state.multiplier = 1;
        nextPhase = "free_start";
      } else nextPhase = "ready";
    }
    const accumulated = Object.keys(result.positions).length
        ? base
        : freeMode
          ? priorBase
          : 0,
      displayDelta =
        result.extend || !base ? base - priorBase : base * (multiplier - 1);
    state.base_minor = accumulated;
    const event = {
      sid,
      round_id: state.round_id,
      phase,
      next_phase: nextPhase,
      bet,
      base_bet_minor: bet.coin_minor * bet.level * 10,
      bought_feature: state.bought_feature ?? false,
      debit_minor: debit,
      win_minor: credit,
      round_award_minor: state.round_award_minor,
      board: [...board],
      original,
      expanded: clone(state.expanded),
      block_counts: { ...state.block_counts },
      special: state.special,
      multiplier,
      extension_index: state.extension_index,
      extension,
      previous_positions: previousPositions,
      new_blocks: newBlocks,
      original_column: originalColumn,
      free: clone(state.free),
      phase_counts: { ...state.counts },
      counts_eval: Object.keys(result.counts).length ? result.counts : null,
      scatter_count: scatters,
      accumulated_minor: accumulated,
      display_delta_minor: displayDelta,
      ...result,
    };
    Object.assign(state, { sid, phase: nextPhase, last_event: event });
    return { state, event, debit_minor: debit, credit_minor: credit };
  }
}
