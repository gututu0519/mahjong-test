import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { transaction } from "../gateway/pg.js";
import { object, signature } from "../shared/core.js";
test("346 client protocol responses match Python reference", () => {
  const f = JSON.parse(readFileSync("fixtures/buffalo-python.json", "utf8")),
    c = JSON.parse(readFileSync("config/buffalo-win.json", "utf8"));
  for (const s of f.cases)
    assert.deepEqual(
      transaction(s.expected.event, s.wallet, c.win_thresholds),
      s.transaction,
      s.sid,
    );
});
test("strict JSON rejects duplicate keys, invalid syntax and unsafe integers", () => {
  for (const v of [
    '{"a":1,"a":2}',
    '{"x":{"a":1,"a":2}}',
    '{"n":9007199254740993}',
    '{"n":1e999}',
    '{"a":NaN}',
    '{"a":1,}',
    "[]",
  ])
    assert.throws(() => object(v));
  assert.equal(object('{"a":{"b":[true,null,"x"]}}').a.b[2], "x");
});
