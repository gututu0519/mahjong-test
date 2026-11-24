import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import * as p from "../../../../other/shared/compat/runtime.js";
import { check, encode } from "../../../../other/shared/core.js";

export interface CashManiaConfig {
  game_id: string;
  version: string;
  probability_model: string;
  original_probability_verified: boolean;
  supported_features: string[];
  unsupported_features: string[];
  presentation_model?: string;
  presentation_weights?: { normal: number; nudge: number; respin: number };
  coin_sizes_minor: number[];
  bet_levels: number[];
  bet_factor: number;
  side_values: number[];
  middle_values: number[];
  side_weights: number[];
  middle_weights: number[];
  payline: number[];
  initial_board: number[];
  win_thresholds: Record<string, number>;
  max_win_multiplier: number;
}
export interface CashManiaBet { coin_minor: number; level: number }

// 金额和中奖公式来自原客户端及普通旋转证据；权重仅为可复现的本地模型。
export function validateConfig(c: CashManiaConfig) {
  check(c.game_id === "cash-mania" && c.probability_model === "local-independent-reels-v1", "CONFIG_INVALID");
  check(c.original_probability_verified === false, "CONFIG_INVALID");
  if (c.presentation_model != null || c.presentation_weights != null) {
    check(c.presentation_model === "local-outcome-preserving-v1", "CONFIG_INVALID");
    const weights = c.presentation_weights;
    check(weights != null && typeof weights === "object" && !Array.isArray(weights) &&
      Object.keys(weights).sort().join(",") === "normal,nudge,respin", "CONFIG_INVALID");
    const choices = [weights!.normal, weights!.nudge, weights!.respin];
    check(choices.every(v => Number.isSafeInteger(v) && v >= 0) &&
      choices.reduce((a, b) => a + b, 0) > 0 && choices.reduce((a, b) => a + b, 0) <= 0x100000000, "CONFIG_INVALID");
    check(encode(c.supported_features) === '["normal-spin","nudge","respin"]', "CONFIG_INVALID");
  } else check(encode(c.supported_features) === '["normal-spin"]', "CONFIG_INVALID");
  check(c.bet_factor === 10 && encode(c.payline) === "[1,4,7]", "CONFIG_INVALID");
  check(encode(c.side_values) === "[0,1,5,10,50,100]", "CONFIG_INVALID");
  check(encode(c.middle_values) === "[0,1,2,3,5,10,15,20,30,40,50,100]", "CONFIG_INVALID");
  for (const [weights, values] of [[c.side_weights, c.side_values], [c.middle_weights, c.middle_values]]) {
    check(Array.isArray(weights) && weights.length === values.length && weights.every(v => Number.isSafeInteger(v) && v >= 0), "CONFIG_INVALID");
    const total = weights.reduce((a, b) => a + b, 0);
    // draw 使用无符号 32 位样本。总和等于 2^32 时无需拒绝，大于它则不允许。
    check(total > 0 && total <= 0x100000000, "CONFIG_INVALID");
  }
  check(c.coin_sizes_minor.every(v => Number.isSafeInteger(v) && v > 0) && c.coin_sizes_minor.length > 0, "CONFIG_INVALID");
  check(c.bet_levels.every(v => Number.isSafeInteger(v) && v > 0) && c.bet_levels.length > 0, "CONFIG_INVALID");
  check(c.initial_board.length === 9 && c.initial_board.every((v, i) => Number.isInteger(v) && v >= 0 && v < (i >= 3 && i <= 5 ? c.middle_values : c.side_values).length), "CONFIG_INVALID");
}

