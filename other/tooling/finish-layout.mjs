// One-time migration of local path references and launchers; no credentials are logged.
import { readFileSync, writeFileSync, existsSync, readdirSync, mkdirSync } from 'node:fs';
import { resolve, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const layout=JSON.parse(readFileSync(resolve(root,'other/tooling/layout.json'),'utf8'));
if(!process.argv.includes('--apply')) throw Error('Explicit --apply required');
const mappings={};
for(const g of layout.games) {mappings['services/'+g]='games/'+g+'/instance';mappings['clients/'+g]='games/'+g+'/frontend';}
Object.assign(mappings,{'services/gtt-gateway':'gateway/instance','services/gtt-admin':'admin/instance','services/gtt-mock-platform':'other/mock-platform/instance','services/game-api':'other/game-api','server':'other/runtime/server','diagnostics':'other/diagnostics/history'});
const normalized=root.replaceAll('\\','/');
function relocate(value) {
  if(typeof value==='string') {
    const p=value.replaceAll('\\','/');
    for(const [old,next] of Object.entries(mappings)) {
      const prefix=normalized+'/'+old;
      if(p.toLowerCase()===prefix.toLowerCase()||p.toLowerCase().startsWith(prefix.toLowerCase()+'/')) return resolve(root,next,p.slice(prefix.length+1));
      if(p===old||p.startsWith(old+'/')) return resolve(root,next,p.slice(old.length+1));
    }
    return value;
  }
  if(Array.isArray(value)) return value.map(relocate);
  if(value&&typeof value==='object') return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,relocate(v)]));
  return value;
}
const dataDirs=['gateway/instance/data','admin/instance/data','other/mock-platform/instance/data',...layout.games.map(g=>'games/'+g+'/instance/data')];
let updated=0;
for(const dir of dataDirs) {
  const at=resolve(root,dir); if(!existsSync(at)) continue;
  for(const name of readdirSync(at)) if(name.endsWith('.json')) {
    const path=resolve(at,name), raw=readFileSync(path,'utf8');
    let old; try {old=JSON.parse(raw);} catch {continue;}
    const next=relocate(old);
    if(JSON.stringify(old)!==JSON.stringify(next)) {
      // Backup remains within the ignored private data directory.
      if(!existsSync(path+'.before-layout')) writeFileSync(path+'.before-layout',raw,{mode:0o600});
      writeFileSync(path,JSON.stringify(next,null,2)+'\n',{mode:0o600});updated++;
    }
  }
}
function batch(path,lines) {writeFileSync(resolve(root,path),'@echo off\r\n'+lines.join('\r\n')+'\r\n');}
for(const game of layout.games) {
  batch(`games/${game}/start.bat`,[`node "%~dp0..\\..\\other\\tooling\\run.mjs" start ${game} %*`,'pause']);
  batch(`games/${game}/instance/start.bat`,['call "%~dp0..\\start.bat" %*']);
  const py=`games/${game}/instance/start-python.bat`, p=resolve(root,py);
  if(existsSync(p)) {
    const old=readFileSync(p,'utf8'), module=/-m\s+([\w.]+)/.exec(old)?.[1];
    if(module) batch(py,[`node "%~dp0..\\..\\..\\other\\tooling\\run.mjs" python -u -m ${module} %*`,'pause']);
  }
}
for(const [base,action] of [['gateway','gateway'],['admin','admin'],['other/mock-platform','mock']]) {
  const tool=base.startsWith('other/')?'..\\tooling':'..\\other\\tooling';
  batch(base+'/start.bat',[`node "%~dp0${tool}\\run.mjs" start ${action} %*`,'pause']);
  batch(base+'/instance/start.bat',['call "%~dp0..\\start.bat" %*']);
}
batch('other/game-api/start.bat',['node "%~dp0..\\tooling\\run.mjs" start game-api %*','pause']);
batch('other/legacy/start-server.bat',['node "%~dp0..\\tooling\\run.mjs" start mahjong-ways2 %*','pause']);
batch('other/legacy/start-python.bat',['node "%~dp0..\\tooling\\run.mjs" python -u -m py.services.local_demo %*','pause']);
console.log(`Updated ${updated} private JSON path references; launchers regenerated. No database contents changed.`);
