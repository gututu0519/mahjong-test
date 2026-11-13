import { RoundChoice } from "../../../../other/shared/prebet.js";
import { BuffaloWin } from "./engine.js";
import { server, jsonBody, success } from "../../../../other/shared/http.js";
import {
  check,
  equal,
  ServiceError,
  sha,
  clone,
  hex,
} from "../../../../other/shared/core.js";
export function gameServer(config: any, secret: string) {
  check(secret.length >= 32, "INTERNAL_KEY_INVALID");
  return server(async (req, res) => {
    check(
      equal(String(req.headers.authorization ?? ""), "Bearer " + secret),
      "AUTH_INVALID",
      "Internal authentication required",
      401,
    );
    if (req.method === "GET" && req.url === "/health")
      return success(res, { status: "ok", service_id: "buffalo-win-node" });
    check(req.method === "POST", "NOT_FOUND", "Not found", 404);
    const p = await jsonBody(req, 4 * 1024 * 1024),
      game = new BuffaloWin(p.configuration ?? config);
    if (req.url === "/v1/describe")
      return success(res, {
        game_id: game.game_id,
        title: game.title,
        version: game.version,
        ruleset_id: game.ruleset_id,
        config: game.config,
      });
    if (req.url === "/v1/initial") return success(res, game.initial_state());
    if (req.url === "/v1/normalize")
      return success(res, game.normalize_bet(p.bet));
    if (req.url === "/v1/validate") {
      const bet = game.normalize_bet(p.bet);
      check(
        !bet.buy_free || p.state.phase === "ready",
        "FEATURE_LOCKED",
        "Finish current round",
        409,
      );
      check(
        p.state.phase === "ready" ||
          (bet.coin_minor === p.state.bet.coin_minor &&
            bet.level === p.state.bet.level),
        "BET_LOCKED",
        "Finish current round",
        409,
      );
      return success(res, { valid: true });
    }
    if (req.url === "/v1/step") {
      check(
        typeof p.seed === "string" && typeof p.operation_id === "string",
        "INVALID_ARGUMENT",
      );
      return success(
        res,
        game.step(p.state, game.normalize_bet(p.bet), p.seed, p.operation_id),
      );
    }
    if (req.url === "/v1/plan") return success(res, plan(game, p));
    throw new ServiceError("NOT_FOUND", "Not found", 404);
  });
}
function fraction(v: any): [bigint, bigint] {
  check(typeof v === "string" || typeof v === "number", "PREBET_RANGE_INVALID");
  const s = String(v).trim();
  const match = /^([+-]?)(\d+)(?:\.(\d*))?(?:[eE]([+-]?\d+))?$/.exec(s);
  check(match && s.length <= 256, "PREBET_RANGE_INVALID");
  const [, sign, whole, decimals = "", exponent = "0"] = match!;
  const scale = decimals.length - Number(exponent);
  check(
    Number.isSafeInteger(scale) && Math.abs(scale) <= 256,
    "PREBET_RANGE_INVALID",
  );
  const numerator = BigInt((sign === "-" ? "-" : "") + whole + decimals);
  return scale >= 0
    ? [numerator, 10n ** BigInt(scale)]
    : [numerator * 10n ** BigInt(-scale), 1n];
}
export function plan(game: BuffaloWin, p: any) {
  const [l, ld] = fraction(p.range[0]),
    [h, hd] = fraction(p.range[1]);
  check(
    l >= -ld &&
      (l >= 0n || l === -ld) &&
      h >= 0n &&
      (l < 0n || l * hd <= h * ld) &&
      l <= 1000000n * ld &&
      h <= 1000000n * hd,
    "PREBET_RANGE_INVALID",
  );
  const basis = p.bet.coin_minor * p.bet.level * 10 * (p.bet.buy_free ? 75 : 1);
  const choice = new RoundChoice<{
    steps: any[];
    total_credit_minor: number;
    basis_minor: number;
  }>(p.range, basis, { n: l, d: ld }, { n: h, d: hd });
  for (let a = 0; a < 3000; a++) {
    let state = clone(p.state),
      total = 0;
    const steps: any[] = [],
      seed = sha(p.seed + ":" + a);
    for (let i = 0; i < 256; i++) {
      const sid = i === 0 ? p.round_id : sha(p.round_id + ":" + i).slice(0, 32),
        bet =
          i === 0
            ? p.bet
            : { coin_minor: p.bet.coin_minor, level: p.bet.level };
      const out = game.step(state, bet, sha(seed + ":" + i), sid);
      total += out.credit_minor;
      if (choice.above(total)) break;
      steps.push({
        previous_sid: state.sid,
        candidate: {
          ...out,
          engine_version: game.version,
          ruleset_id: game.ruleset_id,
        },
      });
      state = out.state;
      if (state.phase === "ready") {
        if (
          choice.consider(
            { steps, total_credit_minor: total, basis_minor: basis },
            total,
            a + 1,
          )
        )
          return choice.finish(a + 1);
        break;
      }
    }
  }
  return choice.finish(3000);
}