export function normalizeBet(c: CashManiaConfig, value: any): CashManiaBet {
  const bet = p.plain(value);
  check(bet && typeof bet === "object" && !Array.isArray(bet), "BET_INVALID", "下注参数必须为对象。");
  check(Object.keys(bet).every(k => ["coin_minor", "level", "cs", "ml"].includes(k)), "FEATURE_UNSUPPORTED", "当前本地版本仅支持普通旋转。");
  check(!(Object.hasOwn(bet, "cs") && Object.hasOwn(bet, "coin_minor")) && !(Object.hasOwn(bet, "ml") && Object.hasOwn(bet, "level")), "BET_INVALID");
  const cs = bet.cs;
  if (Object.hasOwn(bet, "cs")) check(typeof cs === "number" && Number.isFinite(cs) && Math.abs(cs * 100 - Math.round(cs * 100)) < 1e-8, "BET_INVALID");
  const coin_minor = Object.hasOwn(bet, "cs") ? Math.round(cs * 100) : (bet.coin_minor ?? c.coin_sizes_minor[0]);
  const level = bet.ml ?? bet.level ?? c.bet_levels[0];
  check(Number.isSafeInteger(coin_minor) && c.coin_sizes_minor.includes(coin_minor), "BET_INVALID", "不支持的投注币值。");
  check(Number.isSafeInteger(level) && c.bet_levels.includes(level), "BET_INVALID", "不支持的投注等级。");
  check(Number.isSafeInteger(coin_minor * level * 10000), "BET_INVALID");
  return { coin_minor, level };
}

// 每次抽取使用独立 SHA-256 块和拒绝采样，不读取抓取样本或外部随机状态。
function random(seed: string) {
  let counter = 0;
  return (maximum: number) => {
    const limit = Math.floor(0x100000000 / maximum) * maximum;
    let value: number;
    do { value = createHash("sha256").update(`${seed}:${counter++}`).digest().readUInt32BE(0); } while (value >= limit);
    return value % maximum;
  };
}
function pick(weights: number[], draw: (n: number) => number) {
  let target = draw(weights.reduce((a, b) => a + b, 0));
  for (let i = 0; i < weights.length; i++) { target -= weights[i]; if (target < 0) return i; }
  throw new Error("权重抽取失败");
}

// 原版用中行的 0 表示停在两张钞票之间，上下两格必须有可显示的符号。
export function visibleBoard(symbols: number[]): number[] {
  if (!symbols.some((symbol, i) => symbol === 0 && i % 3 !== 1)) return symbols;
  return symbols.map((symbol, i) => {
    if (symbol !== 0 || i % 3 === 1) return symbol;
    const middle = i - i % 3 + 1;
    const opposite = i < middle ? middle + 1 : middle - 1;
    // 只补同轴的展示格。整轴为空时用面额或倍率 1，支付线保留原始抽取。
    return symbols[opposite] || symbols[middle] || 1;
  });
}

export function evaluateBoard(c: CashManiaConfig, board: number[], bet: CashManiaBet) {
  check(board.length === 9 && board.every((v, i) => Number.isInteger(v) && v >= 0 && v < (i === 3 || i === 5 ? 14 : i === 4 ? c.middle_values.length : c.side_values.length)), "STATE_INVALID");
  // 原始普通局上下格可带 12/13 图标，已观察的值均为 1；本地不生成它们。
  const values = board.map((v, i) => i >= 3 && i <= 5 ? (v >= 12 ? 1 : c.middle_values[v]) : c.side_values[v] * bet.coin_minor * bet.level / 100);
  const base = board[1] !== 0 && board[1] === board[7] ? c.side_values[board[1]] * bet.coin_minor * bet.level : 0;
  const win_minor = base * c.middle_values[board[4]];
  return { values, win_minor, base_win_minor: win_minor > 0 ? base : 0 };
}
export function normalRtp(c: CashManiaConfig) {
  const sides = c.side_weights.reduce((a, b) => a + b, 0), middles = c.middle_weights.reduce((a, b) => a + b, 0);
  const side = c.side_weights.reduce((n, w, i) => n + (w / sides) ** 2 * c.side_values[i], 0);
  const middle = c.middle_weights.reduce((n, w, i) => n + w / middles * c.middle_values[i], 0);
  return side * middle / c.bet_factor;
}

