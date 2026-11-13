import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";
import { gunzipSync } from "node:zlib";
import { request as httpRequest } from "node:http";
import { Control } from "../gateway/control.js";
import { Provider } from "../gateway/provider.js";
import { GameClient } from "../gateway/game-client.js";
import { gatewayServer } from "../gateway/http.js";
import { gameServer } from "../games/buffalo-win/service.js";
import { platformServer } from "../services/platform.js";
import { listen, server, body, send } from "../shared/http.js";
import { encode, sha, signedHeaders } from "../shared/core.js";
import { GAME_CODES, gameUnit } from "../gateway/catalog.js";
import { transactions } from "../gateway/admin.js";
import { verifiedReadinessFixture } from "./readiness-fixture.js";
import { GameReadiness } from "../gateway/readiness.js";
import * as py from "../compat/runtime.js";
import * as pg from "../migrated/py/adapters/pg/protocol.js";
import * as vaultsWire from "../migrated/py/adapters/jili/three_billion_vaults.js";
import { method } from "../services/local.js";
import {
  modeKey,
  modePayloads,
  ROUND_MODEL_VERSION,
} from "../games/round-model.js";

async function setup(t: any) {
  const dir = mkdtempSync(join(tmpdir(), "merchant-games-")),
    control = new Control(
      join(dir, "control.db"),
      resolve("config/control.sql"),
    );
  const created = control.saveMerchant(
      "test",
      {
        name: "all-games",
        enabled: true,
        wallet_url: "http://127.0.0.1:8111",
        games: GAME_CODES.map((_, i) => i + 1),
        minor_unit: 10000,
      },
      true,
    ),
    mid = created.merchant.id;
  const config: any = {
    environment: "development",
    sandbox_merchant: mid,
    sandbox_player: "p1",
    sandbox_external_username: "external-p1",
    sandbox_balance_minor: 100000000,
    platform_database: join(dir, "wallet.db"),
    game_database: join(dir, "game.db"),
    gateway_origin: "http://127.0.0.1",
  };
  const { server: wallet, wallet: mock } = platformServer(config, control),
    wp = await listen(wallet);
  control.saveMerchant("test", {
    ...control.merchant(mid),
    wallet_url: `http://127.0.0.1:${wp}`,
  });
  const gc = JSON.parse(readFileSync("config/buffalo-win.json", "utf8")),
    secret = "x".repeat(64),
    game = gameServer(gc, secret),
    gp = await listen(game),
    p = new Provider(
      config.game_database,
      control,
      new GameClient("http://127.0.0.1:" + gp, secret, gc),
      resolve("config/game.sql"),
      "http://127.0.0.1",
      resolve("config/rtp-models.json"),
    );
  await p.initialize();
  p.readiness = verifiedReadinessFixture();
  for(let game_id=1;game_id<=19;game_id++) control.setGameAvailability("fixture",{game_id,enabled:true,version:0});
  const gateway = gatewayServer(p, config, resolve("../clients/buffalo-win")),
    port = await listen(gateway);
  p.playOrigin = config.gateway_origin = "http://127.0.0.1:" + port;
  t.after(async () => {
    await gateway.protocolPool.close();
    for (const s of [gateway, wallet, game]) {
      s.closeAllConnections();
      await new Promise<void>((ok) => s.close(() => ok()));
    }
    p.close();
    control.close();
    rmSync(dir, { recursive: true, force: true });
  });
  const signed = async (path: string, q: any) => {
    const raw = encode(q),
      r = await fetch(config.gateway_origin + path, {
        method: "POST",
        headers: signedHeaders(mid, created.keys.merchant_secret, path, raw),
        body: raw,
      });
    const value: any = await r.json();
    assert.ok(r.ok, JSON.stringify(value));
    return value.data;
  };
  const host = async (
    id: number,
    path: string,
    token: string,
    body?: any,
    extra: any = {},
  ) =>
    new Promise<any>((ok, fail) => {
      const data =
        body === undefined
          ? undefined
          : Buffer.from(
              Buffer.isBuffer(body) || typeof body === "string"
                ? body
                : JSON.stringify(body),
            );
      const req = httpRequest(
        {
          hostname: "127.0.0.1",
          port,
          path,
          method: data ? "POST" : "GET",
          headers: {
            host: `g${id}.localhost:${port}`,
            cookie: `gtt-session=${token}`,
            authorization: "Bearer " + token,
            "x-local-game-session": token,
            ...(data
              ? {
                  "content-type": "application/json",
                  "content-length": data.length,
                }
              : {}),
            ...extra,
          },
        },
        (res) => {
          const chunks: Buffer[] = [];
          res.on("data", (b) => chunks.push(b));
          res.on("end", () =>
            ok({
              status: res.statusCode,
              headers: res.headers,
              text: Buffer.concat(chunks).toString(),
            }),
          );
        },
      );
      req.on("error", fail);
      req.setTimeout(20000, () => req.destroy(Error("timeout")));
      req.end(data);
    });
  return { dir, p, control, config, mid, mock, wp, signed, host, gateway };
}

test("all 19 games can be opened and launched despite incomplete collection", async(t)=>{
  const {p,mid}=await setup(t);
  p.readiness=new GameReadiness();
  assert.equal(p.merchantCatalog(mid).length,19);
  for(let game_id=1;game_id<=19;game_id++){
    assert.equal(p.readiness.get(GAME_CODES[game_id-1]).collection_complete,false);
    const launched=await p.launch(mid,{game_id,player_id:"p1"});
    assert.ok(launched.launch_url);
  }
});

test("closed games reject all new launches before wallet callbacks", async (t) => {
  const {p,mid,control} = await setup(t);
  p.readiness = new GameReadiness();
  for(let game_id=1;game_id<=19;game_id++) control.setGameAvailability("test",{game_id,enabled:false,version:control.gameAvailability(game_id).version});
  assert.equal(control.merchant(mid).games.length,19);
  assert.equal(p.catalog(mid).length,19);
  assert.ok(p.catalog(mid).every((g:any)=>!g.integration_available && g.readiness.blockers.length>0));
  p.walletClient.call = async()=>{throw Error("blocked launch must not call wallet");};
  for(let game_id=1;game_id<=19;game_id++) {
    await assert.rejects(p.launch(mid,{game_id,player_id:"p1"}),{code:"GAME_CLOSED"});
    await assert.rejects(p.multi!.launch(mid,{game_id,player_id:"p1"}),{code:"GAME_CLOSED"});
  }
  assert.equal(p.get("SELECT COUNT(*) AS n FROM merchant_sessions").n,0);
});

