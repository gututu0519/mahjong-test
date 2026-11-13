import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { BuffaloWin } from "../../games/buffalo-win/backend/native/engine.js";
const config = JSON.parse(readFileSync("config/buffalo-win.json", "utf8")),
  fixture = JSON.parse(readFileSync("fixtures/buffalo-python.json", "utf8"));
test("Python reference: identical ruleset and 346 ordinary/purchased/free/extension steps", () => {
  const game = new BuffaloWin(config);
  assert.equal(game.ruleset_id, fixture.ruleset_id);
  for (const f of fixture.cases)
    assert.deepEqual(
      game.step(f.state, f.bet, f.seed, f.sid),
      f.expected,
      `step ${f.sid}`,
    );
});
test("locked bet and buy-free preserve ongoing rounds", () => {
  const g = new BuffaloWin(config),
    f = fixture.cases.find((f) => f.state.phase !== "ready");
  assert.throws(() => g.step(f.state, { coin_minor: 3, level: 2 }, "a", "b"), {
    code: "BET_LOCKED",
  });
  assert.throws(() => g.step(f.state, { ...f.bet, buy_free: true }, "a", "b"), {
    code: "FEATURE_LOCKED",
  });
});
