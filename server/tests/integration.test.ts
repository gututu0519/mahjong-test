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
import { verifiedReadinessFixture } from "./readiness-fixture.js";
import { GameReadiness } from "../gateway/readiness.js";
const root = process.cwd(),
  gameConfig = JSON.parse(readFileSync("config/buffalo-win.json", "utf8")),
  secret = "a".repeat(64),
  password = "test-only-password-2026";

test("merchant creation defaults to all game grants without overriding explicit restrictions", async (t) => {
  const c = await setup(t);
  const created = c.control.saveMerchant("admin", {name:"all-defaults",enabled:true,wallet_url:"http://127.0.0.1:8111"}, true).merchant;
  assert.deepEqual(created.games, Array.from({length:19},(_,i)=>i+1));
  assert.equal(created.minor_unit,10000);
  const empty = c.control.saveMerchant("admin", {name:"explicit-empty",enabled:true,wallet_url:"http://127.0.0.1:8111",games:[]}, true).merchant;
  assert.deepEqual(empty.games,[]);
  assert.equal(empty.minor_unit,10000);
  for (const minor_unit of [100, 1, 1000, "10000", null]) {
    assert.throws(() => c.control.saveMerchant("admin", {name:"invalid-precision",enabled:true,wallet_url:"http://127.0.0.1:8111",games:[1],minor_unit}, true), {code:"WALLET_PRECISION_INVALID"});
  }
  const restricted = c.control.saveMerchant("admin", {name:"fixed-restricted",enabled:true,wallet_url:"http://127.0.0.1:8111",games:[1],minor_unit:10000}, true).merchant;
  assert.equal(restricted.minor_unit,10000);
  assert.deepEqual(c.control.merchant(c.mid).games,[1]);
});

test("merchant catalog exports include available games only and omit internal collection records", async (t) => {
  const c = await setup(t);
  const unauth = await c.request("/api/merchant/games/export",{format:"html"},{},c.adminPort);
  assert.equal(unauth.status,401);
  const login = await c.request("/api/merchant/login",{username:c.created.merchant.name,password:c.created.login.temporary_password},{},c.adminPort);
  assert.equal(login.status,200);
  const headers = {Cookie:login.headers.get("set-cookie")!.split(";")[0],"X-GTT-CSRF":login.data.data.csrf_token};
  for (const format of ["html","csv","json"]) {
    const result = await c.request("/api/merchant/games/export",{format},headers,c.adminPort);
    assert.equal(result.status,200);
    const data = result.data.data;
    assert.equal(data.filename,"GTT-Game-Catalog."+format);
    assert.ok(data.content.includes(c.provider.catalog(c.mid)[0].title));
    assert.ok(!data.content.includes("readiness"));
    assert.ok(!data.content.includes("docs/"));
    assert.ok(!data.content.includes("Fortune Rabbit"));
    assert.ok(!data.content.includes(c.created.keys.merchant_secret));
    if (format === "json") {
      const json = JSON.parse(data.content);
      assert.equal(json.games.length,1);
      assert.deepEqual(Object.keys(json),["games"]);
      assert.deepEqual(json.games,[{brand:"PG Soft",title_zh:"美洲野牛",title_en:"Buffalo Win",id:1}]);
    } else if (format === "csv") assert.ok(data.content.startsWith("\uFEFF"));
  }
  const cross = await c.request("/api/merchant/games/export",{format:"json",merchant_id:"GTT999999"},headers,c.adminPort);
  assert.equal(cross.status,403);
  const bad = await c.request("/api/merchant/games/export",{format:"exe"},headers,c.adminPort);
  assert.equal(bad.status,400);
  c.provider.readiness = new GameReadiness();
  for(let game_id=1;game_id<=19;game_id++) c.control.setGameAvailability("test",{game_id,enabled:false,version:c.control.gameAvailability(game_id).version});
  for (const path of ["/api/merchant/games","/api/merchant/games/export"]) {
    const result = await c.request(path,{format:"json"},headers,c.adminPort);
    assert.equal(result.status,200);
    const data = path.endsWith("export") ? JSON.parse(result.data.data.content) : result.data.data;
    assert.deepEqual(data.games,[]);
  }
  assert.deepEqual((await c.signed("/gtt/v1/games/list",{})).data.data.games,[]);
  assert.deepEqual((await c.request('/api/v1/games',null,{},c.gatewayPort,'GET')).data.games,[]);
});