test("four-place game sessions cannot bypass closure and can finish their existing free round", async (t) => {
  const {p,mid} = await setup(t);
  const launch = await p.launch(mid,{game_id:1,player_id:"p1"});
  const tok = new URL(launch.launch_url).searchParams.get("ops")!;
  const initial = await p.state(tok), bet={coin_minor:2,level:1};
  let result = await p.spin(tok,"approved-purchase",initial.state.sid,{...bet,buy_free:true});
  p.readiness = new GameReadiness();
  p.control.setGameAvailability("test",{game_id:1,enabled:false,version:p.control.gameAvailability(1).version});
  assert.ok(await p.launch(mid,{game_id:1,player_id:"p1"}));
  for(let i=0;(await p.state(tok)).state.phase!=="ready" && i<100;i++) result=await p.spin(tok,"finish-"+i,result.sid,bet);
  assert.equal((await p.state(tok)).state.phase,"ready");
  await assert.rejects(p.spin(tok,"not-approved",result.sid,bet),{code:"GAME_CLOSED"});
  assert.equal(p.get("SELECT COUNT(*) AS n FROM node_calculations WHERE request_key='not-approved'").n,0);
});

test("all games inherit merchant RTP with a 96 percent fallback and scoped game overrides", async (t) => {
  const { p, mid } = await setup(t);
  for (let id = 1; id <= 19; id++) {
    const policy = p.rtp.resolve(mid, "", id);
    assert.equal(policy.target_bp, 9600);
    assert.equal(policy.scope, "default");
    assert.equal(policy.calibrated, id === 1);
  }
  const m90 = p.rtp
    .models()
    .find((m) => m.game_id === 1 && m.target_bp === 9000)!;
  const m96 = p.rtp
    .models()
    .find((m) => m.game_id === 1 && m.target_bp === 9600)!;
  p.rtp.policy(
    "test",
    {
      scope: "merchant",
      merchant_id: mid,
      model_id: m90.id,
      revision: 0,
      reason: "set merchant target",
    },
    true,
  );
  for (let id = 1; id <= 19; id++)
    assert.equal(p.rtp.resolve(mid, "", id).target_bp, 9000);
  p.rtp.policy(
    "test",
    {
      scope: "game",
      game_id: 3,
      merchant_id: mid,
      model_id: m96.id,
      revision: 0,
      reason: "set game override",
    },
    true,
  );
  assert.equal(p.rtp.resolve(mid, "", 3).target_bp, 9600);
  assert.equal(p.rtp.resolve(mid, "", 3).scope, "game");
  assert.equal(p.rtp.resolve(mid, "", 3).calibrated, false);
  assert.equal(p.rtp.resolve(mid, "", 4).target_bp, 9000);
  p.rtp.policy(
    "test",
    {
      scope: "game",
      game_id: 3,
      merchant_id: mid,
      model_id: null,
      revision: 1,
      reason: "restore inheritance",
    },
    true,
  );
  assert.equal(p.rtp.resolve(mid, "", 3).target_bp, 9000);
  assert.equal(
    p.catalog(mid).find((g) => g.id === 3)!.rtp_status,
    "not_calibrated",
  );
  const job = p.get(
    "SELECT * FROM rtp_jobs WHERE game_id=3 AND target_bp=9600 AND status='queued'",
  );
  assert.ok(job, "Game override automatically queues its missing model");
  assert.equal(
    p.get("SELECT game_id FROM rtp_jobs WHERE id=?", job.id).game_id,
    3,
  );
  assert.throws(
    () =>
      p.rtp.createJob("test", {
        game_id: 3,
        target_bp: 9600,
        reason: "test duplicate queue",
      }),
    { code: "RTP_JOB_EXISTS" },
  );
  assert.ok(
    p.rtp.createJob("test", {
      game_id: 4,
      target_bp: 9600,
      reason: "test separate game queue",
    }).id,
  );
});

test("fixed round model freezes a purchased feature and replays its complete payout", async (t) => {
  const { p, mid, signed } = await setup(t),
    code = "super-ace",
    game = p.multi!.game(code);
  const payload = { buy_bonus: true },
    bet = p.multi!.call(code, "normalize_bet", payload);
  // Synthetic test-only model in the temporary DB: exercises seed replay, not calibration evidence.
  const report = {
    algorithm: ROUND_MODEL_VERSION,
    game_id: 15,
    ruleset_id: py.attr(game, "ruleset_id"),
    modes: { [modeKey(bet)]: { candidates: 2, upper_probability: 1 } },
  };
  p.run(
    "INSERT INTO rtp_models VALUES(?,?,?,?,?,?)",
    "test-round-model",
    9600,
    "test-only",
    encode(report),
    1,
    4102444800,
  );
  const launch = await signed("/gtt/v1/games/launch", {
      game_id: 15,
      player_id: "p1",
    }),
    tok = new URL(launch.launch_url).searchParams.get("ops")!;
  let state = p.multi!.initial(mid, "p1", code),
    total = 0;
  const first = await p.spin(tok, "model-start", state.sid, payload);
  total += first.wallet.credit_minor;
  assert.deepEqual(await p.spin(tok, "model-start", state.sid, payload), first);
  const binding = p.get(
      "SELECT * FROM round_model_bindings WHERE merchant_id=? AND game_id=?",
      mid,
      code,
    ),
    plan = JSON.parse(binding.plan_json);
  const m90 = p.rtp
    .models()
    .find((m) => m.game_id === 1 && m.target_bp === 9000)!;
  p.rtp.policy(
    "test",
    {
      scope: "merchant",
      merchant_id: mid,
      model_id: m90.id,
      revision: 0,
      reason: "change during purchased round",
    },
    true,
  );
  for (let i = 0; i < 4096; i++) {
    state = p.multi!.initial(mid, "p1", code);
    if (state.phase === "ready") break;
    const r = await p.spin(tok, "model-continue-" + i, state.sid, {});
    total += r.wallet.credit_minor;
  }
  assert.equal(p.multi!.initial(mid, "p1", code).phase, "ready");
  assert.equal(total, plan.total_credit_minor);
  assert.equal(
    JSON.parse(
      p.get(
        "SELECT context_json FROM round_model_bindings WHERE id=?",
        binding.id,
      ).context_json,
    ).target_rtp,
    96,
  );
  assert.equal(
    p.rtp.snapshot({ game_id: 15, merchant_id: mid }).merchants[0].rounds,
    1,
  );
});

