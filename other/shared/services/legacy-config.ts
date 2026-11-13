import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { check, hex } from "../core.js";
import { Control } from "../control.js";
import { fileURLToPath } from "node:url";

// Creates a Node companion config; old credentials, databases and ports stay owned
// by the existing service directories. Never replaces the original private file.
export function legacyConfig(
  repo: string,
  source = resolve(repo, "services/gtt-gateway/data/sandbox.json"),
) {
  const destination = resolve(dirname(source), "node.json");
  if (existsSync(destination)) return destination;
  check(
    existsSync(source),
    "CONFIG_REQUIRED",
    "Initialize a sandbox or supply an existing private config first.",
  );
  const old = JSON.parse(readFileSync(source, "utf8"));
  check(
    old.environment !== "production",
    "EXPLICIT_PRODUCTION_CONFIG_REQUIRED",
  );
  if (old.merchants) {
    const control = new Control(
      resolve(dirname(source), old.merchant_database ?? "merchants.sqlite3"),
      fileURLToPath(new URL("../../config/control.sql", import.meta.url)),
    );
    try {
      control.migrate(old.merchants);
    } finally {
      control.close();
    }
    delete old.merchants;
  }
  const origin = old.gateway_origin ?? "http://127.0.0.1:8110";
  const config = {
    ...old,
    environment: "development",
    log_directories: {
      gateway: resolve(repo, "services/gtt-gateway/logs"),
      admin: resolve(repo, "services/gtt-admin/logs"),
      platform: resolve(repo, "services/gtt-mock-platform/logs"),
    },
    merchant_database: resolve(
      dirname(source),
      old.merchant_database ?? "merchants.sqlite3",
    ),
    game_database: resolve(
      repo,
      old.game_database ?? "services/gtt-gateway/data/gtt.sqlite3",
    ),
    platform_database: resolve(
      repo,
      "services/gtt-mock-platform/data/platform.sqlite3",
    ),
    game_config: resolve(repo, "services/gtt-gateway/config/buffalo-win.json"),
    client_root: resolve(repo, "clients/buffalo-win"),
    game_origin: "http://127.0.0.1:8113",
    gateway_origin: origin,
    internal_secret: hex(32),
    ports: {
      gateway: Number(new URL(origin).port) || 8110,
      platform: 8111,
      admin: 8112,
      buffalo: 8113,
    },
  };
  mkdirSync(dirname(destination), { recursive: true });
  try {
    writeFileSync(destination, JSON.stringify(config, null, 2) + "\n", {
      flag: "wx",
      mode: 0o600,
    });
  } catch (e) {
    if ((e as any).code !== "EEXIST") throw e;
  }
  return destination;
}
