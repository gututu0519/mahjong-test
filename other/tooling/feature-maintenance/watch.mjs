import fs from 'node:fs/promises';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {DEFAULT_ROOT,REGISTRY,DETECTOR,PRIVATE,hash,canonical,requireFact,repoPath,fact,readJson,writeJson,runDetector,verifyFeature,featureKey} from './verify.mjs';
import {updateWorkbook} from './update-workbook.mjs';
import {captureArchive, captureFolders} from '../../capture/response-capture/capture-layout.mjs';

const STATUS=PRIVATE+'/status.json';
const LOCK=PRIVATE+'/.watch.lock';
async function jsonFetch(url,signal){
  const response=await fetch(url,{signal:AbortSignal.any([AbortSignal.timeout(15000),...(signal?[signal]:[])])});
  requireFact(response.ok,`抓取API返回 ${response.status}`);const text=await response.text();requireFact(Buffer.byteLength(text)<64*1024*1024,'抓取API数据超过限制');return JSON.parse(text);
}
function apiOrigin(value){const url=new URL(value);requireFact(url.protocol==='http:'&&['127.0.0.1','localhost','[::1]'].includes(url.hostname)&&url.pathname==='/'&&!url.search&&!url.hash&&!url.username&&!url.password,'只能轮询本机抓取API根地址');return url.origin;}
async function loadStatus(root){try{const value=await readJson(root,STATUS);return value.version===1?value:{};}catch(error){if(error.code==='ENOENT'||error instanceof SyntaxError)return {};throw error;}}
const reason=error=>error.code==='ENOENT'?'缺少本地文件或目录':String(error.message).slice(0,300);

export function sanitizeDetail(detail,features,sources){
  requireFact(Array.isArray(sources)&&sources.length>0,'未登记可信抓取来源');
  const launch=new URL(detail.url);
  requireFact(launch.protocol==='https:'&&sources.some(s=>s.launch_origins?.includes(launch.origin)),'抓取启动来源未登记，不能作为原始证据');
  const codes=new Set(features.map(f=>f.game_code)),rows=[];
  for(const row of detail.rows??[]){
    let url;try{url=new URL(row.url);}catch{continue;}
    const match=/^\/game-api\/([a-z0-9-]+)\/v\d+\/[A-Za-z/]+$/.exec(url.pathname);
    if(!['http:','https:'].includes(url.protocol)||!match||!codes.has(match[1]))continue;
    const policies=sources.filter(s=>s.game_codes?.includes(match[1]));
    if(!policies.length)continue; // 未支持来源的PP/TaDa保持pending，不猜测来源。
    requireFact(url.protocol==='https:'&&policies.some(s=>s.launch_origins?.includes(launch.origin)&&s.api_origins?.includes(url.origin)),'抓取API来源未登记，拒绝本机或未知来源作为原始证据');
    const clean={url:url.origin+url.pathname};
    for(const key of ['id','method','state','status','mime','body','request_body'])if(['string','number'].includes(typeof row[key]))clean[key]=row[key];
    rows.push(clean);
  }
  return {id:detail.id??detail.session_id,url:launch.origin+launch.pathname,rows};
}