test("all 18 fixed round models replay every supported paid mode through merchant settlement", async (t) => {
  const { p, mid } = await setup(t),
    g = p.multi!;
  for (let id = 2; id <= 19; id++) {
    const code = GAME_CODES[id - 1],
      game = g.game(code),
      payloads = modePayloads(code);
    // Synthetic models in an isolated database test execution, not statistical RTP.
    p.run(
      "INSERT INTO rtp_models VALUES(?,?,?,?,?,?)",
      `test-round-${id}`,
      9600,
      "test-only",
      encode({
        algorithm: ROUND_MODEL_VERSION,
        game_id: id,
        ruleset_id: py.attr(game, "ruleset_id"),
        modes: Object.fromEntries(
          payloads.map((payload) => [
            modeKey(g.call(code, "normalize_bet", payload)),
            { candidates: 2, upper_probability: 1 },
          ]),
        ),
      }),
      1,
      4102444800,
    );
    const launch = await p.launch(mid, {
        game_id: id,
        player_id: "p1",
        external_username: "external-p1",
      }),
      token = new URL(launch.launch_url).searchParams.get("ops")!;
    for (const [mode, base] of payloads.entries()) {
      const start = g.initial(mid, "p1", code);
      let total = 0,
        debit = 0,
        steps = 0;
      do {
        const state = g.initial(mid, "p1", code);
        let payload: any = { ...base };
        if (state.phase !== "ready") {
          if (id === 5)
            payload = {
              action: state.phase === "collect" ? "collect" : "continue",
            };
          else if (id >= 6 && id <= 9)
            payload = { action: "confirm", round_id: state.pending.round_id };
          else if (id >= 16 && id <= 18)
            payload = {
              ...base,
              action: state.phase === "collect" ? "collect" : "spin",
              request_index: (state.protocol_index ?? 0) + 1,
            };
          else delete payload.buy_free;
        }
        const result = await p.spin(
          token,
          `model-${mode}-${steps}`,
          state.sid,
          payload,
        );
        total += result.wallet.credit_minor;
        debit += result.wallet.debit_minor;
        assert.equal(
          result.rtp.target_rtp,
          96,
          `${code} mode ${mode} step ${steps}`,
        );
        assert.ok(++steps < 4096);
      } while (g.initial(mid, "p1", code).phase !== "ready");
      const row = p.get(
          "SELECT plan_json FROM round_model_bindings WHERE merchant_id=? AND game_id=? AND initial_sid=?",
          mid,
          code,
          start.sid,
        ),
        plan = JSON.parse(row.plan_json);
      assert.equal(
        total,
        plan.total_credit_minor,
        `${code} mode ${mode} credit`,
      );
      assert.equal(debit, plan.basis_minor, `${code} mode ${mode} debit`);
      assert.equal(steps, plan.steps, `${code} mode ${mode} steps`);
    }
  }
});

test("round model import verifies game identity, all play modes and validation evidence", async (t) => {
  const { p } = await setup(t),
    game = p.multi!.game("super-ace");
  // Synthetic constant-return statistical fixture, never exported or used by a live merchant.
  const validation = {
    rounds: 20000,
    sum: 19200,
    squares: 18432,
    rtp: 0.96,
    variance: 0,
    ci_half: 0,
    ci_low: 0.96,
    ci_high: 0.96,
    confidence: 0.99,
    unfinished_rounds: 0,
    batch_size: 100,
    batch_sum: 192,
    batch_squares: 184.32,
  };
  const modes = Object.fromEntries(
    [false, true].map((buy_bonus) => [
      modeKey(p.multi!.call("super-ace", "normalize_bet", { buy_bonus })),
      {
        payload: { buy_bonus },
        candidates: 2,
        upper_probability: 0.5,
        validation,
      },
    ]),
  );
  const report = {
    format: 2,
    algorithm: ROUND_MODEL_VERSION,
    game_id: 15,
    target_bp: 9600,
    engine_version: py.attr(game, "version"),
    ruleset_id: py.attr(game, "ruleset_id"),
    modes,
    model_hash: sha(encode(modes)),
  };
  assert.ok(p.rtp.importModel(report).startsWith("round-15-9600-"));
  assert.throws(
    () => p.rtp.importModel({ ...report, ruleset_id: "different-rules" }),
    { code: "RTP_MODEL_INVALID" },
  );
  const incomplete = { ...modes };
  delete incomplete[Object.keys(incomplete)[0]];
  assert.throws(
    () =>
      p.rtp.importModel({
        ...report,
        modes: incomplete,
        model_hash: sha(encode(incomplete)),
      }),
    { code: "RTP_MODEL_INVALID" },
  );
  const bad = structuredClone(modes);
  Object.values(bad)[0].validation.ci_half = 0.5;
  assert.throws(
    () =>
      p.rtp.importModel({
        ...report,
        modes: bad,
        model_hash: sha(encode(bad)),
      }),
    { code: "RTP_MODEL_INVALID" },
  );
});