test("platform availability controls persist, enforce permissions and versioning, and preserve recovery", async(t)=>{
  const c=await setup(t), p=c.provider, tok=await c.launch(), bet={coin_minor:2,level:1};
  let result=await p.spin(tok,"before-close","0",{...bet,buy_free:true});
  const login=async(username:string,pw:string,merchant=false)=>{
    const r=await c.request('/api/'+(merchant?'merchant':'admin')+'/login',{username,password:pw},{},c.adminPort);
    assert.equal(r.status,200);
    return {Cookie:r.headers.get('set-cookie')!.split(';')[0], 'X-GTT-CSRF':r.data.data.csrf_token};
  };
  const admin=await login('admin',password);
  const payload={game_id:1,enabled:false,version:c.control.gameAvailability(1).version};
  const merchant=await login(c.created.merchant.name,c.created.login.temporary_password,true);
  assert.equal((await c.request('/api/merchant/games/availability',payload,merchant,c.adminPort)).status,403);
  c.control.createUser('admin','view-games','viewer',password);
  const viewer=await login('view-games',password);
  assert.equal((await c.request('/api/admin/games/availability',payload,viewer,c.adminPort)).status,403);
  c.control.createUser('admin','operate-games','operator',password);
  const operator=await login('operate-games',password);
  assert.equal((await c.request('/api/admin/games/availability',payload,operator,c.adminPort)).status,200);
  assert.equal((await c.request('/api/admin/games/availability',payload,admin,c.adminPort)).status,409);
  assert.equal(p.merchantCatalog(c.mid).length,0);
  assert.equal(p.catalog().length,19);
  const connection=new Control(join(c.dir,'merchants.sqlite3'),resolve('config/control.sql'));
  assert.equal(connection.gameAvailability(1).enabled,false);connection.close();
  const blocked=await c.signed('/gtt/v1/games/launch',{game_id:1,player_id:'other-player'});
  assert.equal(blocked.data.error.code,'GAME_CLOSED');
  const resume=await c.launch();
  for(let i=0;(await p.state(resume)).state.phase!=='ready'&&i<100;i++)result=await p.spin(resume,'close-resume-'+i,result.sid,bet);
  assert.equal((await p.state(resume)).state.phase,'ready');
  await assert.rejects(p.spin(resume,'new-closed',result.sid,bet),{code:'GAME_CLOSED'});
  p.readiness=new GameReadiness();
  const rejected=await c.request('/api/admin/games/availability',{game_id:1,enabled:true,version:c.control.gameAvailability(1).version},admin,c.adminPort);
  assert.equal(rejected.status,200);
  assert.equal(p.catalog(c.mid)[0].readiness.collection_complete,false);
  assert.equal(p.merchantCatalog(c.mid).length,1);
  const opened = await c.launch({player_id:'unreviewed-player'});
  assert.ok(await p.spin(opened,'unreviewed-spin','0',bet));
  for(const format of ['html','csv','json']) {
    const exported=await c.request('/api/admin/games/export',{format},admin,c.adminPort);
    assert.equal(exported.status,200);
    assert.ok(!exported.data.data.content.includes('免费内重触发'));
    assert.ok(!exported.data.data.content.includes('readiness'));
    if(format==='json'){const data=JSON.parse(exported.data.data.content);assert.equal(data.games.length,19);for(const game of data.games)assert.deepEqual(Object.keys(game),['brand','title_zh','title_en','id']);}
  }
  assert.equal((await c.request('/api/admin/games/availability',{game_id:1,enabled:true,version:c.control.gameAvailability(1).version},admin,c.adminPort)).status,200);
  assert.equal(p.merchantCatalog(c.mid).length,1);
  assert.ok(c.control.get("SELECT 1 FROM admin_audit WHERE action='game.availability.update' AND actor='operate-games'"));
});

