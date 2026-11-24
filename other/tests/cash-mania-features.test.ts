import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import * as p from "../shared/compat/runtime.js";
import * as protocol from "../shared/migrated/py/adapters/pg/protocol.js";
import { DatabaseSync } from "../shared/database/connection.js";
import { method } from "../shared/services/local.js";
import { CashMania, evaluateBoard, normalRtp } from "../../games/cash-mania/backend/engine/engine.js";
import { decodeTransaction, encodeTransaction, pack, roundPresentation, SALT, transaction } from "../../games/cash-mania/backend/adapters/cash_mania.js";
import { build_server } from "../../games/cash-mania/backend/services/cash_mania_demo.js";

type Feature = "nudge" | "respin";
const loadConfig = () => JSON.parse(readFileSync(p.sourcePath("services/cash-mania/config/cash-mania.json"), "utf8"));
function legacyConfig() {
  const c = loadConfig();
  delete c.presentation_model;
  delete c.presentation_weights;
  c.supported_features = ["normal-spin"];
  c.unsupported_features = ["free-spins", "respin", "nudge", "feature-buy", "ante"];
  return c;
}
function featureConfig(feature?: Feature, guaranteedWin = false) {
  const c = legacyConfig();
  c.presentation_model = "local-outcome-preserving-v1";
  c.presentation_weights = feature
    ? { normal: 0, nudge: feature === "nudge" ? 1 : 0, respin: feature === "respin" ? 1 : 0 }
    : { normal: 2, nudge: 1, respin: 1 };
  c.supported_features = ["normal-spin", "nudge", "respin"];
  c.unsupported_features = ["free-spins", "feature-buy", "ante"];
  if (guaranteedWin) {
    // 用合法配置确保结算中奖，避免集成测试靠随机碰到特效。
    c.side_weights = [0, 0, 1, 0, 0, 0];
    c.middle_weights = [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0];
  }
  return c;
}
function step(c: any, seed: string, sid = "1") {
  const engine = p.call(CashMania, [p.from(c)]);
  const state = method(engine, "initial_state", "features-test");
  return p.plain(method(engine, "step", state, p.from({ coin_minor: 2, level: 1 }), seed, sid));
}
function assertFeature(event: any, feature: Feature) {
  assert.ok(event.win_minor > 0);
  assert.equal(event.phase, "ready");
  assert.equal(event.next_phase, "ready");
  assert.equal(event.free, null);
  assert.equal(event.debit_minor, 20, "中间动画不能另扣一次投注");
  assert.equal(event.round_id, event.sid, "同一付费局的表现不能创建新回合");
  if (feature === "nudge") {
    assert.deepEqual(event.nudge_from_position, { "1": 5 });
    assert.equal(event.original_board[4], 0);
    assert.equal(event.original_values[4], 0);
    assert.ok(event.original_board[3] >= 1 && event.original_board[3] <= 11);
    assert.ok(event.original_board[5] >= 1 && event.original_board[5] <= 11);
    for (const i of [0, 1, 2, 6, 7, 8]) {
      assert.equal(event.original_board[i], event.board[i]);
      assert.equal(event.original_values[i], event.reel_values[i]);
    }
    assert.equal(event.respin_board, undefined);
    assert.equal(event.respin_values, undefined);
  } else {
    assert.deepEqual(event.original_board, event.board);
    assert.equal(event.respin_board.length, 9);
    assert.equal(event.respin_values.length, 9);
    const changed = event.respin_board.flatMap((value: number, i: number) => value === event.board[i] ? [] : [i]);
    assert.equal(changed.length, 1);
    assert.ok(changed[0] === 1 || changed[0] === 7);
    assert.ok(event.respin_board[changed[0]] >= 1 && event.respin_board[changed[0]] <= 5);
    assert.notEqual(event.respin_board[1], event.respin_board[7]);
    assert.equal(event.nudge_from_position, undefined);
  }
}

test("Cash Mania 特殊表现：增加表现不改变同种子的最终盘面、派彩和理论返还", () => {
  const old = legacyConfig(), current = featureConfig();
  assert.equal(normalRtp(old), normalRtp(current));
  for (let i = 0; i < 200; i++) {
    const seed = "cash-mania-outcome-" + i;
    const before = step(old, seed), after = step(current, seed);
    assert.deepEqual(after, step(current, seed), "表现也必须可重算");
    assert.deepEqual(after.event.board, before.event.board);
    assert.deepEqual(after.event.reel_values, before.event.reel_values);
    assert.equal(after.credit_minor, before.credit_minor);
    assert.equal(after.debit_minor, before.debit_minor);
    assert.deepEqual(after.event.winning_positions, before.event.winning_positions);
    assert.deepEqual(after.event.line_awards_minor, before.event.line_awards_minor);
    assert.deepEqual(after.state.last_event, after.event);
    assert.equal(before.event.nudge_from_position, undefined, "历史配置保持普通旋转");
    assert.equal(before.event.respin_board, undefined);
    if (after.credit_minor === 0) {
      assert.equal(after.event.nudge_from_position, undefined);
      assert.equal(after.event.respin_board, undefined);
    }
  }
});