test("merchant launch honors documented default game and prebet player type updates", async (t) => {
  const { p, mid, signed, control, config } = await setup(t);
  const docs = JSON.parse(readFileSync("config/integration.json", "utf8"));
  const snippet = docs.sections
    .find((s: any) => s.id === "authentication")
    .blocks.find((b: any) => b.language === "javascript").code;
  const sample = await import(
    "data:text/javascript;base64," + Buffer.from(snippet).toString("base64")
  );
  const first = (
    await sample.post(
      config.gateway_origin,
      mid,
      control.merchant(mid, true).merchant_secret,
      "/gtt/v1/games/launch",
      {
        player_id: "p1",
        external_username: "external-p1",
        prebet_type: "NORMAL",
      },
    )
  ).data;
  assert.equal(first.game_id, 1);
  assert.equal(new URL(first.launch_url).hostname, "g1.localhost");
  await signed("/gtt/v1/games/launch", {
    game_id: 3,
    player_id: "p1",
    external_username: "external-p1",
    prebet_type: "SURE_WIN",
  });
  assert.equal(
    p.get(
      "SELECT prebet_type FROM merchant_players WHERE merchant_id=? AND player_id=?",
      mid,
      "p1",
    ).prebet_type,
    "SURE_WIN",
  );
  await assert.rejects(
    p.launch(mid, { game_id: 3, player_id: "p1", prebet_type: "NORMAL" }),
    { code: "PREBET_PLAYER_REQUIRED" },
  );
  await signed("/gtt/v1/games/launch", { game_id: 3, player_id: "p1" });
  assert.equal(
    p.get(
      "SELECT prebet_type FROM merchant_players WHERE merchant_id=? AND player_id=?",
      mid,
      "p1",
    ).prebet_type,
    "SURE_WIN",
  );
});

test("cross-site iframe loads assets without cookies and authenticates APIs with its launch token", async (t) => {
  const { signed, host, p } = await setup(t);
  const launch = await signed("/gtt/v1/games/launch", { game_id: 1, player_id: "p1" });
  const url = new URL(launch.launch_url), token = url.searchParams.get("ops")!;
  const noCredentials = { cookie: "", authorization: "", "x-local-game-session": "" };
  const entry = await host(1, url.pathname + url.search, "", undefined, noCredentials);
  assert.equal(entry.status, 200, entry.text);
  const assets = ["/local-auth-bootstrap.js", "/local-frame-clock.js", "/shared/984721902a/index.json"];
  for (const path of assets) {
    const r = await host(1, path, "", undefined, noCredentials);
    assert.equal(r.status, 200, `${path}: ${r.text}`);
    assert.equal(r.headers["set-cookie"], undefined, "static requests must not replace the session cookie");
  }
  for (const path of ["/", "/api/v1/wallet", "/api/v1/history", "/fixtures/auth-metadata.json", "/%66ixtures/auth-metadata.json", "/assets/%2e%2e%2ffixtures/auth-metadata.json", "/web-api/game-proxy/v2/GameWallet/Get.json"]) {
    const r = await host(1, path, "", undefined, noCredentials);
    assert.equal(r.status, 401, `${path}: ${r.text}`);
  }
  const headers = { ...noCredentials, "x-local-game-session": token, "content-type": "application/x-www-form-urlencoded" };
  const wallet = await host(1, "/web-api/game-proxy/v2/GameWallet/Get", "", "atk=" + token, headers);
  assert.equal(wallet.status, 200, wallet.text);
  assert.equal(JSON.parse(wallet.text).err, null);
  const cookieOnly = await host(1, "/api/v1/wallet", "", undefined, { ...noCredentials, cookie: `gtt-session=${token}` });
  assert.equal(cookieOnly.status, 200, cookieOnly.text);
  const wrongOrigin = await host(1, assets[0], "", undefined, { ...noCredentials, origin: "http://untrusted.example" });
  assert.equal(wrongOrigin.status, 403, wrongOrigin.text);
  const staleCookie = await host(1, "/api/v1/wallet", token, undefined, { cookie: "gtt-session=stale-cookie", authorization: "" });
  assert.equal(staleCookie.status, 200, staleCookie.text);
  const invalidHeader = await host(1, "/api/v1/wallet", token, undefined, { authorization: "", "x-local-game-session": "invalid-token" });
  assert.equal(invalidHeader.status, 401, invalidHeader.text);
  const expired = p.get("SELECT token_hash FROM merchant_sessions ORDER BY expires_at DESC LIMIT 1");
  p.run("UPDATE merchant_sessions SET expires_at=0 WHERE token_hash=?", expired.token_hash);
  assert.equal((await host(1, "/api/v1/wallet", token)).status, 401);
});

