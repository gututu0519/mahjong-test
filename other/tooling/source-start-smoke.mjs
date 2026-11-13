import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,rmSync,mkdirSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {resolve,dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn,execFileSync} from 'node:child_process';
import {npmExecutable} from './scripts/install-dependencies.mjs';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const dir=mkdtempSync(join(tmpdir(),'gtt-source-start-')),key=join(dir,'key');writeFileSync(key,'s'.repeat(64));
const child=spawn(process.execPath,[npmExecutable(),'start','--','--port','0','--release','source-start-check','--secret-file',key],{cwd:resolve(root,'games/fortune-rabbit'),detached:process.platform!=='win32',stdio:['ignore','pipe','pipe']});
let output='';
try {
  const port=await new Promise((ok,fail)=>{
    const timer=setTimeout(()=>fail(Error('Source npm start timed out: '+output)),120000);
    child.on('error',fail);child.on('exit',code=>{clearTimeout(timer);fail(Error('Source npm start exited '+code+': '+output));});
    child.stderr.on('data',b=>output+=b);child.stdout.on('data',b=>{output+=b;const m=/listening on 127\.0\.0\.1:(\d+)/.exec(output);if(m){clearTimeout(timer);ok(Number(m[1]));}});
  });
  const positions=['[1/3]','[2/3]','[3/3]'].map(x=>output.indexOf(x));
  assert(positions[0]>=0&&positions[1]>positions[0]&&positions[2]>positions[1]);
  const r=await fetch('http://127.0.0.1:'+port+'/v1/describe',{method:'POST',headers:{'content-type':'application/json',authorization:'Bearer '+'s'.repeat(64)},body:JSON.stringify({expected_release:'source-start-check'})});
  assert.equal(r.status,200);assert.equal((await r.json()).data.game_id,'fortune-rabbit');
  mkdirSync(resolve(root,'other/diagnostics/startup'),{recursive:true});writeFileSync(resolve(root,'other/diagnostics/startup/source-game-start.log'),output);
  console.log('Source game npm start passed: install -> compile -> migration stage -> independent compute startup.');
} finally {
  if(child.exitCode===null)await new Promise(ok=>{child.once('exit',ok);if(process.platform==='win32'){try{execFileSync('taskkill',['/PID',String(child.pid),'/T','/F'],{stdio:'pipe'});}catch{child.kill();}}else{try{process.kill(-child.pid,'SIGTERM');}catch{child.kill();}}});
  rmSync(dir,{recursive:true,force:true});
}
