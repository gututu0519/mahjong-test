import {mkdirSync,writeFileSync,existsSync} from 'node:fs';
import {resolve,dirname,posix,win32} from 'node:path';
import {GAME_CODES} from '../dist/gateway/catalog.js';
import {integer,renderEnvironment} from '../dist/shared/config/environment.js';
const args=process.argv.slice(2);
const option=(name,fallback)=>args.includes(name)?args[args.indexOf(name)+1]:fallback;
const release=option('--release',''), output=option('--output','');
if(!/^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$/.test(release)||!output)throw Error('Supply --release <build-id> and --output <new directory>');
const games=args.includes('--all')?GAME_CODES:[option('--game','')];
if(games.some(game=>!GAME_CODES.includes(game)))throw Error('Supply --all or a supported --game');
const base=integer(option('--base-port','8211'),'--base-port',1,65517);
const host=option('--host','127.0.0.1');
if(!host.trim()||/[\r\n]/.test(host))throw Error('Invalid --host');
const plans=games.map((code,i)=>{
  const port=args.includes('--all')?base+i:integer(option('--port',String(base+GAME_CODES.indexOf(code))),'--port',1);
  const values={GAME_ID:code,GAME_RELEASE:release,GAME_CONFIG:option('--game-config',posix.join(option('--install-root','/opt/gtt-node/games'),code,release,'config/game.json')),GAME_BIND:host,GAME_PORT:port,GAME_SECRET_FILE:option('--secret-file',posix.join(option('--secret-root','/etc/gtt-node/secrets'),code+'.key'))};
  for(const key of ['GAME_CONFIG','GAME_SECRET_FILE']) {
    values[key]=values[key].replaceAll('\\','/');
    if(!posix.isAbsolute(values[key])&&!win32.isAbsolute(values[key]))throw Error(key+' must be an absolute deployment target path');
  }
  return {path:resolve(output,code,release+'.env'),text:renderEnvironment(values)};
});
for(const plan of plans)if(existsSync(plan.path))throw Error('Instance configuration already exists: '+plan.path);
for(const plan of plans){mkdirSync(dirname(plan.path),{recursive:true});writeFileSync(plan.path,plan.text,{flag:'wx',mode:0o600});}
console.log(`Generated ${plans.length} game release env files in ${resolve(output)}; no platform credentials included.`);
