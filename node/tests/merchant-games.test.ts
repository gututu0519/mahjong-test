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
import { listen } from "../shared/http.js";
import { encode, signedHeaders } from "../shared/core.js";
import { GAME_CODES, gameUnit } from "../gateway/catalog.js";
import { transactions } from "../gateway/admin.js";
import * as py from "../compat/runtime.js";
import * as pg from "../migrated/server/adapters/pg/protocol.js";
import { method } from "../services/local.js";

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

test("19 games: signed catalog, original client entry, wallet, settlement, idempotency and scoped admin records", async (t) => {
  const f = await setup(t),
    { p, mid, signed, host } = f;
  assert.equal((await signed("/gtt/v1/games/list", {})).games.length, 19);
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
      assert.equal(launch.balance_minor, expectedBalance);
      let path = url.pathname + url.search;
      for (let j = 0; j < 5; j++) {
        const r = await host(id, path, token);
        if ([301, 302, 303, 307, 308].includes(r.status)) {
          const next = new URL(r.headers.location, url);
          assert.equal(next.host, url.host);
          path = next.pathname + next.search;
          continue;
        }
        assert.equal(r.status, 200, r.text.slice(0, 500));
        assert.match(r.text, /<html|<!doctype/i);
        break;
      }
      const wallet = await host(id, "/api/v1/wallet", token);
      assert.equal(wallet.status, 200, wallet.text);
      assert.equal(JSON.parse(wallet.text).minor_unit, gameUnit(code));
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
          data = data.toString().replace("reference-" + code, token);
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
            py.dict([[1, py.call(pg.text_field, [1, token])]]),
          ]);
          data = py.call(pg.pack, [patched, seed, salt]);
        }
      }
      const r = await host(id, path, token, data, headers);
      assert.equal(r.status, 200, r.text.slice(0, 500));
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
  const low = control.saveMerchant(
    "test",
    {
      name: "legacy-precision",
      enabled: true,
      wallet_url: `http://127.0.0.1:${f.wp}`,
      games: [10],
      minor_unit: 100,
    },
    true,
  );
  await assert.rejects(
    p.launch(low.merchant.id, { game_id: 10, player_id: "p1" }),
    (e: any) => e.code === "WALLET_PRECISION_REQUIRED",
  );
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
      minor_unit: 100,
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
  assert.equal((await p.wallet(token)).balance_minor, 123456);
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

test('real game 0.56x search freezes the selected lower seed and reuses its wallet settlement',async t=>{
 const f=await setup(t),{p,mid,control,mock}=f;
 control.saveMerchant('test',{...control.merchant(mid),pre_payout:{enabled:true,url:`http://127.0.0.1:${f.wp}/api/v1/callbacks/gtt/preBetDecision`}});
 method(mock,'prebet_policy',mid,py.from(['0.56','0.56']));
 const launched=await p.launch(mid,{game_id:3,player_id:'p1',external_username:'external-p1'}),token=new URL(launched.launch_url).searchParams.get('ops')!;
 const start=await p.state(token),first=await p.spin(token,'fractional-target',start.state.sid,{});
 let total=first.wallet.credit_minor,index=0;
 while(p.multi!.initial(mid,'p1','fortune-rabbit').phase!=='ready'){
  const state=p.multi!.initial(mid,'p1','fortune-rabbit');const r=await p.spin(token,'continue-'+(++index),state.sid,{});total+=r.wallet.credit_minor;assert.ok(index<4096);
 }
 const row=p.get('SELECT * FROM prebet_rounds WHERE merchant_id=?',mid),planned=JSON.parse(row.plan_json);
 assert.equal(total,planned.total_credit_minor);assert.ok(BigInt(total)*100n<=BigInt(planned.basis_minor)*56n);assert.equal(planned.resolution.actual_credit_minor,total);
 const before=await p.wallet(token);assert.deepEqual(await p.spin(token,'fractional-target',start.state.sid,{}),first);assert.deepEqual(await p.wallet(token),before);
 assert.equal(JSON.parse(p.get('SELECT plan_json FROM prebet_rounds WHERE id=?',row.id).plan_json).seed,planned.seed);
});
