import {readFileSync,existsSync,mkdirSync,writeFileSync,openSync,closeSync,unlinkSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {homedir} from 'node:os';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import {randomUUID} from 'node:crypto';
import {installDependencies,installationEnvironment} from './install-dependencies.mjs';
import {serviceContext} from './service-context.mjs';
import {gameProcessEnvironment,readPostgresConfig} from '../dist/shared/config/environment.js';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const service=JSON.parse(readFileSync(resolve(root,'SERVICE.json'),'utf8'));
const sleep=ms=>new Promise(ok=>setTimeout(ok,ms));
let pm2,lock,lockFile,createdName;
try {
  const [major,minor]=process.versions.node.split('.').map(Number);
  if(major<24||(major===24&&minor<17))throw Error('需要 Node.js 24.17.0 或更新版本');
  const args=process.argv.slice(2);
  if(args.includes('--once'))throw Error('一次性任务请使用 npm run start:foreground -- rtp-worker --once');
  const context=serviceContext(root,service,args);
  // Parse the selected configuration before stopping a working instance.
  if(service.role!=='game') {
    const database=readPostgresConfig(context.environment.GTT_PG_CONFIG,context.environment);
    if(!Array.isArray(database.sources)||!database.sources.length)throw Error('PostgreSQL 配置缺少存储路由 sources');
    if(['gateway','admin'].includes(context.action)) {
      const {Deployment}=await import('../dist/gateway/deployment.js');
      new Deployment(context.config);
    }
  }
  const game=service.role==='game'?JSON.parse(readFileSync(resolve(root,'GAME.json'),'utf8')):null;
  const name=game?`${game.code}-${service.release}`:context.action==='rtp-worker'?'rtp-worker':service.role;
  const script=resolve(root,service.entry_point);
  const home=resolve(process.env.PM2_HOME??resolve(homedir(),'.pm2'));
  mkdirSync(home,{recursive:true});
  lockFile=resolve(home,`gtt-start-${name}.lock`);
  try {lock=openSync(lockFile,'wx');}catch {throw Error('同名实例启动锁已存在，请等待其他启动完成；异常退出后请确认无启动任务再移除 '+lockFile);}
  const require=createRequire(import.meta.url);
  if(existsSync(resolve(root,'node_modules/pm2/package.json'))) {
    try {pm2=require('pm2');}catch(error){if(error.code!=='MODULE_NOT_FOUND')throw error;}
  }
  if(!pm2) {
    console.log('安装锁定的 PM2 与生产依赖');
    await installDependencies(root,{environment:game?installationEnvironment(gameProcessEnvironment(process.env)):process.env});
  }
  pm2??=require('pm2');
  const call=(method,...values)=>new Promise((ok,fail)=>pm2[method](...values,(error,result)=>error?fail(error):ok(result)));
  await call('connect');
  const previous=(await call('list')).filter(item=>item.name===name);
  if(previous.length) {
    if(previous.length!==1)throw Error('存在多个同名 PM2 实例，请先整理：'+name);
    const env=previous[0].pm2_env;
    if(resolve(env.pm_exec_path)!==script||resolve(env.pm_cwd)!==root)throw Error('同名实例属于其他目录或入口，拒绝覆盖：'+name);
    console.log(`重新读取配置并重启：${name} (原 PID ${previous[0].pid})`);
    // Restart with a fresh process definition: PM2 restart/updateEnv merges old
    // environment keys, which would retain values removed from the new config.
    // Delete only the identity-checked instance, never other versions/users.
    await call('delete',previous[0].pm_id);
  }
  {
    const token=randomUUID(), state=resolve(home,`gtt-ready-${name}.json`);
    writeFileSync(state,JSON.stringify({status:'starting',token}),{mode:0o600});
    const env=game?installationEnvironment(gameProcessEnvironment(process.env)):{...process.env};
    // Do not forward parent npm command metadata to the service.
    for(const key of Object.keys(env))if(key.startsWith('npm_')&&!key.startsWith('npm_config_'))delete env[key];
    createdName=name;
    await call('start',{
      name,cwd:root,script,interpreter:process.execPath,args:context.args,
      exec_mode:'fork',instances:1,watch:false,autorestart:true,
      min_uptime:10000,max_restarts:3,restart_delay:3000,kill_timeout:10000,
      wait_ready:false,
      filter_env:game?Object.keys(process.env).filter(key=>!(key in env)):[],
      env:{...env,__GTT_PM2_READY_FILE:state,__GTT_PM2_READY_TOKEN:token},
    });
    const deadline=Date.now()+120000;
    let success=false;
    while(Date.now()<deadline) {
      const status=JSON.parse(readFileSync(state,'utf8'));
      const current=(await call('list')).find(item=>item.name===name);
      if(status.token===token&&status.status==='error')throw Error('后台启动失败：'+status.error+'；查看 pm2 logs '+name);
      if(status.token===token&&status.status==='ready'&&current?.pid===status.pid&&current.pm2_env.status==='online') {
        console.log(`后台${previous.length?'重启':'启动'}成功：${name} (PID ${status.pid})。查看日志：pm2 logs ${name}`);
        success=true;break;
      }
      if(!current||['errored','stopped'].includes(current.pm2_env.status))throw Error('PM2 进程退出，请查看 pm2 logs '+name);
      await sleep(300);
    }
    if(!success)throw Error('等待服务就绪超时，请查看 pm2 logs '+name+'；未宣告启动成功');
  }
} catch(error) {
  if(pm2&&createdName)await new Promise(ok=>pm2.stop(createdName,()=>ok()));
  console.error('PM2 启动失败：'+error.message);process.exitCode=1;
}
finally {
  pm2?.disconnect();
  if(lock!==undefined){closeSync(lock);unlinkSync(lockFile);}
}
