import { readFileSync, realpathSync } from 'node:fs';
import { dirname, isAbsolute, resolve } from 'node:path';
import { parseEnv } from 'node:util';

export type Environment = Record<string, string | undefined>;
const pathKeys = new Set(['GTT_CONFIG_FILE','GTT_PG_CONFIG','GTT_PLATFORM_ENV_FILE','GTT_CLIENT_ROOT','GTT_PROTOCOL_DIRECTORY','GTT_FRONTEND_RELEASES_DIRECTORY','GTT_LOG_DIRECTORY','PGSSLROOTCERT','GAME_CONFIG','GAME_SECRET_FILE']);
const fail = (key: string): never => { throw Object.assign(new Error(`Invalid configuration: ${key}`), {code:'ENV_CONFIG_INVALID'}); };
export function integer(value: string, key: string, min = 0, max = 65535) {
  if(!/^\d+$/.test(value)) return fail(key);
  const n=Number(value); if(!Number.isSafeInteger(n)||n<min||n>max)return fail(key); return n;
}
/** Process variables override file values. Only file-origin paths are relative
 * to the env file, independent of the caller's working directory. No interpolation.
 */
export function readEnvironment(file?: string, environment: Environment = process.env): Environment {
  const values: Environment = file ? parseEnv(readFileSync(resolve(file),'utf8')) : {};
  if(file)for(const key of pathKeys)if(values[key]&&!isAbsolute(values[key]!))values[key]=resolve(dirname(realpathSync(file)),values[key]!);
  return {...values,...Object.fromEntries(Object.entries(environment).filter(([,value])=>value!==undefined))};
}
export function platformEnvironment(file = process.env.GTT_PLATFORM_ENV_FILE, environment: Environment = process.env) {
  const env=readEnvironment(file,environment);
  if(file)env.GTT_PLATFORM_ENV_FILE=resolve(file);
  return env;
}
export function applyPlatformEnvironment(base: any, env: Environment) {
  const config={...base,ports:{...base.ports},hosts:{...base.hosts},public_origins:{...base.public_origins}};
  const mode=env.GTT_ENVIRONMENT??(['development','production'].includes(env.NODE_ENV??'')?env.NODE_ENV:undefined);
  if(mode!==undefined){if(!['development','production'].includes(mode))fail('GTT_ENVIRONMENT');config.environment=mode;}
  const fields: Record<string,string>={GTT_PG_CONFIG:'postgres_config',GTT_INTERNAL_SECRET:'internal_secret',GAME_SERVICES_MODE:'game_services_mode',GATEWAY_ORIGIN:'gateway_origin',GAME_ORIGIN:'game_origin',GTT_CLIENT_ROOT:'client_root',GTT_PROTOCOL_DIRECTORY:'protocol_directory',GTT_FRONTEND_RELEASES_DIRECTORY:'frontend_releases_directory',GTT_FRONTEND_ORIGIN_TEMPLATE:'frontend_origin_template',GTT_LOG_DIRECTORY:'log_directory'};
  for(const [key,field] of Object.entries(fields))if(env[key]!==undefined)config[field]=env[key];
  if(config.game_services_mode&&!['remote','embedded'].includes(config.game_services_mode))fail('GAME_SERVICES_MODE');
  for(const [key,role] of Object.entries({GATEWAY_PORT:'gateway',ADMIN_PORT:'admin',MOCK_PORT:'platform',BUFFALO_PORT:'buffalo'}))if(env[key]!==undefined)config.ports[role]=integer(env[key]!,key);
  for(const [key,role] of Object.entries({GATEWAY_HOST:'gateway',ADMIN_HOST:'admin',MOCK_HOST:'platform'}))if(env[key]!==undefined){if(!env[key]?.trim())fail(key);config.hosts[role]=env[key];}
  for(const role of ['site','api','play','admin','merchant']) {
    const key='GTT_'+role.toUpperCase()+'_ORIGIN'; if(env[key]!==undefined)config.public_origins[role]=env[key];
  }
  if(env.GTT_API_ORIGIN!==undefined&&env.GATEWAY_ORIGIN===undefined)config.gateway_origin=env.GTT_API_ORIGIN;
  if(!Object.keys(config.public_origins).length)delete config.public_origins;
  if(env.GAME_SERVICE_BASE_PORT!==undefined)config.game_service_base_port=integer(env.GAME_SERVICE_BASE_PORT,'GAME_SERVICE_BASE_PORT',1,65517);
  if(env.GTT_PLATFORM_ENV_FILE)config.env_file=env.GTT_PLATFORM_ENV_FILE;
  return config;
}
export function readPlatformConfig(file: string, envFile?: string, environment: Environment=process.env) {
  const base=JSON.parse(readFileSync(file,'utf8'));
  const selected=envFile??environment.GTT_PLATFORM_ENV_FILE??(base.env_file?resolve(dirname(file),base.env_file):undefined);
  return applyPlatformEnvironment(base,platformEnvironment(selected,environment));
}
export function postgresConnection(env: Environment, fallback: any = {}) {
  const connection:any={...fallback};
  for(const [key,field] of Object.entries({PGHOST:'host',PGDATABASE:'database',PGUSER:'user',PGPASSWORD:'password'}))if(env[key]!==undefined)connection[field]=env[key];
  if(env.PGPORT!==undefined)connection.port=integer(env.PGPORT,'PGPORT',1);
  if(env.PGSSLMODE!==undefined) {
    if(env.PGSSLMODE==='disable')connection.ssl=false;
    else if(['require','verify-full'].includes(env.PGSSLMODE))connection.ssl={rejectUnauthorized:env.PGSSLMODE==='verify-full',...(env.PGSSLROOTCERT?{ca:readFileSync(env.PGSSLROOTCERT,'utf8')}:{})};
    else fail('PGSSLMODE');
  }
  for(const name of ['host','database','user'])if(typeof connection[name]!=='string'||!connection[name])fail('PG'+(name==='database'?'DATABASE':name==='user'?'USER':'HOST'));
  connection.port=integer(String(connection.port??5432),'PGPORT',1);
  return connection;
}
export function readPostgresConfig(file: string, environment: Environment=process.env) {
  const config=JSON.parse(readFileSync(file,'utf8'));
  // Test/rehearsal connection targets are explicit and never replaced by a live
  // platform PGDATABASE inherited from the invoking shell.
  if(config.testMode||config.isolated)return {...config,connection:postgresConnection({},config.connection)};
  const selected=environment.GTT_PLATFORM_ENV_FILE??(config.env_file?resolve(dirname(file),config.env_file):undefined);
  const legacy=config.connection??Object.fromEntries(['host','port','database','user','password','ssl'].filter(k=>config[k]!==undefined).map(k=>[k,config[k]]));
  return {...config,...(selected?{env_file:resolve(selected)}:{}),connection:postgresConnection(readEnvironment(selected,environment),legacy)};
}
const gameKeys=new Set(['GAME_ID','GAME_RELEASE','GAME_CONFIG','GAME_BIND','GAME_PORT','GAME_SECRET_FILE','GAME_CLIENT_CONTRACT','GAME_STATE_CONTRACT','GTT_RESOURCE_ROOT','NODE_ENV']);
const systemKeys=new Set(['PATH','SYSTEMROOT','WINDIR','TEMP','TMP','TMPDIR','HOME','USERPROFILE','LANG','LC_ALL','TZ','PATHEXT','COMSPEC']);
export function gameProcessEnvironment(environment: Environment=process.env): Environment {
  return Object.fromEntries(Object.entries(environment).filter(([key,value])=>value!==undefined&&(gameKeys.has(key)||systemKeys.has(key.toUpperCase()))));
}
export function isolatedTestEnvironment(environment: Environment=process.env): Environment {
  return {...Object.fromEntries(Object.entries(environment).filter(([key])=>!/^PG|^GTT_|^(GATEWAY|ADMIN|MOCK|BUFFALO)_|^GAME_/.test(key))),NODE_ENV:'test'};
}
export function readGameEnvironment(file?: string, environment: Environment=process.env) {
  if(file)for(const key of Object.keys(parseEnv(readFileSync(file,'utf8'))))if(!gameKeys.has(key))fail('game env key '+key);
  const env=readEnvironment(file,gameProcessEnvironment(environment));
  if(env.GAME_PORT!==undefined)integer(env.GAME_PORT,'GAME_PORT');
  if(env.GAME_ID&&!/^[a-z0-9][a-z0-9-]*$/.test(env.GAME_ID))fail('GAME_ID');
  if(env.GAME_RELEASE&&!/^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$/.test(env.GAME_RELEASE))fail('GAME_RELEASE');
  return env;
}
export const environmentDescriptions: Record<string,string> = {
  NODE_ENV:'运行环境：development 为开发环境，production 为生产环境。',
  GTT_ENVIRONMENT:'平台运行环境；设置后优先于 NODE_ENV。',
  GTT_CONFIG_FILE:'平台结构配置文件路径；文件内相对路径以 env 实际所在目录为基准。',
  GTT_PG_CONFIG:'PostgreSQL 存储路由配置路径，数据库连接凭据由平台 env 统一提供。',
  GTT_PLATFORM_ENV_FILE:'指定平台环境配置文件的位置。',
  PGHOST:'PostgreSQL 主机地址。',
  PGPORT:'PostgreSQL 连接端口。',
  PGDATABASE:'目标数据库名称。',
  PGUSER:'数据库连接账号。',
  PGPASSWORD:'数据库连接密码；真实配置不得提交或进入发布包。',
  PGSSLMODE:'TLS 模式：disable 不启用，require 仅加密，verify-full 校验证书及主机名。',
  PGSSLROOTCERT:'用于验证 PostgreSQL 服务端证书的 CA 文件路径。',
  GTT_INTERNAL_SECRET:'平台内部认证密钥，不是商户密钥；需至少 32 个字符。',
  GATEWAY_HOST:'网关监听地址。', GATEWAY_PORT:'网关监听端口。',
  ADMIN_HOST:'管理后台监听地址。', ADMIN_PORT:'管理后台监听端口，平台与商户后台共用此服务。',
  MOCK_HOST:'本机模拟商户钱包的监听地址。', MOCK_PORT:'本机模拟商户钱包的监听端口。',
  BUFFALO_PORT:'历史美洲野牛兼容计算服务端口。',
  GATEWAY_ORIGIN:'网关对外访问地址。', GAME_ORIGIN:'历史内嵌计算服务地址，供兼容入口使用。',
  GAME_SERVICES_MODE:'游戏计算模式：remote 使用独立服务，embedded 为历史内嵌兼容模式。',
  GAME_SERVICE_BASE_PORT:'本机开发启动器的默认起始端口；已有实例配置中的端口优先。',
  GTT_SITE_ORIGIN:'官网公开地址。', GTT_API_ORIGIN:'API 公开地址。', GTT_PLAY_ORIGIN:'游戏启动公开地址。',
  GTT_ADMIN_ORIGIN:'平台管理后台公开地址。', GTT_MERCHANT_ORIGIN:'商户工作台公开地址。',
  GTT_FRONTEND_ORIGIN_TEMPLATE:'客户端版本域名模板；{release} 和 {game_id} 由运行时替换。',
  GTT_CLIENT_ROOT:'后端所需游戏启动资料的根目录。',
  GTT_PROTOCOL_DIRECTORY:'原客户端协议镜像的存储路由目录。',
  GTT_FRONTEND_RELEASES_DIRECTORY:'已安装客户端版本的私有启动资料目录。',
  GTT_LOG_DIRECTORY:'平台服务日志目录。',
  GAME_ID:'游戏代码，必须与运行的游戏包一致。',
  GAME_RELEASE:'本实例的发布版本；新旧版本并行时分别使用各自的 env 文件。',
  GAME_CONFIG:'本实例使用的游戏规则配置文件路径。',
  GAME_BIND:'计算服务监听地址，通常为回环或私网地址。',
  GAME_PORT:'计算服务端口；同机并行的版本实例必须使用不同端口。',
  GAME_SECRET_FILE:'本游戏内部认证密钥文件路径，密钥内容不直接写入 env。',
  GAME_CLIENT_CONTRACT:'客户端协议兼容契约；通常保留程序默认值。',
  GAME_STATE_CONTRACT:'游戏状态兼容契约；通常保留程序默认值。',
  GTT_RESOURCE_ROOT:'本实例的运行资源根目录，不包含平台数据库凭据。',
  POSTGRES_USER:'数据库容器首次初始化时创建的账号。',
  POSTGRES_PASSWORD:'数据库容器初始化密码；修改此项不会更改已初始化数据库的密码。',
  POSTGRES_DB:'数据库容器首次初始化时创建的数据库名称。',
};
export function renderEnvironment(values: Record<string,string|number>) {
  const result=Object.entries(values).map(([key,value])=>{
    if(!/^[A-Z][A-Z0-9_]*$/.test(key)||/[\r\n]/.test(String(value)))fail(key);
    return (environmentDescriptions[key]?'# '+environmentDescriptions[key]+'\n':'')+key+'='+JSON.stringify(String(value));
  }).join('\n')+'\n';
  const roundtrip=parseEnv(result);
  for(const [key,value] of Object.entries(values))if(roundtrip[key]!==String(value))fail(key);
  return result;
}
