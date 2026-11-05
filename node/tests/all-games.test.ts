import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import * as p from "../compat/runtime.js";
import { computeServer } from "../services/compute.js";
import { listen } from "../shared/http.js";
const manifest = JSON.parse(
  readFileSync("fixtures/all-games/manifest.json", "utf8"),
);
for (const spec of manifest)
  test(`migrated ${spec.id}: complete reference rounds and bet validation`, async () => {
    const ref = p.jsonLoads(
      gunzipSync(readFileSync("fixtures/all-games/" + spec.file)),
    );
    const factory = p.item(ref, "factory"),
      [modulePath, className] = factory.split(":");
    const name = modulePath.split(".").at(-1);
    const mod = await import(
      pathToFileURL(resolve("dist/migrated/server/games", name, "engine.js"))
        .href
    );
    const game = p.call(mod[className], [
      p.sourcePath(p.item(ref, "config_path")),
    ]);
    assert.equal(p.attr(game, "ruleset_id"), p.item(ref, "ruleset_id"));
    for (const init of p.item(ref, "initial")) {
      assert.deepEqual(
        p.plain(
          p.call(p.attr(game, "initial_state"), [p.item(init, "initial_seed")]),
        ),
        p.plain(p.item(init, "initial")),
      );
      assert.deepEqual(
        p.plain(
          p.call(p.attr(game, "normalize_bet"), [p.item(init, "payload")]),
        ),
        p.plain(p.item(init, "bet")),
      );
    }
    for (const c of p.item(ref, "cases")) {
      const bet = p.call(p.attr(game, "normalize_bet"), [p.item(c, "payload")]);
      assert.deepEqual(p.plain(bet), p.plain(p.item(c, "bet")));
      const out = p.call(p.attr(game, "step"), [
        p.clone(p.item(c, "state")),
        bet,
        p.item(c, "seed"),
        p.item(c, "sid"),
      ]);
      assert.deepEqual(
        p.plain(out),
        p.plain(p.item(c, "expected")),
        `step ${p.item(c, "sid")}`,
      );
    }
    for (const invalid of p.item(ref, "errors"))
      assert.throws(
        () =>
          p.call(p.attr(game, "normalize_bet"), [p.item(invalid, "payload")]),
        (e: any) =>
          e.code === p.item(invalid, "code") ||
          e.constructor.name === p.item(invalid, "code"),
      );
  });
for (const spec of manifest)
  test(`isolated compute ${spec.id}: authenticated deterministic HTTP step`, async (t) => {
    const ref = p.jsonLoads(
        gunzipSync(readFileSync("fixtures/all-games/" + spec.file)),
      ),
      c = p.item(ref, "cases")[0],
      secret = "test-only-compute-secret-".repeat(3);
    const server = computeServer(
        spec.id,
        p.sourcePath(p.item(ref, "config_path")),
        secret,
      ),
      port = await listen(server),
      origin = "http://127.0.0.1:" + port;
    t.after(async () => {
      server.closeAllConnections();
      await new Promise<void>((ok) => server.close(() => ok()));
    });
    assert.equal((await fetch(origin + "/health")).status, 401);
    const raw = p.jsonDumps(
      p.dict([
        ["state", p.item(c, "state")],
        ["bet", p.item(c, "payload")],
        ["seed", p.item(c, "seed")],
        ["operation_id", p.item(c, "sid")],
      ]),
    );
    for (let i = 0; i < 2; i++) {
      const r = await fetch(origin + "/v1/step", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: "Bearer " + secret,
        },
        body: raw,
      });
      const result = await r.json();
      assert.equal(r.status, 200, JSON.stringify(result));
      assert.deepEqual(result.data, p.plain(p.item(c, "expected")));
    }
  });
