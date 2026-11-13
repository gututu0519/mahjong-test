import {existsSync,openSync,closeSync,unlinkSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {spawn} from 'node:child_process';

export function npmExecutable(environment=process.env) {
  const file=environment.npm_execpath??[resolve(dirname(process.execPath),'node_modules/npm/bin/npm-cli.js'),resolve(dirname(process.execPath),'../lib/node_modules/npm/bin/npm-cli.js'),'/usr/share/nodejs/npm/bin/npm-cli.js'].find(p=>existsSync(p));
  if(!file||!existsSync(file))throw Error('未找到 npm，请使用 npm start 启动');
  return file;
}
export function installationEnvironment(runtimeEnvironment,source=process.env) {
  return {...runtimeEnvironment,...Object.fromEntries(Object.entries(source).filter(([key])=>/^(npm_config_|NPM_CONFIG_|NPM_TOKEN$|NODE_AUTH_TOKEN$|HTTPS?_PROXY$|NO_PROXY$)/.test(key)))};
}
export async function installDependencies(root,{development=false,environment=process.env,npm=npmExecutable()}={}) {
  if(!existsSync(resolve(root,'package-lock.json')))throw Error('缺少依赖锁文件');
  const lock=resolve(root,'.startup-install.lock');let fd;
  for(let attempt=0;attempt<240;attempt++) {
    try {fd=openSync(lock,'wx');break;}catch(e){if(e.code!=='EEXIST')throw e;await new Promise(r=>setTimeout(r,500));}
  }
  if(fd===undefined)throw Error('依赖安装锁仍被占用，请检查其他安装进程：'+lock);
  try {
    await new Promise((ok,fail)=>{
      const child=spawn(process.execPath,[npm,'install',development?'--include=dev':'--omit=dev','--ignore-scripts','--no-audit','--no-fund'],{cwd:root,env:environment,stdio:'inherit'});
      const stop=()=>child.kill('SIGTERM');process.once('SIGTERM',stop);process.once('SIGINT',stop);
      const clean=()=>{process.off('SIGTERM',stop);process.off('SIGINT',stop);};
      child.on('error',error=>{clean();fail(error);});
      child.on('exit',(code,signal)=>{clean();code===0&&!signal?ok():fail(Error('依赖安装失败，停止迁移和启动'));});
    });
  } finally {closeSync(fd);unlinkSync(lock);}
}
