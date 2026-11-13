import { readFileSync } from "node:fs";
import { GAME_CODES, gameNumber } from "./catalog.js";
import { check } from "../../other/shared/core.js";

export interface ReadinessEntry {
  id: number;
  code: string;
  brand: string;
  display_name: string;
  collection_complete: boolean;
  blockers: string[];
  special_features: { name: string; implementation: string }[];
  evidence: string[];
  sources: string[];
  reviewed_at: string;
}

// Reviewed release data, never an HTTP/merchant configuration override.
export class GameReadiness {
  private entries: Map<string, ReadinessEntry>;
  constructor(rows: ReadinessEntry[] = JSON.parse(readFileSync(
    new URL("../../config/game-readiness.json", import.meta.url), "utf8",
  )).games) {
    check(Array.isArray(rows) && rows.length === GAME_CODES.length, "READINESS_CONFIG_INVALID");
    this.entries = new Map();
    for (const row of rows) {
      check(GAME_CODES.includes(row.code) && row.id === gameNumber(row.code) &&
        !this.entries.has(row.code) && typeof row.collection_complete === "boolean" &&
        Array.isArray(row.blockers) && row.blockers.every(v => typeof v === "string" && v.length > 0) &&
        Array.isArray(row.evidence) && row.evidence.every(v => typeof v === "string" && v.length > 0) &&
        Array.isArray(row.sources) && row.sources.length > 0 &&
        Array.isArray(row.special_features) && row.special_features.length > 0 &&
        row.special_features.every(v => ["included", "incomplete", "not_applicable"].includes(v.implementation)),
      "READINESS_CONFIG_INVALID");
      check(row.collection_complete
        ? row.blockers.length === 0 && row.evidence.length > 0 && row.special_features.every(v => v.implementation !== "incomplete")
        : row.blockers.length > 0, "READINESS_CONFIG_INVALID");
      this.entries.set(row.code, structuredClone(row));
    }
  }
  get(code: string) {
    const entry = this.entries.get(code);
    check(entry, "GAME_ID_INVALID");
    return structuredClone(entry!);
  }
  assert(code: string) {
    const entry = this.get(code);
    check(entry.collection_complete, "GAME_NOT_READY",
      "特殊玩法尚未收集完整，禁止新接入或开始新整局：" + entry.blockers.join("；"), 403);
  }
}
