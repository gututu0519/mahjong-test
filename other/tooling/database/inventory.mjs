import { DatabaseSync } from 'node:sqlite';
import { readFileSync, readdirSync, existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
export const root=resolve(dirname(fileURLToPath(import.meta.url)),'../../..');
const layout=JSON.parse(readFileSync(resolve(root,'other/tooling/layout.json'),'utf8'));
export function sources({includeMissing=false}={}) {
  const list=[{path:'gateway/instance/data/merchants.sqlite3',schema:'control',kind:'control'},
    {path:'gateway/instance/data/gtt.sqlite3',schema:'game',kind:'game'},
    {path:'other/mock-platform/instance/data/platform.sqlite3',schema:'mock',kind:'mock'},
    ...[...layout.games,'game-api'].map(game=>({path:game==='game-api'?'other/game-api/data/games.sqlite3':`games/${game}/instance/data/games.sqlite3`,schema:'demo_'+game.replaceAll('-','_'),kind:'local'}))];
  const at=resolve(root,'gateway/instance/data/merchant-protocols');
  if(existsSync(at)) for(const e of readdirSync(at,{withFileTypes:true})) if(e.isFile()&&e.name.endsWith('.sqlite3')) {
    const name=e.name.slice(0,-8),code=layout.games.find(g=>name===g||name.startsWith(g+'-fe-'));
    if(!code) throw Error('Unknown protocol database '+e.name);
    const schema='protocol_'+name.replaceAll('-','_');
    if(schema.length>63) throw Error('Protocol schema needs explicit short name: '+name);
    list.push({path:'gateway/instance/data/merchant-protocols/'+e.name,schema,kind:'protocol'});
  }
  return includeMissing?list:list.filter(x=>existsSync(resolve(root,x.path)));
}
export const quote=x=>'"'+x.replaceAll('"','""')+'"';
export function describe(path) {
  const db=new DatabaseSync(path,{readOnly:true});
  try {
    const tables=db.prepare("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").all().map(t=>({...t,
      columns:db.prepare('PRAGMA table_info('+quote(t.name)+')').all(),
      foreignKeys:db.prepare('PRAGMA foreign_key_list('+quote(t.name)+')').all(),
      count:db.prepare('SELECT COUNT(*) AS n FROM '+quote(t.name)).get().n,
      indexes:db.prepare("SELECT name,sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL").all(t.name),
    }));
    const integrity=db.prepare('PRAGMA quick_check').all();
    if(integrity.some(r=>r.quick_check!=='ok')) throw Error('SQLite integrity check failed: '+path);
    return tables;
  } finally {db.close();}
}
if(process.argv.includes('--save')) {
  const result=sources().map(s=>({...s,tables:describe(resolve(root,s.path))}));
  mkdirSync(resolve(root,'other/diagnostics/postgres'),{recursive:true});
  writeFileSync(resolve(root,'other/diagnostics/postgres/inventory.json'),JSON.stringify(result,null,2));
  for(const s of result) console.log(`${s.schema}: ${s.tables.length} tables, ${s.tables.reduce((n,t)=>n+t.count,0)} rows`);
  console.log(`${result.length} active databases; historical backup files excluded.`);
}