test("closed legacy Buffalo rejects new rounds but allows frozen round recovery", async (t) => {
  const c = await setup(t), p = c.provider, tok = await c.launch();
  const bet = {coin_minor:2,level:1};
  const started = await p.spin(tok,"before-gate","0",{...bet,buy_free:true});
  p.readiness = new GameReadiness();
  c.control.setGameAvailability("test",{game_id:1,enabled:false,version:c.control.gameAvailability(1).version});
  const before = c.callbacks;
  const blocked = await c.signed("/gtt/v1/games/launch",{game_id:1,player_id:"new-player"});
  assert.equal(blocked.status,403);
  assert.equal(blocked.data.error.code,"GAME_CLOSED");
  const resumed = await c.launch();
  assert.deepEqual(await p.spin(resumed,"before-gate","0",{...bet,buy_free:true}),started);
  let result = started;
  for(let i=0;(await p.state(resumed)).state.phase!=="ready" && i<100;i++) result=await p.spin(resumed,"resume-"+i,result.sid,bet);
  assert.equal((await p.state(resumed)).state.phase,"ready");
  await assert.rejects(p.spin(resumed,"blocked-next",result.sid,bet),{code:"GAME_CLOSED"});
  assert.equal(p.get("SELECT COUNT(*) AS n FROM node_calculations WHERE request_key='blocked-next'").n,0);
  assert.ok(c.callbacks >= before);
});
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
  const walletRequests: any[] = [];
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
        minor_unit: merchant.minor_unit,
      };
    walletRequests.push({action,request:q});
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
  provider.readiness = verifiedReadinessFixture();
  for(let game_id=1;game_id<=19;game_id++) control.setGameAvailability("fixture",{game_id,enabled:true,version:0});
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
  // This suite replays historical two-decimal wallet/compute contracts. Seed
  // that legacy record explicitly; the merchant creation API now fixes 10000.
  control.run("UPDATE merchants SET minor_unit=100 WHERE id=?", mid);
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
    walletRequests,
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
  for (const [file, type] of [
    ["guide.html", "text/html"],
    ["guide.md", "text/markdown"],
    ["openapi.json", "application/json"],
  ]) {
    const path = "/api/merchant/integration/" + file;
    const denied = await c.request(path, null, {}, c.adminPort, "GET");
    assert.equal(denied.status, 401);
    assert.equal(denied.headers.get("content-disposition"), null);
    const download = await c.request(path, null, mh, c.adminPort, "GET");
    assert.equal(download.status, 200, JSON.stringify(download.data));
    assert.ok(download.headers.get("content-type")?.startsWith(type));
    assert.match(download.headers.get("content-disposition")!, /attachment/);
    const text =
      typeof download.data === "string"
        ? download.data
        : JSON.stringify(download.data);
    assert.ok(!text.includes(c.control.merchant(c.mid, true).merchant_secret));
    assert.ok(!text.includes("https://api.gttgames.com"));
    if (file !== "openapi.json") {
      for (const value of [
        "当前环境与商户配置",
        c.mid,
        "不支持部分退款",
        "ALREADY_REFUNDED",
        "game_id",
        "3000",
        "封面",
        "/wallet/v1/refund",
        "/gtt/v1/transactions/retry",
      ])
        assert.ok(text.includes(value), file + " missing " + value);
      assert.ok(!text.includes("<!-- GTT_CONTEXT -->"));
    }
    if (file === "guide.html") {
      assert.match(text, /^<!doctype html>/i);
      assert.ok(!text.includes("<script"));
      const contract = JSON.parse(
        readFileSync("config/integration.json", "utf8"),
      );
      for (const e of contract.endpoints)
        assert.ok(text.includes('id="api-' + e.id + '"'), e.id);
      for (const s of contract.sections)
        assert.ok(text.includes('id="' + s.id + '"'), s.id);
    }
  }
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
test("merchant profile saves custom wallet callbacks and exports effective URLs", async (t) => {
  const c = await setup(t),
    original = c.control.merchant(c.mid);
  const login = await c.request(
    "/api/merchant/login",
    {
      username: c.created.login.name,
      password: c.created.login.temporary_password,
    },
    {},
    c.adminPort,
  );
  const headers = {
    Cookie: login.headers.get("set-cookie")!.split(";")[0],
    "X-GTT-CSRF": login.data.data.csrf_token,
  };
  const endpoint = original.wallet_url + "/merchant/custom/balance";
  const saved = await c.request(
    "/api/merchant/merchants/profile",
    {
      id: c.mid,
      version: original.version,
      wallet_endpoints: { balance: endpoint },
    },
    headers,
    c.adminPort,
  );
  assert.equal(saved.status, 200, JSON.stringify(saved.data));
  assert.equal(saved.data.data.merchant.wallet_endpoints.balance, endpoint);
  assert.deepEqual(saved.data.data.merchant, c.control.merchant(c.mid));
  const tok = await c.launch(); // The test wallet verifies the signature against its actual URL.
  assert.ok(tok);
  for (const file of ["guide.html", "guide.md", "openapi.json"]) {
    const result = await c.request(
      "/api/merchant/integration/" + file,
      null,
      headers,
      c.adminPort,
      "GET",
    );
    assert.equal(result.status, 200);
    if (file === "openapi.json")
      assert.equal(result.data["x-gtt-wallet-endpoints"].balance, endpoint);
    else assert.ok(result.data.includes(endpoint));
  }
  const current = c.control.merchant(c.mid);
  const rejected = await c.request(
    "/api/merchant/merchants/profile",
    {
      id: c.mid,
      version: current.version,
      name: "must not save",
      wallet_url: "",
      wallet_endpoints: { balance: endpoint },
    },
    headers,
    c.adminPort,
  );
  assert.equal(rejected.status, 400);
  assert.equal(rejected.data.error.code, "WALLET_ENDPOINT_REQUIRED");
  assert.deepEqual(c.control.merchant(c.mid), current);
  const stale = await c.request(
    "/api/merchant/merchants/profile",
    { id: c.mid, version: original.version, wallet_endpoints: {} },
    headers,
    c.adminPort,
  );
  assert.equal(stale.status, 409);
  assert.equal(c.control.merchant(c.mid).wallet_endpoints.balance, endpoint);
});

