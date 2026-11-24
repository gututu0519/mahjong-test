import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,readFileSync,writeFileSync,renameSync,rmSync,existsSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {tmpdir} from 'node:os';
import {createRequire} from 'node:module';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {createServer} from 'node:net';
import {artifactPath,extractArchive} from './archive.mjs';
import {npmExecutable} from './install-dependencies.mjs';

const release=resolve(process.argv[2]);
const record=JSON.parse(readFileSync(join(release,'release.json'),'utf8'));
const temp=mkdtempSync(join(tmpdir(),'gtt-pm2-release-'));
process.env.PM2_HOME=join(temp,'pm2');
const code='fortune-rabbit',name=code+'-'+record.build_id;
const artifact=record.artifacts.find(item=>item.name==='game-'+code);
extractArchive(artifactPath(release,record,artifact),temp);
const root=join(temp,'games',code,record.build_id);
mkdirSync(join(temp,'games',code),{recursive:true});
renameSync(join(temp,artifact.name),root);
const config=join(temp,'config/games',code,record.build_id+'.env');
mkdirSync(join(temp,'config/games',code),{recursive:true});
const key=join(temp,'secret.key');writeFileSync(key,'a'.repeat(64));
const render=port=>writeFileSync(config,[`GAME_ID=${code}`,`GAME_RELEASE=${record.build_id}`,`GAME_CONFIG=${JSON.stringify(join(root,'config/game.json'))}`,`GAME_SECRET_FILE=${JSON.stringify(key)}`,'GAME_BIND=127.0.0.1',`GAME_PORT=${port}`].join('\n'));
const env={...process.env,GAME_BIND:'127.0.0.1',PGPASSWORD:'must-not-reach-game',GTT_INTERNAL_SECRET:'must-not-reach-game',npm_config_cache:join(temp,'npm-cache')};
delete env.GAME_ENV_FILE;
const run=async (...args)=>{
  try {const result=await promisify(execFile)(process.execPath,[npmExecutable(),'start','--',...args],{cwd:root,env,timeout:180000,windowsHide:true,maxBuffer:1024*1024});return {ok:true,...result};}
  catch(error){return {ok:false,stdout:error.stdout??'',stderr:error.stderr??''};}
};
let pm2;
const bundled=JSON.parse(readFileSync(join(root,'SERVICE.json'),'utf8')).dependencies_bundled!==false;
assert.equal(existsSync(join(root,'node_modules')),bundled);
const call=(method,...args)=>new Promise((ok,fail)=>pm2[method](...args,(err,result)=>err?fail(err):ok(result)));
let blocker;
try {
  render(0);
  if(!bundled) {
    env.npm_config_offline='true';
    const failure=await run();delete env.npm_config_offline;
    assert.equal(failure.ok,false,'Empty-cache offline install must fail');
    assert.match(failure.stderr,/依赖安装失败/);
    assert.equal(existsSync(join(process.env.PM2_HOME,'pm2.pid')),false,'Failed dependency installation must not start PM2');
  }
  const first=await run();assert.ok(first.ok,first.stderr+'\n'+first.stdout);
  assert.ok(existsSync(join(root,'node_modules/pm2/package.json')));
  assert.equal(JSON.parse(readFileSync(join(root,'node_modules/pm2/package.json'),'utf8')).version,JSON.parse(readFileSync(join(root,'package.json'),'utf8')).dependencies.pm2);
  pm2=createRequire(join(root,'package.json'))('pm2');
  await call('connect');
  const get=async ()=>(await call('list')).find(item=>item.name===name);
  const initial=await get();assert.ok(initial?.pid);
  assert.equal(initial.pm2_env.PGPASSWORD,undefined);
  assert.equal(initial.pm2_env.GTT_INTERNAL_SECRET,undefined);
  assert.equal(initial.pm2_env.pm_cwd,root);
  assert.ok(initial.pm2_env.args.includes(config));
  const output=readFileSync(initial.pm2_env.pm_out_log_path,'utf8');
  const port=Number(/listening on 127\.0\.0\.1:(\d+)/.exec(output)?.[1]);assert.ok(port);
  assert.equal((await fetch(`http://127.0.0.1:${port}/health`,{headers:{authorization:'Bearer '+'a'.repeat(64)}})).status,200);
  const repeat=await run();assert.ok(repeat.ok,repeat.stderr);assert.notEqual((await get()).pid,initial.pid);
  const lastPort=instance=>Number([...readFileSync(instance.pm2_env.pm_out_log_path,'utf8').matchAll(/listening on 127\.0\.0\.1:(\d+)/g)].at(-1)?.[1]);
  const currentPid=(await get()).pid;
  const reservation=createServer();await new Promise(ok=>reservation.listen(0,'127.0.0.1',ok));
  const changedPort=reservation.address().port;await new Promise(ok=>reservation.close(ok));
  render(changedPort);writeFileSync(key,'b'.repeat(64));
  writeFileSync(config,readFileSync(config,'utf8')+'\nGAME_CLIENT_CONTRACT=restart-test-contract\n');
  const descriptor=async port=>(await (await fetch(`http://127.0.0.1:${port}/v1/describe`,{method:'POST',headers:{authorization:'Bearer '+'b'.repeat(64),'content-type':'application/json'},body:'{}'})).json()).data;
  env.GAME_BIND='127.0.0.1';
  const changed=await run();assert.ok(changed.ok,changed.stderr);assert.notEqual((await get()).pid,currentPid);
  assert.equal(lastPort(await get()),changedPort);
  assert.equal((await descriptor(changedPort)).client_contract,'restart-test-contract');
  assert.equal((await fetch(`http://127.0.0.1:${changedPort}/health`,{headers:{authorization:'Bearer '+'b'.repeat(64)}})).status,200);
  assert.equal((await fetch(`http://127.0.0.1:${changedPort}/health`,{headers:{authorization:'Bearer '+'a'.repeat(64)}})).status,401);
  const alternate=join(temp,'alternate.env');
  render(0);writeFileSync(alternate,readFileSync(config));
  delete env.GAME_BIND;
  const switched=await run('--env-file',alternate);assert.ok(switched.ok,switched.stderr);
  assert.ok((await get()).pm2_env.args.includes(alternate));
  assert.equal((await descriptor(lastPort(await get()))).client_contract,code+':original-v1','Removed env-file key must revert to its default');
  assert.equal((await get()).pm2_env.GAME_BIND,undefined,'Removed caller environment must not survive PM2 restart');
  const healthyPid=(await get()).pid;
  const missing=await run('--env-file',join(temp,'missing.env'));assert.equal(missing.ok,false);assert.equal((await get()).pid,healthyPid);
  writeFileSync(key,'short');
  const invalid=await run();assert.equal(invalid.ok,false);assert.equal((await get()).pid,healthyPid);
  writeFileSync(key,'b'.repeat(64));
  await call('stop',name);
  const stopped=await run();assert.ok(stopped.ok,stopped.stderr);assert.ok((await get()).pid);
  blocker=createServer();await new Promise(ok=>blocker.listen(0,'127.0.0.1',ok));
  render(blocker.address().port);
  const occupied=await run();assert.equal(occupied.ok,false);assert.match(occupied.stderr,/EADDRINUSE/);
  assert.equal((await get()).pm2_env.status,'stopped');
  render(0);
  const recovered=await run();assert.ok(recovered.ok,recovered.stderr);assert.equal((await get()).pm2_env.status,'online');
  await call('delete',name);
  await call('start',{name,cwd:root,script:join(root,'tools',code+'.mjs'),interpreter:process.execPath,args:['game','--env-file',join(temp,'missing.env')],autorestart:true,min_uptime:60000,max_restarts:1});
  const errorDeadline=Date.now()+30000;
  while((await get()).pm2_env.status!=='errored'&&Date.now()<errorDeadline)await new Promise(ok=>setTimeout(ok,300));
  assert.equal((await get()).pm2_env.status,'errored');
  const errored=await run();assert.ok(errored.ok,errored.stderr);assert.equal((await get()).pm2_env.status,'online');
  await call('delete',name);
  const foreign=join(temp,'foreign.mjs');writeFileSync(foreign,'setInterval(()=>{},1000);');
  await call('start',{name,cwd:temp,script:foreign,interpreter:process.execPath,autorestart:false});
  const foreignPid=(await get()).pid;
  const conflict=await run();assert.equal(conflict.ok,false);assert.equal((await get()).pid,foreignPid);
  await call('delete',name);
  const otherVersion=code+'-other-version';
  await call('start',{name:otherVersion,cwd:temp,script:foreign,interpreter:process.execPath,autorestart:false});
  const otherPid=(await call('list')).find(item=>item.name===otherVersion).pid;
  render(0);
  renameSync(join(root,'package-lock.json'),join(root,'package-lock.saved.json'));
  const installation=await run();assert.equal(installation.ok,false);assert.match(installation.stderr,/缺少依赖锁文件/);
  assert.equal((await get()).pm2_env.status,'stopped');
  assert.equal((await call('list')).find(item=>item.name===otherVersion).pid,otherPid);
  const report=process.argv[3]??'pm2-verification.json';
  assert.match(report,/^[a-zA-Z0-9._-]+\.json$/);
  writeFileSync(join(release,report),JSON.stringify({build_id:record.build_id,node:process.version,verified_at:new Date().toISOString(),dependencies_bundled:bundled,checks:[...(!bundled?['empty-cache-install-failure-no-pm2','npm-start-installs-missing-pm2-from-lock']:[]),'background-npm-start','automatic-version-env-discovery','ready-health-endpoint','same-instance-restart-changes-pid','changed-env-port-and-key-take-effect','explicit-new-env-path','removed-process-env-not-retained','invalid-config-preserves-running-instance','stopped-and-failed-instance-recovery','foreign-directory-conflict-refused','port-conflict-fails-and-stops','dependency-preflight-fails-and-stops','game-process-has-no-platform-credentials'],scope:'Real independent game package with isolated PM2_HOME and npm cache; no PostgreSQL startup assertion.'},null,2)+'\n',{flag:'wx'});
  console.log('PM2 background startup verification passed.');
} finally {
  if(blocker)await new Promise(ok=>blocker.close(ok));
  console.log('Cleaning isolated PM2 processes.');
  if(pm2)try {await call('delete','all');console.log('Stopping isolated PM2 daemon.');await new Promise((ok,fail)=>pm2.Client.killDaemon(error=>error?fail(error):ok()));}finally {pm2.disconnect();}
  rmSync(temp,{recursive:true,force:true});
  console.log('Isolated PM2 cleanup complete.');
}
// PM2's Windows client can retain reconnect timers after its daemon is gone.
// All assertions and explicit teardown above must succeed before exiting.
process.exit(0);
