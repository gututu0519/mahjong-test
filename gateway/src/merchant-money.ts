import { check } from "../../other/shared/core.js";

export const MERCHANT_MINOR_UNIT = 10000;

function convert(value: number | string, from: number, to = MERCHANT_MINOR_UNIT) {
  check(from === 100 || from === 10000, "AMOUNT_INVALID");
  const scaled = BigInt(value) * BigInt(to);
  check(scaled % BigInt(from) === 0n, "AMOUNT_INVALID");
  const result = scaled / BigInt(from);
  if (typeof value === "string") return result.toString();
  check(Number.isSafeInteger(value) && Number.isSafeInteger(Number(result)), "AMOUNT_INVALID");
  return Number(result);
}

// Work on boundary copies only. Persisted candidates and original game clients
// retain their native units, seeds, retries and protocol payloads.
function moneyTree(value: any, from: number, money = false): any {
  if (Array.isArray(value)) return value.map(v => moneyTree(v, from, money));
  if (value && typeof value === "object")
    return Object.fromEntries(Object.entries(value).map(([key, v]) =>
      [key, moneyTree(v, from, money || key.endsWith("_minor"))]));
  return money && (typeof value === "number" || typeof value === "string")
    ? convert(value, from) : value;
}

export function merchantRoundMoney(value: any) {
  const copy = { ...value };
  if (value.resolution_minor_unit != null)
    copy.resolution_minor_unit = MERCHANT_MINOR_UNIT;
  if (value.resolution && value.resolution_minor_unit) {
    copy.resolution = {
      ...value.resolution,
      basis_minor: convert(value.resolution.basis_minor, value.resolution_minor_unit),
      actual_credit_minor: convert(value.resolution.actual_credit_minor, value.resolution_minor_unit),
    };
  }
  return copy;
}

export function merchantRoundSummary(value: any) {
  return {
    ...merchantRoundMoney(value),
    minor_unit: MERCHANT_MINOR_UNIT,
    total_debit_minor: convert(value.total_debit_minor, value.minor_unit),
    total_credit_minor: convert(value.total_credit_minor, value.minor_unit),
  };
}

export function merchantLaunch(value: any) {
  return {
    ...value,
    minor_unit: MERCHANT_MINOR_UNIT,
    balance_minor: convert(value.balance_minor, value.minor_unit),
  };
}

export function merchantGameResult(value: any) {
  if (!value) return value;
  const from = value.minor_unit ?? 100;
  const result = {
    ...merchantRoundMoney(value),
    minor_unit: MERCHANT_MINOR_UNIT,
    wallet: moneyTree(value.wallet, from),
    outcome: moneyTree(value.outcome, from),
  };
  if (value.settlement) {
    const s = value.settlement;
    result.settlement = {
      ...moneyTree(s, s.minor_unit), minor_unit: MERCHANT_MINOR_UNIT,
    };
    const exact = result.settlement;
    result.wallet = {
      before_minor: exact.before_minor ?? (exact.balance_minor + exact.debit_minor - exact.credit_minor),
      debit_minor: exact.debit_minor, credit_minor: exact.credit_minor,
      after_minor: exact.balance_minor,
    };
    check(Number.isSafeInteger(result.wallet.before_minor), "AMOUNT_INVALID");
  }
  return result;
}

export function merchantOperations(value: any) {
  return {
    ...value,
    operations: value.operations.map((op: any) => ({
      ...merchantRoundMoney(op), result: merchantGameResult(op.result),
    })),
  };
}