// 仅生成同局中间表现，不改变最终抽取、扣款或派彩。选择权重是本地配置，
// 原站样本只约束盘面关系，不提供触发概率、完整轮轴带或挪轴移位规则。
function presentation(c: CashManiaConfig, board: number[], bet: CashManiaBet, seed: string, win: number): Record<string, any> {
  if (!c.presentation_model || !win) return {};
  const weights = c.presentation_weights!;
  const draw = random(seed + ":presentation");
  const choice = pick([weights.normal, weights.nudge, weights.respin], draw);
  if (choice === 1) {
    const original = [...board];
    original[3] = 1 + draw(c.middle_values.length - 1);
    original[4] = 0;
    original[5] = 1 + draw(c.middle_values.length - 1);
    return { original_board: original, original_values: evaluateBoard(c, original, bet).values,
      nudge_from_position: { "1": 5 } };
  }
  if (choice === 2) {
    const interim = [...board], index = draw(2) === 0 ? 1 : 7;
    const alternatives = c.side_values.map((_, symbol) => symbol).filter(symbol => symbol !== 0 && symbol !== board[index]);
    interim[index] = alternatives[draw(alternatives.length)];
    return { original_board: [...board], respin_board: interim,
      respin_values: evaluateBoard(c, interim, bet).values };
  }
  return {};
}

export const CashMania = p.native(([configuration = p.sourcePath("services/cash-mania/config/cash-mania.json")]) => {
  configuration ??= p.sourcePath("services/cash-mania/config/cash-mania.json");
  const supplied = typeof configuration === "string" ? JSON.parse(readFileSync(configuration, "utf8")) : p.plain(configuration);
  validateConfig(supplied);
  const engine: any = {
    game_id: "cash-mania", title: "Cash Mania", version: supplied.version, minor_unit: 100,
    ruleset_id: createHash("sha256").update(encode(supplied)).digest("hex").slice(0, 16),
    config: p.from(supplied),
  };
  const config = (): CashManiaConfig => p.plain(engine.config);
  engine.normalize_bet = p.native(([bet]) => p.from(normalizeBet(config(), bet)));
  engine.initial_state = p.native(([_seed]) => {
    const c = config();
    return p.from({ phase: "ready", sid: "0", round_id: "0", ruleset_id: engine.ruleset_id, step: 0, board: visibleBoard(c.initial_board), bet: normalizeBet(c, {}), last_event: null });
  });
  engine.public_state = p.native(([state]) => p.clone(state));
  engine.step = p.native(([rawState, rawBet, seed, sid]) => {
    const c = config(), state = p.plain(rawState), bet = normalizeBet(c, rawBet);
    check(state.phase === "ready", "FEATURE_UNSUPPORTED", "当前本地版本不支持跨请求的免费旋转或奖励状态。");
    check(typeof seed === "string" && typeof sid === "string" && sid.length > 0, "STATE_INVALID");
    const draw = random(seed);
    const board = visibleBoard(Array.from({ length: 9 }, (_, i) => pick(i >= 3 && i <= 5 ? c.middle_weights : c.side_weights, draw)));
    const evaluated = evaluateBoard(c, board, bet), debit = bet.coin_minor * bet.level * c.bet_factor;
    const event = {
      sid, round_id: sid, phase: "ready", next_phase: "ready", step: 0, bet, board,
      reel_values: evaluated.values, base_win_minor: evaluated.base_win_minor,
      winning_positions: evaluated.win_minor ? { "1": [...c.payline] } : {},
      line_awards_minor: evaluated.win_minor ? { "1": evaluated.win_minor } : {},
      debit_minor: debit, base_bet_minor: debit, win_minor: evaluated.win_minor,
      round_award_minor: evaluated.win_minor, max_win: false, free: null, ruleset_id: engine.ruleset_id,
      ...presentation(c, board, bet, seed, evaluated.win_minor),
    };
    const next = { ...state, sid, round_id: sid, ruleset_id: engine.ruleset_id, step: 0, board, bet, last_event: event };
    return { state: p.from(next), event: p.from(event), debit_minor: debit, credit_minor: evaluated.win_minor };
  });
  return engine;
});