export async function watchOnce(options={}){
  const root=await fs.realpath(options.root??DEFAULT_ROOT),origin=apiOrigin(options.captureUrl??'http://127.0.0.1:8090');
  const registry=await readJson(root,REGISTRY);requireFact(registry.version===1&&Array.isArray(registry.features),'功能登记无效');
  const old=await loadStatus(root),state={version:1,updated_at:new Date().toISOString(),capture_url:origin,sessions:old.sessions??{},features:Object.fromEntries(registry.features.filter(f=>old.features?.[f.id]).map(f=>[f.id,old.features[f.id]])),errors:[]};
  const candidates=new Map(Object.entries(old.features??{}).map(([id,value])=>[id,value.candidatePath?{path:value.candidatePath,status:value.capture_status}:null]));
  const detectorFact=await fact(root,DETECTOR);
  try{
    const listing=await jsonFetch(origin+'/api/sessions',options.signal),sessions=Array.isArray(listing)?listing:listing.sessions;
    requireFact(Array.isArray(sessions),'抓取会话列表格式无效');
    const folders=captureFolders(path.join(root,captureArchive));
    for(const session of sessions){
      if(options.signal?.aborted)throw new Error('监控已停止');
      if(!/^[a-zA-Z0-9_-]{1,80}$/.test(session.id??'')){state.errors.push('忽略无效会话标识');continue;}
      try{
        const detail=sanitizeDetail(await jsonFetch(origin+'/api/sessions/'+encodeURIComponent(session.id),options.signal),registry.features,registry.capture_sources),detailHash=hash(canonical(detail));
        if(state.sessions[session.id]?.detail_sha256===detailHash&&state.sessions[session.id]?.detector_sha256===detectorFact.sha256&&!state.sessions[session.id]?.stats?.invalid_saved_spins)continue;
        requireFact(folders.has(session.id),'未找到该会话的抓取批次目录');
        const captureRoot=captureArchive+'/'+folders.get(session.id);
        const result=await runDetector(root,detail,captureRoot,{signal:options.signal});
        requireFact(result.session_id===session.id,'检测结果会话不匹配');
        const matchesRegistered=result.features.some(d=>['candidate','evidence_complete'].includes(d.status)&&registry.features.some(f=>f.game_code===d.game_code&&f.name===d.feature_name));
        const detailPath=`${PRIVATE}/sessions/${session.id}/${detailHash}.json`;
        if(matchesRegistered)await writeJson(root,detailPath,detail);const detailFact=matchesRegistered?await fact(root,detailPath):null;
        for(const feature of registry.features){
          const match=result.features.filter(f=>f.game_code===feature.game_code&&f.feature_name===feature.name);
          if(match.length!==1||!['candidate','evidence_complete'].includes(match[0].status))continue;
          const detected=match[0],signature=hash(canonical({detected,detector:detectorFact,session_id:session.id}));
          const candidatePath=`${PRIVATE}/candidates/${featureKey(feature)}/${session.id}-${signature}.json`;
          try{await repoPath(root,candidatePath);}catch(error){if(error.code!=='ENOENT')throw error;await writeJson(root,candidatePath,{version:1,session_id:session.id,source:{detail:detailFact,capture_root:captureRoot,detector:detectorFact},result:{version:1,session_id:session.id,features:[detected]}});}
          if(candidates.get(feature.id)?.status!=='evidence_complete'||detected.status==='evidence_complete')candidates.set(feature.id,{path:candidatePath,status:detected.status});
        }
        state.sessions[session.id]={detail_sha256:detailHash,detector_sha256:detectorFact.sha256,state:session.state,scanned_at:new Date().toISOString(),stats:result.stats??{},pending_games:result.pending_games??[]};
      }catch(error){state.errors.push(`会话 ${session.id}：${reason(error)}`);}
    }
  }catch(error){state.errors.push(reason(error));}
  for(const feature of registry.features){
    if(options.signal?.aborted)break;
    const candidate=candidates.get(feature.id),previous=old.features?.[feature.id];
    const sourceSupported=registry.capture_sources?.some(s=>s.game_codes?.includes(feature.game_code));
    const base={name:feature.name,game_code:feature.game_code,candidatePath:candidate?.path??null,capture_status:candidate?.status??'pending',capture_reason:!sourceSupported?'尚未登记可信原始来源及对应功能解码支持':candidate?.status==='evidence_complete'?'已保存完整协议候选，仍需完成集成验收':candidate?'已保存候选，协议证据尚不完整':'尚无可用完整原始协议候选'};
    try{
      // 已成功写入的报告交给更新器重查回执及hash，重复轮询不会重复写表。
      if(previous?.status==='updated'&&previous.reportPath){const update=await updateWorkbook({root,reportPath:previous.reportPath});state.features[feature.id]={...base,...update,reportPath:previous.reportPath};continue;}
      const verified=await verifyFeature({root,featureId:feature.id,candidatePath:candidate?.path,signal:options.signal,cached:options.cache?.get(feature.id)});
      if(verified.status!=='verified'){state.features[feature.id]={...base,status:'pending',reasons:verified.reasons};continue;}
      options.cache?.set(feature.id,{fingerprint:verified.fingerprint,report:verified.report});
      const update=await updateWorkbook({root,reportPath:verified.reportPath});
      state.features[feature.id]={...base,...update,reportPath:verified.reportPath};
    }catch(error){state.features[feature.id]={...base,status:'pending',reasons:[reason(error)]};}
  }
  await writeJson(root,STATUS,state);return state;
}

