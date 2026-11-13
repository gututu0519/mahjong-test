import { build, runtime, repo } from './build.mjs';
import { spawn } from 'node:child_process';
import { resolve } from 'node:path';
import { existsSync, readFileSync } from 'node:fs';
const [action,...args]=process.argv.slice(2);
if(!action || !/^[a-z][a-z0-9-]*$/.test(action)) throw Error('Supply start, test, cli, or a tool name');
const pathOptions=new Set(action==='render-game-env'?['--output']:['--archives','--config','--env-file','--database','--service-dir','--source','--output','--destination','--assets-manifest','--secret-file','--game-config']);
for(let i=1;i<args.length;i++) if(pathOptions.has(args[i-1])) args[i]=resolve(args[i]);
if(['smoke-release','install-frontend','publish-frontend'].includes(action) && args[0]) args[0]=resolve(args[0]);
if(action==='render-frontend-edge') for(let i=0;i<2&&i<args.length;i++) args[i]=resolve(args[i]);
await build();
const activation=resolve(repo,'gateway/instance/data/database-active.json');
const compute=action==='cli'&&args[0]==='game';
const localEnv=resolve(repo,'gateway/instance/platform.env');
if(['start','cli'].includes(action)&&!compute&&!args.includes('--config')&&!args.includes('--env-file')&&!process.env.GTT_PLATFORM_ENV_FILE&&existsSync(localEnv))process.env.GTT_PLATFORM_ENV_FILE=localEnv;
if(['start','cli'].includes(action)&&!compute&&!process.env.GTT_PLATFORM_ENV_FILE&&!args.includes('--config')&&!args.includes('--env-file')&&existsSync(activation)) {
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
const child=spawn(action==='python'?'python':process.execPath,command,{
  cwd:action==='python'?resolve(repo,'other/runtime'):runtime,
  stdio:'inherit',windowsHide:true,
  env:compute?gameProcessEnvironment(process.env):{...(action==='test'?isolatedTestEnvironment(process.env):process.env),GTT_WORKSPACE_ROOT:repo,
    ...(action==='python'?{GTT_RESOURCE_ROOT:resolve(repo,'other/runtime')} : {}),
    ...(action==='render-integration'?{GTT_CONTRACT_DIRECTORY:resolve(repo,'admin/config')} : {})},
});
child.on('error',e=>{console.error(e.message);process.exitCode=1;});
child.on('exit',(code,signal)=>{process.exitCode=code??(signal?1:0);});
process.on('SIGINT',()=>child.kill('SIGINT'));
process.on('SIGTERM',()=>child.kill('SIGTERM'));
