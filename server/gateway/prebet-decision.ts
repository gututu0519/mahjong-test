import { check, object, signedHeaders, ServiceError } from "../shared/core.js";
import { fetchBounded } from "../shared/http.js";
import { prebetURL } from "./control.js";
import { multiplier } from "./catalog.js";

// Only callback transport and response validation failures may trigger fallback.
// Planning, state, and wallet errors must retain their existing recovery semantics.
export async function decision(url: string, mid: string, secret: string, raw: string) {
  try {
    url = prebetURL(url);
    const response = await fetchBounded(url, {method:"POST", headers:signedHeaders(mid, secret, new URL(url).pathname, raw), body:raw}, 16384);
    check(response.status === 200, "PREBET_HTTP_ERROR");
    const value = object(response.body);
    check(Number.isInteger(value.code), "PREBET_RESPONSE_INVALID");
    check(value.code === 0, "PREBET_" + value.code);
    const range = value.data?.maxWinMulti;
    check(Array.isArray(range) && range.length === 2 && range.every((v: any) =>
      (typeof v === "number" && Number.isFinite(v)) || (typeof v === "string" && /^-?\d+(?:\.\d+)?(?:e[+-]?\d+)?$/i.test(v))), "PREBET_RANGE_INVALID");
    const [lo, hi] = range.map(multiplier);
    check((lo.n === -lo.d || lo.n >= 0n) && hi.n >= 0n &&
      (lo.n < 0n || hi.n * lo.d >= lo.n * hi.d) && lo.n <= 1000000n * lo.d && hi.n <= 1000000n * hi.d, "PREBET_RANGE_INVALID");
    return {policy:{maxWinMulti:range}, error:undefined};
  } catch (error) {
    return {policy:undefined, error:error instanceof ServiceError ? error.code : "PREBET_UNAVAILABLE"};
  }
}
