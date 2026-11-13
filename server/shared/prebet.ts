import { amount, check, ServiceError } from "./core.js";

type Fraction = { n: bigint; d: bigint };
// Only completed, engine-generated rounds may enter this selector. Never
// synthesize a payout by rounding a winning result or truncating a free round.
export class RoundChoice<T extends object> {
  readonly basis: bigint;
  readonly ceiling: bigint;
  best?: { candidate: T; total: number; attempt: number };
  constructor(
    public range: any[],
    public basisMinor: number,
    public low: Fraction,
    public high: Fraction,
    public searchLimit = 3000,
  ) {
    amount(basisMinor);
    check(basisMinor > 0, "AMOUNT_INVALID");
    this.basis = BigInt(basisMinor);
    this.ceiling = (this.basis * high.n) / high.d;
  }
  above(total: number) {
    return BigInt(amount(total)) * this.high.d > this.high.n * this.basis;
  }
  within(total: number) {
    return (
      !this.above(total) &&
      (this.low.n < 0n || BigInt(total) * this.low.d >= this.low.n * this.basis)
    );
  }
  consider(candidate: T, total: number, attempt: number) {
    if (this.above(total)) return false;
    if (!this.best || total > this.best.total)
      this.best = { candidate, total, attempt };
    // Reaching the integer monetary ceiling also proves there can be no closer
    // amount below the requested target, even when that target is fractional.
    return this.within(total) || BigInt(total) === this.ceiling;
  }
  finish(attempts: number) {
    if (!this.best)
      throw new ServiceError(
        "PREBET_RANGE_UNREACHABLE",
        "No complete legal round at or below requested upper bound; no debit",
        503,
      );
    const { candidate, total, attempt } = this.best,
      matched = this.within(total);
    return {
      ...candidate,
      attempts,
      resolution: {
        requested_range: this.range,
        basis_minor: this.basisMinor,
        actual_credit_minor: total,
        actual_multiplier: { numerator: total, denominator: this.basisMinor },
        selection: matched ? "within_range" : "nearest_lower_candidate",
        nearest_scope: matched
          ? "requested_range"
          : BigInt(total) === this.ceiling
            ? "monetary_ceiling"
            : "searched_candidates",
        search_attempts: attempts,
        selected_attempt: attempt,
        search_limit: this.searchLimit,
      },
    };
  }
}
