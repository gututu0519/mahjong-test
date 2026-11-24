import { test } from "node:test";
import { createHash } from "node:crypto";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import * as p from "../shared/compat/runtime.js";
import * as protocol from "../shared/migrated/py/adapters/pg/protocol.js";
import { DatabaseSync } from "../shared/database/connection.js";
import { CashMania, evaluateBoard, normalRtp, normalizeBet } from "../../games/cash-mania/backend/engine/engine.js";
import { observedNormalSpins } from "../../games/cash-mania/backend/fixtures/normal_spins.js";
import { decodeTransaction, encodeTransaction, pack, roundPresentation, SALT, transaction } from "../../games/cash-mania/backend/adapters/cash_mania.js";
import { build_server } from "../../games/cash-mania/backend/services/cash_mania_demo.js";
import { GAME_CODES } from "../../gateway/src/catalog.js";
import { handlerFor, method } from "../shared/services/local.js";
import { computeServer } from "../shared/services/compute.js";
import { listen } from "../shared/http.js";

const configPath = () => p.sourcePath("services/cash-mania/config/cash-mania.json");
const config = () => JSON.parse(readFileSync(configPath(), "utf8"));
const field = (id: number, kind: number, value: any): Buffer => p.call(protocol.field, [id, kind, value]);
const text = (id: number, value: string): Buffer => p.call(protocol.text_field, [id, value]);
const double = (id: number, value: number): Buffer => p.call(protocol.double_field, [id, value]);
const decode = (body: Buffer) => {
  const [raw] = p.call(protocol.unpack, [body, null, SALT]);
  return decodeTransaction(raw);
};

test("Cash Mania：原始普通局证据的中线金额与奖励一致", () => {
  const c = config();
  assert.ok(observedNormalSpins.length >= 49);
  for (const sample of observedNormalSpins) {
    const result = evaluateBoard(c, sample.board, normalizeBet(c, { cs: sample.cs, ml: sample.ml }));
    assert.equal(result.win_minor, Math.round(sample.win * 100), `抓取 ${sample.record}`);
    result.values.forEach((v, i) => assert.ok(Math.abs(v - sample.values[i]) < 1e-8, `抓取 ${sample.record} 第 ${i} 格`));
  }
  assert.equal(c.original_probability_verified, false);
  assert.ok(Math.abs(normalRtp(c) - 0.927165) < 1e-10);
});

test("Cash Mania：不同请求种子的传输字节与抓取使用的独立实现一致", () => {
  // 测试载荷使用 0..240，仅种子和包长来自抓取，不含原站会话。
  const data = Buffer.from(Array.from({ length: 241 }, (_, i) => i));
  const fixtures: [number, string][] = [
    [46, "78764b92885092de042e180e5d95b338cb26bb565d74d443a02a53c70b5e9b71"],
    [84, "3bcb9da85c0ad2bd991fe67e389a31aaf28c0be68ac533b788c014a4e84f7226"],
    [92, "077ca47a482e64be2162c04948a3d0434ca0f9f7aae078099f59878764575642"],
    [132, "e8b42e5ff6567703887c8b6b2973889160975573fbc96c6d6fa9449ea306d5bb"],
  ];
  for (const [seed, expected] of fixtures) assert.equal(createHash("sha256").update(pack(data, seed)).digest("hex"), expected);
});

