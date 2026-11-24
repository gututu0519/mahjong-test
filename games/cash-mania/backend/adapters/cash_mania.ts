import * as p from "../../../../other/shared/compat/runtime.js";
import * as protocol from "../../../../other/shared/migrated/py/adapters/pg/protocol.js";
import * as wire from "../../../../other/shared/migrated/py/adapters/pg/wire.js";
import { check, encode, sha, ServiceError } from "../../../../other/shared/core.js";
import { evaluateBoard, visibleBoard, type CashManiaConfig } from "../engine/engine.js";

export const SALT = 23;
const method = (object: any, name: string, ...args: any[]) => p.call(p.attr(object, name), args);
const field = (id: number, kind: number, value: any): Buffer => p.call(protocol.field, [id, kind, value]);
const double = (id: number, value: number): Buffer => p.call(protocol.double_field, [id, value]);
const text = (id: number, value: string): Buffer => p.call(protocol.text_field, [id, value]);
const spec = (id: number, type: string, extra: any = {}) => ({ id, type, ...extra });

// 字段号取自 Cash Mania 原客户端 GameTransactionModel 的 api 装饰器。
export const schema = {
  __root__: { fields: {
    sid: spec(1, "string"), psid: spec(2, "string"), st: spec(3, "int32"), nst: spec(4, "int32"), pf: spec(5, "int32"), aw: spec(6, "double"),
    wid: spec(7, "uint32"), wt: spec(8, "string"), wk: spec(9, "string"), blb: spec(12, "double"), blab: spec(13, "double"), bl: spec(14, "double"),
    tb: spec(15, "double"), tbb: spec(16, "double"), tw: spec(17, "double"), np: spec(18, "double"), ge: spec(21, "int32", { rule: "repeated" }),
    ml: spec(51, "int32"), cs: spec(52, "double"), rl: spec(53, "int32", { rule: "repeated" }), ctw: spec(54, "double"), cwc: spec(55, "int32"),
    pcwc: spec(57, "int32"), rwsp: spec(58, "string"), gwt: spec(71, "int32"), wp: spec(101, "Int32List", { keyType: "int32" }), lw: spec(102, "double", { keyType: "int32" }),
    fs: spec(104, "FreeSpin"), fb: spec(60, "int32"),
    twbm: spec(103, "double"), imw: spec(105, "bool"), rv: spec(106, "double", { rule: "repeated" }), orl: spec(107, "int32", { rule: "repeated" }),
    orv: spec(108, "double", { rule: "repeated" }), rsrl: spec(109, "int32", { rule: "repeated" }),
    rsrv: spec(110, "double", { rule: "repeated" }), nfp: spec(111, "int32", { keyType: "int32" }),
  } },
  FreeSpin: { fields: { s: spec(1, "int32"), ts: spec(2, "int32"), as: spec(3, "int32"), aw: spec(4, "double"), gt: spec(5, "int32") } },
  Int32List: { fields: { __value: spec(1, "int32", { rule: "repeated" }) } },
};
const packedInts = { ge: 21, rl: 53, orl: 107, rsrl: 109 } as const;
const packedAmounts = { rv: 106, orv: 108, rsrv: 110 } as const;
const amountIds = new Set<number>(Object.values(packedAmounts));
const wireSchema = p.from(schema);

export function encodeTransaction(tx: any): Buffer {
  const singles = { ...tx };
  // 原站数组按 packed protobuf 编码。缺省标志不占用一个额外的 wire 字段。
  for (const key of ["wid", "imw", "cwc", "pcwc"]) if (!singles[key]) delete singles[key];
  const chunks: Buffer[] = [];
  for (const [name, id] of Object.entries(packedInts)) {
    delete singles[name];
    const values: number[] | undefined = tx[name];
    if (values?.length) chunks.push(field(id, 2, Buffer.concat(values.map(v => p.call(protocol.varint, [v])))));
  }
  for (const [name, id] of Object.entries(packedAmounts)) {
    delete singles[name];
    const values: number[] | undefined = tx[name];
    if (!values?.length) continue;
    const data = Buffer.alloc(values.length * 8);
    values.forEach((v, i) => data.writeDoubleLE(v, i * 8));
    chunks.push(field(id, 2, data));
  }
  return Buffer.concat([p.call(wire.encode, [p.from(singles), wireSchema]), ...chunks]);
}

// 同时读取原厂的 packed double 和早期本地服务 single fixed64 格式。
export function decodeTransaction(raw: Buffer): any {
  const normalized: Buffer[] = [];
  for (const [id, kind, value] of p.iter(p.call(protocol.fields, [raw]))) {
    if (kind === 2 && amountIds.has(id)) {
      check(value.length % 8 === 0, "SPIN_INVALID", "盘面数值字段长度错误。");
      for (let offset = 0; offset < value.length; offset += 8) normalized.push(field(id, 1, value.subarray(offset, offset + 8)));
    } else normalized.push(field(id, kind, value));
  }
  return p.plain(p.call(wire.decode, [Buffer.concat(normalized), wireSchema]));
}

