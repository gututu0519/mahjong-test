import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { gunzipSync } from "node:zlib";
import { Control } from "../shared/control.js";
import { Provider } from "../../gateway/src/provider.js";
import { GameClient } from "../../gateway/src/game-client.js";
import { computeServer } from "../shared/services/compute.js";
import { platformServer } from "../shared/services/platform.js";
import { adminServer } from "../../admin/backend/admin.js";
import { gatewayServer } from "../../gateway/src/http.js";
import { listen } from "../shared/http.js";
import { GAME_CODES, gameNumber } from "../../gateway/src/catalog.js";
import { commands } from "../shared/games/round-model.js";
import { encode, ServiceError } from "../shared/core.js";
import { method } from "../shared/services/local.js";
import * as py from "../shared/compat/runtime.js";
import { PG } from "../../gateway/src/pg.js";
import { components } from "../tooling/cli.js";

async function fixture(t: any) {
  const dir = mkdtempSync(join(tmpdir(), "game-services-"));
  const control = new Control(
    join(dir, "control.db"),
    resolve("config/control.sql"),
  );
  const merchant = control.saveMerchant(
    "test",
    {
      name: "remote-games",
      enabled: true,
      wallet_url: "http://127.0.0.1:8111",
      games: GAME_CODES.map((_, i) => i + 1),
    },
    true,
  );
  const mid = merchant.merchant.id;
  const config: any = {
    environment: "development",
    game_services_mode: "remote",
    game_database: join(dir, "games.db"),
    platform_database: join(dir, "wallet.db"),
    gateway_origin: "http://127.0.0.1",
    sandbox_merchant: mid,
    sandbox_player: "p1",
    sandbox_external_username: "external-p1",
    sandbox_balance_minor: 1000000000,
  };
  const { server: wallet, wallet: mock } = platformServer(config, control);
  const servers: any[] = [wallet];
  const wp = await listen(wallet);
  control.saveMerchant("test", {
    ...control.merchant(mid),
    wallet_url: "http://127.0.0.1:" + wp,
  });
  for (let id = 1; id <= 19; id++)
    control.setGameAvailability("test", {
      game_id: id,
      enabled: true,
      version: 0,
    });
  let p: Provider;
  const startProvider = async () => {
    const cfg = JSON.parse(readFileSync("config/buffalo-win.json", "utf8"));
    p = new Provider(
      config.game_database,
      control,
      new GameClient("http://127.0.0.1:1", "x".repeat(64), cfg),
      resolve("config/game.sql"),
      config.gateway_origin,
    );
    p.enableGames(config);
    await p.initialize();
    return p;
  };
  await startProvider();
  const f: any = {
    control,
    mid,
    config,
    servers,
    dir,
    mock,
    wp,
    get p() {
      return p;
    },
    restart: async () => {
      p.close();
      await startProvider();
    },
  };
  f.register = async (code: string, release: string, contract?: string) => {
    const secret = "key-" + code + "-".repeat(64);
    const server = computeServer(
      code,
      resolve(`../services/${code}/config/${code}.json`),
      secret,
      { release, clientContract: contract },
    );
    servers.push(server);
    const port = await listen(server);
    const row = await p.multi!.remote!.register("test", {
      code,
      release,
      origin: "http://127.0.0.1:" + port,
      secret,
    });
    return { ...row, server, port, secret };
  };
  f.launch = async (code: string) => {
    const r = await p.launch(mid, {
      game_id: gameNumber(code),
      player_id: "p1",
      external_username: "external-p1",
    });
    return new URL(r.launch_url).searchParams.get("ops")!;
  };
  t.after(async () => {
    for (const s of servers) {
      s.closeAllConnections();
      await new Promise<void>((ok) => s.close(() => ok()));
    }
    p.close();
    control.close();
    rmSync(dir, { recursive: true, force: true });
  });
  return f;
}