test("Cash Mania：抓取中三种实际回包的中间盘面和中奖分类可还原", () => {
  // 直接取原回应中的游戏字段。排除会话、局号、钱包、认证及时间字段。
  const fixtures: [number, string][] = [
    [1027, "18012001799a9999999999c93f81019a9999999999c93f8901000000000000f03f980301a1037b14ae47e17a943faa0309010304010403030302b80401aa0609080112050a03010407b2060b080111000000000000f03fb9069a9999999999c93fd206487b14ae47e17a943f9a9999999999c93f000000000000f03f000000000000f03f000000000000144000000000000008409a9999999999c93f9a9999999999c93f9a9999999999b93fda0609010304020001030302e206487b14ae47e17a943f9a9999999999c93f000000000000f03f00000000000000400000000000000000000000000000f03f9a9999999999c93f9a9999999999c93f9a9999999999b93ffa060408011005"],
    [2617, "1801200179333333333333f33f8101333333333333f33f89010000000000003840980306a1037b14ae47e17a943faa0309040304030703020301b80403aa0609080112050a03010407b2060b0801110000000000003840b906333333333333f33fd206480000000000001840333333333333f33f0000000000001840000000000000084000000000000034400000000000000840333333333333e33f333333333333f33fb81e85eb51b8be3fda0609040304030703020301ea0609040304030703020401f206480000000000001840333333333333f33f0000000000001840000000000000084000000000000034400000000000000840333333333333e33f0000000000001840b81e85eb51b8be3f"],
    [13533, "18012001799a9999999999c93f81019a9999999999c93f89010000000000004e40980301a1037b14ae47e17a943faa0309040503070804010504b80404aa0609080112050a03010407b2060b0801110000000000004e40b9060000000000000040d20648000000000000f03f00000000000000409a9999999999c93f00000000000034400000000000003e4000000000000014407b14ae47e17a943f0000000000000040000000000000f03fda0609040503070804010504"],
  ];
  for (const [record, bytes] of fixtures) {
    const raw = decodeTransaction(Buffer.from(bytes, "hex"));
    assert.deepEqual(decodeTransaction(encodeTransaction(raw)), raw);
    const presentation = roundPresentation(raw);
    const bet = normalizeBet(config(), { cs: raw.cs, ml: raw.ml });
    const scored = evaluateBoard(config(), presentation.board, bet);
    assert.deepEqual(scored.values, raw.rv);
    assert.equal(scored.win_minor, Math.round(raw.tw * 100));
    const event = { ...presentation, bet, sid: "test", round_id: "test", winning_positions: raw.wp,
      win_minor: scored.win_minor, base_win_minor: scored.base_win_minor, debit_minor: Math.round(raw.tb * 100), base_bet_minor: Math.round(raw.tbb * 100) };
    const tx = transaction(event, { before_minor: 1000, debit_minor: event.debit_minor, after_minor: 1000 - event.debit_minor + event.win_minor }, config());
    assert.deepEqual(roundPresentation(decodeTransaction(encodeTransaction(tx))), presentation);
    if (record === 1027) { assert.deepEqual(presentation.nudge_from_position, { "1": 5 }); assert.equal(presentation.original_board[4], 0); assert.equal(presentation.board[4], 4); }
    if (record === 2617) { assert.equal(presentation.respin_board[7], 4); assert.equal(presentation.board[7], 3); assert.equal(tx.tb, 1.2); assert.equal(tx.tw, 24); }
    if (record === 13533) assert.equal(tx.gwt, 4);
  }
  const old = Buffer.concat([double(106, 2), double(106, 5)]);
  assert.deepEqual(decodeTransaction(old).rv, [2, 5]);
  assert.throws(() => decodeTransaction(field(106, 2, Buffer.alloc(7))));
  const valid = { rl: Array(9).fill(1), rv: Array(9).fill(1) };
  assert.throws(() => roundPresentation({ ...valid, rsrl: valid.rl }));
  assert.throws(() => roundPresentation({ ...valid, nfp: { "1": 5 } }));
  assert.deepEqual(roundPresentation(valid), { board: valid.rl, reel_values: valid.rv });
});

test("Cash Mania：确定性生成、整数结算、下注边界和未实现状态", () => {
  const c = config(), engine = p.call(CashMania, [configPath()]), initial = method(engine, "initial_state", "test"), bet = method(engine, "normalize_bet", p.from({ cs: 0.02, ml: 1 }));
  assert.deepEqual(p.plain(bet), { coin_minor: 2, level: 1 });
  assert.deepEqual(p.plain(method(engine, "normalize_bet", p.from({ coin_minor: 20, level: 10 }))), { coin_minor: 20, level: 10 });
  for (const invalid of [{ cs: 0.03, ml: 1 }, { cs: 0.02, ml: 11 }, { cs: 0.02, ml: 1, fb: 1 }, { cs: 0.02, coin_minor: 2 }, { cs: "0.02" }, { coin_minor: true }, []]) {
    assert.throws(() => method(engine, "normalize_bet", p.from(invalid)));
  }
  const boards = new Set<string>();
  for (let i = 0; i < 400; i++) {
    const args = [initial, bet, "test-seed-" + i, String(i + 1)];
    const a = p.plain(method(engine, "step", ...args)), b = p.plain(method(engine, "step", ...args));
    assert.deepEqual(a, b);
    assert.equal(a.debit_minor, 20);
    assert.equal(a.state.phase, "ready");
    assert.equal(a.credit_minor, a.event.win_minor);
    assert.ok(Number.isSafeInteger(a.credit_minor) && a.credit_minor >= 0);
    assert.equal(a.event.free, null);
    assert.equal(a.event.board.length, 9);
    assert.ok([0, 2, 3, 5, 6, 8].every(index => a.event.board[index] > 0), "原客户端的上下行不能出现空符号");
    boards.add(a.event.board.join(","));
  }
  assert.ok(boards.size > 350, "结果应由随机种子生成，不能循环回放有限样本");
  assert.throws(() => method(engine, "step", p.from({ ...p.plain(initial), phase: "free" }), bet, "a", "1"), (e: any) => e.code === "FEATURE_UNSUPPORTED");
  assert.equal(normalizeBet(c, {}).coin_minor, 2);
  const boundary = { ...c, side_weights: [0x100000000, 0, 0, 0, 0, 0] };
  const boundaryEngine = p.call(CashMania, [p.from(boundary)]);
  assert.equal(p.plain(method(boundaryEngine, "step", initial, bet, "maximum-weight", "1")).credit_minor, 0);
  assert.throws(() => p.call(CashMania, [p.from({ ...boundary, side_weights: [0x100000001, 0, 0, 0, 0, 0] })]), (e: any) => e.code === "CONFIG_INVALID");
});

