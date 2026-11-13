import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { connect, Socket } from "node:net";
import { once } from "node:events";
import { platformServer } from "../services/platform.js";
import { buildLocal, method } from "../services/local.js";
import { Control } from "../gateway/control.js";
import { Provider } from "../gateway/provider.js";
import { GameClient } from "../gateway/game-client.js";
import { gameServer } from "../games/buffalo-win/service.js";
import { gatewayServer } from "../gateway/http.js";
import { listen } from "../shared/http.js";
import { encode, signedHeaders } from "../shared/core.js";
import * as p from "../compat/runtime.js";
import { verifiedReadinessFixture } from "./readiness-fixture.js";

test("native simulator: original page, signed wallet, refund tombstone, prebet and gateway launch", async (t) => {
  const dir = mkdtempSync(join(tmpdir(), "gtt-platform-")),
    control = new Control(
      join(dir, "control.db"),
      resolve("config/control.sql"),
    );
  const created = control.saveMerchant(
      "test",
      {
        name: "platform-test",
        enabled: true,
        wallet_url: "http://127.0.0.1:8111",
        games: [1],
      },
      true,
    ),
    mid = created.merchant.id;
  const config: any = {
    environment: "development",
    sandbox_merchant: mid,
    sandbox_player: "p1",
    sandbox_external_username: "external-p1",
    sandbox_balance_minor: 200000,
    platform_database: join(dir, "wallet.db"),
    gateway_origin: "http://127.0.0.1",
  };
  const { server: wallet } = platformServer(config, control),
    wp = await listen(wallet),
    origin = "http://127.0.0.1:" + wp;
  control.saveMerchant("test", {
    ...control.merchant(mid),
    wallet_url: origin,
    pre_payout: {
      enabled: true,
      url: origin + "/api/v1/callbacks/gtt/preBetDecision",
    },
  });
  const gc = JSON.parse(readFileSync("config/buffalo-win.json", "utf8")),
    secret = "a".repeat(64),
    game = gameServer(gc, secret),
    gp = await listen(game);
  const provider = new Provider(
    join(dir, "game.db"),
    control,
    new GameClient("http://127.0.0.1:" + gp, secret, gc),
    resolve("config/game.sql"),
    "http://127.0.0.1",
    resolve("config/rtp-models.json"),
  );
  await provider.initialize();
  provider.readiness = verifiedReadinessFixture();
  for(let game_id=1;game_id<=19;game_id++) control.setGameAvailability("fixture",{game_id,enabled:true,version:0});
  const gateway = gatewayServer(
      provider,
      config,
      resolve("../clients/buffalo-win"),
    ),
    port = await listen(gateway);
  config.gateway_origin = provider.playOrigin = "http://127.0.0.1:" + port;
  t.after(async () => {
    for (const s of [gateway, game, wallet]) {
      s.closeAllConnections();
      await new Promise<void>((ok) => s.close(() => ok()));
    }
    provider.close();
    control.close();
    rmSync(dir, { recursive: true, force: true });
  });
  const request = async (path: string, payload?: any, signed = false) => {
    const raw = payload === undefined ? undefined : encode(payload);
    const r = await fetch(origin + path, {
      method: raw ? "POST" : "GET",
      headers: signed
        ? signedHeaders(
            mid,
            control.merchant(mid, true).merchant_secret,
            path,
            raw!,
          )
        : { "content-type": "application/json" },
      body: raw,
    });
    return { status: r.status, value: await r.json() };
  };
  assert.equal((await fetch(origin + "/")).status, 200);
  assert.equal(
    (await request("/health")).value.data.service_id,
    "gtt-mock-platform",
  );
  assert.equal(
    (await request("/sandbox/status")).value.data.balance_minor,
    200000,
  );
  const identity = {
    player_id: "p1",
    currency: "USD",
    minor_unit: 10000,
    round_id: "round-1",
  };
  const debit = { ...identity, transaction_id: "d1", amount_minor: 100 };
  assert.equal((await request("/wallet/v1/debit", debit)).status, 401);
  const d = await request("/wallet/v1/debit", debit, true);
  assert.equal(d.status, 200, JSON.stringify(d));
  assert.equal(d.value.data.balance_minor, 199900);
  assert.deepEqual(
    (await request("/wallet/v1/debit", debit, true)).value,
    d.value,
  );
  assert.equal(
    (await request("/wallet/v1/debit", { ...debit, amount_minor: 101 }, true))
      .status,
    409,
  );
  const refund = await request(
    "/wallet/v1/refund",
    {
      ...identity,
      transaction_id: "r1",
      reference_id: "d-late",
      amount_minor: 100,
    },
    true,
  );
  assert.equal(refund.status, 200, JSON.stringify(refund));
  const canceled = await request(
    "/wallet/v1/debit",
    { ...debit, transaction_id: "d-late" },
    true,
  );
  assert.equal(canceled.status, 409);
  assert.equal(
    (await request("/sandbox/prebet-policy", { maxWinMulti: [-1, 0] })).status,
    200,
  );
  const decision = await request(
    "/api/v1/callbacks/gtt/preBetDecision",
    {
      player_name: "external-p1",
      timestamp: 1700000000,
      bet_amount: "1.00",
      type: "NORMAL",
    },
    true,
  );
  assert.equal(decision.value.code, 0, JSON.stringify(decision));
  const launch = await request("/sandbox/launch", { language: "en" });
  assert.equal(launch.status, 201, JSON.stringify(launch));
  const token = new URL(launch.value.data.launch_url).searchParams.get("ops")!;
  const spin = await provider.spin(token, "aux-spin", "0", { cs: 0.1, ml: 1 });
  assert.ok(spin);
  assert.equal(
    (await request("/sandbox/status")).value.data.transactions.length > 1,
    true,
  );
});

