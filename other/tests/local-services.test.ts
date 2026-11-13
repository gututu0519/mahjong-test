import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";
import { buildLocal, method } from "../shared/services/local.js";
import { listen } from "../shared/http.js";
import * as p from "../shared/compat/runtime.js";

for (const id of readdirSync("../services").filter((id) =>
  existsSync(`../services/${id}/service.json`),
))
  test(`Node standalone ${id}: original entry, API, wallet and isolation`, async (t) => {
    const dir = mkdtempSync(join(tmpdir(), "gtt-node-service-"));
    const { server, app, spec } = await buildLocal(resolve("../services", id), {
      database: join(dir, "game.sqlite3"),
      port: 0,
    });
    const port = await listen(server);
    const origin = `http://127.0.0.1:${port}`;
    t.after(async () => {
      server.closeAllConnections();
      await new Promise<void>((ok) => server.close(() => ok()));
      rmSync(dir, { recursive: true, force: true });
    });
    const request = async (path: string, body?: any, headers: any = {}) =>
      fetch(origin + path, {
        method: body === undefined ? "GET" : "POST",
        redirect: "manual",
        headers: {
          ...(body === undefined ? {} : { "content-type": "application/json" }),
          ...headers,
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        signal: AbortSignal.timeout(5000),
      });
    const health = await request("/health");
    assert.equal(health.status, 200);
    assert.equal((await health.json()).service_id, id);
    const session = p.plain(method(app.service, "create_session")),
      token = session.token;
    assert.equal(
      session.minor_unit,
      [
        "super-ace",
        "fortune-gems2",
        "jokers-fortune-winx",
        "3-billion-vaults",
        "money-pot-deluxe",
        "roma-x-10000",
      ].includes(id)
        ? 10000
        : 100,
    );
    const state = p.plain(method(app.service, "state", token, spec.games[0]));
    assert.equal(state.state.phase, "ready");
    const balance = await request("/api/v1/wallet", undefined, {
      authorization: "Bearer " + token,
    });
    assert.equal(balance.status, 200);
    assert.equal((await balance.json()).balance_minor, session.balance_minor);
    if (id === "game-api") {
      assert.equal((await request("/")).status, 404);
      return;
    }
    const launch = await request(`/api/v1/games/${id}/launch`, {
      language: id === "buffalo-win" ? "zh" : "en",
    });
    assert.equal(launch.status, 201, await launch.clone().text());
    const data = await launch.json();
    let url = new URL(data.launch_url, origin);
    for (let i = 0; i < 4; i++) {
      const response = await request(url.pathname + url.search);
      if ([301, 302, 303, 307, 308].includes(response.status)) {
        url = new URL(response.headers.get("location")!, origin);
        continue;
      }
      assert.equal(response.status, 200, await response.clone().text());
      const html = await response.text();
      assert.ok(
        html.includes("<html") ||
          html.includes("<!doctype") ||
          html.includes("<!DOCTYPE"),
      );
      break;
    }
    assert.equal((await request("/fixtures/auth-metadata.json")).status, 404);
  });
