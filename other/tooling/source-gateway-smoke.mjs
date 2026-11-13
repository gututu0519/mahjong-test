import pg from 'pg';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,rmSync,mkdirSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {resolve,join} from 'node:path';
import {spawn,execFileSync} from 'node:child_process';
import {root} from './database/inventory.mjs';
import {databaseSettings} from './database/settings.mjs';
import {npmExecutable} from './scripts/install-dependencies.mjs';
import {renderEnvironment,isolatedTestEnvironment} from '../runtime/server/dist/shared/config/environment.js';
const settings=databaseSettings(),database='gtt_source_start_'+Date.now();
const admin=new pg.Client({...settings.connection,database:'postgres'});await admin.connect();await admin.query('CREATE DATABASE "'+database+'" TEMPLATE template0');await admin.end();
const dir=mkdtempSync(join(tmpdir(),'gtt-source-gateway-')),file=join(dir,'platform.env');
writeFileSync(file,renderEnvironment({NODE_ENV:'development',GTT_CONFIG_FILE:'node.json',GTT_PG_CONFIG:'postgres.json',PGHOST:settings.host,PGPORT:settings.port,PGUSER:settings.user,PGPASSWORD:settings.password,PGDATABASE:database,GTT_INTERNAL_SECRET:'q'.repeat(64),GATEWAY_PORT:0}));
const control=join(dir,'control.sqlite3'),game=join(dir,'game.sqlite3');
writeFileSync(join(dir,'postgres.json'),JSON.stringify({env_file:'platform.env',sources:[{path:control,schema:'source_control',kind:'control'},{path:game,schema:'source_game',kind:'game'}]}));
writeFileSync(join(dir,'node.json'),JSON.stringify({environment:'development',merchant_database:control,game_database:game,game_services_mode:'remote',client_root:resolve(root,'other/runtime/server/clients/buffalo-win'),gateway_origin:'http://127.0.0.1:0'}));
const child=spawn(process.execPath,[npmExecutable(),'start','--','--env-file',file],{cwd:resolve(root,'gateway'),env:isolatedTestEnvironment(process.env),detached:process.platform!=='win32',stdio:['ignore','pipe','pipe']});
let output='';
try {
  const port=await new Promise((ok,fail)=>{
    const timer=setTimeout(()=>fail(Error('Source gateway startup timeout: '+output)),120000);
    child.on('error',fail);child.on('exit',code=>{clearTimeout(timer);fail(Error('Exited '+code+': '+output));});
    child.stderr.on('data',b=>output+=b);child.stdout.on('data',b=>{output+=b;const m=/listening on 127\.0\.0\.1:(\d+)/.exec(output);if(m){clearTimeout(timer);ok(Number(m[1]));}});
  });
  const positions=['[1/3]','[2/3]','[3/3]'].map(s=>output.indexOf(s));assert(positions[0]>=0&&positions[1]>positions[0]&&positions[2]>positions[1]);
  assert.equal((await fetch('http://127.0.0.1:'+port+'/health')).status,200);assert.equal((await fetch('http://127.0.0.1:'+port+'/')).status,200);
  const client=new pg.Client({...settings.connection,database});await client.connect();
  try {assert.equal(Number((await client.query('SELECT COUNT(*) AS n FROM gtt_meta.schema_migrations')).rows[0].n),2);}finally{await client.end();}
  mkdirSync(resolve(root,'other/diagnostics/startup'),{recursive:true});writeFileSync(resolve(root,'other/diagnostics/startup/source-gateway-start.log'),output);
  console.log('Source gateway npm start passed with a new isolated PostgreSQL database and unified Buffalo entry.');
} finally {
  if(child.exitCode===null)await new Promise(ok=>{child.once('exit',ok);if(process.platform==='win32'){try{execFileSync('taskkill',['/PID',String(child.pid),'/T','/F'],{stdio:'pipe'});}catch{child.kill();}}else{try{process.kill(-child.pid,'SIGTERM');}catch{child.kill();}}});
  rmSync(dir,{recursive:true,force:true});
}
