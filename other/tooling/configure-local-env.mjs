// One-time configuration migration. No SQL, password rotation or data migration.
import {readFileSync,writeFileSync,mkdirSync,existsSync,copyFileSync,renameSync} from 'node:fs';
import {resolve,dirname,relative} from 'node:path';
import {build,repo} from './build.mjs';
await build();
const {renderEnvironment,readPostgresConfig}=await import('../runtime/server/dist/shared/config/environment.js');
const {GAME_CODES}=await import('../runtime/server/dist/gateway/catalog.js');
const data=resolve(repo,'gateway/instance/data'), envFile=resolve(repo,'gateway/instance/platform.env');
if(existsSync(envFile))throw Error('platform.env already exists; existing configuration will not be overwritten.');
const names=['node.json','postgres.json','postgres-migration.json'];
const raw=Object.fromEntries(names.map(name=>[name,readFileSync(resolve(data,name),'utf8')]));
const node=JSON.parse(raw['node.json']), pg=JSON.parse(raw['postgres.json']), migration=JSON.parse(raw['postgres-migration.json']);
const connection=readPostgresConfig(resolve(data,'postgres.json'),{}).connection;
if(connection.ssl)throw Error('Configure PGSSLMODE and PGSSLROOTCERT explicitly before migrating this TLS connection.');
const values={NODE_ENV:node.environment??'development',GTT_CONFIG_FILE:'data/node.json',GTT_PG_CONFIG:'data/postgres.json',PGHOST:connection.host,PGPORT:connection.port,PGDATABASE:connection.database,PGUSER:connection.user,PGPASSWORD:connection.password??'',PGSSLMODE:'disable'};
const fields={internal_secret:'GTT_INTERNAL_SECRET',game_services_mode:'GAME_SERVICES_MODE',gateway_origin:'GATEWAY_ORIGIN',game_origin:'GAME_ORIGIN',game_service_base_port:'GAME_SERVICE_BASE_PORT',frontend_origin_template:'GTT_FRONTEND_ORIGIN_TEMPLATE'};
const basePort=node.game_service_base_port??8211;
for(const [field,key]of Object.entries(fields))if(node[field]!==undefined){values[key]=node[field];delete node[field];}
delete node.environment;
for(const [role,key]of Object.entries({gateway:'GATEWAY_PORT',admin:'ADMIN_PORT',platform:'MOCK_PORT',buffalo:'BUFFALO_PORT'}))if(node.ports?.[role]!==undefined){values[key]=node.ports[role];delete node.ports[role];}
if(node.ports&&!Object.keys(node.ports).length)delete node.ports;
for(const role of ['site','api','play','admin','merchant'])if(node.public_origins?.[role]!==undefined){values['GTT_'+role.toUpperCase()+'_ORIGIN']=node.public_origins[role];delete node.public_origins[role];}
if(node.public_origins&&!Object.keys(node.public_origins).length)delete node.public_origins;
node.env_file='../platform.env';pg.env_file='../platform.env';delete pg.connection;
for(const key of ['host','port','user','password','database','ssl','connection'])delete migration[key];
migration.env_file='../platform.env';
const plans=[{path:envFile,text:'# 本机平台配置：网关、管理后台、RTP worker 和数据库工具共用。\n'+renderEnvironment(values)}];
const descriptors=JSON.parse(readFileSync(resolve(repo,'gateway/config/game-descriptors.json'),'utf8'));
for(let i=0;i<GAME_CODES.length;i++) {
  const code=GAME_CODES[i], release=descriptors[code].ruleset_id.replace(/[^A-Za-z0-9._-]/g,'-');
  const target=resolve(repo,`games/${code}/instance/releases/${release}.env`);
  const config=resolve(repo,`games/${code}/instance/config/${code}.json`), key=resolve(dirname(node.merchant_database),'game-service-keys',code+'.key');
  plans.push({path:target,text:renderEnvironment({GAME_ID:code,GAME_RELEASE:release,GAME_CONFIG:relative(dirname(target),config).replaceAll('\\','/'),GAME_BIND:'127.0.0.1',GAME_PORT:basePort+i,GAME_SECRET_FILE:relative(dirname(target),key).replaceAll('\\','/')})});
}
const infra=resolve(repo,'other/deploy/instance/postgres.env');
const originalInfra=migration.container_env_file??resolve(data,'postgres-container-'+migration.container.replace(/^gtt-postgres-/,'')+'.env');
if(existsSync(originalInfra)){plans.push({path:infra,text:readFileSync(originalInfra,'utf8')});migration.container_env_file=infra;}
for(const plan of plans)if(existsSync(plan.path))throw Error('Configuration already exists: '+relative(repo,plan.path));
if(!process.argv.includes('--apply')) {
  console.log(`Ready: 1 platform env, ${GAME_CODES.length} game instance envs, ${existsSync(originalInfra)?1:0} database container env. Run with --apply to migrate configuration only.`);
} else {
  const backup=resolve(data,'configuration-backups','before-env-'+Date.now());mkdirSync(backup,{recursive:true});
  for(const name of names)copyFileSync(resolve(data,name),resolve(backup,name));
  for(const plan of plans){mkdirSync(dirname(plan.path),{recursive:true});writeFileSync(plan.path,plan.text,{flag:'wx',mode:0o600});}
  for(const [name,value]of Object.entries({'node.json':node,'postgres.json':pg,'postgres-migration.json':migration})) {
    const next=resolve(data,name+'.env-next');writeFileSync(next,JSON.stringify(value,null,2)+'\n',{flag:'wx',mode:0o600});renameSync(next,resolve(data,name));
  }
  const trial=resolve(data,'postgres-trial.json');
  if(existsSync(trial)){copyFileSync(trial,resolve(backup,'postgres-trial.json'));const c=JSON.parse(readFileSync(trial,'utf8'));c.isolated=true;writeFileSync(trial,JSON.stringify(c,null,2)+'\n',{mode:0o600});}
  console.log(`Configured gateway/instance/platform.env and ${GAME_CODES.length} isolated game env files. Database unchanged. Previous private JSON configuration backed up in ${relative(repo,backup)}.`);
}
