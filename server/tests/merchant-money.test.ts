import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { merchantGameResult, merchantRoundMoney, merchantRoundSummary } from "../gateway/merchant-money.js";

test("merchant views preserve exact four-decimal balances without changing native game data", () => {
  const native = {
    minor_unit:100,
    wallet:{before_minor:200000,debit_minor:100,credit_minor:20,after_minor:199920},
    outcome:{win_minor:20,display_delta_minor:-3,awards_minor:{A:20},bet:{coin_minor:10,level:1}},
    settlement:{minor_unit:10000,before_minor:20000007,debit_minor:10000,credit_minor:2000,balance_minor:19992007},
    resolution_minor_unit:100,
    resolution:{basis_minor:100,actual_credit_minor:20,actual_multiplier:{numerator:1,denominator:5}},
  };
  const saved = structuredClone(native), result = merchantGameResult(native);
  assert.deepEqual(result.wallet,{before_minor:20000007,debit_minor:10000,credit_minor:2000,after_minor:19992007});
  assert.equal(result.minor_unit,10000);
  assert.equal(result.outcome.display_delta_minor,-300);
  assert.deepEqual(result.outcome.awards_minor,{A:2000});
  assert.deepEqual(result.outcome.bet,{coin_minor:1000,level:1});
  assert.equal(result.resolution.basis_minor,10000);
  assert.equal(result.resolution.actual_credit_minor,2000);
  assert.deepEqual(result.resolution.actual_multiplier,{numerator:1,denominator:5});
  assert.deepEqual(native,saved);
  assert.deepEqual(merchantGameResult(result),result);
  const round = merchantRoundSummary({minor_unit:100,total_debit_minor:"9000000000000000",total_credit_minor:"0",resolution_minor_unit:null,resolution:null});
  assert.equal(round.total_debit_minor,"900000000000000000");
  assert.equal(round.minor_unit,10000);
  assert.equal(round.resolution_minor_unit,null);
  assert.deepEqual(merchantRoundMoney({resolution:null,resolution_minor_unit:100}),{resolution:null,resolution_minor_unit:10000});
});

test("published merchant contract uses one unit and never requires merchants to echo precision", () => {
  const contract = JSON.parse(readFileSync("config/integration.json","utf8"));
  function checkExample(value:any) {
    if (!value || typeof value !== "object") return;
    for (const [key,v] of Object.entries(value)) {
      if (key === "minor_unit" || key === "resolution_minor_unit") assert.ok(v === 10000 || v === null,JSON.stringify(value));
      else checkExample(v);
    }
  }
  for (const endpoint of contract.endpoints) {
    checkExample(endpoint.request_example);
    checkExample(endpoint.response_example);
    if (endpoint.id.startsWith("wallet-")) {
      assert.ok(!endpoint.request_schema.required.includes("minor_unit"));
      assert.equal(Object.hasOwn(endpoint.request_example,"minor_unit"),false);
      assert.equal(Object.hasOwn(endpoint.response_example.data,"minor_unit"),false);
    }
  }
  for (const name of ["Balance","Mutation","WalletHistory"]) {
    assert.ok(!contract.schemas[name].required.includes("minor_unit"));
    assert.deepEqual(contract.schemas[name].properties.minor_unit.enum,[10000]);
  }
  const markdown = readFileSync("config/guide.md","utf8");
  assert.ok(!/minor_unit[^\n]*必填[^\n]*(?:100 \/|100 或)/.test(markdown));
  assert.ok(markdown.includes("商户无需配置、传入或回传 minor_unit"));
});
