import { DatabaseSync } from "node:sqlite";
import { request as httpRequest } from "node:http";
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { server, listen, body, send, success } from "../shared/http.js";
import {
  encode,
  object,
  signedHeaders,
  signature,
  sha,
  ServiceError,
} from "../shared/core.js";
import { Control, passwordMatches } from "../gateway/control.js";
import { Provider } from "../gateway/provider.js";
import { GameClient } from "../gateway/game-client.js";
import { gameServer } from "../games/buffalo-win/service.js";
import { gatewayServer } from "../gateway/http.js";
import { adminServer } from "../gateway/admin.js";
import { asset, repairModule } from "../gateway/assets.js";
import { sample } from "../games/buffalo-win/calibration.js";
const root = process.cwd(),
  gameConfig = JSON.parse(readFileSync("config/buffalo-win.json", "utf8")),
  secret = "a".repeat(64),
  password = "test-only-password-2026";
async function setup(t: any, legacy = false) {
  const dir = mkdtempSync(join(tmpdir(), "gtt-node-"));
  if (legacy) {
    for (const [target, source] of [
      ["merchants.sqlite3", "legacy-control.sql"],
      ["gtt.sqlite3", "legacy-game.sql"],
    ]) {
      const db = new DatabaseSync(join(dir, target));
      db.exec("PRAGMA foreign_keys=OFF"); // iterdump orders tables alphabetically.
      db.exec(readFileSync(resolve("fixtures", source), "utf8"));
      db.close();
    }
  }
  const control = new Control(
    join(dir, "merchants.sqlite3"),
    resolve("config/control.sql"),
  );
  if (!legacy) control.createUser("test", "admin", "admin", password);
  let balance = 200000,
    dropDebit = false,
    dropCredit = false,
    range: any = [-1, 0];
  const ledger = new Map<string, any>();
  let callbacks = 0;
  const wallet = server(async (req, res) => {
    const raw = await body(req);
    const merchant = control.merchant(
      String(req.headers["x-gtt-merchant"]),
      true,
    );
    assert.equal(
      req.headers["x-gtt-signature"],
      signature(
        merchant.merchant_secret,
        req.url!,
        String(req.headers["x-gtt-timestamp"]),
        String(req.headers["x-gtt-nonce"]),
        raw,
      ),
    );
    const q = object(raw.toString()),
      action = req.url!.split("/").at(-1),
      identity = {
        player_id: q.player_id,
        currency: q.currency,
        minor_unit: 100,
      };
    if (action === "preBetDecision")
      return send(res, 200, {
        code: 0,
        data: { maxWinMulti: range },
        msg: null,
      });
    if (action === "balance")
      return success(res, { ...identity, balance_minor: balance });
    const id = q.transaction_id;
    if (ledger.has(id)) return success(res, ledger.get(id));
    if (action === "debit" && balance < q.amount_minor)
      throw new ServiceError(
        "INSUFFICIENT_BALANCE",
        "Insufficient balance",
        409,
      );
    const before = balance;
    balance += action === "debit" ? -q.amount_minor : q.amount_minor;
    callbacks++;
    const result = {
      ...identity,
      transaction_id: id,
      status: "applied",
      amount_minor: q.amount_minor,
      applied_minor: q.amount_minor,
      balance_before_minor: before,
      balance_minor: balance,
    };
    ledger.set(id, result);
    if (
      (action === "debit" && dropDebit) ||
      (action === "credit" && dropCredit)
    ) {
      dropDebit = false;
      dropCredit = false;
      res.destroy();
      return;
    }
    success(res, result);
  });
  const wp = await listen(wallet),
    gs = gameServer(gameConfig, secret),
    gp = await listen(gs),
    client = new GameClient("http://127.0.0.1:" + gp, secret, gameConfig);
  const provider = new Provider(
    join(dir, "gtt.sqlite3"),
    control,
    client,
    resolve("config/game.sql"),
    "http://127.0.0.1",
    resolve("config/rtp-models.json"),
  );
  await provider.initialize();
  const created = control.saveMerchant(
      "admin",
      {
        name: "merchant-test",
        enabled: true,
        wallet_url: "http://127.0.0.1:" + wp,
        games: [1],
      },
      true,
    ),
    mid = created.merchant.id;
  const config: any = {
    environment: "development",
    gateway_origin: "http://127.0.0.1",
  };
  const gateway = gatewayServer(
      provider,
      config,
      resolve("../clients/buffalo-win"),
    ),
    gatewayPort = await listen(gateway);
  provider.playOrigin = "http://127.0.0.1:" + gatewayPort;
  config.gateway_origin = provider.playOrigin;
  const admin = adminServer(
      provider,
      config,
      resolve("frontend/admin"),
      resolve("config"),
    ),
    adminPort = await listen(admin);
  t.after(async () => {
    for (const s of [admin, gateway, gs, wallet]) {
      s.closeAllConnections();
      await new Promise<void>((ok) => s.close(() => ok()));
    }
    provider.close();
    control.close();
    rmSync(dir, { recursive: true, force: true });
  });
  const request = async (
    path: string,
    p: any,
    headers: any = {},
    port = gatewayPort,
    method = "POST",
  ) => {
    const response = await fetch("http://127.0.0.1:" + port + path, {
      method,
      headers: Object.fromEntries(
        new Headers(
          Object.fromEntries(
            Object.entries({
              "content-type": "application/json",
              ...headers,
            }).map(([k, v]) => [k.toLowerCase(), String(v)]),
          ),
        ),
      ),
      ...(method === "GET"
        ? {}
        : { body: typeof p === "string" ? p : encode(p) }),
    });
    const text = await response.text();
    let data: any;
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
    return { status: response.status, data, headers: response.headers };
  };
  const signed = async (path: string, p: any) => {
    const b = encode(p),
      m = control.merchant(mid, true);
    return request(path, b, signedHeaders(mid, m.merchant_secret, path, b));
  };
  const launch = async (extra = {}) => {
    const r = await signed("/gtt/v1/games/launch", {
      player_id: "player-1",
      game_id: 1,
      language: "en",
      ...extra,
    });
    assert.equal(r.status, 201, JSON.stringify(r.data));
    return new URL(r.data.data.launch_url).searchParams.get("ops")!;
  };
  return {
    provider,
    control,
    created,
    mid,
    request,
    signed,
    launch,
    adminPort,
    gatewayPort,
    client,
    dir,
    ledger,
    get balance() {
      return balance;
    },
    set balance(v: number) {
      balance = v;
    },
    get callbacks() {
      return callbacks;
    },
    set dropDebit(v: boolean) {
      dropDebit = v;
    },
    set dropCredit(v: boolean) {
      dropCredit = v;
    },
    set range(v: any) {
      range = v;
    },
  };
}
test("merchant launch, full purchased feature, duplicate spins and persisted wallet recovery", async (t) => {
  const c = await setup(t),
    tok = await c.launch();
  let previous = "0",
    paid = 0,
    won = 0,
    steps = 0;
  c.dropDebit = true;
  await assert.rejects(
    () =>
      c.provider.spin(tok, "buy", previous, {
        coin_minor: 2,
        level: 1,
        buy_free: true,
      }),
    { code: "WALLET_UNCERTAIN" },
  );
  assert.equal(c.balance, 198500);
  const pending = c.provider.get(
    "SELECT * FROM game_operations WHERE status='prepared'",
  );
  assert.ok(pending);
  const restored = new Provider(
    join(c.dir, "gtt.sqlite3"),
    c.control,
    c.client,
    resolve("config/game.sql"),
    "",
    resolve("config/rtp-models.json"),
  );
  await restored.initialize();
  const recovered = await restored.retry(c.mid, pending.id);
  restored.close();
  paid += recovered.wallet.debit_minor;
  won += recovered.wallet.credit_minor;
  previous = recovered.sid;
  let result = recovered;
  assert.deepEqual(
    await c.provider.spin(tok, "buy", "0", {
      coin_minor: 2,
      level: 1,
      buy_free: true,
    }),
    recovered,
  );
  while (result.outcome.next_phase !== "ready") {
    result = await c.provider.spin(tok, "next-" + steps, previous, {
      coin_minor: 2,
      level: 1,
    });
    previous = result.sid;
    paid += result.wallet.debit_minor;
    won += result.wallet.credit_minor;
    assert.ok(++steps < 256);
  }
  assert.equal(paid, 1500);
  assert.equal(c.balance, 200000 - paid + won);
  assert.equal(
    c.provider.rtp.snapshot({ merchant_id: c.mid }).merchants[0].rounds,
    1,
  );
  assert.equal(
    c.provider.get(
      "SELECT COUNT(*) AS n FROM game_operations WHERE status IN ('prepared','debited')",
    ).n,
    0,
  );
  const state = await c.provider.state(tok);
  assert.equal(state.state.phase, "ready");
});
test("signed HTTP rejects tamper and replay; client startup, game info and S3-compatible HTML work", async (t) => {
  const c = await setup(t),
    path = "/gtt/v1/games/list",
    b = "{}",
    h = signedHeaders(
      c.mid,
      c.control.merchant(c.mid, true).merchant_secret,
      path,
      b,
    );
  assert.equal((await c.request(path, b, h)).status, 200);
  assert.equal((await c.request(path, b, h)).data.error.code, "AUTH_REPLAY");
  assert.equal(
    (
      await c.request(
        path,
        '{"x":1}',
        signedHeaders(
          c.mid,
          c.control.merchant(c.mid, true).merchant_secret,
          path,
          b,
        ),
      )
    ).status,
    401,
  );
  const tok = await c.launch();
  const entry = await c.request("/", null, {}, c.gatewayPort, "GET");
  assert.equal(entry.status, 200);
  assert.match(entry.data, /local-auth-bootstrap.js/);
  assert.equal(
    (
      await c.request(
        "/fixtures/auth-metadata.json",
        null,
        {},
        c.gatewayPort,
        "GET",
      )
    ).status,
    404,
  );
  const info = await c.request(
    "/game-api/buffalo-win/v2/GameInfo/Get",
    new URLSearchParams({ atk: tok }).toString(),
    { "content-type": "application/x-www-form-urlencoded" },
  );
  assert.equal(info.status, 200);
  assert.equal(info.data.dt.fb.bm, 75);
  assert.equal(info.data.dt.bl, 2000);
  const state = await c.request(
    "/api/v1/games/buffalo-win/state",
    null,
    { Authorization: "Bearer " + tok },
    c.gatewayPort,
    "GET",
  );
  assert.equal(state.status, 200);
  assert.equal(state.data.game_id, 1);
});
test("admin UI routes, tenant permissions, CSRF, key rotation and password compatibility", async (t) => {
  const c = await setup(t);
  const login = await c.request(
    "/api/admin/login",
    { username: "admin", password },
    {},
    c.adminPort,
  );
  assert.equal(login.status, 200, JSON.stringify(login.data));
  const headers: any = {
    Cookie: login.headers.get("set-cookie")!.split(";")[0],
    "X-GTT-CSRF": login.data.data.csrf_token,
  };
  for (const path of [
    "overview",
    "merchants/list",
    "games",
    "transactions/list",
    "audit",
    "users/list",
    "prebet/list",
    "integration/docs",
    "rtp/read",
  ]) {
    const r = await c.request("/api/admin/" + path, {}, headers, c.adminPort);
    assert.equal(r.status, 200, path + ": " + JSON.stringify(r.data));
  }
  assert.equal(
    (
      await c.request(
        "/api/admin/merchants/list",
        {},
        { ...headers, "X-GTT-CSRF": "" },
        c.adminPort,
      )
    ).status,
    403,
  );
  const mlogin = await c.request(
    "/api/merchant/login",
    {
      username: c.created.login.name,
      password: c.created.login.temporary_password,
    },
    {},
    c.adminPort,
  );
  assert.equal(mlogin.status, 200);
  const mh = {
    Cookie: mlogin.headers.get("set-cookie")!.split(";")[0],
    "X-GTT-CSRF": mlogin.data.data.csrf_token,
  };
  assert.equal(
    (
      await c.request(
        "/api/merchant/merchants/create",
        {},
        { ...mh },
        c.adminPort,
      )
    ).status,
    403,
  );
  assert.equal(
    (
      await c.request(
        "/api/merchant/transactions/list",
        { merchant_id: "GTT999999" },
        mh,
        c.adminPort,
      )
    ).status,
    403,
  );
  assert.equal(
    (
      await c.request(
        "/api/merchant/rtp/policy",
        { scope: "platform", revision: 0, reason: "test policy" },
        mh,
        c.adminPort,
      )
    ).status,
    403,
  );
  const old = c.control.merchant(c.mid, true).merchant_secret;
  const r = await c.request(
    "/api/admin/merchants/signing/rotate",
    {
      id: c.mid,
      version: c.control.merchant(c.mid).version,
      reason: "test rotation",
    },
    headers,
    c.adminPort,
  );
  assert.equal(r.status, 200);
  assert.notEqual(r.data.data.keys.merchant_secret, old);
  assert.equal(
    (
      await c.request(
        "/gtt/v1/games/list",
        "{}",
        signedHeaders(c.mid, old, "/gtt/v1/games/list", "{}"),
      )
    ).status,
    401,
  );
  assert.throws(
    () =>
      c.control.updateUser("admin", {
        username: "admin",
        role: "viewer",
        enabled: true,
      }),
    { code: "LAST_ADMIN" },
  );
  assert.equal(
    passwordMatches(
      password,
      c.control.get(
        "SELECT password_hash FROM admin_users WHERE username='admin'",
      ).password_hash,
    ),
    true,
  );
});
test("prebet full-round planning, RTP mode switch and round-bound model configuration", async (t) => {
  const c = await setup(t);
  const m = c.control.merchant(c.mid, true);
  c.control.profile("owner", c.mid, {
    version: m.version,
    pre_payout: {
      enabled: true,
      url: m.wallet_url + "/api/v1/callbacks/gtt/preBetDecision",
    },
  });
  const tok = await c.launch({ external_username: "platform-player" });
  c.range = [-1, 0];
  const r = await c.provider.spin(tok, "prebet", "0", {
    coin_minor: 2,
    level: 1,
  });
  assert.equal(r.rtp.mode, "prebet");
  const plan = JSON.parse(
    c.provider.get("SELECT plan_json FROM prebet_rounds").plan_json,
  );
  assert.equal(plan.total_credit_minor, 0);
  const model = c.provider.rtp.models().find((m) => m.target_bp === 9600);
  assert.ok(model);
  const before = c.provider.rtp.mode(c.mid);
  c.provider.rtp.policy(
    "admin",
    {
      scope: "merchant",
      merchant_id: c.mid,
      model_id: model.id,
      revision: 0,
      activate_rtp: true,
      mode_revision: before.revision,
      reason: "test mode switch",
    },
    true,
  );
  assert.equal(c.control.merchant(c.mid).pre_payout.enabled, false);
  assert.equal(c.provider.rtp.resolve(c.mid).target_bp, 9600);
  if (r.outcome.next_phase !== "ready")
    assert.equal((await c.provider.state(tok)).rtp.mode, "prebet");
});
test("insufficient funds do not advance state; concurrent retries debit once", async (t) => {
  const c = await setup(t),
    tok = await c.launch();
  c.balance = 0;
  await assert.rejects(
    () => c.provider.spin(tok, "bad", "0", { coin_minor: 2, level: 1 }),
    { code: "INSUFFICIENT_BALANCE" },
  );
  assert.equal((await c.provider.state(tok)).state.sid, "0");
  c.balance = 200000;
  const a = await Promise.all([
    c.provider.spin(tok, "ok", "0", { coin_minor: 2, level: 1 }),
    c.provider.spin(tok, "ok", "0", { coin_minor: 2, level: 1 }),
  ]);
  assert.deepEqual(a[0], a[1]);
  assert.equal(
    [...c.ledger.keys()].filter((k) => k.endsWith(":debit")).length,
    1,
  );
  await assert.rejects(
    () => c.provider.spin(tok, "ok", "0", { coin_minor: 3, level: 1 }),
    { code: "IDEMPOTENCY_CONFLICT" },
  );
});
test("complete-round calibration smoke uses no wallet or truncated rounds", () => {
  const r = sample(gameConfig, true, 30, "calibration-smoke");
  assert.equal(r.rounds, 30);
  assert.equal(r.cost, 1500);
  assert.equal(r.unfinished_rounds, 0);
  assert.ok(r.steps > 30);
});

