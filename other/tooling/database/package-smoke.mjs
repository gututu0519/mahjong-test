import pg from 'pg';
import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,writeFileSync,existsSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {resolve,join} from 'node:path';
import {execFileSync,spawn} from 'node:child_process';
import {root} from './inventory.mjs';
import {isolatedTestEnvironment,gameProcessEnvironment,renderEnvironment} from '../../runtime/server/dist/shared/config/environment.js';
import {artifactPath,extractArchive} from '../scripts/archive.mjs';
import {npmExecutable} from '../scripts/install-dependencies.mjs';
const release=resolve(process.argv[2]), directory=mkdtempSync(join(tmpdir(),'gtt-pg-package-'));
const releaseRecord=JSON.parse(readFileSync(join(release,'release.json'),'utf8'));
const archivesAt=process.argv.indexOf('--archives');
const archives=archivesAt>=0?resolve(process.argv[archivesAt+1]):undefined;
const unpack=name=>extractArchive(artifactPath(release,releaseRecord,releaseRecord.artifacts.find(a=>a.name===name),archives),directory);
const {databaseSettings}=await import('./settings.mjs');
const settings=databaseSettings();
const database='gtt_package_'+Date.now(), admin=new pg.Client({...settings.connection,database:'postgres'});await admin.connect();
await admin.query('CREATE DATABASE "'+database+'" TEMPLATE template0');await admin.end();
const connection={...settings.connection,database};
const client=new pg.Client(connection);await client.connect();
const configFile=join(directory,'postgres.json');
const platformFile=join(directory,'platform.env'), config=join(directory,'node.json');
writeFileSync(configFile,JSON.stringify({driver:'postgres',env_file:'platform.env',sources:[{path:join(directory,'merchants.sqlite3'),schema:'package_control',kind:'control'},{path:join(directory,'gtt.sqlite3'),schema:'package_game',kind:'game'}]}),{mode:0o600});
const env={NODE_ENV:'development',GTT_CONFIG_FILE:'node.json',GTT_PG_CONFIG:'postgres.json',PGHOST:connection.host,PGPORT:connection.port,PGDATABASE:database,PGUSER:connection.user,PGPASSWORD:connection.password,PGSSLMODE:connection.ssl?(connection.ssl.rejectUnauthorized===false?'require':'verify-full'):'disable',GTT_INTERNAL_SECRET:'b'.repeat(64),GATEWAY_PORT:0,ADMIN_PORT:0,GAME_SERVICES_MODE:'remote'};
if(connection.ssl?.ca){writeFileSync(join(directory,'ca.pem'),connection.ssl.ca);env.PGSSLROOTCERT='ca.pem';}
writeFileSync(platformFile,renderEnvironment(env),{mode:0o600});
const children=[];
const npm=npmExecutable();
const pipeline=!!releaseRecord.startup;
const logs=[];
async function start(action,file,packageName) {
  packageName??=action==='admin'?(releaseRecord.topology?.admin??'gateway'):'gateway';
  const cliArgs=['--env-file',file,...(action==='game'?['--port','0']:[])];
  const command=pipeline?[npm,'start','--',...cliArgs]:['dist/cli.js',action,...cliArgs];
  const child=spawn(process.execPath,command,{cwd:join(directory,packageName),env:action==='game'?gameProcessEnvironment(process.env):isolatedTestEnvironment(process.env),detached:process.platform!=='win32',stdio:['ignore','pipe','pipe']});
  children.push(child);
  return new Promise((ok,fail)=>{
    let output='';const timer=setTimeout(()=>fail(Error(action+' timeout: '+output)),90000);
    child.on('error',fail);child.on('exit',code=>{clearTimeout(timer);fail(Error(action+' exited '+code+': '+output));});
    child.stderr.on('data',b=>output+=b);
    child.stdout.on('data',b=>{output+=b;const m=/listening on 127\.0\.0\.1:(\d+)/.exec(output);if(m){clearTimeout(timer);logs.push({action,output});ok(Number(m[1]));}});
  });
}
try {
  unpack('gateway');
  if(releaseRecord.topology?.admin)unpack(releaseRecord.topology.admin);
  const adminPackage=releaseRecord.topology?.admin??'gateway';
  let c;
  if(pipeline) {
    for(const path of ['frontend','clients','dist/gateway/admin.js','dist/gateway/catalog-export.js'])assert.equal(existsSync(join(directory,'gateway',path)),false,'Gateway must not contain '+path);
    c={environment:'development',game_services_mode:'remote',merchant_database:join(directory,'merchants.sqlite3'),game_database:join(directory,'gtt.sqlite3'),client_root:join(directory,'gateway/clients/buffalo-win'),internal_secret:'invalid-JSON-fallback',gateway_origin:'http://127.0.0.1:8110',ports:{gateway:8110,admin:8112}};
    writeFileSync(config,JSON.stringify(c));
    rmSync(join(directory,'gateway/node_modules'),{recursive:true,force:true});
  } else {
    const {metadata,ensureSchema}=await import('../../runtime/server/dist/shared/database/runner.js');
    await metadata(client);await ensureSchema(client,'package_control','control');await ensureSchema(client,'package_game','game');
    execFileSync(process.execPath,['dist/cli.js','init','--env-file',platformFile],{cwd:join(directory,'gateway'),env:isolatedTestEnvironment(process.env),stdio:'pipe'});
    c=JSON.parse(readFileSync(config,'utf8'));c.internal_secret='invalid-JSON-fallback';writeFileSync(config,JSON.stringify(c));
  }
  const gateway=await start('gateway',platformFile);
  if(pipeline)execFileSync(process.execPath,['dist/cli.js','admin-init','--env-file',platformFile],{cwd:join(directory,adminPackage),env:isolatedTestEnvironment(process.env),stdio:'pipe'});
  const consolePort=await start('admin',platformFile);
  assert.equal((await fetch('http://127.0.0.1:'+gateway+'/health')).status,200);
  assert.equal((await fetch('http://127.0.0.1:'+gateway+'/')).status,200,'Legacy Buffalo entry must use unified resources');
  assert.equal((await fetch('http://127.0.0.1:'+gateway+'/admin.js')).status,404);
  const account=JSON.parse(readFileSync(join(directory,'admin-bootstrap.json'),'utf8'));
  const login=await fetch('http://127.0.0.1:'+consolePort+'/api/admin/login',{method:'POST',headers:{'content-type':'application/json',origin:'http://127.0.0.1:'+consolePort},body:JSON.stringify({username:account.username,password:account.password})});
  assert.equal(login.status,200,await login.text());
  execFileSync(process.execPath,pipeline?[npm,'start','--','rtp-worker','--env-file',platformFile,'--once']:['dist/cli.js','rtp-worker','--env-file',platformFile,'--once'],{cwd:join(directory,'gateway'),env:isolatedTestEnvironment(process.env),stdio:'pipe',timeout:90000});
  assert.equal(existsSync(c.merchant_database),false,'Packaged PostgreSQL runtime must not create a SQLite control database');
  assert.equal(existsSync(c.game_database),false,'Packaged PostgreSQL runtime must not create a SQLite settlement database');
  assert((await client.query('SELECT COUNT(*) AS n FROM gtt_meta.schema_migrations')).rows[0].n>=2);
  unpack('game-fortune-rabbit');
  const gameKey=join(directory,'game.key'),gameEnv=join(directory,'game.env'),build=JSON.parse(readFileSync(join(release,'release.json'),'utf8')).build_id;
  writeFileSync(gameKey,'c'.repeat(64));writeFileSync(gameEnv,renderEnvironment({GAME_ID:'fortune-rabbit',GAME_RELEASE:build,GAME_CONFIG:join(directory,'game-fortune-rabbit/config/game.json').replaceAll('\\','/'),GAME_SECRET_FILE:gameKey.replaceAll('\\','/'),GAME_PORT:0,GAME_BIND:'127.0.0.1'}));
  const game=await start('game',gameEnv,'game-fortune-rabbit');
  const description=await fetch('http://127.0.0.1:'+game+'/v1/describe',{method:'POST',headers:{'content-type':'application/json',authorization:'Bearer '+'c'.repeat(64)},body:JSON.stringify({expected_release:build})});
  assert.equal(description.status,200);assert.equal((await description.json()).data.game_id,'fortune-rabbit');
  if(pipeline) {
    for(const {action,output}of logs) {
      const stages=['[1/3]','[2/3]','[3/3]'].map(label=>output.indexOf(label));
      assert(stages[0]>=0&&stages[1]>stages[0]&&stages[2]>stages[1],action+' startup order');
    }
    assert(existsSync(join(directory,'gateway/node_modules/pg/package.json')),'npm start must install missing dependencies');
    const gameRoot=join(directory,'game-fortune-rabbit'),pkgPath=join(gameRoot,'package.json'),original=readFileSync(pkgPath);
    const invalid=JSON.parse(original);invalid.dependencies={'bad package name':'1.0.0'};writeFileSync(pkgPath,JSON.stringify(invalid));
    try {
      assert.throws(()=>execFileSync(process.execPath,[npm,'start','--','--env-file',gameEnv],{cwd:gameRoot,env:isolatedTestEnvironment(process.env),stdio:'pipe',timeout:30000}),error=>{
        const output=String(error.stdout)+String(error.stderr);assert(output.includes('[1/3]'));assert(!output.includes('[2/3]'));return true;
      });
    } finally {writeFileSync(pkgPath,original);}
    await client.query('CREATE SCHEMA unmanaged_failure');
    const badConfig=join(directory,'bad-postgres.json');
    writeFileSync(badConfig,JSON.stringify({driver:'postgres',env_file:'platform.env',sources:[{path:c.merchant_database,schema:'unmanaged_failure',kind:'control'}]}));
    assert.throws(()=>execFileSync(process.execPath,[npm,'start','--','--env-file',platformFile],{cwd:join(directory,'gateway'),env:{...isolatedTestEnvironment(process.env),GTT_PG_CONFIG:badConfig},stdio:'pipe',timeout:30000}),error=>{
      const output=String(error.stdout)+String(error.stderr);assert(output.includes('[2/3]'));assert(output.includes('Refusing existing unmanaged namespace'));assert(!output.includes('[3/3]'));return true;
    });
  }
  writeFileSync(join(release,'postgres-verification.json'),JSON.stringify({database,verified_at:new Date().toISOString(),checks:['clean-unpack','packaged-pg-dependencies','versioned-migrations','shared-platform-env-only-credentials','gateway-health','admin-login','rtp-worker-shared-env','no-sqlite-business-databases','independent-game-release-env',...(pipeline?['independent-admin-artifact','unified-buffalo-resources','npm-start-ordered-pipeline','missing-dependencies-installed','install-failure-stops-migration','migration-failure-stops-server']:[])]},null,2));
  console.log('Packaged gateway/admin passed with one platform.env; standalone game passed with its own release env. No SQLite business databases created.');
} finally {
  for(const child of children)if(child.exitCode===null)await new Promise(ok=>{child.once('exit',ok);if(process.platform==='win32') {try{execFileSync('taskkill',['/PID',String(child.pid),'/T','/F'],{stdio:'pipe'});}catch{child.kill();}}else {try{process.kill(-child.pid,'SIGTERM');}catch{child.kill();}}});
  await client.end();rmSync(directory,{recursive:true,force:true});
}
