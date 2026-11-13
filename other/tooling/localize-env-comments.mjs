// Update comments without rewriting configuration values or printing secrets.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,readdirSync,existsSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseEnv} from 'node:util';
import {environmentDescriptions} from '../runtime/server/dist/shared/config/environment.js';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const layout=JSON.parse(readFileSync(resolve(root,'other/tooling/layout.json'),'utf8'));
const files=['gateway/instance/platform.env','other/deploy/instance/postgres.env'];
for(const game of layout.games) {
  const folder=`games/${game}/instance/releases`;
  if(existsSync(resolve(root,folder)))for(const entry of readdirSync(resolve(root,folder),{withFileTypes:true}))
    if(entry.isFile()&&entry.name.endsWith('.env'))files.push(folder+'/'+entry.name);
}
const plans=[];
for(const file of files) {
  if(!existsSync(resolve(root,file)))continue;
  const original=readFileSync(resolve(root,file),'utf8');
  const lines=[];
  for(let line of original.split(/\r?\n/)) {
    if(line==='# Local platform: gateway, admin, RTP worker and database tooling.')line='# 本机平台配置：网关、管理后台、RTP worker 和数据库工具共用。';
    const key=/^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=/.exec(line)?.[1];
    if(key&&environmentDescriptions[key]) {
      const comment='# '+environmentDescriptions[key];
      if(lines.at(-1)!==comment)lines.push(comment);
    }
    lines.push(line);
  }
  const updated=lines.join('\n');
  assert.deepEqual(parseEnv(updated),parseEnv(original),'Comment update altered configuration values: '+file);
  plans.push({file,original,updated});
}
if(process.argv.includes('--apply')) {
  let changed=0;
  for(const {file,original,updated} of plans)if(original!==updated){writeFileSync(resolve(root,file),updated,{mode:0o600});changed++;}
  console.log(`已为 ${changed} 份运行 env 更新中文注释，${plans.length} 份配置的全部键值核对一致。`);
} else console.log(`已检查 ${plans.length} 份运行 env；添加 --apply 仅更新注释，不修改配置值。`);