// A raw client checks browser-required Origin/Cookie and masked binary frames.
async function channel(port: number, path: string, headers = "") {
  const socket = connect(port, "127.0.0.1");
  await once(socket, "connect");
  let bytes = Buffer.alloc(0),
    wake: (() => void) | undefined;
  socket.on("data", (v) => {
    bytes = Buffer.concat([bytes, v]);
    wake?.();
  });
  const until = async (predicate: () => boolean) => {
    const deadline = Date.now() + 3000;
    while (!predicate()) {
      if (Date.now() > deadline) {
        socket.destroy();
        throw Error("WebSocket timeout: " + bytes.toString());
      }
      await new Promise<void>((ok) => {
        const timer = setTimeout(ok, 50);
        wake = () => {
          clearTimeout(timer);
          ok();
        };
      });
    }
  };
  socket.write(
    `GET ${path} HTTP/1.1\r\nHost: 127.0.0.1:${port}\r\nOrigin: http://127.0.0.1:${port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n${headers}\r\n`,
  );
  await until(() => bytes.includes("\r\n\r\n"));
  const index = bytes.indexOf("\r\n\r\n");
  if (!bytes.toString().startsWith("HTTP/1.1 101")) socket.destroy();
  assert.match(bytes.subarray(0, index).toString(), /^HTTP\/1.1 101/);
  bytes = bytes.subarray(index + 4);
  return {
    socket,
    send(opcode: number, value: Buffer | string) {
      const data = Buffer.from(value),
        mask = Buffer.from([1, 2, 3, 4]);
      assert.ok(data.length < 126);
      const masked = Buffer.from(data);
      for (let i = 0; i < masked.length; i++) masked[i] ^= mask[i % 4];
      socket.write(
        Buffer.concat([
          Buffer.from([128 | opcode, 128 | data.length]),
          mask,
          masked,
        ]),
      );
    },
    async read() {
      await until(
        () => bytes.length >= 2 && bytes.length >= 2 + (bytes[1] & 127),
      );
      const n = bytes[1] & 127,
        result = { opcode: bytes[0] & 15, data: bytes.subarray(2, 2 + n) };
      bytes = bytes.subarray(2 + n);
      return result;
    },
  };
}
for (const kind of ["tada", "signalr"])
  test(`native ${kind} WebSocket: authentication, heartbeat and retained operation rejection`, async (t) => {
    const dir = mkdtempSync(join(tmpdir(), "gtt-ws-")),
      id = kind === "tada" ? "fortune-gems2" : "tower-run-treasure-steps";
    const { server, app } = await buildLocal(resolve("../services", id), {
        database: join(dir, "game.db"),
        port: 0,
      }),
      port = await listen(server),
      token = p.plain(method(app.service, "create_session")).token;
    const sockets: Socket[] = [];
    t.after(async () => {
      sockets.forEach((s) => s.destroy());
      server.closeAllConnections();
      await new Promise<void>((ok) => server.close(() => ok()));
      rmSync(dir, { recursive: true, force: true });
    });
    const ws = await channel(
      port,
      kind === "tada" ? "/lifeservice/ws2" : "/platform/player-events",
      kind === "signalr" ? `Cookie: tower-session=${token}\r\n` : "",
    );
    sockets.push(ws.socket);
    if (kind === "tada") {
      ws.send(
        2,
        Buffer.concat([Buffer.from([34, token.length]), Buffer.from(token)]),
      );
      assert.deepEqual(JSON.parse((await ws.read()).data.toString()), {
        error: 0,
      });
      ws.send(1, '{"cmdType":-1}');
      ws.send(9, "alive");
      assert.equal((await ws.read()).opcode, 10);
      ws.send(1, '{"cmdType":42}');
      assert.equal((await ws.read()).data.readUInt16BE(), 1008);
    } else {
      ws.send(1, '{"protocol":"json","version":1}\x1e');
      assert.equal((await ws.read()).data.toString(), "{}\x1e");
      ws.send(1, '{"type":6}\x1e');
      assert.equal((await ws.read()).data.toString(), '{"type":6}\x1e');
      ws.send(
        1,
        '{"type":1,"invocationId":"1","target":"RefreshFeatureStates"}\x1e',
      );
      assert.equal(
        JSON.parse(
          (await ws.read()).data.toString().trimEnd().replace(/\x1e$/, ""),
        ).type,
        3,
      );
      ws.send(1, '{"type":1,"invocationId":"2","target":"ClaimReward"}\x1e');
      assert.match(
        (await ws.read()).data.toString(),
        /Unsupported platform operation/,
      );
    }
  });
