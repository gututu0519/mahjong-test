import {existsSync,openSync,closeSync,unlinkSync,readFileSync} from 'node:fs';
import {isDeepStrictEqual} from 'node:util';
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
function installedDevelopmentTreeMatches(root) {
  const json = file => JSON.parse(readFileSync(resolve(root,file),'utf8'));
  try {
    const manifest = json('package.json');
    const {packages} = json('package-lock.json');
    const installed = json('node_modules/.package-lock.json').packages;
    for (const field of ['dependencies','devDependencies','optionalDependencies','peerDependencies']) {
      if (!isDeepStrictEqual(manifest[field],packages[''][field])) return false;
    }
    return Object.entries(packages).every(([path,entry]) => {
      if (!path) return true;
      if (entry.link || !isDeepStrictEqual(installed[path],entry)) return false;
      const pkg = json(path+'/package.json');
      if (pkg.version !== entry.version) return false;
      const bins = typeof pkg.bin === 'string' ? [pkg.bin] : Object.values(pkg.bin || {});
      return bins.every(bin => existsSync(resolve(root,path,bin))) &&
        (!pkg.main || existsSync(resolve(root,path,pkg.main)) || existsSync(resolve(root,path,pkg.main+'.js')));
    });
  } catch { return false; }
}
export async function installDependencies(root,{development=false,environment=process.env,npm=npmExecutable()}={}) {
  if(!existsSync(resolve(root,'package-lock.json')))throw Error('缺少依赖锁文件');
  const lock=resolve(root,'.startup-install.lock');let fd;
  for(let attempt=0;attempt<240;attempt++) {
    try {fd=openSync(lock,'wx');break;}catch(e){if(e.code!=='EEXIST')throw e;if(!attempt)console.log('正在等待其他启动任务完成依赖检查或安装');await new Promise(r=>setTimeout(r,500));}
  }
  if(fd===undefined)throw Error('依赖安装锁仍被占用，请检查其他安装进程：'+lock);
  try {
    if (development && installedDevelopmentTreeMatches(root)) {
      console.log('本地开发依赖与锁文件一致，继续编译');
      return;
    }
    await new Promise((ok,fail)=>{
      const child=spawn(process.execPath,[npm,'install',development?'--include=dev':'--omit=dev','--ignore-scripts','--no-audit','--no-fund'],{cwd:root,env:environment,stdio:['ignore','inherit','inherit']});
      let timedOut=false;
      const timer=development && setTimeout(()=>{ timedOut=true; child.kill('SIGKILL'); },120000);
      const stop=()=>child.kill('SIGTERM');process.once('SIGTERM',stop);process.once('SIGINT',stop);
      const clean=()=>{clearTimeout(timer);process.off('SIGTERM',stop);process.off('SIGINT',stop);};
      child.on('error',error=>{clean();fail(error);});
      child.on('exit',(code,signal)=>{clean();code===0&&!signal&&!timedOut?ok():fail(Error(timedOut?'开发依赖安装超过 120 秒，已停止本次启动，请检查 npm 安装日志。':'依赖安装失败，停止迁移和启动'));});
    });
  } finally {closeSync(fd);unlinkSync(lock);}
}
