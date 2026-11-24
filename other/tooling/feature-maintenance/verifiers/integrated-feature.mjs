import fs from 'node:fs/promises';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {captureArchive, captureFolders} from '../../../capture/response-capture/capture-layout.mjs';
import {DEFAULT_ROOT,REGISTRY,READINESS,VERIFIER,DETECTOR,PRIVATE,canonical,hash,requireFact,repoPath,fact,checkFile,readJson,writeJson,snapshot,runFile,runDetector,featureKey} from '../verify.mjs';

const identity=f=>({id:f.id,game_id:f.game_id,game_code:f.game_code,name:f.name});
const same=(a,b)=>canonical(a)===canonical(b);
const utc=value=>typeof value==='string'&&!Number.isNaN(Date.parse(value));
function localUrl(value){
  const url=new URL(value);requireFact(url.protocol==='http:'&&(['127.0.0.1','localhost','[::1]'].includes(url.hostname)||/^g[1-9]\d*\.localhost$/.test(url.hostname))&&!url.username&&!url.password&&!url.search&&!url.hash,'UI记录必须使用无会话参数的真实本机URL');return url;
}
async function media(root,item){
  await checkFile(root,item);const bytes=await fs.readFile(await repoPath(root,item.path));
  if(item.path.endsWith('.png'))requireFact(bytes.length>64&&bytes.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10]))&&bytes.readUInt32BE(16)>=320&&bytes.readUInt32BE(20)>=240&&bytes.subarray(-8,-4).toString()==='IEND','UI截图不是完整且可辨认尺寸的PNG');
  else if(item.path.endsWith('.mp4'))requireFact(bytes.length>1024&&bytes.subarray(4,8).toString()==='ftyp'&&bytes.includes(Buffer.from('moov'))&&bytes.includes(Buffer.from('mdat')),'UI录像缺少MP4媒体结构');
  else if(item.path.endsWith('.webm'))requireFact(bytes.length>1024&&bytes.subarray(0,4).equals(Buffer.from([26,69,223,163])),'UI录像不是WebM');
  else throw new Error('UI附件只接受PNG截图或MP4/WebM录像');
}

