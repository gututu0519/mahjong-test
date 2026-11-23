import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash, randomUUID} from 'node:crypto';
import {spawn} from 'node:child_process';
import {fileURLToPath, pathToFileURL} from 'node:url';

export const DEFAULT_ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
export const REGISTRY='other/tooling/feature-maintenance/features.json';
export const READINESS='gateway/config/game-readiness.json';
export const VERIFIER='other/tooling/feature-maintenance/verifiers/integrated-feature.mjs';
export const DETECTOR='other/capture/response-capture/feature_evidence.py';
export const PRIVATE='other/diagnostics/feature-maintenance';
export const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const EXECUTED_SOURCE_HASH=hash(await fs.readFile(fileURLToPath(import.meta.url)));
export const canonical=value=>value===null?'null':Array.isArray(value)?'['+value.map(canonical).join(',')+']':typeof value==='object'?'{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}':JSON.stringify(value);
export const requireFact=(condition,reason)=>{if(!condition)throw new Error(reason);};
export const featureKey=feature=>feature.id.replace(/[^a-zA-Z0-9_-]/g,'_');
export const relativePath=(root,file)=>path.relative(root,file).replaceAll('\\','/');
export function within(root,file){const rel=path.relative(root,file);return rel!==''&&!rel.startsWith('..'+path.sep)&&rel!=='..'&&!path.isAbsolute(rel);}
export async function repoPath(root,name,{directory=false,missing=false}={}){
  requireFact(typeof name==='string'&&name.length>0&&!path.isAbsolute(name)&&!name.includes('\\')&&!name.includes(':')&&!name.includes('\0'),'路径必须为仓库内相对路径');
  const target=path.resolve(root,name);requireFact(within(root,target),'路径越过仓库边界');
  if(missing){let ancestor=path.dirname(target);while(true){try{const real=await fs.realpath(ancestor);requireFact(real===root||within(root,real),'父目录链接越过仓库边界');break;}catch(error){if(error.code!=='ENOENT')throw error;ancestor=path.dirname(ancestor);}}return target;}
  const real=await fs.realpath(target);requireFact(within(root,real),'文件链接越过仓库边界');
  const stat=await fs.stat(real);requireFact(directory?stat.isDirectory():stat.isFile(),directory?'需要目录':'需要文件');return real;
}
export async function fact(root,name){const file=await repoPath(root,name);return {path:name,sha256:hash(await fs.readFile(file))};}
export async function checkFile(root,item){
  requireFact(item&&Object.keys(item).sort().join(',')==='path,sha256'&&/^[a-f0-9]{64}$/.test(item.sha256),'文件证据必须包含且仅包含 path/sha256');
  const current=await fact(root,item.path);requireFact(current.sha256===item.sha256,`文件已变化：${item.path}`);return current;
}
export async function readJson(root,name){return JSON.parse(await fs.readFile(await repoPath(root,name),'utf8'));}
export async function writeJson(root,name,value){
  const file=await repoPath(root,name,{missing:true});await fs.mkdir(path.dirname(file),{recursive:true});
  const temp=file+'.'+randomUUID()+'.tmp';await fs.writeFile(temp,JSON.stringify(value,null,2)+'\n');await fs.rename(temp,file);return file;
}
export async function snapshot(root,roots){
  requireFact(Array.isArray(roots)&&roots.length>0,'没有登记实现目录');const files=[];
  async function walk(name){const absolute=await repoPath(root,name,{directory:true});for(const entry of (await fs.readdir(absolute,{withFileTypes:true})).sort((a,b)=>a.name.localeCompare(b.name))){
    requireFact(!entry.isSymbolicLink(),`实现目录含符号链接：${name}/${entry.name}`);
    const child=name+'/'+entry.name;if(entry.isDirectory())await walk(child);else if(entry.isFile())files.push(await fact(root,child));
  }}
  for(const name of roots)await walk(name);
  requireFact(files.length>0,'实现目录没有文件');return files.sort((a,b)=>a.path.localeCompare(b.path));
}
export function runFile(executable,args,{cwd,input='',timeout=120000,env=process.env,signal,maxBytes=16*1024*1024}={}){
  return new Promise((resolve,reject)=>{
    const child=spawn(executable,args,{cwd,env,shell:false,windowsHide:true,stdio:['pipe','pipe','pipe']});
    const stdout=[],stderr=[];let size=0,failed=false;
    const finishError=error=>{if(failed)return;failed=true;child.kill();reject(error);};
    const timer=setTimeout(()=>finishError(new Error('验证子进程超时')),timeout);
    const stop=()=>finishError(new Error('验证已停止'));signal?.addEventListener('abort',stop,{once:true});
    const collect=(list,chunk)=>{size+=chunk.length;if(size>maxBytes)finishError(new Error('验证输出超过限制'));else list.push(chunk);};
    child.stdout.on('data',chunk=>collect(stdout,chunk));child.stderr.on('data',chunk=>collect(stderr,chunk));
    child.on('error',finishError);child.on('close',(code)=>{clearTimeout(timer);signal?.removeEventListener('abort',stop);if(!failed)resolve({code,stdout:Buffer.concat(stdout).toString('utf8'),stderr:Buffer.concat(stderr).toString('utf8')});});
    child.stdin.on('error',()=>{});child.stdin.end(input);if(signal?.aborted)stop();
  });
}
export async function runDetector(root,detail,captureRoot,{signal}={}){
  const program=await repoPath(root,DETECTOR),bodies=await repoPath(root,captureRoot,{directory:true});
  const result=await runFile('python',[program,'-','--bodies-root',bodies],{cwd:root,input:JSON.stringify(detail),timeout:60000,signal});
  requireFact(result.code===0,'抓取证据检测器执行失败');const value=JSON.parse(result.stdout);
  requireFact(value.version===1&&Array.isArray(value.features),'检测器输出格式无效');return value;
}