test("Python-created databases retain passwords, tokens, settled operations and unfinished purchased features", async (t) => {
  const c = await setup(t, true);
  const f = JSON.parse(readFileSync("fixtures/legacy-meta.json", "utf8"));
  c.control.run(
    "UPDATE merchants SET wallet_url=? WHERE id=?",
    c.control.merchant(c.mid).wallet_url,
    f.merchant_id,
  );
  c.balance = f.result.wallet.after_minor;
  assert.equal(
    c.control.login("admin", password, "fixture").data.user.role,
    "admin",
  );
  assert.equal(c.provider.session(f.token).merchant_id, f.merchant_id);
  assert.deepEqual(
    await c.provider.retry(f.merchant_id, f.result.sid),
    f.result,
  );
  const state = await c.provider.state(f.token);
  assert.notEqual(state.state.phase, "ready");
  const next = await c.provider.spin(
    f.token,
    "continued-by-node",
    state.state.sid,
    { coin_minor: 2, level: 1 },
  );
  assert.equal(next.wallet.debit_minor, 0);
  assert.equal(next.round_id, f.result.round_id);
  assert.equal(c.provider.get("PRAGMA integrity_check").integrity_check, "ok");
  assert.deepEqual(c.provider.all("PRAGMA foreign_key_check"), []);
});

