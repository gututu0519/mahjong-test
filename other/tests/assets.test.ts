import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { repairModule } from "../../gateway/src/assets.js";

test("Mahjong shared modules remain valid when repairing their self-check regex", () => {
  for (const module of ["b4d9192613","0b68fe0fe5","c2fc9a6814","4528468aab","75d1870451","b85c56d865","72c6a58ab7"]) {
    const source=readFileSync(`../clients/mahjong-ways2/shared/${module}/index.js`,"utf8");
    assert.doesNotThrow(()=>repairModule(source),module);
  }
});
