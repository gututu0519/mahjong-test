import * as py from "../compat/runtime.js";
import { method } from "./local.js";
import { check, sha } from "../shared/core.js";
import { RoundChoice } from "../shared/prebet.js";
import { multiplier } from "../gateway/catalog.js";
import { extremes, selectRound } from "../games/round-model.js";

export const invokeEngine = (engine: any, name: string, ...args: any[]) =>
  py.plain(method(engine, name, ...args.map(py.from)));

// Planning is performed inside the selected game process, never in the gateway.
// The seed schedule matches the existing persisted prebet contract exactly.
export function prebetPlan(code: string, engine: any, q: any) {
  const first = invokeEngine(engine, "step", q.state, q.bet, q.seed, q.sid);
  const choice = new RoundChoice<any>(
    q.range,
    first.debit_minor,
    multiplier(q.range[0]),
    multiplier(q.range[1]),
  );
  for (let attempt = 0; attempt < 3000; attempt++) {
    const root = sha(q.seed + ":plan:" + attempt);
    let current = structuredClone(q.state),
      total = 0,
      done = false;
    for (let i = 0; i < 4096; i++) {
      let command = { ...q.payload };
      if (current.phase !== "ready") {
        if (code === "tower-run-treasure-steps")
          command = {
            action: current.phase === "collect" ? "collect" : "continue",
          };
        else if (Object.hasOwn(py.plain(py.attr(engine, "config")), "costs"))
          command = { action: "confirm", round_id: current.pending.round_id };
        else if (
          [
            "gates-of-olympus",
            "sweet-bonanza-pop",
            "big-bass-bonanza",
          ].includes(code)
        )
          command = {
            ...q.payload,
            action: current.phase === "collect" ? "collect" : "spin",
            request_index: (q.payload.request_index ?? 0) + i,
          };
        else delete command.buy_free;
      }
      const out = invokeEngine(
        engine,
        "step",
        current,
        invokeEngine(engine, "normalize_bet", command),
        sha(root + ":" + i),
        String(Number(q.sid) + i),
      );
      total += out.credit_minor;
      check(Number.isSafeInteger(total), "AMOUNT_INVALID");
      current = out.state;
      if (choice.above(total)) break;
      if (current.phase === "ready") {
        done = true;
        break;
      }
    }
    if (
      done &&
      choice.consider(
        {
          seed: root,
          total_credit_minor: total,
          basis_minor: first.debit_minor,
        },
        total,
        attempt + 1,
      )
    )
      return choice.finish(attempt + 1);
  }
  return choice.finish(3000);
}

export function rtpPlan(code: string, engine: any, q: any) {
  check(
    Number.isInteger(q.candidates) && q.candidates >= 1 && q.candidates <= 4096,
    "INVALID_ARGUMENT",
  );
  const pair = extremes(
    code,
    engine,
    q.state,
    q.payload,
    q.seed,
    q.sid,
    q.candidates,
  );
  const plan = selectRound(pair, q.upper_probability, q.seed);
  delete plan.terminal_state;
  return plan;
}