for (const feature of ["nudge", "respin"] as const) {
  test(`Cash Mania ${feature}：合法中间盘面、确定性和协议往返`, () => {
    const c = featureConfig(feature, true);
    for (let i = 0; i < 25; i++) {
      const result = step(c, "feature-evidence-" + i), event = result.event;
      assertFeature(event, feature);
      assert.deepEqual(result, step(c, "feature-evidence-" + i));
      assert.equal(event.win_minor, 50);
      const intermediate = feature === "nudge" ? event.original_board : event.respin_board;
      const values = feature === "nudge" ? event.original_values : event.respin_values;
      const scored = evaluateBoard(c, intermediate, event.bet);
      assert.equal(scored.win_minor, 0, "已观察的中间盘面不能提前显示最终中奖");
      assert.deepEqual(values, scored.values);
      const tx = transaction(event, { before_minor: 1000, debit_minor: result.debit_minor, after_minor: 1030 }, c);
      const decoded = decodeTransaction(encodeTransaction(tx));
      assert.deepEqual(roundPresentation(decoded), roundPresentation(tx));
      assert.equal(decoded.st, 1);
      assert.equal(decoded.nst, 1);
      assert.equal(decoded.tb, 0.2);
      assert.equal(decoded.tw, 0.5);
      assert.ok(Math.abs(decoded.bl - (decoded.blb - decoded.tb + decoded.tw)) < 1e-8);
    }
    const engine = p.call(CashMania, [p.from(c)]);
    for (const forbidden of [{ feature }, { presentation: feature }, { presentation_weights: { [feature]: 1 } }]) {
      assert.throws(() => method(engine, "normalize_bet", p.from({ coin_minor: 2, level: 1, ...forbidden })),
        (error: any) => error.code === "FEATURE_UNSUPPORTED", "玩家请求不能选择或控制表现");
    }
  });

  test(`Cash Mania ${feature}：单次结算、重复传输和重开恢复保持同一表现`, t => {
    if (process.env.GTT_PG_CONFIG) assert.equal(JSON.parse(readFileSync(process.env.GTT_PG_CONFIG, "utf8")).testMode, true);
    const dir = mkdtempSync(join(tmpdir(), "cash-mania-features-"));
    const database = join(dir, "session.sqlite3"), configuration = join(dir, "cash-mania.json");
    t.after(() => rmSync(dir, { recursive: true, force: true }));
    writeFileSync(configuration, JSON.stringify(featureConfig(feature, true)));
    let app = p.call(build_server, [0, database, configuration]);
    app.service.merchant_bet_type = 1;
    const session = p.plain(method(app.service, "create_session")), token = session.token;
    const before = p.plain(method(app.service, "wallet", token)).balance_minor;
    const field = (id: number, type: number, value: any): Buffer => p.call(protocol.field, [id, type, value]);
    const text = (id: number, value: string): Buffer => p.call(protocol.text_field, [id, value]);
    const double = (id: number, value: number): Buffer => p.call(protocol.double_field, [id, value]);
    const body = (seed: number) => pack(Buffer.concat([
      text(1, token), field(2, 0, 1), field(3, 0, 1), text(5, "0"), text(12, "0_C"), double(21, 0.02), field(22, 0, 1),
    ]), seed);
    const decode = (bytes: Buffer) => decodeTransaction(p.call(protocol.unpack, [bytes, null, SALT])[0]);
    const request = body(37), response = app.pg.spin(request, token), tx = decode(response);
    const state = p.plain(method(app.service, "state", token, "cash-mania")).state;
    assertFeature(state.last_event, feature);
    assert.equal(tx.tb, 0.2);
    assert.equal(tx.tw, 0.5);
    assert.deepEqual(app.pg.spin(request, token), response);
    assert.deepEqual(decode(app.pg.spin(body(93), token)), tx, "传输 seed 改变仍为原结算");
    assert.equal(p.plain(method(app.service, "wallet", token)).balance_minor, before + 30);
    assert.equal(p.plain(method(app.service, "history", token, 20)).length, 1);
    assert.equal(app.pg.history(token, new URLSearchParams(), true).dt.bs.bc, 1);
    const ledger = new DatabaseSync(database);
    try {
      const rows = ledger.prepare("SELECT debit_minor,credit_minor,balance_before,balance_after FROM ledger WHERE kind='spin'").all();
      assert.equal(rows.length, 1);
      assert.equal(rows[0].debit_minor, 20);
      assert.equal(rows[0].credit_minor, 50);
      assert.equal(rows[0].balance_before, before);
      assert.equal(rows[0].balance_after, before + 30);
      const saved = ledger.prepare("SELECT response_json,state_json FROM spins").all();
      assert.equal(saved.length, 1);
      assert.deepEqual(JSON.parse(saved[0].state_json).last_event, state.last_event);
      assert.deepEqual(JSON.parse(saved[0].response_json).outcome, state.last_event);
    } finally { ledger.close(); }
    app = p.call(build_server, [0, database, configuration]);
    app.service.merchant_bet_type = 1;
    assert.deepEqual(decode(app.pg.game_info(pack(text(1, token), 67), token)), tx);
    assert.deepEqual(app.pg.spin(request, token), response);
    assert.deepEqual(p.plain(method(app.service, "state", token, "cash-mania")).state, state);
    assert.equal(p.plain(method(app.service, "wallet", token)).balance_minor, before + 30);
  });
}