test("all 19 merchant games calculate through registered HTTP services, with no embedded engine instances", async (t) => {
  const f = await fixture(t),
    registry = f.p.multi!.remote!;
  for (const origin of [
    "http://127.example.com",
    "http://169.254.169.254",
    "http://127.0.0.1:8211/?token=key",
    "http://user:password@127.0.0.1:8211",
  ])
    assert.throws(() => registry.validateOrigin(origin), {
      code: "GAME_SERVICE_URL_INVALID",
    });
  assert.throws(
    () =>
      registry.select("legacy", "player", "fortune-rabbit", { phase: "free" }),
    { code: "GAME_VERSION_REQUIRED" },
  );
  for (const code of GAME_CODES) {
    const r = await f.register(code, "r1");
    await registry.activate("test", { id: r.id, revision: 0 });
    const token = await f.launch(code);
    const raw = f.p.multi!.initial(f.mid, "p1", code);
    const payload = JSON.parse(
      gunzipSync(readFileSync(`fixtures/all-games/${code}.json.gz`)).toString(),
    ).initial[0].payload;
    const response = await f.p.spin(token, "remote-first", raw.sid, payload);
    assert.ok(response.settlement);
    const operation = f.p.get(
      "SELECT * FROM game_operations WHERE merchant_id=? AND game_id=?",
      f.mid,
      code,
    );
    assert.equal(
      JSON.parse(operation.candidate_json).service_release_id,
      r.id,
      code,
    );
    assert.equal(f.p.multi!.engines.get(code), null);
    r.server.closeAllConnections();
    await new Promise<void>((ok) => r.server.close(() => ok()));
    assert.deepEqual(
      await f.p.spin(token, "remote-first", raw.sid, payload),
      response,
    );
    const publicGame = f.p
      .merchantCatalog(f.mid)
      .find((g: any) => g.code === code);
    assert.ok(!JSON.stringify(publicGame).includes(r.secret));
    assert.ok(!JSON.stringify(publicGame).includes("origin"));
  }
});

test("version activation pins a complete purchased round across restart, supports rollback and rejects incompatible contracts", async (t) => {
  const f = await fixture(t),
    code = "gates-of-olympus";
  const v1 = await f.register(code, "r1"),
    v2 = await f.register(code, "r2");
  let registry = f.p.multi!.remote!;
  await registry.activate("test", { id: v1.id, revision: 0 });
  const token = await f.launch(code);
  const initial = f.p.multi!.initial(f.mid, "p1", code);
  let response = await f.p.spin(token, "purchase", initial.sid, {
    action: "buy",
  });
  assert.notEqual(f.p.multi!.initial(f.mid, "p1", code).phase, "ready");
  await registry.activate("test", { id: v2.id, revision: 1 });
  await assert.rejects(registry.activate("test", { id: v1.id, revision: 1 }), {
    code: "VERSION_CONFLICT",
  });
  await f.restart();
  registry = f.p.multi!.remote!;
  let count = 0;
  while (f.p.multi!.initial(f.mid, "p1", code).phase !== "ready") {
    const state = f.p.multi!.initial(f.mid, "p1", code);
    response = await f.p.spin(token, "continue-" + count, state.sid, {
      action: state.phase === "collect" ? "collect" : "spin",
      request_index: ++count,
    });
    assert.ok(count < 512);
  }
  for (const row of f.p.all(
    "SELECT candidate_json FROM game_operations WHERE game_id=?",
    code,
  ))
    assert.equal(JSON.parse(row.candidate_json).service_release_id, v1.id);
  const ready = f.p.multi!.initial(f.mid, "p1", code);
  await f.p.spin(token, "new-version", ready.sid, { action: "buy" });
  const latest = f.p.get(
    "SELECT candidate_json FROM game_operations ORDER BY seq DESC LIMIT 1",
  );
  assert.equal(JSON.parse(latest.candidate_json).service_release_id, v2.id);
  await registry.activate("test", { id: v1.id, revision: 2 });
  assert.equal(registry.active(code).id, v1.id);
  const incompatible = await f.register(
    code,
    "r3",
    "different-client-contract",
  );
  await assert.rejects(
    registry.activate("test", { id: incompatible.id, revision: 3 }),
    { code: "GAME_CONTRACT_MISMATCH" },
  );
  assert.equal(registry.active(code).id, v1.id);
  assert.throws(() => registry.retire("test", { id: v1.id }), {
    code: "GAME_RELEASE_ACTIVE",
  });
  registry.retire("test", { id: v2.id });
  assert.equal(registry.release(v2.id).status, "retired");
  assert.equal(
    registry.select(f.mid, "p1", code, f.p.multi!.initial(f.mid, "p1", code))
      .id,
    v2.id,
  );
});

