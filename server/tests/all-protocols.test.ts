import { test } from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { readFileSync, mkdtempSync, rmSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import * as p from "../compat/runtime.js";
import { buildLocal, method } from "../services/local.js";
const manifest = JSON.parse(
  readFileSync("fixtures/protocols/manifest.json", "utf8"),
);
function revive(v: any): any {
  if (v instanceof p.Dict) {
    if (v.has("__bytes__")) return Buffer.from(v.get("__bytes__"), "base64");
    return p.dict([...v].map(([k, x]) => [k, revive(x)]));
  }
  return Array.isArray(v) ? v.map(revive) : v;
}
function normalize(v: any): any {
  if (typeof v === "string")
    return v.replace(/\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ/g, "<TIME>");
  if (Buffer.isBuffer(v)) return v.toString("base64");
  if (Array.isArray(v)) return v.map(normalize);
  if (v && typeof v === "object")
    return Object.fromEntries(
      Object.entries(v).map(([k, x]) => [k, normalize(x)]),
    );
  return v;
}
for (const spec of manifest)
  test(`original ${spec.id} adapter: login, wire spins, retries and restoration`, async () => {
    const ref = revive(
        p.jsonLoads(
          gunzipSync(readFileSync("fixtures/protocols/" + spec.file)),
        ),
      ),
      dir = mkdtempSync(join(tmpdir(), "gtt-protocol-"));
    const old = {
      time: p.modules.time.time,
      hex: p.modules.secrets.token_hex,
      token: p.modules.secrets.token_urlsafe,
      uuid: p.modules.uuid.uuid4,
    };
    p.modules.time.time = () => p.float(1700000000);
    p.modules.secrets.token_hex = (n = 32) => "b".repeat(n * 2);
    p.modules.secrets.token_urlsafe = () => `reference-${spec.id}`;
    p.modules.uuid.uuid4 = () => ({ hex: "a".repeat(32) });
    try {
      const { app } = await buildLocal(resolve("../services", spec.id), {
        database: join(dir, "game.db"),
        port: 0,
      });
      assert.deepEqual(
        p.plain(method(app.service, "create_session")),
        p.plain(p.item(ref, "session")),
      );
      const adapter = app[p.item(ref, "adapter")];
      let i = 0;
      for (const c of p.item(ref, "calls")) {
        const result = method(
          adapter,
          p.item(c, "method"),
          ...p.item(c, "args"),
        );
        assert.deepEqual(
          normalize(p.plain(result)),
          normalize(p.plain(p.item(c, "expected"))),
          `call ${i++} ${p.item(c, "method")}`,
        );
      }
      // Restore an actual SQL dump emitted by Python, including unfinished rounds
      // and original cached protocol responses. Compare balances and retry bytes.
      const legacyPath = join(dir, "legacy.db"),
        db = new DatabaseSync(legacyPath);
      try {
        db.exec("PRAGMA foreign_keys=OFF");
        db.exec(p.item(ref, "legacy_sql"));
      } finally {
        db.close();
      }
      const restored = (
          await buildLocal(resolve("../services", spec.id), {
            database: legacyPath,
            port: 0,
          })
        ).app,
        token = p.item(p.item(ref, "session"), "token");
      for (const [methodName, field, args] of [
        ["state", "final_state", [token, spec.id]],
        ["wallet", "final_wallet", [token]],
        ["history", "final_history", [token]],
      ] as const) {
        assert.deepEqual(
          p.plain(method(restored.service, methodName, ...args)),
          p.plain(p.item(ref, field)),
          `legacy ${methodName}`,
        );
      }
    } finally {
      p.modules.time.time = old.time;
      p.modules.secrets.token_hex = old.hex;
      p.modules.secrets.token_urlsafe = old.token;
      p.modules.uuid.uuid4 = old.uuid;
      rmSync(dir, { recursive: true, force: true });
    }
  });
