import {spawn} from 'node:child_process';
import {openSync,closeSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {root} from './inventory.mjs';
const logdir=resolve(root,'other/diagnostics/postgres');mkdirSync(logdir,{recursive:true});
for(const name of ['games','gateway','admin']) {
  const out=openSync(resolve(logdir,name+'.stdout.log'),'a'),err=openSync(resolve(logdir,name+'.stderr.log'),'a');
  const child=spawn(process.execPath,[resolve(root,'other/tooling/run.mjs'),'start',name],{cwd:root,detached:true,windowsHide:true,stdio:['ignore',out,err]});
  child.unref();closeSync(out);closeSync(err);console.log(`${name}: started launcher PID ${child.pid}`);
}
