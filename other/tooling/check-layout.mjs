import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync, lstatSync, realpathSync } from 'node:fs';
import { resolve, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { DatabaseSync } from 'node:sqlite';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const layout=JSON.parse(readFileSync(resolve(root,'other/tooling/layout.json'),'utf8'));
assert.deepEqual(readdirSync(root,{withFileTypes:true}).filter(e=>e.isDirectory()&&!['.git','update'].includes(e.name)).map(e=>e.name).sort(),['admin','games','gateway','other']);
const files=new Set(Object.values(layout.modules));
function walk(path) {
  return readdirSync(path,{withFileTypes:true}).flatMap(e=>e.isDirectory()?walk(resolve(path,e.name)):[resolve(path,e.name)]);
}
for(const base of ['gateway/src','admin/backend','other/shared',...layout.games.map(g=>'games/'+g+'/backend')])
  for(const path of walk(resolve(root,base))) if(path.endsWith('.ts')) assert(files.has(relative(root,path).replaceAll('\\','/')),`Unmapped TypeScript source: ${path}`);
for(const path of files) assert(existsSync(resolve(root,path)),`Missing source ${path}`);
for(const game of layout.games) for(const [name,target] of [['clients','frontend'],['services','instance']]) {
  const link=resolve(root,'other/runtime',name,game);
  assert(lstatSync(link).isSymbolicLink());
  assert.equal(realpathSync(link),realpathSync(resolve(root,'games',game,target)));
}
let databases=0;
const activePath=resolve(root,'gateway/instance/data/database-active.json');
if(existsSync(activePath)) {
  const active=JSON.parse(readFileSync(activePath,'utf8'));
  const {readPostgresConfig}=await import('../runtime/server/dist/shared/config/environment.js');
  const config=readPostgresConfig(active.configFile);
  const {default:pg}=await import('pg');
  const {verifySchema}=await import('../runtime/server/dist/shared/database/runner.js');
  const client=new pg.Client(config.connection);await client.connect();
  try {
    assert.equal((await client.query('SELECT current_database() AS name')).rows[0].name,active.database);
    for(const source of config.sources)await verifySchema(client,source.schema);
    databases=1;
    console.log(`PostgreSQL active: ${active.database}; ${config.sources.length} registered namespaces verified.`);
  } finally {await client.end();}
} else for(const base of ['gateway/instance/data','other/mock-platform/instance/data',...layout.games.map(g=>'games/'+g+'/instance/data')]) {
  const at=resolve(root,base); if(!existsSync(at)) continue;
  for(const e of readdirSync(at,{withFileTypes:true})) if(e.isFile()&&/\.(sqlite3?|db)$/.test(e.name)) {
    const db=new DatabaseSync(resolve(at,e.name),{readOnly:true});
    try {assert.deepEqual(db.prepare('PRAGMA quick_check').all().map(r=>r.quick_check),['ok'],`Database check failed: ${base}/${e.name}`);databases++;}
    finally {db.close();}
  }
}
if(process.argv.includes('--migration')) {
  const moves=JSON.parse(readFileSync(resolve(root,'other/diagnostics/layout/moves.json'),'utf8'));
  const relocated=old=>{for(const {from,to} of moves) if(old===from||old.startsWith(from+'/')) old=to+old.slice(from.length);return old;};
  const tracked=execFileSync('git',['ls-files','-z'],{cwd:root,encoding:'utf8'}).split('\0').filter(Boolean);
  const missing=tracked.filter(p=>!existsSync(resolve(root,relocated(p))));
  assert.deepEqual(missing,[],'Tracked files lost during relocation');
  const assets=execFileSync('git',['ls-tree','-r','HEAD','--','clients'],{cwd:root,encoding:'utf8',maxBuffer:32*1024*1024}).trim().split('\n').filter(Boolean);
  for(const entry of assets) {
    const [,hash,old]=/^\d+ blob ([a-f0-9]+)\t(.+)$/.exec(entry);
    const data=readFileSync(resolve(root,relocated(old)));
    const actual=createHash('sha1').update(`blob ${data.length}\0`).update(data).digest('hex');
    assert.equal(actual,hash,`Client bytes changed: ${old}`);
  }
  console.log(`Migration audit: ${tracked.length} tracked paths retained; ${assets.length} tracked client files byte-identical.`);
}
console.log(`Layout audit passed: ${layout.games.length} games, ${files.size} modules, ${databases} databases; resource links verified.`);