test("merchant profile derives prebet from URL without a switch or confirmation and preserves version checks", async (t) => {
  const c = await setup(t),
    p = c.provider,
    control = c.control;
  const model = p.rtp
    .models()
    .find((m) => m.game_id === 1 && m.target_bp === 9000)!;
  p.rtp.policy(
    "admin",
    {
      scope: "merchant",
      merchant_id: c.mid,
      model_id: model.id,
      revision: 0,
      reason: "retain merchant RTP",
      activate_rtp: true,
      mode_revision: 0,
    },
    true,
  );
  const login = await c.request(
    "/api/merchant/login",
    {
      username: c.created.login.name,
      password: c.created.login.temporary_password,
    },
    {},
    c.adminPort,
  );
  const headers = {
    Cookie: login.headers.get("set-cookie")!.split(";")[0],
    "X-GTT-CSRF": login.data.data.csrf_token,
  };
  const url =
    control.merchant(c.mid).wallet_url + "/api/v1/callbacks/gtt/preBetDecision";
  const save = (q: any) =>
    c.request("/api/merchant/merchants/profile", q, headers, c.adminPort);
  const original = control.merchant(c.mid),
    policy = p.all("SELECT * FROM rtp_policies");
  const change = {
    id: c.mid,
    version: original.version,
    name: "updated profile",
    pre_payout: { enabled: true, url },
  };
  const enabled = await save(change);
  assert.equal(enabled.status, 200, JSON.stringify(enabled.data));
  assert.equal(enabled.data.data.mode_changed, true);
  assert.equal(enabled.data.data.merchant.version, original.version + 1);
  assert.deepEqual(enabled.data.data.merchant, control.merchant(c.mid));
  assert.equal(p.rtp.mode(c.mid).mode, "prebet");
  assert.equal(control.merchant(c.mid).pre_payout.enabled, true);
  assert.equal(
    (await save({ ...change, confirm_mode_change: true })).status,
    409,
  );
  const current = control.merchant(c.mid),
    mode = p.rtp.mode(c.mid);
  const invalid = await save({
    id: c.mid,
    version: current.version,
    name: "must roll back",
    pre_payout: { enabled: true, url: "not-a-url" },
  });
  assert.equal(invalid.status, 400);
  assert.deepEqual(control.merchant(c.mid), current);
  // A write failure after changing the attached control DB must roll back both DBs.
  p.run(
    "CREATE TEMP TRIGGER mode_failure BEFORE INSERT ON main.rtp_events BEGIN SELECT RAISE(ABORT,'test rollback'); END",
  );
  assert.throws(() =>
    p.rtp.updateMerchant(
      "test",
      {
        id: c.mid,
        version: current.version,
        pre_payout: { url: "" },
        confirm_mode_change: true,
      },
      true,
    ),
  );
  p.run("DROP TRIGGER mode_failure");
  assert.deepEqual(control.merchant(c.mid), current);
  assert.deepEqual(p.rtp.mode(c.mid), mode);
  const off = await save({
    id: c.mid,
    version: current.version,
    pre_payout: { url: "" },
    confirm_mode_change: true,
  });
  assert.equal(off.status, 200, JSON.stringify(off.data));
  assert.equal(p.rtp.mode(c.mid).mode, "rtp");
  assert.equal(control.merchant(c.mid).pre_payout.enabled, false);
  assert.deepEqual(p.all("SELECT * FROM rtp_policies"), policy);
  assert.equal(p.rtp.resolve(c.mid).target_bp, 9000);
  assert.ok(
    p.get(
      "SELECT 1 FROM rtp_events WHERE merchant_id=? AND action='rtp.mode.change'",
      c.mid,
    ),
  );
  assert.ok(
    control.get(
      "SELECT 1 FROM admin_audit WHERE target=? AND action='merchant.profile.update'",
      c.mid,
    ),
  );
  // RTP center edits invalidate a previously opened merchant form too.
  const stale = control.merchant(c.mid);
  p.rtp.setMode("admin", {
    merchant_id: c.mid,
    mode: "prebet",
    url,
    revision: p.rtp.mode(c.mid).revision,
    reason: "another editor change",
  });
  assert.equal(
    (
      await save({
        id: c.mid,
        version: stale.version,
        pre_payout: { url: "" },
        confirm_mode_change: true,
      })
    ).status,
    409,
  );
  assert.equal(p.rtp.mode(c.mid).mode, "prebet");
  // The platform editor uses the same atomic save flow and validation.
  const owner = await c.request(
    "/api/admin/login",
    { username: "admin", password },
    {},
    c.adminPort,
  );
  const ah = {
    Cookie: owner.headers.get("set-cookie")!.split(";")[0],
    "X-GTT-CSRF": owner.data.data.csrf_token,
  };
  const latest = control.merchant(c.mid);
  const platform = await c.request(
    "/api/admin/merchants/update",
    {
      id: c.mid,
      version: latest.version,
      name: latest.name,
      wallet_url: latest.wallet_url,
      enabled: true,
      games: [1],
      currency: latest.currency,
      minor_unit: latest.minor_unit,
      pre_payout: { url: "" },
      confirm_mode_change: true,
    },
    ah,
    c.adminPort,
  );
  assert.equal(platform.status, 200, JSON.stringify(platform.data));
  assert.deepEqual(platform.data.data.merchant, control.merchant(c.mid));
  assert.equal(p.rtp.mode(c.mid).mode, "rtp");
});