test("all shared client modules match Python repair output byte-for-byte", () => {
  const refs = JSON.parse(readFileSync("fixtures/module-hashes.json", "utf8"));
  for (const [name, hash] of Object.entries(refs)) {
    const source = readFileSync(
      resolve("../clients/buffalo-win", name),
      "utf8",
    );
    assert.equal(sha(repairModule(source)), hash, name);
  }
});

test("illegal bet during a purchased round does not reserve or block a valid continuation", async (t) => {
  const c = await setup(t),
    tok = await c.launch();
  const start = await c.provider.spin(tok, "buy", "0", {
    coin_minor: 2,
    level: 1,
    buy_free: true,
  });
  await assert.rejects(
    () =>
      c.provider.spin(tok, "invalid", start.sid, { coin_minor: 3, level: 1 }),
    { code: "BET_LOCKED" },
  );
  assert.equal(
    c.provider.get(
      "SELECT COUNT(*) AS n FROM node_calculations WHERE status='pending'",
    ).n,
    0,
  );
  const next = await c.provider.spin(tok, "valid", start.sid, {
    coin_minor: 2,
    level: 1,
  });
  assert.equal(next.wallet.debit_minor, 0);
});

test("lost calculation response retains the seed and can resume without a second debit", async (t) => {
  const c = await setup(t),
    tok = await c.launch();
  const original = c.client.call.bind(c.client);
  const seeds: string[] = [];
  let lose = true;
  c.client.call = async (action, p, configuration) => {
    const out = await original(action, p, configuration);
    if (action === "step") {
      seeds.push(p.seed);
      if (lose) {
        lose = false;
        throw new ServiceError("GAME_UNAVAILABLE", "Lost response", 503);
      }
    }
    return out;
  };
  await assert.rejects(
    () => c.provider.spin(tok, "lost", "0", { coin_minor: 2, level: 1 }),
    { code: "GAME_UNAVAILABLE" },
  );
  assert.equal(c.callbacks, 0);
  assert.equal(
    c.provider.get(
      "SELECT COUNT(*) AS n FROM node_calculations WHERE status='pending'",
    ).n,
    1,
  );
  const result = await c.provider.spin(tok, "lost", "0", {
    coin_minor: 2,
    level: 1,
  });
  assert.equal(seeds.length, 2);
  assert.equal(seeds[0], seeds[1]);
  assert.equal(result.wallet.debit_minor, 20);
  assert.equal(
    [...c.ledger.keys()].filter((k) => k.endsWith(":debit")).length,
    1,
  );
});