test("lost remote calculation remains pinned after switching versions and restarting, without a second debit", async (t) => {
  const f = await fixture(t),
    code = "fortune-rabbit";
  const v1 = await f.register(code, "r1"),
    v2 = await f.register(code, "r2");
  const registry = f.p.multi!.remote!;
  await registry.activate("test", { id: v1.id, revision: 0 });
  const token = await f.launch(code),
    state = f.p.multi!.initial(f.mid, "p1", code);
  const original = registry.request.bind(registry);
  let dropped = false;
  registry.request = async (r: any, action: string, value: any = {}) => {
    const out = await original(r, action, value);
    if (
      !dropped &&
      action === "invoke" &&
      value.method === "step" &&
      value.args[2] !== "validation-only"
    ) {
      dropped = true;
      throw new ServiceError("GAME_UNAVAILABLE", "lost reply", 503);
    }
    return out;
  };
  await assert.rejects(f.p.spin(token, "lost", state.sid, {}), {
    code: "GAME_UNAVAILABLE",
  });
  assert.equal(f.p.get("SELECT COUNT(*) AS n FROM game_operations").n, 0);
  const pending = f.p.get(
    "SELECT * FROM node_calculations WHERE status='pending'",
  );
  await registry.activate("test", { id: v2.id, revision: 1 });
  await f.restart();
  const reply = await f.p.spin(token, "lost", state.sid, {});
  assert.equal(f.p.get("SELECT COUNT(*) AS n FROM game_operations").n, 1);
  assert.equal(
    JSON.parse(
      f.p.get("SELECT candidate_json FROM game_operations").candidate_json,
    ).service_release_id,
    v1.id,
  );
  assert.equal(
    f.p.get("SELECT seed FROM node_calculations WHERE id=?", pending.id).seed,
    pending.seed,
  );
  assert.deepEqual(await f.p.spin(token, "lost", state.sid, {}), reply);
});

test("service registry API enforces platform permissions and never returns credentials to merchants", async (t) => {
  const f = await fixture(t);
  const empty = await components({
    environment: "development",
    merchant_database: join(f.dir, "empty-control.db"),
    game_database: join(f.dir, "empty-games.db"),
    gateway_origin: "http://127.0.0.1:8110",
  });
  assert.ok(empty.provider.multi?.remote);
  assert.equal(
    empty.control.get("SELECT COUNT(*) AS n FROM game_service_routes").n,
    0,
  );
  empty.provider.close();
  empty.control.close();
  const admin = f.control.createUser("test", "deploy-admin", "admin");
  const merchant = f.control.createUser(
    "test",
    "tenant-admin",
    "merchant_admin",
    undefined,
    f.mid,
  );
  const app = adminServer(
    f.p,
    f.config,
    resolve("frontend/admin"),
    resolve("config"),
  );
  f.servers.push(app);
  const origin = "http://127.0.0.1:" + (await listen(app));
  const login = async (name: string, password: string, tenant = false) => {
    const response = await fetch(
      origin + `/api/${tenant ? "merchant" : "admin"}/login`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ username: name, password }),
      },
    );
    const data: any = await response.json();
    assert.equal(response.status, 200, JSON.stringify(data));
    return {
      cookie: response.headers.get("set-cookie")!.split(";")[0],
      csrf: data.data.csrf_token,
    };
  };
  const post = (path: string, q: any, s: any) =>
    fetch(origin + path, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        cookie: s.cookie,
        "x-gtt-csrf": s.csrf,
      },
      body: JSON.stringify(q),
    });
  const a = await login("deploy-admin", admin.temporary_password);
  const m = await login("tenant-admin", merchant.temporary_password, true);
  assert.equal((await post("/api/admin/services/list", {}, a)).status, 200);
  for (const action of ["list", "register", "activate", "retire", "probe"])
    assert.equal(
      (await post("/api/merchant/services/" + action, {}, m)).status,
      403,
      action,
    );
  const v = await f.register("fortune-rabbit", "r1");
  const list = await (await post("/api/admin/services/list", {}, a)).text();
  assert.ok(!list.includes(v.secret));
  assert.equal(
    (await post("/api/admin/services/activate", { id: v.id, revision: 0 }, a))
      .status,
    200,
  );
  const noCsrf = { ...a, csrf: "bad" };
  assert.equal(
    (
      await post(
        "/api/admin/services/activate",
        { id: v.id, revision: 1 },
        noCsrf,
      )
    ).status,
    403,
  );
});

