import { readFileSync, writeFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { definitions } from "../dist/migrated/py/games/catalog.js";
import * as p from "../dist/compat/runtime.js";
import { invoke, modePayloads } from "../dist/games/round-model.js";
const root = resolve(dirname(fileURLToPath(import.meta.url)), ".."),
  repo = resolve(root, "..");
const descriptors = {};
for (const [code, definition] of Object.entries(definitions)) {
  const game = p.call(definition.factory, [
    p.jsonLoads(
      readFileSync(resolve(repo, `services/${code}/config/${code}.json`)),
    ),
  ]);
  descriptors[code] = {
    game_id: code,
    title: p.attr(game, "title"),
    version: p.attr(game, "version"),
    ruleset_id: p.attr(game, "ruleset_id"),
    config: p.plain(p.attr(game, "config")),
    sample_bet: invoke(game, "normalize_bet", modePayloads(code)[0]),
  };
}
writeFileSync(
  resolve(root, "config/game-descriptors.json"),
  JSON.stringify(descriptors, null, 2) + "\n",
);
