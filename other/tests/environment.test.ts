import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,readFileSync,readdirSync,rmSync,mkdirSync,symlinkSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {resolve,join} from 'node:path';
import {execFileSync,spawn} from 'node:child_process';
import {readEnvironment,readPlatformConfig,readPostgresConfig,readGameEnvironment,gameProcessEnvironment,isolatedTestEnvironment,renderEnvironment} from '../shared/config/environment.js';

function fixture(t: any) {const dir=mkdtempSync(join(tmpdir(),'gtt-env-'));t.after(()=>rmSync(dir,{recursive:true,force:true}));return dir;}
test('platform env uses process > file > JSON defaults and env-relative paths without changing process variables',t=>{
  const dir=fixture(t),file=join(dir,'platform.env'),json=join(dir,'node.json');
  writeFileSync(file,'GTT_PG_CONFIG="data/postgres.json"\nPGPASSWORD="file#password"\nADMIN_PORT=9123\nGATEWAY_HOST=0.0.0.0\n');
  writeFileSync(json,JSON.stringify({env_file:'platform.env',ports:{admin:8112,gateway:8110},environment:'development'}));
  const c=readPlatformConfig(json,undefined,{ADMIN_PORT:'9124'});
  assert.equal(c.ports.admin,9124);assert.equal(c.ports.gateway,8110);assert.equal(c.hosts.gateway,'0.0.0.0');
  assert.equal(c.postgres_config,join(dir,'data/postgres.json'));
  assert.equal(readEnvironment(file,{}).PGPASSWORD,'file#password');
  assert.throws(()=>readPlatformConfig(json,undefined,{ADMIN_PORT:'oops'}),/ADMIN_PORT/);
  assert.throws(()=>readPlatformConfig(json,undefined,{GAME_SERVICES_MODE:'misspelled'}),/GAME_SERVICES_MODE/);
});
test('PostgreSQL credentials have one env source and isolated profiles cannot inherit the business database',t=>{
  const dir=fixture(t),file=join(dir,'platform.env'),route=join(dir,'postgres.json');
  writeFileSync(file,renderEnvironment({PGHOST:'127.0.0.1',PGPORT:15432,PGDATABASE:'business',PGUSER:'owner',PGPASSWORD:'secret#value'}));
  writeFileSync(route,JSON.stringify({env_file:'platform.env',sources:[]}));
  assert.equal(readPostgresConfig(route,{}).connection.password,'secret#value');
  assert.equal(readPostgresConfig(route,{PGDATABASE:'override'}).connection.database,'override');
  writeFileSync(route,JSON.stringify({isolated:true,connection:{host:'127.0.0.1',port:15432,database:'test_only',user:'test',password:'test-secret'}}));
  const c=readPostgresConfig(route,{PGDATABASE:'business',PGPASSWORD:'wrong',GTT_PLATFORM_ENV_FILE:'missing.env'});
  assert.equal(c.connection.database,'test_only');assert.equal(c.connection.password,'test-secret');
});
test('game env paths remain correct through generated runtime directory links',t=>{
  const dir=fixture(t),real=join(dir,'real','release'),view=join(dir,'runtime','deep','view');
  mkdirSync(real,{recursive:true});mkdirSync(join(dir,'runtime','deep'),{recursive:true});
  writeFileSync(join(real,'game.env'),'GAME_SECRET_FILE=../key\n');
  symlinkSync(real,view,process.platform==='win32'?'junction':'dir');
  assert.equal(readGameEnvironment(join(view,'game.env'),{}).GAME_SECRET_FILE,join(dir,'real','key'));
});
test('compute children receive only game and OS variables, not platform/database credentials',t=>{
  const dir=fixture(t),file=join(dir,'game.env');
  const env=gameProcessEnvironment({Path:'system-path',HOME:'/home/game',GAME_PORT:'8221',PGPASSWORD:'secret',PGDATABASE:'business',DATABASE_URL:'secret-url',GTT_PG_CONFIG:'private.json',GTT_PLATFORM_ENV_FILE:'platform.env',CLOUD_TOKEN:'secret',NODE_OPTIONS:'--env-file=platform.env'});
  assert.deepEqual(env,{Path:'system-path',HOME:'/home/game',GAME_PORT:'8221'});
  writeFileSync(file,'GAME_ID=buffalo-win\nGAME_RELEASE=v1\nGAME_CONFIG=game.json\nGAME_SECRET_FILE=key\nGAME_PORT=8211\n');
  const game=readGameEnvironment(file,{GAME_PORT:'8212',PGPASSWORD:'must-not-inherit'});
  assert.equal(game.GAME_PORT,'8212');assert.equal(game.GAME_CONFIG,join(dir,'game.json'));assert.equal(game.PGPASSWORD,undefined);
  writeFileSync(file,'PGPASSWORD=secret\n');assert.throws(()=>readGameEnvironment(file,{}),/game env key PGPASSWORD/);
  assert.equal(isolatedTestEnvironment({PGDATABASE:'business',GTT_PLATFORM_ENV_FILE:'x',ADMIN_PORT:'8112'}).PGDATABASE,undefined);
});
test('deployment generator creates 19 version-specific env files, preserves target paths and refuses overwrite',t=>{
  const dir=fixture(t);
  const command=['tools/render-game-env.mjs','--all','--release','env-test-v1','--output',dir,'--base-port','8311'];
  execFileSync(process.execPath,command,{stdio:'pipe'});
  assert.equal(readdirSync(dir).length,19);
  const ports=new Set();
  for(const game of readdirSync(dir)) {
    const env=readGameEnvironment(join(dir,game,'env-test-v1.env'),{});
    assert.equal(env.GAME_ID,game);assert.equal(env.GAME_RELEASE,'env-test-v1');
    assert.equal(readFileSync(join(dir,game,'env-test-v1.env'),'utf8').includes('/opt/gtt-node/games/'),true);
    assert.equal(env.PGPASSWORD,undefined);ports.add(env.GAME_PORT);
  }
  assert.equal(ports.size,19);assert.throws(()=>execFileSync(process.execPath,command,{stdio:'pipe'}));
  assert.throws(()=>execFileSync(process.execPath,['tools/render-game-env.mjs','--game','buffalo-win','--release','bad-relative','--output',dir,'--secret-file','relative.key'],{stdio:'pipe'}));
  const production=JSON.parse(readFileSync('deploy/production.example.json','utf8')),routes=JSON.parse(readFileSync('config/postgres.example.json','utf8'));
  assert.equal(routes.sources.find((s:any)=>s.schema==='control').path,production.merchant_database);
  assert.equal(routes.sources.find((s:any)=>s.schema==='game').path,production.game_database);
  assert.equal(routes.protocolDirectory,production.game_database.replace(/\/[^/]+$/,'/merchant-protocols'));
  for(const role of ['gateway','admin','rtp-worker'])assert.match(readFileSync('deploy/gtt-node-'+role+'.service','utf8'),/^EnvironmentFile=\/etc\/gtt-node\/platform\.env$/m);
});
test('independent compute CLI starts from its release env and explicit flags override its port',async t=>{
  const dir=fixture(t),file=join(dir,'release.env'),key=join(dir,'key');writeFileSync(key,'a'.repeat(64));
  writeFileSync(file,renderEnvironment({GAME_ID:'buffalo-win',GAME_RELEASE:'env-cli-test',GAME_CONFIG:resolve('../services/buffalo-win/config/buffalo-win.json').replaceAll('\\','/'),GAME_SECRET_FILE:key.replaceAll('\\','/'),GAME_PORT:'overridden-by-cli',GAME_BIND:'127.0.0.1'}));
  const child=spawn(process.execPath,['dist/cli.js','game','--env-file',file,'--port','0'],{env:gameProcessEnvironment({...process.env,PGPASSWORD:'never-forward'}),stdio:['ignore','pipe','pipe']});
  t.after(async()=>{if(child.exitCode===null&&child.signalCode===null)await new Promise<void>(ok=>{child.once('exit',()=>ok());child.kill();});});
  const port=await new Promise<number>((ok,fail)=>{let output='';const timer=setTimeout(()=>fail(Error('Compute startup timeout: '+output)),15000);child.on('error',fail);child.on('exit',code=>{clearTimeout(timer);fail(Error('Exited '+code+': '+output));});child.stderr.on('data',b=>output+=b);child.stdout.on('data',b=>{output+=b;const m=/listening on 127\.0\.0\.1:(\d+)/.exec(output);if(m){clearTimeout(timer);ok(Number(m[1]));}});});
  const response=await fetch('http://127.0.0.1:'+port+'/v1/describe',{method:'POST',headers:{'content-type':'application/json',authorization:'Bearer '+'a'.repeat(64)},body:JSON.stringify({expected_release:'env-cli-test'})});
  assert.equal(response.status,200);const result:any=await response.json();assert.equal(result.data.release,'env-cli-test');
});