test("19 games: signed catalog, original client entry, wallet, settlement, idempotency and scoped admin records", async (t) => {
  const f = await setup(t),
    { p, mid, signed, host } = f;
  assert.equal((await signed("/gtt/v1/games/list", {})).games.length, 19);
  assert.ok((await signed("/gtt/v1/games/list", {})).games.every((g: any) => g.minor_unit === 10000));
  assert.equal(
    (await (await fetch(`http://127.0.0.1:${f.wp}/sandbox/games`)).json()).data
      .games.length,
    19,
  );
  let expectedBalance = 100000000;
  for (let i = 0; i < GAME_CODES.length; i++)
    await t.test(GAME_CODES[i], async () => {
      const code = GAME_CODES[i],
        id = i + 1,
        launch = await signed("/gtt/v1/games/launch", {
          game_id: id,
          player_id: "p1",
          external_username: "external-p1",
        }),
        url = new URL(launch.launch_url),
        token = url.searchParams.get("ops")!;
      assert.equal(url.hostname, `g${id}.localhost`);
      assert.equal(url.searchParams.has("mock"),false,code);
      if ([1,2,3,4,19].includes(id)) assert.equal(url.searchParams.get("btt"),"1",code);
      assert.equal(launch.balance_minor, expectedBalance);
      let path = url.pathname + url.search;
      for (let j = 0; j < 5; j++) {
        const r = await host(id, path, token);
        if ([301, 302, 303, 307, 308].includes(r.status)) {
          const next = new URL(r.headers.location, url);
          assert.equal(next.host, url.host);
          assert.equal(next.searchParams.has("mock"),false,code);
          assert.equal(next.searchParams.get("ops"),token,code);
          if (id>=6 && id<=9) {
            assert.equal(next.searchParams.get("mode"),"1",code);
            assert.equal(next.searchParams.get("partner"),mid,code);
            assert.equal(next.searchParams.get("currency"),"USD",code);
            assert.equal(next.searchParams.has("disableddemotext"),false,code);
          }
          if (id>=10 && id<=15) {
            assert.equal(next.searchParams.get("demo"),"false",code);
            assert.equal(next.searchParams.has("loginFrom"),false,code);
          }
          path = next.pathname + next.search;
          continue;
        }
        assert.equal(r.status, 200, r.text.slice(0, 500));
        assert.match(r.text, /<html|<!doctype/i);
        assert.match(r.text,/window\.__GTT_MERCHANT__=Object\.freeze/);
        if(id===5){assert.match(r.text,/practice:\s*0/);assert.ok(r.text.includes('ticket: "'+token+'"'));}
        if(id>=16 && id<=18){
          assert.match(r.text,/demoMode.{0,8}0/);assert.match(r.text,/accountType.{0,8}R/);
          const settings=await host(id,"/hub-demo/ge/v3/saveSettings.do",token,"mgckey="+token+"&id=game",{"content-type":"application/x-www-form-urlencoded"});
          assert.equal(settings.status,200,settings.text);
          assert.equal(settings.text,"");
        }
        break;
      }
      const wallet = await host(id, "/api/v1/wallet", token);
      assert.equal(wallet.status, 200, wallet.text);
      assert.equal(JSON.parse(wallet.text).minor_unit, gameUnit(code));
      if ([12,13].includes(id)) {
        const info=await host(id,"/tada/command",token,{token,ack:1,payload:[]});
        assert.equal(info.status,200,info.text);
        const data=py.plain(py.call(vaultsWire.unpack,["GameInfoAck",py.from(JSON.parse(info.text).data)]));
        assert.equal(data.WalletInfo[0].currencyNumber,80);
        assert.equal(data.WalletInfo[0].currencyName,"USD");
        assert.equal(data.WalletInfo[0].currencySymbol,"USD");
        assert.equal(data.WalletInfo[0].coin,expectedBalance/10000);
      }
      if([1,2,3,4,19].includes(id)) {
        const auth=await host(id,"/web-api/auth/session/v2/verifyOperatorPlayerSession",token,new URLSearchParams({os:token,btt:"1",otk:mid}).toString(),{"content-type":"application/x-www-form-urlencoded"});
        assert.equal(auth.status,200,auth.text);
        assert.equal(JSON.parse(auth.text).dt.cc,"USD");
        assert.equal(JSON.parse(auth.text).dt.nkn,"p1");
      }
      const ref = JSON.parse(
          gunzipSync(
            readFileSync(`fixtures/all-games/${code}.json.gz`),
          ).toString(),
        ),
        bet = ref.initial[0].payload,
        state = await p.state(token);
      const spin = await host(
        id,
        `/api/v1/games/${code}/spin`,
        token,
        { previous_sid: state.state.sid, bet },
        { "idempotency-key": "same-key" },
      );
      assert.equal(spin.status, 200, spin.text);
      const result = JSON.parse(spin.text);
      assert.equal(result.game_id, code);
      assert.deepEqual(
        {
          ...(await p.spin(token, "same-key", state.state.sid, bet)),
          game_id: code,
        },
        result,
      );
      expectedBalance +=
        result.settlement.credit_minor - result.settlement.debit_minor;
      const publicOperations = await signed("/gtt/v1/transactions/list", {});
      const publicResult = publicOperations.operations.find((o: any) => o.game_id === id).result;
      assert.equal(publicResult.minor_unit, 10000);
      assert.equal(publicResult.wallet.after_minor, expectedBalance);
      assert.equal(publicResult.wallet.debit_minor, result.settlement.debit_minor);
      const retried = await signed("/gtt/v1/transactions/retry", {operation_id:publicOperations.operations.find((o: any) => o.game_id === id).operation_id});
      assert.deepEqual(retried, publicResult);
      assert.equal(result.settlement.balance_minor, expectedBalance);
      const history: any = transactions(p, { merchant_id: mid, game_id: id });
      assert.equal(history.length, 1);
      assert.equal(history[0].debit_minor, result.settlement.debit_minor);
      assert.equal(history[0].minor_unit, 10000);
      const after = await host(id, "/api/v1/wallet", token);
      assert.equal(after.status, 200, after.text);
      assert.equal(
        JSON.parse(after.text).balance_minor,
        Math.floor((expectedBalance * gameUnit(code)) / 10000),
      );
      assert.equal((await host(id, "/api/v1/sessions", token, {})).status, 401);
      assert.equal(
        (await host(id === 19 ? 1 : id + 1, "/api/v1/wallet", token)).status,
        403,
      );
    });
  const facts = p.all(
    "SELECT * FROM rtp_facts WHERE merchant_id=? AND closed=1 AND voided=0 AND CAST(debit_minor AS INTEGER)>0",
    mid,
  );
  const aggregate = p.rtp.snapshot({ game_id: 0, merchant_id: mid })
    .merchants[0];
  assert.equal(aggregate.minor_unit, 10000);
  assert.equal(aggregate.rounds, facts.length);
  for (const field of ["debit_minor", "credit_minor"])
    assert.equal(
      aggregate[field],
      String(
        facts.reduce(
          (sum, r) =>
            sum +
            (BigInt(r[field]) * 10000n) /
              BigInt(gameUnit(GAME_CODES[r.game_id - 1])),
          0n,
        ),
      ),
    );
});

