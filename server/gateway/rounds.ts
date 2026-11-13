import { amount, check, identifier, limit } from "../shared/core.js";
import { gameCode, gameNumber, gameUnit } from "./catalog.js";
import type { Provider } from "./provider.js";

function decisionFields(row: any) {
  return {
    decision_id: row?.id ?? null,
    decision_status: !row ? "not_requested" : row.policy_json ? "accepted" : row.error_code ? "fallback" : "pending",
    fallback_reason: row?.error_code && !row.policy_json ? row.error_code : null,
    requested_range: row?.policy_json ? JSON.parse(row.policy_json).maxWinMulti : null,
    resolution: row?.plan_json ? JSON.parse(row.plan_json).resolution ?? null : null,
    resolution_minor_unit: row ? gameUnit(row.game_id) : null,
  };
}

// Freeze callback metadata alongside the candidate. Wallet retries send identical data.
export function roundMetadata(p: Provider, mid: string, code: string, candidate: any) {
  const row = p.get("SELECT * FROM prebet_rounds WHERE merchant_id=? AND game_id=? AND id=?", mid, code, candidate.event.round_id);
  return {
    ...decisionFields(row),
    game_id: gameNumber(code),
    round_id: candidate.event.round_id,
    round_end: candidate.state.phase === "ready",
  };
}

export function walletRound(candidate: any) {
  // Historical prepared operations keep their original callback shape on retry.
  if (!Object.hasOwn(candidate, "decision_id")) return {};
  return Object.fromEntries(["decision_id", "decision_status", "fallback_reason", "game_id", "round_id", "round_end", "requested_range", "resolution", "resolution_minor_unit"].map(k => [k, candidate[k]]));
}

export function roundSummary(p: Provider, mid: string, q: any) {
  let code: string, rid: string, decision: any;
  if (q.decision_id !== undefined) {
    decision = p.get("SELECT * FROM prebet_rounds WHERE merchant_id=? AND id=?", mid, identifier(q.decision_id));
    check(decision, "NOT_FOUND", "Round not found", 404);
    code = decision.game_id; rid = decision.id;
    check(q.game_id === undefined || gameCode(q.game_id) === code, "NOT_FOUND", "Round not found", 404);
    check(q.round_id === undefined || identifier(q.round_id) === rid, "NOT_FOUND", "Round not found", 404);
  } else {
    code = gameCode(q.game_id); rid = identifier(q.round_id);
    decision = p.get("SELECT * FROM prebet_rounds WHERE merchant_id=? AND game_id=? AND id=?", mid, code, rid);
  }
  const operations = p.all("SELECT * FROM game_operations WHERE merchant_id=? AND game_id=? AND json_extract(candidate_json,'$.event.round_id')=? ORDER BY seq", mid, code, rid);
  check(decision || operations.length, "NOT_FOUND", "Round not found", 404);
  const merchant = p.control.merchant(mid);
  let debit = 0n, credit = 0n;
  for (const op of operations) {
    const c = JSON.parse(op.candidate_json);
    if (op.debit_json) debit += BigInt(JSON.parse(op.debit_json).applied_minor);
    else if (op.status === "settled") debit += BigInt(c.wallet_debit_minor ?? c.debit_minor);
    if (op.status === "settled") credit += BigInt(c.wallet_credit_minor ?? c.credit_minor);
  }
  const pending = operations.some(o => ["prepared", "debited"].includes(o.status));
  const ended = operations.some(o => o.status === "settled" && JSON.parse(o.candidate_json).state.phase === "ready");
  // Cancellation here is only a definitive rejection BEFORE any money was applied.
  // An uncertain debit or a paid unfinished free round is never reported cancelled.
  const cancelled = operations.length > 0 && operations.every(o => o.status === "rejected") && debit === 0n;
  const status = pending ? "settling" : cancelled ? "cancelled" : ended ? "completed" : operations.length ? "active" : "preparing";
  const last = operations.at(-1);
  return {
    ...decisionFields(decision),
    game_id: gameNumber(code), round_id: rid,
    revision: p.get("SELECT COALESCE(MAX(seq),0) AS n FROM merchant_round_events WHERE merchant_id=? AND game_id=? AND round_id=?",mid,code,rid).n,
    player_id: decision?.player_id ?? last.player_id,
    status, terminal: status === "completed" || status === "cancelled",
    cancel_reason: cancelled ? last.error_code : null,
    currency: merchant.currency, minor_unit: merchant.minor_unit,
    total_debit_minor: debit.toString(), total_credit_minor: credit.toString(),
    execution_mode: last ? JSON.parse(last.candidate_json).rtp?.mode ?? "legacy" : null,
    operations: operations.map(o => {
      const c = JSON.parse(o.candidate_json);
      return {operation_id:o.id, status:o.status, error_code:o.error_code,
        debit_transaction_id:(c.wallet_debit_minor ?? c.debit_minor) ? o.id+":debit" : null,
        credit_transaction_id:(c.wallet_credit_minor ?? c.credit_minor) ? o.id+":credit" : null};
    }),
  };
}

export function roundChanges(p: Provider, mid: string, q: any) {
  const after = q.after_seq ?? 0;
  amount(after);
  const rows = p.all("SELECT * FROM merchant_round_events WHERE merchant_id=? AND seq>? ORDER BY seq LIMIT ?", mid, after, limit(q.limit ?? 20));
  const snapshots = new Map<string, any>();
  return {
    changes: rows.map(row => {
      const key = row.game_id + ":" + row.round_id;
      if (!snapshots.has(key)) {
        const {operations, ...summary} = roundSummary(p,mid,{game_id:gameNumber(row.game_id),round_id:row.round_id});
        snapshots.set(key,summary);
      }
      return {seq:row.seq,changed_at:row.created_at,round:snapshots.get(key)};
    }),
    next_after_seq: rows.at(-1)?.seq ?? after,
  };
}