// 采集核对和本地协议适配使用同一组原始字段。没有中间盘面时不补造一个阶段。
export function roundPresentation(tx: any) {
  const nine = (values: unknown, integers: boolean) => Array.isArray(values) && values.length === 9 &&
    values.every(v => Number.isFinite(v) && (!integers || Number.isInteger(v)));
  check(nine(tx.rl, true) && nine(tx.rv, false), "SPIN_INVALID", "最终盘面数据不完整。");
  if (tx.orl != null || tx.orv != null) check(nine(tx.orl, true) && (tx.orv == null || nine(tx.orv, false)), "SPIN_INVALID", "原始盘面数据不完整。");
  if (tx.rsrl != null || tx.rsrv != null) check(nine(tx.rsrl, true) && nine(tx.rsrv, false), "SPIN_INVALID", "重转盘面数据不完整。");
  if (tx.nfp != null) check(tx.orl && tx.orv && typeof tx.nfp === "object" && !Array.isArray(tx.nfp) &&
    Object.entries(tx.nfp).every(([k, v]) => /^\d+$/.test(k) && Number.isInteger(v)), "SPIN_INVALID", "挪轴起始位置缺少对应盘面。");
  if (tx.gwt != null) check(Number.isInteger(tx.gwt), "SPIN_INVALID", "中奖分类无效。");
  return { board: tx.rl, reel_values: tx.rv, ...(tx.orl != null && { original_board: tx.orl }),
    ...(tx.orv != null && { original_values: tx.orv }), ...(tx.rsrl != null && { respin_board: tx.rsrl, respin_values: tx.rsrv }),
    ...(tx.nfp != null && { nudge_from_position: tx.nfp }), ...(tx.gwt != null && { game_win_type: tx.gwt }) };
}
export function pack(raw: Buffer, seed: number): Buffer { return p.call(protocol.pack, [raw, seed, SALT]); }
export function request(body: Buffer): { value: any; seed: number } {
  try {
    const [raw, seed] = p.call(protocol.unpack, [body, null, SALT]);
    return { value: p.plain(p.call(protocol.decode_request, [raw])), seed };
  } catch { throw new ServiceError("SPIN_INVALID", "无效的二进制请求。"); }
}
export function transaction(event: any, wallet: any, config: CashManiaConfig) {
  const win = event.win_minor / 100, debit = event.debit_minor / 100;
  // 旧回合恢复、重试和历史详情也要能显示，保留持久化的原始记录及结算金额。
  const clientReels = (symbols: number[], values: number[]) => {
    const board = visibleBoard(symbols);
    return { board, values: board === symbols ? values : evaluateBoard(config, board, event.bet).values };
  };
  const final = clientReels(event.board, event.reel_values);
  const original = event.original_board ? clientReels(event.original_board, event.original_values ?? event.reel_values) : final;
  const respin = event.respin_board && clientReels(event.respin_board, event.respin_values);
  return {
    sid: event.sid, psid: event.round_id, st: 1, nst: 1, pf: 1, ml: event.bet.level, cs: event.bet.coin_minor / 100,
    rl: final.board, orl: original.board, rv: final.values,
    ...(event.original_values != null && { orv: original.values }),
    ...(respin && { rsrl: respin.board, rsrv: respin.values }),
    ...(event.nudge_from_position != null && { nfp: event.nudge_from_position }),
    wp: win ? event.winning_positions : null, lw: win ? { "1": win } : null,
    twbm: event.base_win_minor / 100, imw: false,
    aw: win, tw: win, ctw: win, tb: debit, tbb: event.base_bet_minor / 100, np: (event.win_minor - event.debit_minor) / 100,
    cwc: win ? 1 : 0, pcwc: win ? 1 : 0, rwsp: win ? JSON.stringify({ "1": win }) : null,
    // 已有分类逐局保留。新生成的普通局沿用基础表现，样本不足以推出完整分界。
    gwt: event.game_win_type ?? -1, ge: [1, 11], wid: 0, wt: "C", wk: "0_C",
    blb: wallet.before_minor / 100, blab: (wallet.before_minor - wallet.debit_minor) / 100, bl: wallet.after_minor / 100,
  };
}

