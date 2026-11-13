// Source-workspace npm start: install tooling, compile, migrate, then use the
// existing service entry. Deployment packages use tools/start-service.mjs.
import {existsSync,readFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {installDependencies,npmExecutable} from './scripts/install-dependencies.mjs';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const args=process.argv.slice(2),requested=args[0]&&!args[0].startsWith('-')?args.shift():'gateway';
for(let i=1;i<args.length;i++)if(['--config','--env-file','--database','--service-dir','--game-config','--secret-file'].includes(args[i-1]))args[i]=resolve(args[i]);
try {
  console.log('[1/3] 安装开发依赖并编译源码');
  await installDependencies(resolve(root,'other/tooling'),{development:true,npm:npmExecutable()});
  const {build,runtime}=await import('./build.mjs');await build();
  const {serviceContext}=await import('../runtime/server/tools/service-context.mjs');
  const {migrateService}=await import('../runtime/server/tools/migrate-service.mjs');
  let context;
  if(requested==='game') {
    const id=args[0]&&!args[0].startsWith('-')?args.shift():args[args.indexOf('--game-id')+1];
    const {GAME_CODES}=await import('../runtime/server/dist/gateway/catalog.js');
    if(!GAME_CODES.includes(id))throw Error('请指定已接入的游戏代码');
    const descriptor=JSON.parse(readFileSync(resolve(root,'gateway/config/game-descriptors.json'),'utf8'))[id];
    const release=descriptor.ruleset_id.replace(/[^A-Za-z0-9._-]/g,'-');
    const game={code:id,release,config:resolve(root,`games/${id}/instance/config/${id}.json`),secretFile:resolve(root,`gateway/instance/data/game-service-keys/${id}.key`),port:8211+GAME_CODES.indexOf(id),envFile:resolve(root,`games/${id}/instance/releases/${release}.env`)};
    context=serviceContext(runtime,{role:'game',action:'game',game},args);
  } else {
    const action=requested==='mock'?'platform':['gateway','admin','games','rtp-worker','platform'].includes(requested)?requested:'service';
    const env={...process.env},file=resolve(root,'gateway/instance/platform.env');
    if(!args.includes('--env-file')&&!args.includes('--config')&&!env.GTT_PLATFORM_ENV_FILE&&existsSync(file))env.GTT_PLATFORM_ENV_FILE=file;
    context=serviceContext(runtime,{role:'workspace',action},args,env);
  }
  console.log('[2/3] 执行版本化迁移');await migrateService(context);
  if(requested==='game')for(const key of Object.keys(process.env))delete process.env[key];
  Object.assign(process.env,context.environment);
  console.log('[3/3] 启动 '+requested);
  if(requested==='game') {const {main}=await import('../runtime/server/dist/cli.js');await main(context.args);}
  else {
    process.argv=[process.execPath,resolve(runtime,'tools/start.mjs'),requested,...context.args.slice(1)];
    await import(pathToFileURL(resolve(runtime,'tools/start.mjs')).href);
  }
} catch(error){console.error('启动流水线失败：'+error.message);process.exitCode=1;}