test("lost credit response is recovered from persisted operation without paying twice", async (t) => {
  const c = await setup(t),
    tok = await c.launch();
  const original = c.client.call.bind(c.client);
  let sequence = 0,
    sid = "0",
    found = false;
  c.client.call = (action, p, configuration) =>
    original(
      action,
      action === "step" ? { ...p, seed: "credit-recovery-" + sequence++ } : p,
      configuration,
    );
  c.dropCredit = true;
  for (let i = 0; i < 100; i++) {
    try {
      sid = (
        await c.provider.spin(tok, `credit-${i}`, sid, {
          coin_minor: 2,
          level: 1,
        })
      ).sid;
    } catch (e) {
      assert.equal((e as ServiceError).code, "WALLET_UNCERTAIN");
      found = true;
      break;
    }
  }
  assert.ok(found, "deterministic sequence must produce a payout");
  const pending = c.provider.get(
    "SELECT * FROM game_operations WHERE status IN ('prepared','debited')",
  );
  assert.ok(JSON.parse(pending.candidate_json).credit_minor > 0);
  const before = { balance: c.balance, callbacks: c.callbacks };
  const restored = new Provider(
    join(c.dir, "gtt.sqlite3"),
    c.control,
    c.client,
    resolve("config/game.sql"),
    "",
    resolve("config/rtp-models.json"),
  );
  try {
    await restored.initialize();
    const result = await restored.retry(c.mid, pending.id);
    assert.equal(result.wallet.after_minor, before.balance);
    assert.equal(c.balance, before.balance);
    assert.equal(c.callbacks, before.callbacks);
    assert.deepEqual(await c.provider.retry(c.mid, pending.id), result);
  } finally {
    restored.close();
  }
});

