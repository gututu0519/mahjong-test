import { test } from "node:test";
import assert from "node:assert/strict";
import {
  mkdtempSync,
  mkdirSync,
  writeFileSync,
  readFileSync,
  rmSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve, dirname } from "node:path";
import { legacyConfig } from "../services/legacy-config.js";
import { Control } from "../gateway/control.js";
import { buildLocal, method } from "../services/local.js";
import { listen } from "../shared/http.js";
import * as p from "../compat/runtime.js";
import { main } from "../cli.js";

test("new local configuration uses the single 8110 environment and preserves existing files", async () => {
  const dir = mkdtempSync(join(tmpdir(), "gtt-single-environment-")), path = join(dir, "config.json");
  try {
    await main(["init", "--config", path]);
    const original = readFileSync(path, "utf8"), config = JSON.parse(original);
    assert.equal(config.gateway_origin, "http://127.0.0.1:8110");
    assert.equal(config.game_origin, "http://127.0.0.1:8113");
    assert.deepEqual(config.ports, {gateway:8110, admin:8112, buffalo:8113});
    assert.equal(JSON.parse(readFileSync(join(dir,"admin-bootstrap.json"),"utf8")).url,"http://127.0.0.1:8112/");
    await assert.rejects(main(["init", "--config", path]), {code:"CONFIG_EXISTS"});
    assert.equal(readFileSync(path,"utf8"),original);
  } finally { rmSync(dir, {recursive:true,force:true}); }
});
test("inline legacy merchants import idempotently without changing existing secrets", () => {
  const dir = mkdtempSync(join(tmpdir(), "gtt-inline-")),
    source = join(dir, "services/gtt-gateway/data/sandbox.json");
  mkdirSync(dirname(source), { recursive: true });
  const raw = JSON.stringify({
    sandbox_merchant: "GTT000001",
    merchants: {
      GTT000001: {
        name: "legacy-inline",
        enabled: true,
        wallet_url: "http://127.0.0.1:8111",
        currency: "USD",
        minor_unit: 100,
        games: ["buffalo-win"],
        merchant_secret: "a".repeat(64),
      },
    },
  });
  writeFileSync(source, raw);
  try {
    const path = legacyConfig(dir),
      c = JSON.parse(readFileSync(path, "utf8"));
    assert.equal(c.merchants, undefined);
    assert.equal(readFileSync(source, "utf8"), raw);
    const control = new Control(
      c.merchant_database,
      resolve("config/control.sql"),
    );
    try {
      assert.equal(
        control.merchant("GTT000001", true).merchant_secret,
        "a".repeat(64),
      );
      control.migrate({
        ...JSON.parse(raw).merchants,
        GTT000001: {
          ...JSON.parse(raw).merchants.GTT000001,
          merchant_secret: "b".repeat(64),
        },
      });
      assert.equal(
        control.merchant("GTT000001", true).merchant_secret,
        "a".repeat(64),
      );
    } finally {
      control.close();
    }
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
test("old launcher config preserves ports, credentials and service-owned stores without overwriting", () => {
  const dir = mkdtempSync(join(tmpdir(), "gtt-legacy-config-"));
  try {
    const source = join(dir, "services/gtt-gateway/data/sandbox.json");
    mkdirSync(dirname(source), { recursive: true });
    const raw = JSON.stringify({
      gateway_origin: "http://127.0.0.1:8110",
      merchant_database: "merchants.sqlite3",
      sandbox_merchant: "GTT000001",
      sandbox_player: "demo",
      sandbox_balance_minor: 123,
    });
    writeFileSync(source, raw);
    const path = legacyConfig(dir),
      config = JSON.parse(readFileSync(path, "utf8"));
    assert.equal(
      config.merchant_database,
      join(dirname(source), "merchants.sqlite3"),
    );
    assert.equal(
      config.game_database,
      join(dir, "services/gtt-gateway/data/gtt.sqlite3"),
    );
    assert.equal(config.ports.gateway, 8110);
    assert.equal(config.ports.admin, 8112);
    assert.equal(config.sandbox_balance_minor, 123);
    assert.equal(readFileSync(source, "utf8"), raw);
    legacyConfig(dir);
    assert.equal(
      JSON.parse(readFileSync(path, "utf8")).internal_secret,
      config.internal_secret,
    );
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
test("lobby still launches a separate Node game service and settlement rollback preserves balance", async (t) => {
  const dir = mkdtempSync(join(tmpdir(), "gtt-lobby-"));
  const target = await buildLocal(resolve("../services/fortune-rabbit"), {
      database: join(dir, "rabbit.db"),
      port: 0,
    }),
    tp = await listen(target.server);
  const lobby = await buildLocal(resolve("../services/mahjong-ways2"), {
      database: join(dir, "mahjong.db"),
      port: 0,
      launchPorts: { "fortune-rabbit": tp },
    }),
    lp = await listen(lobby.server);
  t.after(async () => {
    for (const { server } of [lobby, target]) {
      server.closeAllConnections();
      await new Promise<void>((ok) => server.close(() => ok()));
    }
    rmSync(dir, { recursive: true, force: true });
  });
  const response = await fetch(
    `http://127.0.0.1:${lp}/api/v1/games/fortune-rabbit/launch`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: '{"language":"en"}',
    },
  );
  assert.equal(response.status, 201, await response.clone().text());
  assert.equal(new URL((await response.json()).launch_url).port, String(tp));
  const session = p.plain(method(target.app.service, "create_session")),
    token = session.token;
  const state = p.plain(
    method(target.app.service, "state", token, "fortune-rabbit"),
  );
  assert.throws(
    () =>
      method(
        target.app.service,
        "spin",
        token,
        "fortune-rabbit",
        "invalid",
        "stale",
        p.dict(),
      ),
    (e: any) => e.code === "STALE_STATE",
  );
  assert.equal(
    p.plain(method(target.app.service, "wallet", token)).balance_minor,
    session.balance_minor,
  );
  const result = method(
    target.app.service,
    "spin",
    token,
    "fortune-rabbit",
    "retry",
    state.state.sid,
    p.dict(),
  );
  assert.deepEqual(
    p.plain(
      method(
        target.app.service,
        "spin",
        token,
        "fortune-rabbit",
        "retry",
        state.state.sid,
        p.dict(),
      ),
    ),
    p.plain(result),
  );
});
