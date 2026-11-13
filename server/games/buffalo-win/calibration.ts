import { BuffaloWin } from "./engine.js";
import { sha, clone, check, pythonJSON, now } from "../../shared/core.js";
import { parentPort, workerData, isMainThread } from "node:worker_threads";
export function sample(
  config: any,
  buy: boolean,
  count: number,
  seed: string,
  progress = (v: any) => {},
) {
  const game = new BuffaloWin(config),
    cost = 20 * (buy ? 75 : 1);
  let sum = 0n,
    squares = 0n,
    steps = 0,
    largest = 0;
  for (let i = 0; i < count; i++) {
    let state: any = game.initial_state(),
      credit = 0,
      paid = 0;
    for (let j = 0; j < 4096; j++) {
      const r = game.step(
        state,
        {
          coin_minor: 2,
          level: 1,
          ...(buy && j === 0 ? { buy_free: true } : {}),
        },
        sha(seed + ":" + i + ":" + j),
        i + ":" + j,
      );
      state = r.state;
      credit += r.credit_minor;
      paid += r.debit_minor;
      steps++;
      if (state.phase === "ready") break;
      check(j < 4095, "RTP_UNFINISHED_ROUND");
    }
    check(paid === cost, "RTP_INVALID_DEBIT");
    sum += BigInt(credit);
    squares += BigInt(credit) ** 2n;
    largest = Math.max(largest, credit);
    if (i % 1000 === 0) progress({ done: i / count });
  }
  const mean = Number(sum) / (count * cost),
    variance =
      Math.max(0, (Number(squares) - Number(sum) ** 2 / count) / (count - 1)) /
      cost ** 2,
    half = 2.576 * Math.sqrt(variance / count);
  return {
    rounds: count,
    cost,
    credit: Number(sum),
    credit_squared: Number(squares),
    steps,
    largest_credit: largest,
    rtp: mean,
    ci_low: mean - half,
    ci_high: mean + half,
    ci_half: half,
    confidence: 0.99,
    seed,
    unfinished_rounds: 0,
  };
}
function configured(base: any, filler: number) {
  const c = clone(base);
  c.symbol_weights = Object.fromEntries(
    Object.entries(base.symbol_weights).map(([k, v]) => [k, Number(v) * 50]),
  );
  c.symbol_weights["2"] = Math.max(1, Math.min(10000, Math.round(filler * 50)));
  return c;
}
export function calibrate(
  base: any,
  target: number,
  progress = (v: any) => {},
) {
  check(
    Number.isInteger(target) && target >= 8000 && target <= 9900,
    "RTP_TARGET_INVALID",
  );
  const started = Date.now(),
    modes: any = {};
  for (const buy of [false, true]) {
    const name = buy ? "buy_free" : "normal",
      seed = "node-rtp-v1:" + target + ":" + name;
    let low = 1,
      high = 150;
    for (let i = 0; i < 9; i++) {
      const filler = (low + high) / 2,
        r = sample(
          configured(base, filler),
          buy,
          buy ? 2000 : 20000,
          seed + ":train",
          (v) =>
            progress({ mode: name, stage: "search", iteration: i + 1, ...v }),
        );
      progress({
        mode: name,
        stage: "search",
        iteration: i + 1,
        filler,
        rtp: r.rtp,
      });
      if (r.rtp > target / 10000) low = filler;
      else high = filler;
    }
    let filler = (low + high) / 2;
    const left = Math.max(1, filler - 3),
      right = Math.min(150, filler + 3),
      n = buy ? 20000 : 200000;
    const a = sample(configured(base, left), buy, n, seed + ":slope", (v) =>
        progress({ mode: name, stage: "slope", ...v }),
      ),
      b = sample(configured(base, right), buy, n, seed + ":slope", (v) =>
        progress({ mode: name, stage: "slope", ...v }),
      ),
      slope = (b.rtp - a.rtp) / (right - left);
    check(slope < 0, "RTP_CALIBRATION_FAILED");
    filler = Math.max(
      1,
      Math.min(150, left + (target / 10000 - a.rtp) / slope),
    );
    const attempts: any[] = [];
    for (let attempt = 0; attempt < 4; attempt++) {
      const config = configured(base, filler),
        v = sample(
          config,
          buy,
          buy ? 200000 : 2000000,
          seed + ":holdout:" + attempt,
          (x) =>
            progress({
              mode: name,
              stage: "validation",
              attempt: attempt + 1,
              ...x,
            }),
        ),
        passed =
          v.ci_low <= target / 10000 &&
          target / 10000 <= v.ci_high &&
          v.ci_half <= 0.015;
      attempts.push({ filler, report: v, passed });
      progress({
        mode: name,
        stage: "result",
        attempt: attempt + 1,
        rtp: v.rtp,
        passed,
      });
      if (passed) {
        modes[name] = { config, validation: v, attempts };
        break;
      }
      filler = Math.max(
        1,
        Math.min(150, filler + (target / 10000 - v.rtp) / slope),
      );
    }
    check(
      modes[name],
      "RTP_CALIBRATION_FAILED",
      "Independent holdout validation failed",
    );
  }
  return {
    format: 1,
    game_id: 1,
    engine_version: "1.2.0",
    target_bp: target,
    method:
      "complete-round Monte Carlo; 99% normal approximation; up to four independent validations per mode",
    certified_theoretical: false,
    created_at: now(),
    seconds: (Date.now() - started) / 1000,
    modes,
    model_hash: sha(
      pythonJSON(
        Object.fromEntries(
          Object.entries(modes).map(([k, v]: any) => [k, v.config]),
        ),
      ),
    ),
  };
}
if (!isMainThread) {
  try {
    parentPort!.postMessage({
      result: calibrate(workerData.config, workerData.target, (v) =>
        parentPort!.postMessage({ progress: v }),
      ),
    });
  } catch (e) {
    parentPort!.postMessage({
      error: e instanceof Error ? e.message : "Calibration failed",
    });
  }
}
