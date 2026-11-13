import {readFileSync,existsSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {platformEnvironment,readPlatformConfig,readGameEnvironment,gameProcessEnvironment,integer} from '../dist/shared/config/environment.js';

export function serviceContext(root, service, supplied=[], environment=process.env) {
  const args=[...supplied];
  const action=args[0]&&!args[0].startsWith('-')?args.shift():service.action;
  if(!(service.start_actions??[service.action]).includes(action))throw Error(`此包不能启动 ${action}，请使用相应的独立服务包`);
  const option=(name,fallback)=>{const i=args.indexOf(name);if(i<0)return fallback;if(!args[i+1]||args[i+1].startsWith('--'))throw Error('缺少参数 '+name);return args[i+1];};
  let envFile=option('--env-file',undefined);
  if(service.role==='game') {
    const game=service.game??JSON.parse(readFileSync(resolve(root,'GAME.json'),'utf8'));
    envFile=envFile??environment.GAME_ENV_FILE;
    if(!envFile)envFile=[...(game.envFile?[game.envFile]:[]),resolve(root,'game.env'),`/etc/gtt-node/games/${game.code}/${game.release}.env`].find(p=>existsSync(p));
    const overrides={};
    for(const [flag,key]of Object.entries({'--game-id':'GAME_ID','--release':'GAME_RELEASE','--game-config':'GAME_CONFIG','--secret-file':'GAME_SECRET_FILE','--host':'GAME_BIND','--port':'GAME_PORT','--client-contract':'GAME_CLIENT_CONTRACT','--state-contract':'GAME_STATE_CONTRACT'})) {
      const value=option(flag,undefined);if(value!==undefined)overrides[key]=value;
    }
    const env=readGameEnvironment(envFile,{...environment,...overrides});
    env.GAME_ID??=game.code;env.GAME_RELEASE??=game.release;env.GAME_CONFIG??=game.config??resolve(root,'config/game.json');env.GAME_BIND??='127.0.0.1';env.GAME_PORT??=String(game.port??8214);env.GAME_SECRET_FILE??=game.secretFile;
    if(env.GAME_ID!==game.code)throw Error('游戏 env 与交付包身份不一致');
    integer(env.GAME_PORT,'GAME_PORT');
    if(!env.GAME_SECRET_FILE)throw Error('请配置 GAME_SECRET_FILE 或传入 --secret-file');
    if(readFileSync(env.GAME_SECRET_FILE,'utf8').trim().length<32)throw Error('游戏认证密钥至少需要 32 个字符');
    JSON.parse(readFileSync(env.GAME_CONFIG,'utf8'));
    return {role:service.role,action,args:[action,...args,...(envFile&&!args.includes('--env-file')?['--env-file',resolve(envFile)]:[])],environment:gameProcessEnvironment(env)};
  }
  if(!envFile&&!args.includes('--config'))envFile=environment.GTT_PLATFORM_ENV_FILE??[resolve(root,'platform.env'),'/etc/gtt-node/platform.env'].find(p=>existsSync(p));
  const env=platformEnvironment(envFile,environment);
  const configFile=resolve(option('--config',env.GTT_CONFIG_FILE??resolve(root,'config/production.json')));
  if(!existsSync(configFile))throw Error('缺少平台配置，请配置 GTT_CONFIG_FILE 或传入 --env-file / --config');
  const config=readPlatformConfig(configFile,envFile,env);
  const selected=config.env_file??env.GTT_PLATFORM_ENV_FILE;
  const pg=config.postgres_config??env.GTT_PG_CONFIG;
  if(!pg)throw Error('npm start 需要 PostgreSQL 配置 GTT_PG_CONFIG；不会自动创建 SQLite 业务库');
  return {role:service.role,action,config,configFile,
    args:[action,...args,...(!args.includes('--config')?['--config',configFile]:[]),...(selected&&!args.includes('--env-file')?['--env-file',selected]:[])],
    environment:{...environment,GTT_PG_CONFIG:resolve(dirname(configFile),pg),...(selected?{GTT_PLATFORM_ENV_FILE:selected}:{})}};
}