test("original wire adapters settle through the merchant wallet for all 19 games", async (t) => {
  const { p, mid, signed, host } = await setup(t);
  for (let i = 0; i < 19; i++)
    await t.test(GAME_CODES[i], async () => {
      const code = GAME_CODES[i],
        id = i + 1,
        launch = await signed("/gtt/v1/games/launch", {
          game_id: id,
          player_id: "p1",
        }),
        token = new URL(launch.launch_url).searchParams.get("ops")!;
      const ref = JSON.parse(
        gunzipSync(
          readFileSync(`fixtures/protocols/${code}.json.gz`),
        ).toString(),
      );
      let path = "",
        data: any,
        headers: any = {},
        calls: any[] = [];
      if (ref.adapter === "hacksaw") {
        path = "/api/play/bet";
        data = { ...ref.calls[1].args[0], sessionUuid: token };
      } else if (ref.adapter === "pp") {
        path = "/hub-demo/ge/v3/gameService";
        const q = { ...ref.calls[1].args[0], mgckey: [token] };
        data = new URLSearchParams(
          Object.entries(q).map(([k, v]: any) => [k, v[0]]),
        ).toString();
        headers = { "content-type": "application/x-www-form-urlencoded" };
      } else if (ref.adapter === "playngo") {
        path = "/";
        data = new URLSearchParams({
          d: `3\n${token}!\n1 1 10 10 1`,
        }).toString();
        headers = { "content-type": "application/x-www-form-urlencoded" };
      } else if (["jili", "tada"].includes(ref.adapter)) {
        const spin = ref.calls.find(
          (c: any) =>
            c.method === "handle" && c.args[1] !== 2 && c.args[1] !== 4,
        );
        assert.ok(spin);
        path = "/" + ref.adapter + "/command";
        data = {
          token,
          ack: spin.args[1],
          payload: spin.args[2],
          key: spin.args[3],
        };
      } else {
        const c = ref.calls.find((c: any) => c.method === "spin");
        data = Buffer.from(c.args[0].__bytes__, "base64");
        path = `/game-api/${code}/v4/${code === "captains-bounty" ? "spin" : "Spin"}`;
        if (code === "buffalo-win") {
          path = "/game-api/buffalo-win/v2/Spin";
          const form = new URLSearchParams(data.toString().replace("reference-" + code, token));
          form.set("btt", "1");
          data = form.toString();
          headers = { "content-type": "application/x-www-form-urlencoded" };
        }
        if (code !== "buffalo-win") {
          const salt =
            code === "captains-bounty"
              ? 9
              : code === "fortune-rabbit"
                ? 25
                : code === "wild-bandito"
                  ? 5
                  : 11;
          const [raw, seed] = py.call(pg.unpack, [data, null, salt]);
          const patched = py.call(pg.patch, [
            raw,
            py.dict([[1, py.call(pg.text_field, [1, token])],[2,py.call(pg.field,[2,0,1])]]),
          ]);
          data = py.call(pg.pack, [patched, seed, salt]);
        }
      }
      const r = await host(id, path, token, data, headers);
      assert.equal(r.status, 200, r.text.slice(0, 500));
      if ([1,2,3,4,19].includes(id)) {
        let demo: any;
        if (id === 1) {
          const form = new URLSearchParams(data);form.set("btt","2");demo=form.toString();
        } else {
          const salt = id === 2 ? 9 : id === 3 ? 25 : id === 4 ? 5 : 11;
          const [raw,seed] = py.call(pg.unpack,[data,null,salt]);
          demo=py.call(pg.pack,[py.call(pg.patch,[raw,py.dict([[2,py.call(pg.field,[2,0,2])]])]),seed,salt]);
        }
        const rejected = await host(id,path,token,demo,headers);
        assert.equal(rejected.status,400,"Merchant session accepted demo bet type: "+code);
      }
      const rows = p.all(
        "SELECT * FROM game_operations WHERE merchant_id=? AND game_id=?",
        mid,
        code,
      );
      assert.equal(rows.length, 1, r.text.slice(0, 500));
      assert.equal(rows[0].status, "settled");
      const again = await host(id, path, token, data, headers);
      assert.equal(again.status, 200, again.text.slice(0, 500));
      assert.equal(
        p.get(
          "SELECT COUNT(*) AS n FROM game_operations WHERE merchant_id=? AND game_id=?",
          mid,
          code,
        ).n,
        1,
      );
    });
});

test("complete prebet rounds, exact wallet precision, revocation and uncertain settlement recovery", async (t) => {
  const f = await setup(t),
    { p, mid, control, mock, signed } = f;
  control.saveMerchant("test", {
    ...control.merchant(mid),
    pre_payout: {
      enabled: true,
      url: `http://127.0.0.1:${f.wp}/api/v1/callbacks/gtt/preBetDecision`,
    },
  });
  // Wide finite cap keeps this existing purchase/continuation test independent of the zero-payout default.
  method(mock, "prebet_policy", mid, py.from([-1, 1000000]));
  for (let id = 1; id <= 19; id++)
    await t.test(GAME_CODES[id - 1], async () => {
      const code = GAME_CODES[id - 1],
        launch = await signed("/gtt/v1/games/launch", {
          game_id: id,
          player_id: "p1",
          external_username: "external-p1",
        }),
        token = new URL(launch.launch_url).searchParams.get("ops")!,
        g = p.multi!,
        ref = JSON.parse(
          gunzipSync(
            readFileSync(`fixtures/all-games/${code}.json.gz`),
          ).toString(),
        ),
        base = ref.initial.at(-1).payload;
      let index = 0,
        total = 0,
        first: any;
      do {
        const s = g.initial(mid, "p1", code);
        let bet = { ...base };
        if (s.phase !== "ready") {
          if (id === 5)
            bet = { action: s.phase === "collect" ? "collect" : "continue" };
          else if (id >= 6 && id <= 9)
            bet = { action: "confirm", round_id: s.pending.round_id };
          else if (id >= 16 && id <= 18)
            bet = {
              ...base,
              action: s.phase === "collect" ? "collect" : "spin",
              request_index: (base.request_index ?? 0) + index,
            };
          else delete bet.buy_free;
        }
        const result = await p.spin(token, "complete-" + index, s.sid, bet);
        first ??= result;
        total += result.wallet.credit_minor;
        index++;
        assert.ok(index < 4096);
      } while (g.initial(mid, "p1", code).phase !== "ready");
      const round = p.get(
          "SELECT * FROM prebet_rounds WHERE merchant_id=? AND game_id=?",
          mid,
          code,
        ),
        plan = JSON.parse(round.plan_json);
      assert.equal(total, plan.total_credit_minor);
      const request=JSON.parse(round.prebet_request_json);
      assert.match(request.bet_amount,/^\d+\.\d{4}$/);
      assert.equal(request.decision_id,first.decision_id);assert.equal(request.round_id,first.round_id);assert.equal(request.game_id,id);
      const summary=await signed('/gtt/v1/rounds/get',{decision_id:first.decision_id});
      assert.equal(summary.status,'completed');assert.equal(summary.terminal,true);
      assert.equal(summary.game_id,id);assert.equal(summary.resolution.actual_credit_minor,total*(10000/gameUnit(code)));
      assert.equal(summary.total_credit_minor,String(total*(10000/gameUnit(code))));
      assert.equal(summary.resolution_minor_unit,10000);
      assert.equal(summary.resolution.basis_minor,first.settlement.debit_minor);
      assert.equal(
        first.settlement.debit_minor,
        first.wallet.debit_minor * (10000 / gameUnit(code)),
      );
    });
  const launch = await p.launch(mid, {
      game_id: 2,
      player_id: "p1",
      external_username: "external-p1",
    }),
    token = new URL(launch.launch_url).searchParams.get("ops")!,
    s = await p.state(token),
    original = p.walletClient.call.bind(p.walletClient);
  let drop = true;
  p.walletClient.call = async (...args: Parameters<typeof original>) => {
    const r = await original(...args);
    if (args[1] === "debit" && drop) {
      drop = false;
      throw Error("response lost after wallet committed");
    }
    return r;
  };
  const ref = JSON.parse(
    gunzipSync(
      readFileSync("fixtures/all-games/captains-bounty.json.gz"),
    ).toString(),
  );
  await assert.rejects(
    p.spin(token, "lost-response", s.state.sid, ref.initial[0].payload),
    (e: any) => e.code === "WALLET_UNCERTAIN",
  );
  const pending = p.get(
    "SELECT id FROM game_operations WHERE status='prepared' AND request_key='lost-response'",
  );
  assert.ok(pending);
  control.saveMerchant("test", { ...control.merchant(mid), games: [1] });
  await assert.rejects(p.state(token), (e: any) => e.code === "GAME_FORBIDDEN");
  const recovered = await p.retry(mid, pending.id, true);
  assert.ok(recovered.settlement);
  assert.equal(
    p.get("SELECT status FROM game_operations WHERE id=?", pending.id).status,
    "settled",
  );
  assert.throws(() => control.saveMerchant(
    "test",
    {
      name: "legacy-precision",
      enabled: true,
      wallet_url: `http://127.0.0.1:${f.wp}`,
      games: [10],
      minor_unit: 100,
    },
    true,
  ), { code: "WALLET_PRECISION_INVALID" });
});