test("remote prebet plans stay bound to the old service until the complete feature is settled", async (t) => {
  const f = await fixture(t),
    code = "gates-of-olympus";
  f.control.saveMerchant("test", {
    ...f.control.merchant(f.mid),
    pre_payout: {
      enabled: true,
      url: `http://127.0.0.1:${f.wp}/api/v1/callbacks/gtt/preBetDecision`,
    },
  });
  method(f.mock, "prebet_policy", f.mid, py.from([0, 100000]));
  const old = await f.register(code, "r1"),
    next = await f.register(code, "r2");
  const registry = f.p.multi!.remote!;
  await registry.activate("test", { id: old.id, revision: 0 });
  const token = await f.launch(code),
    state = f.p.multi!.initial(f.mid, "p1", code);
  await f.p.spin(token, "prebet-buy", state.sid, { action: "buy" });
  const decision = f.p.get("SELECT * FROM prebet_rounds WHERE game_id=?", code);
  assert.ok(decision.plan_json);
  await registry.activate("test", { id: next.id, revision: 1 });
  let index = 0;
  while (f.p.multi!.initial(f.mid, "p1", code).phase !== "ready") {
    const state = f.p.multi!.initial(f.mid, "p1", code);
    await f.p.spin(token, "prebet-step-" + index, state.sid, {
      action: state.phase === "collect" ? "collect" : "spin",
      request_index: ++index,
    });
    assert.ok(index < 512);
  }
  const operations = f.p
    .all("SELECT candidate_json FROM game_operations WHERE game_id=?", code)
    .map((r: any) => JSON.parse(r.candidate_json));
  assert.ok(operations.every((c: any) => c.service_release_id === old.id));
  assert.equal(
    operations.reduce((n: number, c: any) => n + c.credit_minor, 0),
    JSON.parse(decision.plan_json).total_credit_minor,
  );
  assert.equal(
    registry
      .list()
      .find((g) => g.code === code)!
      .releases.find((r) => r.id === old.id)!.open_rounds,
    0,
  );
});

test("a missing original service never redirects an ongoing free feature to the newly active release", async (t) => {
  const f = await fixture(t),
    code = "gates-of-olympus";
  const old = await f.register(code, "r1"),
    next = await f.register(code, "r2"),
    registry = f.p.multi!.remote!;
  await registry.activate("test", { id: old.id, revision: 0 });
  const token = await f.launch(code),
    initial = f.p.multi!.initial(f.mid, "p1", code);
  await f.p.spin(token, "buy", initial.sid, { action: "buy" });
  await registry.activate("test", { id: next.id, revision: 1 });
  old.server.closeAllConnections();
  await new Promise<void>((ok) => old.server.close(() => ok()));
  const count = f.p.get("SELECT COUNT(*) AS n FROM game_operations").n;
  const state = f.p.multi!.initial(f.mid, "p1", code);
  await assert.rejects(
    f.p.spin(token, "old-service-down", state.sid, {
      action: state.phase === "collect" ? "collect" : "spin",
    }),
    { code: "GAME_UNAVAILABLE" },
  );
  assert.equal(f.p.get("SELECT COUNT(*) AS n FROM game_operations").n, count);
  assert.equal(registry.select(f.mid, "p1", code, state).id, old.id);
});

test("a rejected debit releases the version reservation for the next new round", async (t) => {
  const f = await fixture(t),
    code = "fortune-rabbit";
  const old = await f.register(code, "r1"),
    next = await f.register(code, "r2"),
    registry = f.p.multi!.remote!;
  await registry.activate("test", { id: old.id, revision: 0 });
  const token = await f.launch(code),
    initial = f.p.multi!.initial(f.mid, "p1", code);
  const call = f.p.walletClient.call.bind(f.p.walletClient);
  f.p.walletClient.call = async (mid: string, action: string, q: any) => {
    if (action === "debit")
      throw new ServiceError("INSUFFICIENT_BALANCE", "test decline", 409);
    return call(mid, action, q);
  };
  await assert.rejects(f.p.spin(token, "rejected", initial.sid, {}), {
    code: "INSUFFICIENT_BALANCE",
  });
  f.p.walletClient.call = call;
  await registry.activate("test", { id: next.id, revision: 1 });
  await f.p.spin(token, "accepted", initial.sid, {});
  const accepted = f.p.get(
    "SELECT candidate_json FROM game_operations WHERE request_key='accepted'",
  );
  assert.equal(JSON.parse(accepted.candidate_json).service_release_id, next.id);
});

test("the retained Buffalo PG entry also uses the independent service without the legacy 8113 server", async (t) => {
  const f = await fixture(t),
    code = "buffalo-win",
    registered = await f.register(code, "r1");
  await f.p.multi!.remote!.activate("test", { id: registered.id, revision: 0 });
  const token = await f.launch(code),
    initial = f.p.multi!.initial(f.mid, "p1", code),
    pg = new PG(f.p);
  const info = await pg.info(token);
  assert.ok(info.dt.cs.length);
  const form = new URLSearchParams({
    wk: "0_C",
    btt: "1",
    pf: "1",
    cs: String(info.dt.cs[0]),
    ml: String(info.dt.ml[0]),
    fb: "0",
    id: initial.sid,
  });
  assert.ok((await pg.spin(form, token)).dt.si);
});