export function createAdapter(service: any) {
  const game = method(service.registry, "get", "cash-mania");
  const config = (): CashManiaConfig => p.plain(game.config);
  const invoke = (name: string, ...args: any[]) => p.plain(method(service, name, ...args));
  const currency = () => service.merchant_currency ?? "PGC";
  return {
    wallet(token: string) {
      const balance = invoke("wallet", token).balance_minor / 100;
      return { dt: { cc: currency(), tb: balance, pb: 0, cb: balance, tbb: 0, tfgb: 0, rfgc: 0, inbe: false, infge: false, iebe: false, iefge: false, ch: { k: "0_C", cid: 0, cb: balance }, p: null, ocr: null, bwc: 0, fgwc: 0 }, err: null };
    },
    spin(body: Buffer, token: string) {
      const { value: req, seed } = request(body);
      check(req.atk === token && req.btt === (service.merchant_bet_type ?? 2) && req.pf === 1 && req.wk === "0_C", "SPIN_INVALID", "会话或钱包参数不匹配。");
      check(!req.fb && !req.ab, "FEATURE_UNSUPPORTED", "当前本地版本仅支持普通旋转，未开放购买或加注玩法。");
      const { atk: _token, ...identity } = req;
      const result = invoke("spin", token, "cash-mania", "pg:" + sha(encode(identity)), req.id, p.from({ cs: req.cs, ml: req.ml }));
      return pack(encodeTransaction(transaction(result.outcome, result.wallet, config())), seed);
    },
    game_info(body: Buffer, token: string) {
      const { value: req, seed } = request(body);
      check(req.atk === token, "SESSION_INVALID", "会话无效。", 401);
      const snapshot = invoke("state", token, "cash-mania"), state = snapshot.state, balance = snapshot.balance_minor, c = config();
      const evaluated = evaluateBoard(c, state.board, state.bet);
      const event = state.last_event ?? { sid: state.sid, round_id: "0", bet: state.bet, board: state.board, reel_values: evaluated.values, base_win_minor: 0, winning_positions: {}, win_minor: 0, debit_minor: 0, base_bet_minor: state.bet.coin_minor * state.bet.level * c.bet_factor };
      const wallet = { before_minor: balance + event.debit_minor - event.win_minor, debit_minor: event.debit_minor, after_minor: balance };
      const coins = Buffer.alloc(c.coin_sizes_minor.length * 8);
      c.coin_sizes_minor.forEach((v, i) => coins.writeDoubleLE(v / 100, i * 8));
      const info = Buffer.concat([
        double(1, balance / 100), text(4, currency()), field(11, 2, coins), field(12, 2, Buffer.from(c.bet_levels)), field(13, 0, c.bet_factor),
        field(22, 2, Buffer.concat(["mw", "bw", "mgw", "smgw"].map((k, i) => double(i + 1, c.win_thresholds[k])))), field(23, 2, field(1, 0, c.max_win_multiplier)),
      ]);
      return pack(Buffer.concat([encodeTransaction(transaction(event, wallet, c)), field(900, 2, info)]), seed);
    },
    history(token: string, form: URLSearchParams, summary = false) {
      // 查询真实结算记录，正常轮次一笔对应一组历史。
      const c = config();
      const context = p.context(method(service, "connection"));
      let records: any[];
      try {
        const player = method(service.sessions, "_player", context.value, token);
        const query = method(context.value, "execute", "SELECT response_json,created_at FROM spins WHERE player_id=? AND game_id=? ORDER BY id DESC", p.tuple([p.item(player, "id"), "cash-mania"]));
        records = Array.from(p.iter(method(query, "fetchall"))).map((row: any) => {
          const result = JSON.parse(p.item(row, "response_json")), event = result.outcome, tx = transaction(event, result.wallet, c), timestamp = p.item(row, "created_at") * 1000;
          return { bt: timestamp, tid: event.round_id, gid: 1682240, gtba: tx.tb, gtwa: tx.tw, gtwla: tx.np, cc: currency(), ge: [1, 11], fscc: 0, mgcc: 0, bd: [{ bl: tx.bl, bt: timestamp, gd: { ...tx, tst: timestamp }, ib: false, tba: tx.tb, tid: event.sid, twla: tx.np }] };
        });
      } finally { context.exit(null); }
      const number = (name: string, fallback: number) => {
        const value = form.get(name); if (!value) return fallback;
        const parsed = Number(value); check(Number.isSafeInteger(parsed), "BAD_REQUEST"); return parsed;
      };
      records = records.filter(r => r.bt >= number("dtf", 0) && r.bt <= number("dtt", 253402300799000));
      if (summary) return { dt: { lut: records[0]?.bt ?? 0, bs: records.length ? { bc: records.length, btba: records.reduce((n, r) => n + r.gtba, 0), btwla: records.reduce((n, r) => n + r.gtwla, 0), btwa: records.reduce((n, r) => n + r.gtwa, 0), gid: 1682240, lbid: records[0].tid } : null }, err: null };
      const page = Math.max(1, number("bn", 1)), count = Math.min(100, Math.max(1, number("rc", 20)));
      return { dt: { bh: records.slice((page - 1) * count, page * count) }, err: null };
    },
  };
}