export async function acquireLock(root=DEFAULT_ROOT){
  root=await fs.realpath(root);const lock=await repoPath(root,LOCK,{missing:true});await fs.mkdir(path.dirname(lock),{recursive:true});
  const nonce=randomUUID(),record={pid:process.pid,created_at:new Date().toISOString(),command:process.argv,nonce};
  let handle;
  try{handle=await fs.open(lock,'wx');}catch(error){
    if(error.code!=='EEXIST')throw error;
    // 无法确认旧PID已退出时保留锁，绝不按PID结束任何进程。
    const bytes=await fs.readFile(lock),previous=JSON.parse(bytes.toString());let alive=true;
    requireFact(Number.isInteger(previous.pid)&&previous.pid>0,'旧监控锁PID无效，保留原锁供核对');
    try{process.kill(previous.pid,0);}catch(e){if(e.code==='ESRCH')alive=false;else throw new Error('已有监控锁且无法核验所属进程');}
    requireFact(!alive,'已有监控实例或PID归属无法确认，保留原锁');
    requireFact((await fs.readFile(lock)).equals(bytes),'监控锁已被其他实例更新');await fs.unlink(lock);handle=await fs.open(lock,'wx');
  }
  await handle.writeFile(JSON.stringify(record));await handle.close();
  return async()=>{try{const current=JSON.parse(await fs.readFile(lock,'utf8'));if(current.nonce===nonce)await fs.unlink(lock);}catch(error){if(error.code!=='ENOENT')throw error;}};
}
async function main(){
  const args=process.argv.slice(2),value=(name,fallback)=>{const at=args.indexOf(name);return at<0?fallback:args[at+1];};
  for(let i=0;i<args.length;i++){requireFact(['--once','--parent-pipe','--capture-url','--interval-ms'].includes(args[i]),'未知监控参数');if(!['--once','--parent-pipe'].includes(args[i]))i++;}
  const captureUrl=value('--capture-url','http://127.0.0.1:8090'),interval=Number(value('--interval-ms','10000'));apiOrigin(captureUrl);
  requireFact(Number.isInteger(interval)&&interval>=1000&&interval<=60000,'轮询间隔需在1000至60000毫秒之间');
  const controller=new AbortController(),stop=()=>controller.abort();process.once('SIGINT',stop);process.once('SIGTERM',stop);
  const release=await acquireLock(),cache=new Map();
  let input='';const parentInput=chunk=>{input+=chunk;let index;while((index=input.indexOf('\n'))>=0){if(input.slice(0,index).replace(/\r$/,'')==='stop')stop();input=input.slice(index+1);}if(input.length>64)input='';};
  if(args.includes('--parent-pipe')){process.stdin.setEncoding('utf8');process.stdin.on('data',parentInput);process.stdin.once('end',stop);process.stdin.resume();}
  try{
    do{
      try{const state=await watchOnce({captureUrl,cache,signal:controller.signal});if(args.includes('--once')){console.log(JSON.stringify({status:state.errors.length?'failed':'checked',features:Object.fromEntries(Object.entries(state.features).map(([id,f])=>[id,f.status])),errors:state.errors}));if(state.errors.length)process.exitCode=1;}}
      catch(error){await writeJson(DEFAULT_ROOT,PRIVATE+'/watch-error.json',{version:1,at:new Date().toISOString(),status:'pending',reason:reason(error)});if(args.includes('--once'))process.exitCode=1;}
      if(args.includes('--once')||controller.signal.aborted)break;
      await new Promise(resolve=>{const timer=setTimeout(done,interval);function done(){clearTimeout(timer);controller.signal.removeEventListener('abort',done);resolve();}controller.signal.addEventListener('abort',done,{once:true});});
    }while(!controller.signal.aborted);
  }finally{await release();process.removeListener('SIGINT',stop);process.removeListener('SIGTERM',stop);if(args.includes('--parent-pipe')){process.stdin.removeListener('data',parentInput);process.stdin.removeListener('end',stop);process.stdin.pause();}}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href)main().catch(error=>{console.error(error.message);process.exitCode=1;});
