// Generates schema-only migration input from the audited SQLite inventories.
// Run once when introducing migration 0001; later changes get a new migration.
import { sources, describe, root } from './inventory.mjs';
import { resolve } from 'node:path';
import { mkdirSync, writeFileSync, existsSync } from 'node:fs';
const file=resolve(root,'other/migrations/postgres/0001-baseline.json');
if(existsSync(file)) throw Error('Migration 0001 already exists. Create a new migration instead.');
const kinds={};
for(const source of sources()) {
  const tables=kinds[source.kind]??={};
  for(const {count,...table} of describe(resolve(root,source.path))) {
    const existing=tables[table.name];
    if(existing && JSON.stringify(existing.columns)!==JSON.stringify(table.columns)) throw Error('Schema variation requires explicit handling: '+source.kind+'.'+table.name);
    tables[table.name]=table;
  }
}
mkdirSync(resolve(root,'other/migrations/postgres'),{recursive:true});
writeFileSync(file,JSON.stringify({version:'0001',description:'SQLite schema baseline; no business rows or credentials',kinds},null,2)+'\n',{flag:'wx'});
console.log('Created schema-only baseline for '+Object.keys(kinds).join(', '));
