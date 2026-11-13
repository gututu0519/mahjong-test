import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { sha } from "../shared/core.js";
import { GameReadiness } from "../gateway/readiness.js";
import { catalogExport } from "../gateway/catalog-export.js";
import { verifiedReadinessFixture } from "./readiness-fixture.js";

test("readiness release snapshot preserves workbook provenance and never silently approves missing data",()=>{
  const data = JSON.parse(readFileSync("config/game-readiness.json","utf8"));
  assert.equal(data.workbook_sha256,sha(readFileSync("../docs/品牌游戏与特殊玩法维护表.xlsx")));
  const actual = new GameReadiness();
  for(const game of data.games){
    assert.ok(actual.get(game.code).blockers.length>0);
    for(const source of game.sources) assert.ok(existsSync("../"+source.split(" · ")[0]),source);
  }
  const incomplete = structuredClone(data.games); incomplete.pop();
  assert.throws(()=>new GameReadiness(incomplete),{code:"READINESS_CONFIG_INVALID"});
  const fake = structuredClone(data.games); fake[0].collection_complete=true; fake[0].blockers=[];
  assert.throws(()=>new GameReadiness(fake),{code:"READINESS_CONFIG_INVALID"});
  const verified=verifiedReadinessFixture(); verified.assert("buffalo-win");
  const copy=actual.get("buffalo-win");copy.collection_complete=true;
  assert.throws(()=>actual.assert("buffalo-win"),{code:"GAME_NOT_READY"});
});

test("catalog HTML escapes text and CSV neutralizes spreadsheet formulas",()=>{
  const readiness = new GameReadiness().get("buffalo-win");
  readiness.display_name='=HYPERLINK("https://example.invalid")';
  readiness.blockers=['<script>alert(1)</script>'];
  const games=[{id:1,brand:'<script>alert(1)</script>',title:readiness.display_name,readiness,integration_available:false}];
  const html=catalogExport(games,"html").content;
  assert.ok(!html.includes('<script>')); assert.ok(html.includes('&lt;script&gt;'));
  const csv=catalogExport([{...games[0],brand:readiness.display_name}],"csv").content;
  assert.ok(csv.includes('"\'=HYPERLINK('));
  assert.throws(()=>catalogExport(games,"xlsx"),{code:"EXPORT_FORMAT_INVALID"});
});