test("Cash Mania：旧回合的上下行空格可恢复显示，保留原始余额、支付线和空停位置", () => {
  const c = config(), bet = { coin_minor: 2, level: 1 };
  const final = [1, 0, 3, 1, 4, 1, 2, 1, 0];
  const original = [1, 0, 3, 0, 0, 0, 2, 1, 0];
  const interim = [0, 0, 0, 1, 4, 1, 2, 1, 0];
  const event = { sid: "43", round_id: "43", bet, board: final, reel_values: evaluateBoard(c, final, bet).values,
    win_minor: 0, base_win_minor: 0, debit_minor: 20, base_bet_minor: 20 };
  const wallet = { before_minor: 200000, debit_minor: 20, after_minor: 199980 };
  const stored = JSON.stringify(event);
  const render = (extra: object) => decodeTransaction(encodeTransaction(transaction({ ...event, ...extra }, wallet, c)));
  const base = render({});
  assert.deepEqual(base.rl, [1, 0, 3, 1, 4, 1, 2, 1, 2]);
  assert.deepEqual(base.orl, base.rl);
  assert.deepEqual(base.rv, evaluateBoard(c, base.rl, bet).values);
  assert.equal(base.bl, 1999.8);
  assert.equal(base.tw, 0);
  assert.equal(JSON.stringify(event), stored);
  for (const [symbols, valueField, symbolField] of [[original, "orv", "orl"], [interim, "rsrv", "rsrl"]] as const) {
    const values = evaluateBoard(c, symbols, bet).values;
    const tx = render(symbolField === "orl" ? { original_board: symbols, original_values: values } : { respin_board: symbols, respin_values: values });
    const displayed = tx[symbolField];
    assert.ok([0, 2, 3, 5, 6, 8].every(i => displayed[i] > 0));
    for (const i of c.payline) assert.equal(displayed[i], symbols[i]);
    assert.deepEqual(tx[valueField], evaluateBoard(c, displayed, bet).values);
  }
});

