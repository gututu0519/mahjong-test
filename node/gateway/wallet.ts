import {
  check,
  encode,
  signedHeaders,
  amount,
  ServiceError,
  object,
} from "../shared/core.js";
import { fetchBounded } from "../shared/http.js";
import { Control, walletOrigin } from "./control.js";
export class Wallet {
  constructor(
    private control: Control,
    public timeout = 3000,
  ) {}
  async call(mid: string, action: string, p: any) {
    const m = this.control.merchant(mid, true);
    check(m, "AUTH_INVALID");
    const origin = walletOrigin(m.wallet_url),
      path = "/wallet/v1/" + action,
      body = encode(p);
    try {
      const r = await fetchBounded(origin + path, {
        method: "POST",
        headers: signedHeaders(mid, m.merchant_secret, path, body),
        body,
        timeout: this.timeout,
      });
      const v = object(r.body);
      if (r.status !== 200) {
        if (
          r.status < 500 &&
          [
            "INSUFFICIENT_BALANCE",
            "TRANSACTION_CANCELED",
            "TRANSACTION_CONFLICT",
            "ACCOUNT_NOT_FOUND",
            "CURRENCY_MISMATCH",
            "ALREADY_REFUNDED",
            "REFERENCE_INVALID",
          ].includes(v.error?.code)
        )
          throw new ServiceError(v.error.code, v.error.code, 409);
        throw new Error("Wallet rejected callback");
      }
      const d = v.data;
      check(
        d &&
          d.player_id === p.player_id &&
          d.currency === m.currency &&
          d.minor_unit === p.minor_unit,
        "WALLET_UNCERTAIN",
      );
      amount(d.balance_minor);
      if (["debit", "credit", "refund"].includes(action)) {
        check(
          d.transaction_id === p.transaction_id &&
            d.status === "applied" &&
            amount(d.amount_minor) === p.amount_minor,
          "WALLET_UNCERTAIN",
        );
        const before = BigInt(amount(d.balance_before_minor)),
          applied = BigInt(amount(d.applied_minor));
        check(
          (action === "refund"
            ? applied === 0n || applied === BigInt(p.amount_minor)
            : applied === BigInt(p.amount_minor)) &&
            BigInt(d.balance_minor) ===
              before + (action === "debit" ? -applied : applied),
          "WALLET_UNCERTAIN",
        );
      }
      return d;
    } catch (e) {
      if (e instanceof ServiceError && e.status === 409) throw e;
      throw new ServiceError(
        "WALLET_UNCERTAIN",
        "Unknown wallet result; retry original transaction",
        503,
      );
    }
  }
}
