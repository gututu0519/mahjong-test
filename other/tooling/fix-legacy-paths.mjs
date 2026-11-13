// Preserve the launcher's logical resource tree rather than resolving junctions
// back to archival Python source directories. Relative schema reads stay local.
import { readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
if(!process.argv.includes('--apply')) throw Error('Explicit --apply required');
function walk(path) {return readdirSync(path,{withFileTypes:true}).flatMap(e=>e.isDirectory()&&e.name!=='__pycache__'?walk(resolve(path,e.name)):e.isFile()&&e.name.endsWith('.py')?[resolve(path,e.name)]:[]);}
let changed=0;
for(const base of ['other/legacy/py','other/capture/tools','other/deploy/legacy']) {
  for(const path of walk(resolve(root,base))) {
    const old=readFileSync(path,'utf8');
    const next=old.replace(/Path\(__file__\)\.resolve\(\)\.parents/g,'Path(__file__).absolute().parents');
    if(old!==next) {writeFileSync(path,next);changed++;}
  }
}
console.log(`Preserved logical resource paths in ${changed} legacy Python tools.`);
