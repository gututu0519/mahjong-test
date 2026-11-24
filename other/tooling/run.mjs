import { spawn } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';

const entry = fileURLToPath(import.meta.url);
const repo = resolve(dirname(entry), '../..');
const runtime = resolve(repo, 'other/runtime/server');

export async function runWorkspaceTool(action, supplied) {
  if (!action || !/^[a-z][a-z0-9-]*$/.test(action)) throw Error('Supply start, test, cli, or a tool name');
  const args = [...supplied];
  const launching = action === 'start' || action === 'cli';
  const reuseBuild = launching && args[1] === '--use-built';
  if (reuseBuild) args.splice(1, 1);
  const pathOptions=new Set(action==='render-game-env'?['--output']:['--archives','--config','--env-file','--database','--service-dir','--source','--output','--destination','--assets-manifest','--secret-file','--game-config','--service-release','--client-bundle','--receipt']);
  for(let i=1;i<args.length;i++) if(pathOptions.has(args[i-1])) args[i]=resolve(args[i]);
  if(['smoke-release','smoke-pm2-release','smoke-install-release','smoke-game-bundle','install-frontend','publish-frontend'].includes(action) && args[0]) args[0]=resolve(args[0]);
  if(action==='render-frontend-edge') for(let i=0;i<2&&i<args.length;i++) args[i]=resolve(args[i]);
  if (reuseBuild) {
    const files = ['dist/.built', 'dist/cli.js'];
    if (action === 'start' && args[0] !== 'game') files.push('tools/start.mjs');
    for (const file of files) {
      if (!existsSync(resolve(runtime, file))) throw Error('缺少已编译的运行文件 '+file+'，请先在项目根目录执行 npm run build。');
    }
  } else {
    const { build } = await import('./build.mjs');
    await build();
  }
  // 独立计算服务复用源码工作区单款计算服务入口，读取该版本的配置和认证文件。
  if (action === 'start' && args[0] === 'game') {
    const { startSourceService } = await import('./start-source.mjs');
    return startSourceService(args);
  }
  const activation=resolve(repo,'gateway/instance/data/database-active.json');
  const compute=action==='cli'&&args[0]==='game';
  const localEnv=resolve(repo,'gateway/instance/platform.env');
  if(launching&&!compute&&!args.includes('--config')&&!args.includes('--env-file')&&!process.env.GTT_PLATFORM_ENV_FILE&&existsSync(localEnv))process.env.GTT_PLATFORM_ENV_FILE=localEnv;
  if(launching&&!compute&&!process.env.GTT_PLATFORM_ENV_FILE&&!args.includes('--config')&&!args.includes('--env-file')&&existsSync(activation)) {
    const active=JSON.parse(readFileSync(activation,'utf8'));
    if(active.driver!=='postgres'||!active.configFile)throw Error('Invalid database activation configuration');
    process.env.GTT_PG_CONFIG=resolve(active.configFile);
  }
  const {gameProcessEnvironment,isolatedTestEnvironment}=await import('./../runtime/server/dist/shared/config/environment.js');
  let command;
  if(action==='test') command=['--test','--test-concurrency=1',...args,'dist/tests/*.test.js'];
  else if(action==='cli') command=['dist/cli.js',...args];
  else if(action==='python') command=args;
  else command=[resolve(runtime,'tools',action+'.mjs'),...args];
  const cwd = action==='python'?resolve(repo,'other/runtime'):runtime;
  const env = compute?gameProcessEnvironment(process.env):{...(action==='test'?isolatedTestEnvironment(process.env):process.env),GTT_WORKSPACE_ROOT:repo,
      ...(action==='python'?{GTT_RESOURCE_ROOT:resolve(repo,'other/runtime')} : {}),
      ...(action==='render-integration'?{GTT_CONTRACT_DIRECTORY:resolve(repo,'admin/config')} : {})};
  if (reuseBuild) {
    // 已有构建可直接在本进程监听，控制台的正常退出通道能到达同一服务。
    const [script, ...options] = command;
    if (compute) for (const key of Object.keys(process.env)) if (!(key in env)) delete process.env[key];
    Object.assign(process.env, env);
    process.chdir(cwd);
    const url = pathToFileURL(resolve(cwd, script)).href;
    if (action === 'cli') {
      const { main } = await import(url);
      return main(options);
    }
    process.argv = [process.execPath, script, ...options];
    await import(url);
    return;
  }
  const child=spawn(action==='python'?'python':process.execPath,command,{
    cwd, env, stdio:'inherit',windowsHide:true,
  });
  child.on('error',e=>{console.error(e.message);process.exitCode=1;});
  child.on('exit',(code,signal)=>{process.exitCode=code??(signal?1:0);});
  process.on('SIGINT',()=>child.kill('SIGINT'));
  process.on('SIGTERM',()=>child.kill('SIGTERM'));
}

if (process.argv[1] && resolve(process.argv[1]) === entry) {
  const [action, ...args] = process.argv.slice(2);
  try {
    await runWorkspaceTool(action, args);
  } catch (error) {
    if (action !== 'start' && action !== 'cli') throw error;
    console.error('启动流水线失败：' + error.message);
    process.exitCode = 1;
  }
}
