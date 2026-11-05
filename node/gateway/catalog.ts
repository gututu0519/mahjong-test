import { check } from "../shared/core.js";
// Published IDs from server/merchant/identifiers.py. Append only.
export const GAME_CODES = [
  "buffalo-win",
  "captains-bounty",
  "fortune-rabbit",
  "wild-bandito",
  "tower-run-treasure-steps",
  "great-game-serengeti",
  "dr-zappo",
  "le-vampire",
  "wicked-grin",
  "roma-x-10000",
  "money-pot-deluxe",
  "3-billion-vaults",
  "jokers-fortune-winx",
  "fortune-gems2",
  "super-ace",
  "big-bass-bonanza",
  "sweet-bonanza-pop",
  "gates-of-olympus",
  "mahjong-ways2",
];
export const fineGames = new Set([
  "roma-x-10000",
  "money-pot-deluxe",
  "3-billion-vaults",
  "jokers-fortune-winx",
  "fortune-gems2",
  "super-ace",
]);
export function gameCode(id: any) {
  check(
    Number.isInteger(id) && id >= 1 && id <= GAME_CODES.length,
    "GAME_ID_INVALID",
  );
  return GAME_CODES[id - 1];
}
export function gameNumber(code: string) {
  const n = GAME_CODES.indexOf(code) + 1;
  check(n > 0, "GAME_ID_INVALID");
  return n;
}
export const gameUnit = (code: string) => (fineGames.has(code) ? 10000 : 100);
export function units(value: number, from: number, to: number) {
  check(Number.isSafeInteger(value) && value >= 0, "AMOUNT_INVALID");
  const n = BigInt(value) * BigInt(to);
  check(
    n % BigInt(from) === 0n,
    "WALLET_PRECISION_REQUIRED",
    "This game requires a wallet supporting minor_unit=10000.",
  );
  const result = Number(n / BigInt(from));
  check(Number.isSafeInteger(result), "AMOUNT_INVALID");
  return result;
}
export function displayUnits(value: number, from: number, to: number) {
  check(Number.isSafeInteger(value) && value >= 0, "AMOUNT_INVALID");
  const result = Number((BigInt(value) * BigInt(to)) / BigInt(from));
  check(Number.isSafeInteger(result), "AMOUNT_INVALID");
  return result;
}
export function multiplier(value: string | number) {
  const s = String(value);
  check(
    s.length <= 64 && /^-?\d+(?:\.\d+)?(?:e[+-]?\d+)?$/i.test(s),
    "PREBET_RANGE_INVALID",
  );
  const [base, exponent = "0"] = s.toLowerCase().split("e"),
    places = (base.split(".")[1] ?? "").length - Number(exponent);
  check(Math.abs(places) <= 300, "PREBET_RANGE_INVALID");
  const n = BigInt(base.replace(".", ""));
  return {
    n: n * (places < 0 ? 10n ** BigInt(-places) : 1n),
    d: places > 0 ? 10n ** BigInt(places) : 1n,
  };
}