export async function verifyIntegratedFeature(options){
  const {root,registry,feature,signal}=options;
  await checkFile(root,options.executedVerifier);
  const pending=reason=>({version:1,status:'pending',feature_id:feature.id,reasons:[reason]});
  const readiness=await readJson(root,READINESS),games=readiness.games?.filter(g=>g.id===feature.game_id&&g.code===feature.game_code)??[];
  const included=games.length===1?games[0].special_features?.filter(f=>f.name===feature.name)??[]:[];
  if(included.length!==1||included[0].implementation!=='included')return pending('当前readiness中同名玩法尚未实现完成');
  if(!options.candidatePath)return pending('尚无完整抓取证据候选');
  const candidateFact=await fact(root,options.candidatePath),candidate=await readJson(root,options.candidatePath);
  requireFact(candidate.version===1&&typeof candidate.session_id==='string'&&/^[a-zA-Z0-9_-]{1,80}$/.test(candidate.session_id)&&candidate.source&&candidate.result,'候选记录格式无效');
  const selected=candidate.result.features?.filter(f=>f.game_code===feature.game_code&&f.feature_name===feature.name)??[];
  if(selected.length!==1||selected[0].status!=='evidence_complete')return pending(selected[0]?.pending_reasons?.join('；')||'抓取候选尚未具备完整协议证据');
  requireFact(candidate.source.detector.path===DETECTOR,'候选检测器未绑定固定路径');
  await checkFile(root,candidate.source.detail);await checkFile(root,candidate.source.detector);
  const folder=captureFolders(path.join(root,captureArchive)).get(candidate.session_id);
  requireFact(folder && candidate.source.capture_root===captureArchive+'/'+folder,'抓取目录与会话不匹配');
  const detail=await readJson(root,candidate.source.detail.path);
  requireFact((detail.id??detail.session_id)===candidate.session_id,'抓取快照会话不匹配');
  const rerun=await runDetector(root,detail,candidate.source.capture_root,{signal});
  const verified=rerun.features.filter(f=>f.game_code===feature.game_code&&f.feature_name===feature.name);
  requireFact(rerun.session_id===candidate.session_id&&verified.length===1&&same(verified[0],selected[0]),'重跑检测器的结果与候选不一致');
  const captured=verified[0];requireFact(captured.status==='evidence_complete'&&Array.isArray(captured.checks)&&captured.checks.length>0&&captured.checks.every(c=>c.passed===true&&typeof c.name==='string'),'完整协议检查未全部通过');
  requireFact(Array.isArray(captured.evidence)&&captured.evidence.length>0,'完整证据没有原始文件');
  const policies=registry.capture_sources?.filter(s=>s.game_codes?.includes(feature.game_code))??[];
  if(!policies.length)return pending('该游戏尚未登记可信原始抓取来源，不能用本机模拟代替');
  const launch=new URL(detail.url);
  requireFact(launch.protocol==='https:'&&policies.some(s=>s.launch_origins?.includes(launch.origin))&&!launch.username&&!launch.password&&!launch.search&&!launch.hash,'候选启动来源不可信或未脱敏');
  const manifestPath=candidate.source.capture_root+'/manifest.json';let manifest;
  try{manifest=await readJson(root,manifestPath);}catch(error){if(error.code==='ENOENT')return pending('原始会话仍未保存完成manifest，继续记录候选但不最终验收');throw error;}
  requireFact(manifest.id===candidate.session_id&&manifest.state==='completed','原始抓取会话未正常完成');
  const manifestLaunch=new URL(manifest.url);requireFact(manifestLaunch.origin+manifestLaunch.pathname===launch.origin+launch.pathname,'候选启动来源与原始manifest不一致');
  for(const item of captured.evidence){
    const origins=(manifest.rows??[]).filter(row=>row.state==='complete'&&row.status===200&&(row.body===item.path||row.request_body===item.path)).map(row=>{try{return new URL(row.url);}catch{return null;}}).filter(Boolean);
    requireFact(origins.some(url=>url.protocol==='https:'&&url.pathname.startsWith(`/game-api/${feature.game_code}/`)&&policies.some(policy=>policy.launch_origins?.includes(launch.origin)&&policy.api_origins?.includes(url.origin))),'证据没有对应的可信原站manifest请求，本机响应不算原始抓取');
  }
  const manifestFact=await fact(root,manifestPath);
  const evidence=[];
  for(const item of captured.evidence){requireFact(typeof item.path==='string'&&!item.path.startsWith('/')&&!item.path.includes('..'),'原始证据路径不合法');evidence.push(await checkFile(root,{path:candidate.source.capture_root+'/'+item.path,sha256:item.sha256}));}

  const acceptancePath=options.acceptancePath??`${PRIVATE}/acceptance/${featureKey(feature)}.json`;
  let acceptance;try{acceptance=await readJson(root,acceptancePath);}catch(error){if(error.code==='ENOENT')return pending('完整抓取证据已保存，仍缺真实本地UI验收记录');throw error;}
  const synthetic=options.syntheticFixtureAllowed===true&&registry.synthetic_fixture===true;
  requireFact(acceptance.version===1&&acceptance.kind==='integrated-feature-acceptance'&&same(acceptance.feature,identity(feature)),'验收身份格式不匹配');
  requireFact(acceptance.synthetic===false||(synthetic&&acceptance.synthetic===true),'生产验证不接受合成验收记录');
  requireFact(utc(acceptance.created_at)&&Date.parse(acceptance.created_at)<=Date.now()+60000,'验收时间无效');
  requireFact(acceptance.capture?.session_id===candidate.session_id&&same(acceptance.capture.candidate,candidateFact),'验收记录未绑定本次完整抓取候选');
  const requiredRoots=[`games/${feature.game_code}/backend`,`games/${feature.game_code}/frontend`,`games/${feature.game_code}/instance/config`];
  requireFact(requiredRoots.every(name=>feature.implementation_roots?.includes(name)),'登记必须覆盖当前游戏后端、前端资源和配置');
  const implementation=await snapshot(root,feature.implementation_roots);
  requireFact(same(acceptance.implementation,implementation),'源码或资源hash已变化，或验收未覆盖全部登记实现文件');
  const files=[candidateFact,await fact(root,acceptancePath),await fact(root,REGISTRY),candidate.source.detail,candidate.source.detector,manifestFact,await fact(root,'other/tooling/feature-maintenance/verify.mjs'),await fact(root,VERIFIER)];
  requireFact(acceptance.ui&&Array.isArray(acceptance.ui.attachments)&&acceptance.ui.attachments.length>0,'没有UI附件产物');
  const recordFile=await checkFile(root,acceptance.ui.record),record=await readJson(root,recordFile.path);files.push(recordFile);
  requireFact(record.version===1&&record.kind==='local-ui-record'&&record.feature_id===feature.id&&record.game_code===feature.game_code&&record.capture_session_id===candidate.session_id,'UI记录与验收玩法或抓取会话不匹配');
  requireFact(record.synthetic===false||(synthetic&&record.synthetic===true),'生产验证不接受合成UI记录');
  requireFact(record.implementation_sha256===hash(canonical(implementation)),'UI测试时的源码/资源版本与当前版本不一致');
  requireFact(utc(record.started_at)&&utc(record.finished_at)&&Date.parse(record.started_at)<=Date.parse(record.finished_at)&&Date.parse(record.finished_at)<=Date.now()+60000,'UI测试时间无效');
  requireFact(typeof record.browser?.name==='string'&&record.browser.name.length>0&&typeof record.browser?.version==='string'&&record.browser.version.length>0,'UI记录缺少浏览器信息');
  const attachments=new Map();for(const item of acceptance.ui.attachments){await media(root,item);requireFact(!attachments.has(item.path),'UI附件重复');attachments.set(item.path,item);files.push(item);}
  const networkFile=await checkFile(root,record.network),network=await readJson(root,networkFile.path);files.push(networkFile);
  requireFact(network.version===1&&network.kind==='local-ui-network'&&network.feature_id===feature.id&&network.game_code===feature.game_code&&Array.isArray(network.records)&&network.records.length>0,'UI没有对应的实际本地接口记录');
  const origin=localUrl(network.origin).origin,requests=new Set();
  for(const item of network.records){
    requireFact(typeof item.request_id==='string'&&item.request_id.length>0&&!requests.has(item.request_id),'UI接口请求标识无效');
    requireFact(localUrl(item.url).origin===origin&&['GET','POST'].includes(item.method)&&item.response_status===200,'UI接口记录不是本地成功请求');
    requireFact(utc(item.at)&&Date.parse(item.at)>=Date.parse(record.started_at)&&Date.parse(item.at)<=Date.parse(record.finished_at),'UI接口时间不在验收期间');
    const response=await checkFile(root,item.response_body);requireFact((await fs.stat(await repoPath(root,response.path))).size>0,'UI接口响应产物为空');files.push(response);requests.add(item.request_id);
  }
  const actions=['navigate','trigger-feature','observe-result','reload','observe-restored'];
  requireFact(Array.isArray(record.events)&&record.events.length>=actions.length,'UI验收必须包含入口、触发、结果、刷新和恢复');
  let actionIndex=0,previous=Date.parse(record.started_at);
  for(const event of record.events){
    requireFact(utc(event.at)&&Date.parse(event.at)>=previous&&Date.parse(event.at)<=Date.parse(record.finished_at),'UI操作时间顺序无效');previous=Date.parse(event.at);
    requireFact(attachments.has(event.artifact),'UI步骤没有对应截图或录像');
    if(event.action===actions[actionIndex]){
      if(event.action==='navigate')requireFact(localUrl(event.url).origin===origin,'UI入口与接口记录不是同一本地服务');
      if(['trigger-feature','observe-result','observe-restored'].includes(event.action))requireFact(requests.has(event.request_id),'UI结果未关联实际响应文件');
      actionIndex++;
    }
  }
  requireFact(actionIndex===actions.length,'UI验收步骤缺失或顺序不正确');

  requireFact(Array.isArray(feature.test_files)&&feature.test_files.length>0,'未登记该玩法的专项测试文件');
  const tests=[];for(const name of feature.test_files){requireFact(/^other\/tests\/feature-maintenance\/[a-zA-Z0-9_-]+\.test\.mjs$/.test(name),'专项测试必须为登记目录内固定 .test.mjs 文件');tests.push(await checkFile(root,await fact(root,name)));}
  files.push(...tests);
  const verifier=await checkFile(root,options.executedVerifier),workbook=await fact(root,registry.workbook);
  requireFact(readiness.workbook_sha256===workbook.sha256,'readiness与维护表基线摘要不一致');
  const fingerprint=hash(canonical({evidence,implementation,files,readiness:await fact(root,READINESS),workbook:workbook.sha256}));
  if(options.cached?.fingerprint===fingerprint){
    for(const item of options.cached.report.validation.files)await checkFile(root,item);
    return {status:'verified',report:options.cached.report,fingerprint,cached:true};
  }
  const runDir=`${PRIVATE}/validation/${featureKey(feature)}-${randomUUID()}`,started=new Date().toISOString();
  const env={...process.env};for(const key of Object.keys(env))if(key==='NODE_OPTIONS'||key==='NODE_PATH'||key.startsWith('NODE_TEST_')||key.startsWith('GTT_'))delete env[key];
  env.GTT_FEATURE_ACCEPTANCE_PATH=await repoPath(root,acceptancePath);env.GTT_FEATURE_CANDIDATE_PATH=await repoPath(root,options.candidatePath);env.GTT_FEATURE_SYNTHETIC=synthetic?'1':'0';
  const result=await runFile(process.execPath,['--test','--test-reporter=tap',...await Promise.all(tests.map(t=>repoPath(root,t.path)))],{cwd:root,timeout:120000,env,signal});
  const outputPath=runDir+'/node-test.tap',output=await repoPath(root,outputPath,{missing:true});await fs.mkdir(path.dirname(output),{recursive:true});await fs.writeFile(output,result.stdout);
  const errorPath=runDir+'/node-test.stderr.txt';await fs.writeFile(await repoPath(root,errorPath,{missing:true}),result.stderr);
  const count=name=>Number(result.stdout.match(new RegExp('^# '+name+' (\\d+)\\s*$','m'))?.[1]??NaN);
  const passed=result.code===0&&count('tests')>0&&count('pass')>0&&['fail','cancelled','skipped','todo'].every(name=>count(name)===0);
  const runPath=runDir+'/run.json';await writeJson(root,runPath,{version:1,kind:'node-test-execution',synthetic,executable:process.execPath,args:['--test','--test-reporter=tap',...feature.test_files],started_at:started,finished_at:new Date().toISOString(),exit_code:result.code,tests:count('tests')||0,passed,stdout:await fact(root,outputPath),stderr:await fact(root,errorPath),input_fingerprint:fingerprint});
  requireFact(passed,'登记专项测试没有实际全部通过（空测试、跳过、TODO也不算通过）');
  files.push(await fact(root,outputPath),await fact(root,errorPath),await fact(root,runPath));
  // 测试可能运行较久，发布报告前重验输入，防止期间改代码或替换证据。
  for(const item of [...evidence,...implementation,...files,workbook])await checkFile(root,item);
  requireFact(same(await snapshot(root,feature.implementation_roots),implementation),'测试期间实现目录发生增删');
  const report={version:1,status:'verified',feature:identity(feature),target:{sheet:feature.sheet,cell:feature.cell,before:'❌',after:'✅'},workbook_sha256:workbook.sha256,evidence,implementation,validation:{passed:true,checks:['完整抓取协议检测重新执行通过','当前readiness同名实现included','完整源码资源快照一致','本地UI入口触发结果刷新恢复及响应产物可追溯','登记专项测试实际执行且无跳过失败','报告生成前输入重新核验'].map(name=>({name,passed:true})),files:[...new Map(files.map(f=>[f.path,f])).values()],verifier},created_at:new Date().toISOString()};
  return {status:'verified',report,fingerprint};
}
