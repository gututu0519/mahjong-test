import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {check} from '../../other/shared/core.js';
import {Control} from '../../other/shared/control.js';
import {listen} from '../../other/shared/http.js';
import {accessLog} from '../../other/shared/logging.js';
import {platformEnvironment,readPlatformConfig} from '../../other/shared/config/environment.js';
import {runtimeData} from '../../other/shared/config/runtime-data.js';
import {Provider} from '../../gateway/src/provider.js';
import {GameClient} from '../../gateway/src/game-client.js';
import {adminServer} from './admin.js';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
export async function main(args=process.argv.slice(2)) {
  if(process.channel)process.once('disconnect',()=>process.emit('SIGTERM'));
  const action=args[0];
  check(['admin','admin-init'].includes(action),'SERVICE_PACKAGE_MISMATCH','此包仅提供后台服务及管理员初始化');
  const option=(name:string,fallback?:string)=>{const i=args.indexOf(name);if(i<0)return fallback;check(!!args[i+1]&&!args[i+1].startsWith('--'),'CONFIG_INVALID');return args[i+1];};
  const envFile=option('--env-file');
  const env=platformEnvironment(envFile);
  if(env.GTT_PLATFORM_ENV_FILE)process.env.GTT_PLATFORM_ENV_FILE=env.GTT_PLATFORM_ENV_FILE;
  const path=resolve(option('--config',env.GTT_CONFIG_FILE)??runtimeData('production.json'));
  const config=readPlatformConfig(path,envFile);
  if(config.postgres_config)process.env.GTT_PG_CONFIG=resolve(dirname(path),config.postgres_config);
  const control=new Control(config.merchant_database,runtimeData('control.sql'));
  if(action==='admin-init') {
    try {
      check(!control.users().length,'ADMIN_EXISTS');
      const target=resolve(dirname(path),'admin-bootstrap.json');check(!existsSync(target),'BOOTSTRAP_EXISTS');
      const result=control.createUser('system',option('--username','admin')!,'admin');
      writeFileSync(target,JSON.stringify({username:result.user.username,password:result.temporary_password,url:config.public_origins?.admin??`http://127.0.0.1:${config.ports?.admin??8112}/`},null,2),{flag:'wx',mode:0o600});
      console.log('Administrator credentials file:',target);
    } finally {control.close();}
    return;
  }
  const c={...config,game_services_mode:config.game_services_mode??'remote'};
  const game=new GameClient(c.game_origin??'http://127.0.0.1:1',c.internal_secret??'',JSON.parse(readFileSync(c.game_config??runtimeData('buffalo-win.json'),'utf8')));
  const provider=new Provider(c.game_database,control,game,runtimeData('game.sql'),c.public_origins?.play??c.gateway_origin,runtimeData('rtp-models.json'));
  try {
    provider.enableGames(c);await provider.initialize();
    const server=adminServer(provider,c,resolve(root,'frontend/admin'),dirname(runtimeData('integration.json')));
    accessLog(server,resolve(c.log_directories?.admin??c.log_directory??resolve(dirname(path),'logs/admin'),'service.log'));
    const host=c.hosts?.admin??'127.0.0.1';
    const port=await listen(server,c.ports?.admin??8112,host);
    console.log(`admin Node service listening on ${host}:${port}`);
    let closing=false;
    const stop=()=>{if(closing)return;closing=true;server.close(()=>{provider.close();control.close();});};
    process.on('SIGTERM',stop);process.on('SIGINT',stop);
  } catch(error) {provider.close();control.close();throw error;}
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))main().catch(error=>{console.error(error.code??error.name,error.message);process.exitCode=1;});