test("production portal boundaries and secure cookies remain enforced", async (t) => {
  const c = await setup(t);
  const cfg = {
    environment: "production",
    public_origins: Object.fromEntries(
      ["site", "api", "play", "admin", "merchant"].map((k) => [
        k,
        `https://${k}.example.test`,
      ]),
    ),
  };
  const s = adminServer(
    c.provider,
    cfg,
    resolve("frontend/admin"),
    resolve("config"),
  );
  const port = await listen(s);
  t.after(async () => {
    s.closeAllConnections();
    await new Promise<void>((ok) => s.close(() => ok()));
  });
  const headers = {
    host: "admin.example.test",
    "x-forwarded-proto": "https",
    origin: "https://admin.example.test",
  };
  // Native HTTP allows a proxy-style Host override; fetch ignores Host here.
  const proxyRequest = (path: string, p: any, h: any): Promise<any> =>
    new Promise((ok, fail) => {
      const req = httpRequest(
        {
          hostname: "127.0.0.1",
          port,
          path,
          method: "POST",
          headers: { "content-type": "application/json", ...h },
        },
        (res) => {
          const chunks: Buffer[] = [];
          res.on("data", (b) => chunks.push(b));
          res.on("end", () =>
            ok({
              status: res.statusCode,
              data: JSON.parse(Buffer.concat(chunks).toString()),
              headers: new Headers(
                Object.fromEntries(
                  Object.entries(res.headers).map(([k, v]) => [k, String(v)]),
                ),
              ),
            }),
          );
        },
      );
      req.on("error", fail);
      req.end(JSON.stringify(p));
    });
  const login = await proxyRequest(
    "/api/admin/login",
    { username: "admin", password },
    headers,
  );
  assert.equal(login.status, 200, JSON.stringify(login.data));
  assert.match(
    login.headers.get("set-cookie")!,
    /^__Host-gtt_admin_session=.*; HttpOnly; SameSite=Strict; Path=\/; Max-Age=28800; Secure$/,
  );
  assert.equal(
    (await proxyRequest("/api/merchant/login", {}, headers)).status,
    404,
  );
  assert.equal(
    (
      await proxyRequest(
        "/api/admin/login",
        {},
        { ...headers, "x-forwarded-proto": "http" },
      )
    ).status,
    403,
  );
  assert.equal(
    (
      await proxyRequest(
        "/api/admin/login",
        {},
        { ...headers, origin: "https://foreign.example.test" },
      )
    ).status,
    403,
  );
  c.control.createUser("admin", "viewer-test", "viewer", password);
  const account = c.control.login("viewer-test", password, "test");
  assert.throws(() => c.control.session(account.token, "merchants.write"), {
    code: "FORBIDDEN",
  });
  assert.ok(
    c.control.audits({}).some((a: any) => a.action === "permission.denied"),
  );
});