test("profile mode changes preserve already-started RTP and prebet purchased rounds", async (t) => {
  const c = await setup(t),
    p = c.provider,
    url =
      c.control.merchant(c.mid).wallet_url +
      "/api/v1/callbacks/gtt/preBetDecision";
  const update = (enabled: boolean) =>
    p.rtp.updateMerchant(
      "test",
      {
        id: c.mid,
        version: c.control.merchant(c.mid).version,
        pre_payout: { url: enabled ? url : "" },
        confirm_mode_change: true,
      },
      true,
    );
  const tok = await c.launch({ external_username: "platform-player" });
  const bet = { coin_minor: 2, level: 1 },
    first = await p.spin(tok, "rtp-purchase", "0", { ...bet, buy_free: true });
  assert.equal(first.rtp.mode, "rtp");
  assert.notEqual((await p.state(tok)).state.phase, "ready");
  update(true);
  const next = await p.spin(tok, "rtp-continue", first.sid, bet);
  assert.equal(next.wallet.debit_minor, 0);
  assert.equal(next.round_id, first.round_id);
  assert.deepEqual(next.rtp, first.rtp);
  const launch = await p.launch(c.mid, {
    game_id: 1,
    player_id: "player-2",
    external_username: "platform-player-2",
  });
  const other = new URL(launch.launch_url, p.playOrigin).searchParams.get(
    "ops",
  )!;
  const paid = await p.spin(other, "prebet-purchase", "0", {
    ...bet,
    buy_free: true,
  });
  assert.equal(paid.rtp.mode, "prebet");
  assert.notEqual((await p.state(other)).state.phase, "ready");
  update(false);
  const continued = await p.spin(other, "prebet-continue", paid.sid, bet);
  assert.equal(continued.wallet.debit_minor, 0);
  assert.equal(continued.wallet.credit_minor, 0);
  assert.equal(continued.round_id, paid.round_id);
  assert.deepEqual(continued.rtp, paid.rtp);
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
  assert.equal(c.control.merchant(c.mid).pre_payout.enabled, true);
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


test("prebet callback failures fall back to bound RTP without duplicate callbacks or debits", async(t)=>{
  const c=await setup(t), p=c.provider;
  let calls=0, variant:any={code:0,data:{maxWinMulti:[-1,0]}}, status=200, delay=0;
  const callback=server(async(req,res)=>{await body(req);calls++;if(delay)await new Promise(r=>setTimeout(r,delay));send(res,status,variant);});
  const port=await listen(callback);
  t.after(()=>{callback.closeAllConnections();callback.close();});
  c.control.prebet(c.mid,{enabled:false,url:'http://127.0.0.1:'+port+'/decision'});
  // Old switches and mode rows cannot disable a configured address.
  p.run("INSERT OR REPLACE INTO rtp_modes VALUES(?,?,?)",c.mid,"rtp",1);
  assert.equal(p.rtp.mode(c.mid).mode,'prebet');
  const variants=[{code:1},{code:3202},{code:'0'},'not json',{}, {code:0,data:{maxWinMulti:['',0]}}, {code:0,data:{maxWinMulti:[3,2]}}, {code:0,data:{maxWinMulti:[-2,0]}}, {code:0,data:{maxWinMulti:[0,1000001]}},'x'.repeat(17000)];
  for(let i=0;i<variants.length+2;i++){
    variant=variants[i] ?? {code:0,data:{maxWinMulti:[-1,0]}};
    status=i===variants.length?503:200;delay=i===variants.length+1?3100:0;
    const tok=await c.launch({player_id:'failure-'+i,external_username:'external-'+i});
    const before=calls;
    const result=await p.spin(tok,'fallback','0',{coin_minor:2,level:1,buy_free:true});
    assert.equal(result.rtp.mode,'rtp');assert.equal(result.rtp.target_rtp,96);
    assert.deepEqual(await p.spin(tok,'fallback','0',{coin_minor:2,level:1,buy_free:true}),result);
    let r=result, steps=0;
    while((await p.state(tok)).state.phase!=='ready'){
      r=await p.spin(tok,'continue-'+steps++,r.sid,{coin_minor:2,level:1});
      assert.deepEqual(r.rtp,result.rtp);assert.ok(steps<1000);
    }
    assert.equal(calls,before+1);
    assert.equal(p.get("SELECT COUNT(*) AS n FROM prebet_rounds WHERE player_id=? AND error_code IS NOT NULL",'failure-'+i).n,1);
  }
  delay=0;variant={code:0,data:{maxWinMulti:[-1,0]}};
  const token=await c.launch({player_id:'success',external_username:'success'});
  const success=await p.spin(token,'valid','0',{coin_minor:2,level:1});
  assert.equal(success.rtp.mode,'prebet');assert.equal(success.wallet.credit_minor,0);
  // Missing callback transport also falls back; a lost debit response reuses it.
  c.control.prebet(c.mid,{url:'http://127.0.0.1:1/decision'});
  const retryToken=await c.launch({player_id:'retry',external_username:'retry'});
  c.dropDebit=true;
  await assert.rejects(p.spin(retryToken,'retry-key','0',{coin_minor:2,level:1}),{code:'WALLET_UNCERTAIN'});
  const recovered=await p.spin(retryToken,'retry-key','0',{coin_minor:2,level:1});
  assert.equal(recovered.rtp.mode,'rtp');
  assert.equal(p.get("SELECT COUNT(*) AS n FROM game_operations WHERE player_id='retry'").n,1);
});


test("signed round correlation joins decisions, callbacks and terminal changes including zero-credit tails",async(t)=>{
  const c=await setup(t),p=c.provider;
  c.control.prebet(c.mid,{url:c.control.merchant(c.mid).wallet_url+'/api/v1/callbacks/gtt/preBetDecision'});
  const tok=await c.launch({external_username:'round-player'}), bet={coin_minor:2,level:1};
  let result=await p.spin(tok,'correlated','0',{...bet,buy_free:true});
  const rid=result.round_id, did=result.decision_id;
  assert.ok(did);assert.equal(did,rid);assert.equal(result.decision_status,'accepted');
  const decision=c.walletRequests.find(x=>x.action==='preBetDecision').request;
  assert.equal(decision.decision_id,did);assert.equal(decision.round_id,rid);assert.equal(decision.game_id,1);
  let query=await c.signed('/gtt/v1/rounds/get',{decision_id:did});
  assert.equal(query.status,200);assert.equal(query.data.data.status,'active');assert.equal(query.data.data.terminal,false);
  const head=await c.signed('/gtt/v1/rounds/changes',{after_seq:0,limit:100});
  const cursor=head.data.data.next_after_seq;
  let steps=0;
  while((await p.state(tok)).state.phase!=='ready')result=await p.spin(tok,'tail-'+steps++,result.sid,bet);
  assert.ok(steps>0);assert.equal(result.round_end,true);
  query=await c.signed('/gtt/v1/rounds/get',{game_id:1,round_id:rid});
  const round=query.data.data;
  assert.equal(round.status,'completed');assert.equal(round.terminal,true);
  assert.equal(round.total_debit_minor,'150000');assert.equal(round.total_credit_minor,'0');
  assert.equal(round.resolution.actual_credit_minor,0);assert.equal(round.resolution_minor_unit,10000);
  const callbacks=c.walletRequests.filter(x=>x.request.decision_id===did && x.action!=='preBetDecision');
  assert.ok(callbacks.some(x=>x.action==='balance'&&x.request.round_end));
  for(const x of callbacks){assert.equal(x.request.round_id,rid);assert.equal(x.request.game_id,1);assert.equal(x.request.resolution.basis_minor*100,round.resolution.basis_minor);assert.equal(x.request.resolution.actual_credit_minor*100,round.resolution.actual_credit_minor);}
  const operations=await c.signed('/gtt/v1/transactions/list',{});
  assert.ok(operations.data.data.operations.every((o:any)=>o.decision_id===did&&o.round_id===rid));
  let after=cursor,terminalSeen=false;
  for(let i=0;i<1000;i++){
    const changes=await c.signed('/gtt/v1/rounds/changes',{after_seq:after,limit:2});
    assert.equal(changes.status,200);
    if(!changes.data.data.changes.length)break;
    assert.ok(changes.data.data.next_after_seq>after);after=changes.data.data.next_after_seq;
    terminalSeen ||= changes.data.data.changes.some((e:any)=>e.round.round_id===rid&&e.round.terminal);
  }
  assert.ok(terminalSeen,'zero-credit final step must be visible through durable change polling');
  const other=c.control.saveMerchant('test',{name:'round-other',enabled:true,wallet_url:c.control.merchant(c.mid).wallet_url},true);
  const path='/gtt/v1/rounds/get',raw=encode({decision_id:did});
  const cross=await c.request(path,raw,signedHeaders(other.merchant.id,other.keys.merchant_secret,path,raw));assert.equal(cross.status,404);
  assert.equal((await c.signed(path,{decision_id:did,game_id:2})).status,404);
  assert.equal((await c.signed('/gtt/v1/rounds/changes',{after_seq:-1})).status,400);
  // Failed callback retains its decision ID; actual model use is explicitly exposed.
  c.range=[];
  const failed=await c.launch({player_id:'fallback-link',external_username:'fallback-link'});
  const fallback=await p.spin(failed,'fallback-link','0',bet);
  const fallbackRound=(await c.signed(path,{decision_id:fallback.decision_id})).data.data;
  assert.equal(fallback.decision_status,'fallback');assert.equal(fallbackRound.execution_mode,'rtp');
  assert.equal(fallbackRound.resolution,null);assert.ok(fallbackRound.fallback_reason);
  assert.equal(c.walletRequests.filter(x=>x.action==='preBetDecision').at(-1).request.round_id,fallback.round_id);
  // Explicit pre-debit rejection releases a reservation; uncertain wallet results do not.
  c.range=[-1,0];c.balance=0;
  const rejected=await c.launch({player_id:'cancel-link',external_username:'cancel-link'});
  await assert.rejects(p.spin(rejected,'cancel-link','0',bet),{code:'INSUFFICIENT_BALANCE'});
  const cancelledId=c.walletRequests.filter(x=>x.action==='preBetDecision').at(-1).request.decision_id;
  const cancelled=(await c.signed(path,{decision_id:cancelledId})).data.data;
  assert.equal(cancelled.status,'cancelled');assert.equal(cancelled.total_debit_minor,'0');assert.equal(cancelled.cancel_reason,'INSUFFICIENT_BALANCE');
  c.balance=200000;c.dropDebit=true;
  const pending=await c.launch({player_id:'pending-link',external_username:'pending-link'});
  await assert.rejects(p.spin(pending,'pending-link','0',bet),{code:'WALLET_UNCERTAIN'});
  const pendingId=c.walletRequests.filter(x=>x.action==='preBetDecision').at(-1).request.decision_id;
  assert.equal((await c.signed(path,{decision_id:pendingId})).data.data.status,'settling');
  const recovered=await p.spin(pending,'pending-link','0',bet);
  assert.equal(recovered.decision_id,pendingId);
  // A recovered zero-payout step can still have extension/free steps remaining.
  let tail = recovered, tailIndex = 0;
  while ((await p.state(pending)).state.phase !== 'ready') {
    assert.ok(tailIndex < 1000);
    tail = await p.spin(pending, 'pending-tail-' + tailIndex++, tail.sid, bet);
  }
  assert.equal((await c.signed(path,{decision_id:pendingId})).data.data.status,'completed');
});
