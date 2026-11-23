import * as p from "../../../../other/shared/compat/runtime.js";
import * as protocol from "../../../../other/shared/migrated/py/adapters/pg/protocol.js";
import * as wire from "../../../../other/shared/migrated/py/adapters/pg/wire.js";
import { check, encode, sha, ServiceError } from "../../../../other/shared/core.js";
import { evaluateBoard, type CashManiaConfig } from "../engine/engine.js";

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
    twbm: spec(103, "double"), imw: spec(105, "bool"), rv: spec(106, "double", { rule: "repeated" }), orl: spec(107, "int32", { rule: "repeated" }),
  } },
  Int32List: { fields: { __value: spec(1, "int32", { rule: "repeated" }) } },
};
export function encodeTransaction(tx: any): Buffer { return p.call(wire.encode, [p.from(tx), p.from(schema)]); }
export function pack(raw: Buffer, seed: number): Buffer { return p.call(protocol.pack, [raw, seed, SALT]); }
export function request(body: Buffer): { value: any; seed: number } {
  try {
    const [raw, seed] = p.call(protocol.unpack, [body, null, SALT]);
    return { value: p.plain(p.call(protocol.decode_request, [raw])), seed };
  } catch { throw new ServiceError("SPIN_INVALID", "无效的二进制请求。"); }
}
export function transaction(event: any, wallet: any) {
  const win = event.win_minor / 100, debit = event.debit_minor / 100;
  return {
    sid: event.sid, psid: event.round_id, st: 1, nst: 1, pf: 1, ml: event.bet.level, cs: event.bet.coin_minor / 100,
    rl: event.board, orl: event.board, rv: event.reel_values,
    wp: win ? event.winning_positions : null, lw: win ? { "1": win } : null,
    twbm: event.base_win_minor / 100, imw: false,
    aw: win, tw: win, ctw: win, tb: debit, tbb: event.base_bet_minor / 100, np: (event.win_minor - event.debit_minor) / 100,
    cwc: win ? 1 : 0, pcwc: win ? 1 : 0, rwsp: win ? JSON.stringify({ "1": win }) : null,
    // 未确认原厂大赢分类边界；本地普通版使用基础中奖动画。
    gwt: -1, ge: [1, 11], wid: 0, wt: "C", wk: "0_C",
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
      return pack(encodeTransaction(transaction(result.outcome, result.wallet)), seed);
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
      return pack(Buffer.concat([encodeTransaction(transaction(event, wallet)), field(900, 2, info)]), seed);
    },
    history(token: string, form: URLSearchParams, summary = false) {
      // 查询真实结算记录，正常轮次一笔对应一组历史。
      const context = p.context(method(service, "connection"));
      let records: any[];
      try {
        const player = method(service.sessions, "_player", context.value, token);
        const query = method(context.value, "execute", "SELECT response_json,created_at FROM spins WHERE player_id=? AND game_id=? ORDER BY id DESC", p.tuple([p.item(player, "id"), "cash-mania"]));
        records = Array.from(p.iter(method(query, "fetchall"))).map((row: any) => {
          const result = JSON.parse(p.item(row, "response_json")), event = result.outcome, tx = transaction(event, result.wallet), timestamp = p.item(row, "created_at") * 1000;
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
