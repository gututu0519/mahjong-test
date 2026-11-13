import assert from 'node:assert/strict';
import {readFileSync,existsSync,readdirSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {readEnvironment,readPlatformConfig,readPostgresConfig,readGameEnvironment} from '../runtime/server/dist/shared/config/environment.js';
import {GAME_CODES} from '../runtime/server/dist/gateway/catalog.js';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..'),data=resolve(root,'gateway/instance/data');
const platform=resolve(root,'gateway/instance/platform.env');
assert(existsSync(platform));assert(!existsSync(resolve(root,'.env')));
const env=readEnvironment(platform,{}),node=readPlatformConfig(resolve(data,'node.json'),undefined,{}),pg=readPostgresConfig(resolve(data,'postgres.json'),{});
assert.equal(node.postgres_config,resolve(data,'postgres.json'));
const raw=JSON.parse(readFileSync(resolve(data,'postgres.json'),'utf8')),migration=JSON.parse(readFileSync(resolve(data,'postgres-migration.json'),'utf8'));
assert.equal(raw.connection,undefined);for(const key of ['host','port','user','password','database','connection'])assert.equal(migration[key],undefined);
assert.equal(JSON.parse(readFileSync(resolve(data,'node.json'),'utf8')).internal_secret,undefined);
const migrationAudit=process.argv.includes('--migration');
if(migrationAudit) {
  const backups=resolve(data,'configuration-backups'),latest=readdirSync(backups).filter(n=>n.startsWith('before-env-')).sort().at(-1);
  assert(latest);
  const old=JSON.parse(readFileSync(resolve(backups,latest,'postgres.json'),'utf8')).connection;
  for(const key of ['host','port','user','password','database'])assert.equal(pg.connection[key],old[key],key+' changed during configuration migration');
  const oldNode=JSON.parse(readFileSync(resolve(backups,latest,'node.json'),'utf8'));
  assert.equal(env.GTT_INTERNAL_SECRET,oldNode.internal_secret);
  for(const [role,port]of Object.entries(oldNode.ports??{}))assert.equal(node.ports[role],port);
}
const descriptors=JSON.parse(readFileSync(resolve(root,'gateway/config/game-descriptors.json'),'utf8'));
for(let i=0;i<GAME_CODES.length;i++) {
  const code=GAME_CODES[i],release=descriptors[code].ruleset_id.replace(/[^A-Za-z0-9._-]/g,'-');
  const game=readGameEnvironment(resolve(root,`games/${code}/instance/releases/${release}.env`),{});
  assert.equal(game.GAME_ID,code);assert.equal(game.GAME_RELEASE,release);
  if(migrationAudit)assert.equal(Number(game.GAME_PORT),(node.game_service_base_port??8211)+i);
  assert(existsSync(game.GAME_SECRET_FILE));assert(existsSync(game.GAME_CONFIG));
  assert(!Object.keys(game).some(k=>k.startsWith('PG')||k==='GTT_PG_CONFIG'||k==='GTT_PLATFORM_ENV_FILE'));
}
assert(existsSync(resolve(root,'other/deploy/instance/postgres.env')));
const report={checked_at:new Date().toISOString(),platform_env:'gateway/instance/platform.env',game_env_files:GAME_CODES.length,database_container_env:'other/deploy/instance/postgres.env',database_and_internal_secret_preserved:migrationAudit?true:'not-requested',active_json_credentials_removed:true,root_env:false};
mkdirSync(resolve(root,'other/diagnostics/environment'),{recursive:true});
writeFileSync(resolve(root,'other/diagnostics/environment/configuration-verification.json'),JSON.stringify(report,null,2));
console.log('Environment audit passed: 1 platform + 19 game instances + 1 database-container env; active JSON credential copies removed'+(migrationAudit?'; original credentials preserved':'')+'.');
