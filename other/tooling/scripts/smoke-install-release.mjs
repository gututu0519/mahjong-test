import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,writeFileSync,existsSync,mkdirSync,rmSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {tmpdir} from 'node:os';
import {createRequire} from 'node:module';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {createServer} from 'node:net';
import {artifactPath,extractArchive} from './archive.mjs';
import {npmExecutable} from './install-dependencies.mjs';
import {isolatedTestEnvironment,renderEnvironment} from '../dist/shared/config/environment.js';

const release=resolve(process.argv[2]);
const record=JSON.parse(readFileSync(join(release,'release.json'),'utf8'));
const report=join(release,'install-verification.json');
assert.equal(existsSync(report),false);
const temp=mkdtempSync(join(tmpdir(),'gtt-cold-install-'));
process.env.PM2_HOME=join(temp,'pm2');
const configDir=join(temp,'config');mkdirSync(configDir);
// This listener deliberately rejects PostgreSQL handshakes. No real database
// credentials or business database are involved in migration-failure testing.
const rejectDatabase=createServer(socket=>socket.destroy());
await new Promise(ok=>rejectDatabase.listen(0,'127.0.0.1',ok));
const config=join(configDir,'production.json'),pg=join(configDir,'postgres.json'),envFile=join(configDir,'platform.env');
writeFileSync(config,JSON.stringify({environment:'development',game_services_mode:'remote',merchant_database:join(temp,'merchants.sqlite3'),game_database:join(temp,'game.sqlite3')}));
writeFileSync(pg,JSON.stringify({driver:'postgres',env_file:envFile,sources:[{path:join(temp,'merchants.sqlite3'),schema:'control',kind:'control'},{path:join(temp,'game.sqlite3'),schema:'game',kind:'game'}]}));
writeFileSync(envFile,renderEnvironment({NODE_ENV:'development',GTT_CONFIG_FILE:config.replaceAll('\\','/'),GTT_PG_CONFIG:pg.replaceAll('\\','/'),PGHOST:'127.0.0.1',PGPORT:rejectDatabase.address().port,PGUSER:'isolated',PGDATABASE:'isolated',PGPASSWORD:'not-a-real-password',PGSSLMODE:'disable'}));
const environment={...isolatedTestEnvironment(process.env),PM2_HOME:process.env.PM2_HOME,npm_config_cache:join(temp,'npm-cache')};
let pm2;
const checked=[];
try {
  for(const name of ['gateway','admin','mock-platform']) {
    const artifact=record.artifacts.find(item=>item.name===name);
    extractArchive(artifactPath(release,record,artifact),temp);
    const root=join(temp,name),service=JSON.parse(readFileSync(join(root,'SERVICE.json'),'utf8'));
    assert.equal(service.dependencies_bundled,false);
    assert.equal(existsSync(join(root,'node_modules')),false);
    let result;
    try {await promisify(execFile)(process.execPath,[npmExecutable(),'start'],{cwd:root,env:environment,timeout:180000,windowsHide:true,maxBuffer:1024*1024});assert.fail('Migration failure must reject startup');}
    catch(error){result=error;}
    assert.match(result.stderr??'',/后台启动失败/);
    assert.doesNotMatch(result.stdout??'',/后台启动成功/);
    for(const dependency of ['pm2','pg'])assert.ok(existsSync(join(root,'node_modules',dependency,'package.json')));
    pm2??=createRequire(join(root,'package.json'))('pm2');
    await new Promise((ok,fail)=>pm2.connect(error=>error?fail(error):ok()));
    const processes=await new Promise((ok,fail)=>pm2.list((error,list)=>error?fail(error):ok(list)));
    const instance=processes.find(item=>item.name===name);
    assert.equal(instance?.pm2_env.status,'stopped');
    const log=readFileSync(instance.pm2_env.pm_out_log_path,'utf8');
    assert.match(log,/\[2\/3\]/);
    assert.doesNotMatch(log,/\[3\/3\]/);
    checked.push(name);
  }
  writeFileSync(report,JSON.stringify({build_id:record.build_id,node:process.version,verified_at:new Date().toISOString(),packages:checked,checks:['no-delivered-node-modules','npm-start-installs-pm2-and-pg','sibling-config-discovery','migration-failure-stops-before-service-start'],scope:'Negative migration test against an isolated rejecting TCP listener; not successful PostgreSQL migration verification.'},null,2)+'\n',{flag:'wx'});
} finally {
  if(pm2)try {
    await new Promise((ok,fail)=>pm2.delete('all',error=>error?fail(error):ok()));
    await new Promise((ok,fail)=>pm2.Client.killDaemon(error=>error?fail(error):ok()));
  } finally {pm2.disconnect();}
  await new Promise(ok=>rejectDatabase.close(ok));
  rmSync(temp,{recursive:true,force:true});
}
console.log('Cold install and migration failure verification passed: '+checked.join(', '));
process.exit(0);
