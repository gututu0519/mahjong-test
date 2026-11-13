// One-time, fail-on-collision physical migration. Kept as a record of the mapping.
import { existsSync, readdirSync, readFileSync, writeFileSync, mkdirSync, renameSync, rmdirSync } from 'node:fs';
import { resolve, dirname, relative, posix } from 'node:path';
import { fileURLToPath } from 'node:url';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
if (!process.argv.includes('--apply')) throw Error('Explicit --apply required');
if (!existsSync(resolve(root, 'server/package.json'))) throw Error('Old layout not found; migration must run only once');
const games = readdirSync(resolve(root, 'clients'));
const slug = name => name === 'three_billion_vaults' ? '3-billion-vaults' : name.replaceAll('_', '-');
const entries = { local_demo:'mahjong-ways2', mahjong_assets:'mahjong-ways2', buffalo_demo:'buffalo-win', buffalo_preview:'buffalo-win', olympus_demo:'gates-of-olympus', olympus_preview:'gates-of-olympus' };
const modules = {}, files = {}, moves = [];
function move(from, to) {
  const a=resolve(root,from), b=resolve(root,to);
  if (!existsSync(a)) return;
  if (existsSync(b)) throw Error(`Destination already exists: ${to}`);
  mkdirSync(dirname(b),{recursive:true}); renameSync(a,b); moves.push({from,to});
}
function walk(dir) {
  return readdirSync(resolve(root,dir),{withFileTypes:true}).flatMap(e=>e.isDirectory()?walk(dir+'/'+e.name):[dir+'/'+e.name]);
}
function destination(path) {
  let m;
  if ((m=/^games\/buffalo-win\/(.*)/.exec(path))) return 'games/buffalo-win/backend/native/'+m[1];
  if ((m=/^migrated\/py\/games\/([^/]+)\/(.*)/.exec(path))) return `games/${slug(m[1])}/backend/engine/${m[2]}`;
  if ((m=/^migrated\/py\/adapters\/([^/]+)\/([^/]+)\.ts$/.exec(path))) {
    const game=m[2]==='tower_run'?'tower-run-treasure-steps':m[2]==='mahjong_metadata'?'mahjong-ways2':slug(m[2]);
    if(games.includes(game)) return `games/${game}/backend/adapters/${m[1]}/${m[2]}.ts`;
  }
  if ((m=/^migrated\/py\/services\/([^/]+)\.ts$/.exec(path))) {
    const game=entries[m[1]]??slug(m[1].replace(/_demo$/,''));
    if(games.includes(game)) return `games/${game}/backend/services/${m[1]}.ts`;
  }
  if(path==='gateway/admin.ts'||path==='gateway/catalog-export.ts') return 'admin/backend/'+path.slice(8);
  if(path==='gateway/control.ts') return 'other/shared/control.ts';
  if(path.startsWith('gateway/')) return 'gateway/src/'+path.slice(8);
  if(path.startsWith('shared/')) return 'other/shared/'+path.slice(7);
  if(path.startsWith('tests/')) return 'other/tests/'+path.slice(6);
  if(path.startsWith('fixtures/')) return 'other/tests/fixtures/'+path.slice(9);
  if(path.startsWith('tools/')) return 'other/tooling/scripts/'+path.slice(6);
  if(path.startsWith('deploy/')) return 'other/deploy/node/'+path.slice(7);
  if(path==='config/buffalo-win.json') return 'games/buffalo-win/backend/native/config.json';
  if(/^config\/(guide\.|integration\.|openapi\.)/.test(path)) return 'admin/'+path;
  if(path.startsWith('config/')) return 'gateway/'+path;
  if(path==='cli.ts') return 'other/tooling/cli.ts';
  if(path==='package.json'||path==='package-lock.json'||path==='tsconfig.json') return 'other/tooling/'+path;
  if(path.endsWith('.md')) return 'other/docs/node/'+path;
  if(path==='.gitignore') return 'other/tooling/legacy.gitignore';
  return 'other/shared/'+path;
}
// Record all source mappings before changing any import.
for (const p of walk('server').filter(p=>!/^server\/(node_modules|dist|runtime|frontend)\//.test(p))) {
  const old=p.slice(7), next=destination(old); files[old]=next;
  if(old.endsWith('.ts')) modules[old]=next;
}
const rewrite=(text,old,next)=>text.replace(/(\bfrom\s*|\bimport\s*\(\s*|\bimport\s*)(["'])(\.[^"']+)\2/g,(all,prefix,quote,spec)=>{
  const target=posix.normalize(posix.join(posix.dirname(old),spec)).replace(/\.js$/,'.ts');
  if(!modules[target]) return all;
  let ref=posix.relative(posix.dirname(next),modules[target]).replace(/\.ts$/,'.js');
  if(!ref.startsWith('.')) ref='./'+ref;
  return prefix+quote+ref+quote;
});
for(const [old,next] of Object.entries(files)) {
  if(old.endsWith('.ts')) {
    const p=resolve(root,'server',old), text=readFileSync(p,'utf8');
    writeFileSync(p,rewrite(text,old,next));
  }
  move('server/'+old,next);
}
move('server/frontend/admin','admin/frontend');
move('server/frontend/platform','other/mock-platform/frontend');
move('server/node_modules','other/tooling/node_modules');
move('server/dist','other/diagnostics/pre-layout/dist');
move('server/runtime','other/diagnostics/pre-layout/runtime');
for(const game of games) { move('clients/'+game,`games/${game}/frontend`); move('services/'+game,`games/${game}/instance`); }
move('services/gtt-gateway','gateway/instance');
move('services/gtt-admin','admin/instance');
move('services/gtt-mock-platform','other/mock-platform/instance');
move('services/game-api','other/game-api');
move('services/README.md','other/docs/services.md');
for(const [from,to] of Object.entries({py:'other/legacy/py',demo:'other/demo',deploy:'other/deploy/legacy',diagnostics:'other/diagnostics/history',docs:'other/docs/project',tools:'other/capture/tools','response-capture':'other/capture/response-capture','__pycache__':'other/diagnostics/python-cache','original.har':'other/capture/archives/original.har','official-audio.har':'other/capture/archives/official-audio.har','DEVELOPMENT_HANDOFF.md':'other/docs/DEVELOPMENT_HANDOFF.md','start-server.bat':'other/legacy/start-server.bat','start-python.bat':'other/legacy/start-python.bat'})) move(from,to);
// Keep each game's rules next to its implementation, and record resource aliases.
const documents={};
for(const name of readdirSync(resolve(root,'other/docs/project'))) {
  const game=games.find(g=>name.startsWith(g+'-')||name===g+'.md');
  if(game) { const dest=`games/${game}/docs/${name}`; move('other/docs/project/'+name,dest); documents[name]=dest; }
}
function removeEmpty(at) {
  if(!existsSync(at)) return;
  for(const e of readdirSync(at,{withFileTypes:true})) if(e.isDirectory()) removeEmpty(resolve(at,e.name));
  if(!readdirSync(at).length) rmdirSync(at);
}
for(const name of ['server','clients','services']) removeEmpty(resolve(root,name));
writeFileSync(resolve(root,'other/tooling/layout.json'),JSON.stringify({version:1,games,modules,files,documents},null,2)+'\n');
mkdirSync(resolve(root,'other/diagnostics/layout'),{recursive:true});
writeFileSync(resolve(root,'other/diagnostics/layout/moves.json'),JSON.stringify(moves,null,2)+'\n');
console.log(`Moved ${moves.length} paths; ${Object.keys(modules).length} TypeScript modules mapped.`);
