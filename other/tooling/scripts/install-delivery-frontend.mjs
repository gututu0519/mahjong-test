import {cpSync,mkdtempSync,readFileSync,rmSync} from 'node:fs';
import {dirname,join,resolve} from 'node:path';
import {tmpdir} from 'node:os';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';

const here=dirname(fileURLToPath(import.meta.url));
const [installer,destination,publicDirectory]=process.argv.slice(2);
if(!installer||!destination)throw Error('用法：node install-delivery-frontend.mjs <网关 tools/install-frontend.mjs> <前端版本存储根目录> [client 素材目录]');
const {game,release}=JSON.parse(readFileSync(join(here,'manifest.json'),'utf8'));
const objects=publicDirectory??resolve(here,'../..',`${game}-client-${release}`);
const stage=mkdtempSync(join(tmpdir(),'gtt-frontend-install-'));
try {
  cpSync(join(here,'manifest.json'),join(stage,'manifest.json'));
  cpSync(join(here,'bootstrap'),join(stage,'bootstrap'),{recursive:true});
  cpSync(objects,join(stage,'objects'),{recursive:true});
  execFileSync(process.execPath,[resolve(installer),stage,'--destination',resolve(destination)],{stdio:'inherit'});
} finally {rmSync(stage,{recursive:true,force:true});}