test("merchant separation, exact prebet bounds and protocol cache restoration", async (t) => {
  const f = await setup(t),
    { p, control, mid, mock, host } = f;
  control.saveMerchant("test", {
    ...control.merchant(mid),
    pre_payout: {
      enabled: true,
      url: `http://127.0.0.1:${f.wp}/api/v1/callbacks/gtt/preBetDecision`,
    },
  });
  method(mock, "prebet_policy", mid, py.from(["0", "0.000000001"]));
  for (const id of [2, 18]) {
    const code = GAME_CODES[id - 1],
      launch = await p.launch(mid, {
        game_id: id,
        player_id: "p1",
        external_username: "external-p1",
      }),
      token = new URL(launch.launch_url).searchParams.get("ops")!,
      s = await p.state(token),
      r = await p.spin(token, "bounded", s.state.sid, {});
    assert.equal(r.wallet.credit_minor, 0);
    assert.equal(p.multi!.initial(mid, "p1", code).phase, "ready");
    const before = await host(id, "/api/v1/wallet", token);
    assert.equal(before.status, 200);
    const worker = await f.gateway.protocolPool.worker(code);
    await worker.instance.terminate();
    const after = await host(id, "/api/v1/wallet", token);
    assert.deepEqual(JSON.parse(after.text), JSON.parse(before.text));
  }
  const other = control.saveMerchant(
    "test",
    {
      name: "other-merchant",
      enabled: true,
      games: [2],
      minor_unit: 10000,
      wallet_url: `http://127.0.0.1:${f.wp}`,
    },
    true,
  );
  await fetch(`http://127.0.0.1:${f.wp}/health`);
  method(mock, "seed", other.merchant.id, "p1", 123456);
  const launched = await p.launch(other.merchant.id, {
      game_id: 2,
      player_id: "p1",
    }),
    token = new URL(launched.launch_url).searchParams.get("ops")!;
  assert.equal((await p.state(token)).state.sid, "0");
  assert.equal((await p.wallet(token)).balance_minor, 1234);
  assert.equal(p.multi!.history(token).length, 0);
  const previous = p.get(
    "SELECT id FROM game_operations WHERE merchant_id=? LIMIT 1",
    mid,
  );
  await assert.rejects(
    p.retry(other.merchant.id, previous.id),
    (e: any) => e.code === "NOT_FOUND",
  );
  const base = p.multi!.initial(mid, "p1", "captains-bounty");
  assert.notEqual(base.sid, "0");
});

