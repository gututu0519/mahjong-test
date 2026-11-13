import { test } from "node:test";
import assert from "node:assert/strict";
import { plan } from "../../games/buffalo-win/backend/native/service.js";
import type { BuffaloWin } from "../../games/buffalo-win/backend/native/engine.js";

for (const buy_free of [false, true])
  test(`zero upper bound rejects a positive free continuation, purchase=${buy_free}`, () => {
    for (const range of [
      [-1, 0],
      ["-1", "0"],
      [0, 0],
    ]) {
      let attempt = 0;
      const game = {
        version: "test",
        ruleset_id: "test",
        step(state: any, bet: any, _seed: string, sid: string) {
          if (state.phase === "ready") {
            attempt++;
            return {
              state: { sid, phase: "free" },
              event: {},
              debit_minor: buy_free ? 7500 : 100,
              credit_minor: 0,
            };
          }
          return {
            state: { sid, phase: "ready" },
            event: {},
            debit_minor: 0,
            credit_minor: attempt === 1 ? 50 : 0,
          };
        },
      } as unknown as BuffaloWin;
      const r = plan(game, {
        state: { sid: "0", phase: "ready" },
        bet: { coin_minor: 10, level: 1, buy_free },
        seed: "zero-cap",
        round_id: "test-round",
        range,
      });
      assert.equal(r.total_credit_minor, 0);
      assert.equal(r.attempts, 2);
      assert.equal(r.steps.length, 2);
      assert.equal(
        r.steps.reduce((n: number, s: any) => n + s.candidate.credit_minor, 0),
        0,
      );
    }
  });

test("zero upper bound never relaxes to a positive payout when no legal zero round exists", () => {
  const game = {
    step(_state: any, _bet: any, _seed: string, sid: string) {
      return {
        state: { sid, phase: "ready" },
        event: {},
        debit_minor: 100,
        credit_minor: 1,
      };
    },
  } as unknown as BuffaloWin;
  assert.throws(
    () =>
      plan(game, {
        state: { sid: "0", phase: "ready" },
        bet: { coin_minor: 10, level: 1 },
        seed: "positive-only",
        round_id: "test-round",
        range: [-1, 0],
      }),
    { code: "PREBET_RANGE_UNREACHABLE" },
  );
});