export async function verifyFeature(options={}){
  const root=await fs.realpath(options.root??DEFAULT_ROOT);let feature;
  try{
    const registry=await readJson(root,REGISTRY);requireFact(registry.version===1&&Array.isArray(registry.features),'功能登记格式无效');
    const matches=registry.features.filter(f=>f.id===options.featureId);requireFact(matches.length===1,'功能必须唯一登记');feature=matches[0];
    requireFact(feature.verifier===VERIFIER,'必须使用固定集成验证器');await repoPath(root,VERIFIER);
    requireFact(feature.before==='❌'&&feature.after==='✅','目标不是未完成到完成的登记变更');
    requireFact((await fact(root,'other/tooling/feature-maintenance/verify.mjs')).sha256===EXECUTED_SOURCE_HASH,'验证器入口源码与运行版本不一致，请重启监控');
    const executedVerifier=await fact(root,VERIFIER);
    const {verifyIntegratedFeature}=await import(pathToFileURL(await repoPath(root,VERIFIER)).href+'?sha256='+executedVerifier.sha256);
    const syntheticFixtureAllowed=options.allowSynthetic===true&&registry.synthetic_fixture===true&&path.resolve(root).toLowerCase()!==DEFAULT_ROOT.toLowerCase();
    const result=await verifyIntegratedFeature({...options,root,registry,feature,syntheticFixtureAllowed,executedVerifier});
    if(result.status!=='verified')return result;
    const reportPath=options.reportPath??`${PRIVATE}/reports/${featureKey(feature)}-${hash(canonical(result.report))}.json`;
    await writeJson(root,reportPath,result.report);
    return {...result,reportPath};
  }catch(error){return {version:1,status:'pending',feature_id:feature?.id??options.featureId,reasons:[error.code==='ENOENT'?'缺少登记文件、证据或验收产物':String(error.message).slice(0,400)]};}
}

async function main(){
  const args=process.argv.slice(2),option=name=>{const at=args.indexOf(name);return at<0?undefined:args[at+1];};
  requireFact(option('--feature'),'需要 --feature <登记id>');
  const result=await verifyFeature({featureId:option('--feature'),candidatePath:option('--candidate'),acceptancePath:option('--acceptance')});
  console.log(JSON.stringify(result.status==='verified'?{status:result.status,reportPath:result.reportPath}:result,null,2));
  if(result.status!=='verified')process.exitCode=2;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href)main().catch(error=>{console.error(error.message);process.exitCode=1;});
