import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { root } from './inventory.mjs';
process.env.GTT_PG_CONFIG=resolve(root,'gateway/instance/data/postgres-trial.json');
const {components}=await import('../../runtime/server/dist/cli.js');
const config=JSON.parse(readFileSync(resolve(root,'gateway/instance/data/node.json'),'utf8'));
config.postgres_config=process.env.GTT_PG_CONFIG;
const {control,provider}=await components(config);
try {
  assert(control.get('SELECT COUNT(*) AS n FROM merchants').n>0);
  assert.equal(provider.catalog().length,19);
  console.log('PostgreSQL gateway bootstrap, control metadata and 19-game catalog passed.');
} finally {provider.close();control.close();}
