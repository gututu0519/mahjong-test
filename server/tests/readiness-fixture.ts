import { readFileSync } from "node:fs";
import { GameReadiness } from "../gateway/readiness.js";

// Synthetic approval exists only inside test processes. It is not a release
// assertion about the captured games, nor a runtime/config bypass switch.
export function verifiedReadinessFixture() {
  const rows = JSON.parse(readFileSync("config/game-readiness.json", "utf8")).games;
  return new GameReadiness(rows.map((row: any) => ({
    ...row, collection_complete: true, blockers: [], evidence: ["synthetic-test-fixture"],
    special_features: row.special_features.map((f: any) => ({...f, implementation: f.implementation === "incomplete" ? "included" : f.implementation})),
  })));
}