for (const bounds of [
  [-1, 0],
  ["0.000000001", "0.000000001"],
])
  test(`all 19 merchant games: zero cap or downward monetary ceiling ${JSON.stringify(bounds)}`, async (t) => {
    const f = await setup(t),
      { p, mid, control } = f;
    control.saveMerchant("test", {
      ...control.merchant(mid),
      pre_payout: {
        enabled: true,
        url: `http://127.0.0.1:${f.wp}/api/v1/callbacks/gtt/preBetDecision`,
      },
    });
    method(f.mock, "prebet_policy", mid, py.from(bounds));
    for (let id = 1; id <= 19; id++)
      await t.test(GAME_CODES[id - 1], async () => {
        const code = GAME_CODES[id - 1],
          launch = await p.launch(mid, {
            game_id: id,
            player_id: "p1",
            external_username: "external-p1",
          }),
          token = new URL(launch.launch_url).searchParams.get("ops")!;
        let index = 0,
          first: any;
        do {
          const state = p.multi!.initial(mid, "p1", code);
          let bet: any = JSON.parse(
            gunzipSync(
              readFileSync(`fixtures/all-games/${code}.json.gz`),
            ).toString(),
          ).initial[0].payload;
          if (state.phase !== "ready") {
            if (id === 5)
              bet = {
                action: state.phase === "collect" ? "collect" : "continue",
              };
            else if (id >= 6 && id <= 9)
              bet = { action: "confirm", round_id: state.pending.round_id };
            else if (id >= 16 && id <= 18)
              bet = {
                action: state.phase === "collect" ? "collect" : "spin",
                request_index: index,
              };
          }
          const r = await p.spin(token, "zero-" + index, state.sid, bet);
          first ??= r;
          assert.equal(r.wallet.credit_minor, 0);
          assert.equal(r.settlement.credit_minor, 0);
          index++;
          assert.ok(index < 4096);
        } while (p.multi!.initial(mid, "p1", code).phase !== "ready");
        const row = p.get(
          "SELECT * FROM prebet_rounds WHERE merchant_id=? AND game_id=?",
          mid,
          code,
        );
        assert.deepEqual(JSON.parse(row.policy_json).maxWinMulti, bounds);
        assert.equal(
          JSON.parse(row.plan_json).resolution.selection,
          bounds[0] === -1 ? "within_range" : "nearest_lower_candidate",
        );
        assert.equal(JSON.parse(row.plan_json).total_credit_minor, 0);
        const w = await p.walletClient.call(mid, "balance", {
          player_id: "p1",
          currency: "USD",
          minor_unit: 10000,
        });
        assert.equal(w.balance_minor, first.settlement.balance_minor);
      });
  });

test("real game 0.56x search freezes the selected lower seed and reuses its wallet settlement", async (t) => {
  const f = await setup(t),
    { p, mid, control, mock } = f;
  control.saveMerchant("test", {
    ...control.merchant(mid),
    pre_payout: {
      enabled: true,
      url: `http://127.0.0.1:${f.wp}/api/v1/callbacks/gtt/preBetDecision`,
    },
  });
  method(mock, "prebet_policy", mid, py.from(["0.56", "0.56"]));
  const launched = await p.launch(mid, {
      game_id: 3,
      player_id: "p1",
      external_username: "external-p1",
    }),
    token = new URL(launched.launch_url).searchParams.get("ops")!;
  const start = await p.state(token),
    first = await p.spin(token, "fractional-target", start.state.sid, {});
  let total = first.wallet.credit_minor,
    index = 0;
  while (p.multi!.initial(mid, "p1", "fortune-rabbit").phase !== "ready") {
    const state = p.multi!.initial(mid, "p1", "fortune-rabbit");
    const r = await p.spin(token, "continue-" + ++index, state.sid, {});
    total += r.wallet.credit_minor;
    assert.ok(index < 4096);
  }
  const row = p.get("SELECT * FROM prebet_rounds WHERE merchant_id=?", mid),
    planned = JSON.parse(row.plan_json);
  assert.equal(total, planned.total_credit_minor);
  assert.ok(BigInt(total) * 100n <= BigInt(planned.basis_minor) * 56n);
  assert.equal(planned.resolution.actual_credit_minor, total);
  const before = await p.wallet(token);
  assert.deepEqual(
    await p.spin(token, "fractional-target", start.state.sid, {}),
    first,
  );
  assert.deepEqual(await p.wallet(token), before);
  assert.equal(
    JSON.parse(
      p.get("SELECT plan_json FROM prebet_rounds WHERE id=?", row.id).plan_json,
    ).seed,
    planned.seed,
  );
});


test("all 19 games fall back from invalid prebet to their RTP path and freeze the round",async(t)=>{
  const {p,mid,control,signed}=await setup(t);
  let calls=0;
  const callback=server(async(req,res)=>{await body(req);calls++;send(res,200,{code:0,data:{maxWinMulti:[false,0]}});});
  const port=await listen(callback);t.after(()=>{callback.closeAllConnections();callback.close();});
  control.prebet(mid,{enabled:false,url:'http://127.0.0.1:'+port+'/decision'});
  for(let id=1;id<=19;id++){
    const code=GAME_CODES[id-1], game=p.multi!;
    const launch=await signed('/gtt/v1/games/launch',{game_id:id,player_id:'p1',external_username:'external-p1'});
    const token=new URL(launch.launch_url).searchParams.get('ops')!;
    const ref=JSON.parse(gunzipSync(readFileSync('fixtures/all-games/'+code+'.json.gz')).toString());
    const base=ref.initial.at(-1).payload;
    if(id!==1){
      const bet=game.call(code,'normalize_bet',base);
      const report={algorithm:ROUND_MODEL_VERSION,game_id:id,ruleset_id:py.attr(game.game(code),'ruleset_id'),modes:{[modeKey(bet)]:{candidates:2,upper_probability:0.5}}};
      p.run('INSERT INTO rtp_models VALUES(?,?,?,?,?,?)','fallback-test-'+id,9600,'test-only',encode(report),1,4102444800);
    }
    const before=calls;let steps=0,first:any;
    do {
      const state=game.initial(mid,'p1',code);let bet={...base};
      if(state.phase!=='ready'){
        if(id===5)bet={action:state.phase==='collect'?'collect':'continue'};
        else if(id>=6&&id<=9)bet={action:'confirm',round_id:state.pending.round_id};
        else if(id>=16&&id<=18)bet={...base,action:state.phase==='collect'?'collect':'spin',request_index:(base.request_index??0)+steps};
        else delete bet.buy_free;
      }
      const result=await p.spin(token,'fallback-'+steps,state.sid,bet);first??=result;
      assert.notEqual(result.rtp.mode,'prebet',code);
      assert.deepEqual(result.rtp,first.rtp,code);
      assert.deepEqual(await p.spin(token,'fallback-'+steps,state.sid,bet),result);
      assert.ok(++steps<4096);
    }while(game.initial(mid,'p1',code).phase!=='ready');
    assert.equal(calls,before+1,code);
    if(id===1){assert.equal(first.rtp.mode,'rtp');assert.equal(first.rtp.target_rtp,96);}
    else{assert.equal(first.rtp.requested_target_rtp,96);assert.equal(first.rtp.status,'active');assert.equal(first.rtp.model_id,'fallback-test-'+id);}
    assert.ok(p.get('SELECT error_code FROM prebet_rounds WHERE game_id=?',code).error_code);
  }
});