test("Cash Mania：二进制商户请求、幂等、拒绝扣款和重开恢复", t => {
  // 明确拒绝把此测试指向非隔离 PostgreSQL 配置。
  if (process.env.GTT_PG_CONFIG) assert.equal(JSON.parse(readFileSync(process.env.GTT_PG_CONFIG, "utf8")).testMode, true);
  const dir = mkdtempSync(join(tmpdir(), "cash-mania-test-")), database = join(dir, "session.sqlite3");
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  let app = p.call(build_server, [0, database, configPath()]);
  assert.equal(p.plain(app.auth).uiogc.bf, 1, "保留原捕获的购买入口标志，缺少结算能力不得隐藏入口");
  assert.equal(p.plain(app.auth).jc.bf, 1);
  app.service.merchant_bet_type = 1;
  const session = p.plain(method(app.service, "create_session")), token = session.token;
  const initial = p.plain(method(app.service, "state", token, "cash-mania"));
  const spin = (previous: string, options: any = {}, seed = 37) => pack(Buffer.concat([
    text(1, token), field(2, 0, options.btt ?? 1), field(3, 0, 1), text(5, previous), text(12, "0_C"), double(21, options.cs ?? 0.02), field(22, 0, 1),
    ...(options.fb ? [field(24, 0, options.fb)] : []), ...(options.ab ? [field(31, 0, options.ab)] : []),
  ]), seed);
  const infoRequest = pack(text(1, token), 67);
  const before = decode(app.pg.game_info(infoRequest, token));
  assert.equal(before.sid, "0");
  assert.equal(before.bl * 100, initial.balance_minor);
  assert.equal(GAME_CODES[19], "cash-mania");
  assert.equal(SALT, 23);
  for (const options of [{ btt: 2 }, { fb: 1 }, { fb: 2 }, { ab: 1 }, { cs: 0.03 }]) {
    assert.throws(() => app.pg.spin(spin("0", options), token));
    assert.equal(p.plain(method(app.service, "wallet", token)).balance_minor, initial.balance_minor);
  }
  const body = spin("0"), response = app.pg.spin(body, token), tx = decode(response);
  assert.equal(tx.tb, 0.2);
  assert.ok(Math.abs(tx.bl - (tx.blb - tx.tb + tx.tw)) < 1e-8);
  assert.deepEqual(app.pg.spin(body, token), response);
  assert.deepEqual(decode(app.pg.spin(spin("0", {}, 93), token)), tx, "传输seed变化不能重复结算");
  assert.equal(p.plain(method(app.service, "history", token, 20)).length, 1);
  assert.equal(app.pg.history(token, new URLSearchParams(), true).dt.bs.bc, 1);
  assert.throws(() => app.pg.spin(spin("0", { cs: 0.2 }), token), (e: any) => e.code === "STALE_STATE");
  const after = p.plain(method(app.service, "wallet", token)).balance_minor;
  const ledger = new DatabaseSync(database);
  try { assert.equal(ledger.prepare("SELECT COUNT(*) AS count FROM ledger WHERE kind='spin'").get().count, 1); } finally { ledger.close(); }
  app = p.call(build_server, [0, database, configPath()]);
  app.service.merchant_bet_type = 1;
  assert.equal(p.plain(method(app.service, "wallet", token)).balance_minor, after);
  assert.deepEqual(decode(app.pg.game_info(infoRequest, token)), tx, "重连GameInfo应恢复最后结算盘面");
  assert.deepEqual(app.pg.spin(body, token), response);
  const handler = handlerFor(app, { url: "/game-api/cash-mania/v4/Spin", method: "POST", headers: { host: "127.0.0.1", "content-type": "application/octet-stream", "content-length": String(body.length), "x-local-game-session": token }, socket: { remoteAddress: "127.0.0.1" } } as any, body);
  method(handler, "do_POST");
  assert.equal(handler.__status, 200);
  assert.deepEqual(Buffer.concat(handler.__chunks), response);
  assert.equal(p.plain(method(app.service, "wallet", token)).balance_minor, after);
});

test("Cash Mania：独立计算服务鉴权与远程确定性结果", async t => {
  const secret = "cash-mania-isolated-compute-test-".repeat(2), server = computeServer("cash-mania", configPath(), secret);
  const port = await listen(server), origin = "http://127.0.0.1:" + port;
  t.after(async () => { server.closeAllConnections(); await new Promise<void>(ok => server.close(() => ok())); });
  assert.equal((await fetch(origin + "/health")).status, 401);
  const post = async (path: string, body: any) => {
    const response = await fetch(origin + path, { method: "POST", headers: { authorization: "Bearer " + secret, "content-type": "application/json" }, body: JSON.stringify(body), signal: AbortSignal.timeout(10000) });
    assert.equal(response.status, 200, await response.clone().text()); return (await response.json()).data;
  };
  const descriptor = await post("/v1/describe", {});
  assert.equal(descriptor.game_id, "cash-mania");
  assert.equal(descriptor.minor_unit, 100);
  assert.equal(descriptor.config.original_probability_verified, false);
  const state = await post("/v1/initial", { seed: "remote-test" }), bet = { cs: 0.02, ml: 1 };
  assert.deepEqual(await post("/v1/normalize", { bet }), { coin_minor: 2, level: 1 });
  const body = { state, bet, seed: "remote-spin", operation_id: "1", expected_ruleset: descriptor.ruleset_id };
  const first = await post("/v1/step", body), second = await post("/v1/step", body);
  assert.deepEqual(first, second);
  assert.equal(first.debit_minor, 20);
  assert.equal(first.state.phase, "ready");
  const local = p.call(CashMania, [p.from(descriptor.config)]);
  assert.deepEqual(first, p.plain(method(local, "step", p.from(state), p.from(bet), body.seed, body.operation_id)));
});
