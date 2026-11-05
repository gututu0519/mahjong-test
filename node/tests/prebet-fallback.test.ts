import { test } from "node:test";
import assert from "node:assert/strict";
import { plan } from "../games/buffalo-win/service.js";
import type { BuffaloWin } from "../games/buffalo-win/engine.js";
function choose(range: any[], totals: number[]) {
  let attempt = 0;
  const game = {
    version: "test",
    ruleset_id: "test",
    step(state: any, _bet: any, _seed: string, sid: string) {
      if (state.phase === "ready") {
        const index = attempt++;
        return {
          state: { sid, phase: "free", index },
          event: {},
          debit_minor: 20,
          credit_minor: 0,
        };
      }
      return {
        state: { sid, phase: "ready" },
        event: { selected: state.index },
        debit_minor: 0,
        credit_minor: totals[Math.min(state.index, totals.length - 1)],
      };
    },
  } as unknown as BuffaloWin;
  return plan(game, {
    state: { sid: "0", phase: "ready" },
    bet: { coin_minor: 2, level: 1 },
    seed: "fallback",
    round_id: "fallback-round",
    range,
  });
}
test("unavailable 0.56x selects closest lower complete candidate without rounding its payout", () => {
  const r = choose(["0.56", "0.56"], [4, 12, 10, 8]);
  assert.equal(r.total_credit_minor, 10);
  assert.equal(r.steps.length, 2);
  assert.equal(r.steps[1].candidate.event.selected, 2);
  assert.equal(r.resolution.selection, "nearest_lower_candidate");
  assert.equal(r.resolution.nearest_scope, "searched_candidates");
  assert.equal(r.attempts, 3000);
  assert.deepEqual(r.resolution.actual_multiplier, {
    numerator: 10,
    denominator: 20,
  });
});
test("unavailable 10x selects 9x over earlier 7x, never 10.5x", () => {
  const r = choose([10, 10], [140, 210, 180, 160]);
  assert.equal(r.total_credit_minor, 180);
  assert.equal(r.resolution.selection, "nearest_lower_candidate");
});
test("an exact match is preferred over earlier lower candidates", () => {
  const r = choose([10, 10], [180, 200]);
  assert.equal(r.total_credit_minor, 200);
  assert.equal(r.attempts, 2);
  assert.equal(r.resolution.selection, "within_range");
});
test("a supported interval keeps its original range, unsupported interval falls down", () => {
  assert.equal(choose([5, 10], [80, 140]).total_credit_minor, 140);
  assert.equal(choose([5, 10], [80, 60]).total_credit_minor, 80);
});
test("integer monetary ceiling is safe to return early, and zero upper bound stays zero", () => {
  const r = choose(["0.56", "0.56"], [11]);
  assert.equal(r.total_credit_minor, 11);
  assert.equal(r.attempts, 1);
  assert.equal(r.resolution.nearest_scope, "monetary_ceiling");
  assert.equal(choose([-1, 0], [1, 0]).total_credit_minor, 0);
  assert.throws(() => choose([-1, 0], [1]), {
    code: "PREBET_RANGE_UNREACHABLE",
  });
});
