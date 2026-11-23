import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {tmpdir} from 'node:os';
import {createServer} from 'node:http';
import {deflateSync} from 'node:zlib';
import {DEFAULT_ROOT,REGISTRY,READINESS,VERIFIER,DETECTOR,PRIVATE,hash,canonical,fact,writeJson,readJson,snapshot,verifyFeature,featureKey,runFile} from '../verify.mjs';
import {watchOnce,acquireLock,sanitizeDetail} from '../watch.mjs';

// 本文件所有完成案例均为隔离的合成框架测试，不代表任何真实玩法通过验收。
function png(){
  const crc=bytes=>{let n=0xffffffff;for(const byte of bytes){n^=byte;for(let i=0;i<8;i++)n=(n>>>1)^((n&1)?0xedb88320:0);}return (n^0xffffffff)>>>0;};
  const chunk=(name,data)=>{const label=Buffer.from(name),out=Buffer.alloc(data.length+12);out.writeUInt32BE(data.length);label.copy(out,4);data.copy(out,8);out.writeUInt32BE(crc(Buffer.concat([label,data])),data.length+8);return out;};
  const header=Buffer.alloc(13);header.writeUInt32BE(320,0);header.writeUInt32BE(240,4);header[8]=8;header[9]=2;
  return Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]),chunk('IHDR',header),chunk('IDAT',deflateSync(Buffer.alloc((320*3+1)*240))),chunk('IEND',Buffer.alloc(0))]);
}
async function fixture(t,{included=true,testBody}={}){
  const root=await fs.mkdtemp(path.join(tmpdir(),'synthetic-feature-pipeline-'));t.after(()=>fs.rm(root,{recursive:true,force:true}));
  const put=async(name,bytes)=>{const file=path.join(root,name);await fs.mkdir(path.dirname(file),{recursive:true});await fs.writeFile(file,bytes);};
  for(const name of ['other/tooling/feature-maintenance/verify.mjs',VERIFIER])await put(name,await fs.readFile(path.join(DEFAULT_ROOT,name)));
  const feature={id:'synthetic-game:complete',game_id:901,game_code:'synthetic-game',name:'合成测试功能',sheet:'Synthetic',cell:'C2',before:'❌',after:'✅',verifier:VERIFIER,test_files:['other/tests/feature-maintenance/synthetic-feature.test.mjs'],implementation_roots:['games/synthetic-game/backend','games/synthetic-game/frontend','games/synthetic-game/instance/config']};
  const workbook='other/docs/project/synthetic.xlsx';await put(workbook,'仅用于hash门禁的隔离合成占位，不是实际工作簿');
  await writeJson(root,REGISTRY,{version:1,synthetic_fixture:true,workbook,features:[feature],capture_sources:[{game_codes:[feature.game_code],launch_origins:['https://capture.synthetic.test'],api_origins:['https://api.synthetic.test']}]});
  await writeJson(root,READINESS,{version:1,workbook_sha256:(await fact(root,workbook)).sha256,games:[{id:901,code:'synthetic-game',special_features:[{name:feature.name,implementation:included?'included':'incomplete'}]}]});
  await put('games/synthetic-game/backend/engine.mjs','export const synthetic=true;\n');await put('games/synthetic-game/frontend/index.html','<p>synthetic</p>');await put('games/synthetic-game/instance/config/game.json','{"synthetic":true}');
  const session='a'.repeat(32),captureRoot=`other/capture/response-capture/captures/${session}`,bodyPath=captureRoot+'/bodies/000001.bin';await put(bodyPath,'synthetic-protocol-evidence');
  const detected={game_code:feature.game_code,feature_id:'synthetic',feature_name:feature.name,status:'evidence_complete',evidence:[{path:'bodies/000001.bin',sha256:(await fact(root,bodyPath)).sha256}],checks:[{name:'synthetic_full_chain',passed:true}],pending_reasons:[]};
  const output={version:1,session_id:session,features:[detected]};
  await put(DETECTOR,`# 仅供隔离框架测试的合成检测器\nimport json\nprint(json.dumps(json.loads(${JSON.stringify(JSON.stringify(output))})))\n`);
  const detailPath=PRIVATE+'/synthetic-detail.json',detail={id:session,url:'https://capture.synthetic.test/game',rows:[{id:1,url:'https://api.synthetic.test/game-api/synthetic-game/v4/Spin',state:'complete',status:200,body:'bodies/000001.bin'}]};await writeJson(root,detailPath,detail);
  await writeJson(root,captureRoot+'/manifest.json',{...detail,state:'completed'});
  const candidatePath=PRIVATE+'/synthetic-candidate.json';await writeJson(root,candidatePath,{version:1,session_id:session,source:{detail:await fact(root,detailPath),capture_root:captureRoot,detector:await fact(root,DETECTOR)},result:output});
  const implementation=await snapshot(root,feature.implementation_roots),framePath=PRIVATE+'/synthetic-frame.png';await put(framePath,png());
  const responsePath=PRIVATE+'/synthetic-response.json';await writeJson(root,responsePath,{synthetic:true,feature_id:feature.id,round_id:'fixture-round',result:'fixture-only'});
  const base=Date.now()-20000,at=offset=>new Date(base+offset).toISOString(),origin='http://127.0.0.1:12345';
  const networkPath=PRIVATE+'/synthetic-network.json';await writeJson(root,networkPath,{version:1,kind:'local-ui-network',feature_id:feature.id,game_code:feature.game_code,origin,records:[{request_id:'trigger',at:at(500),url:origin+'/game-api/synthetic-game/Spin',method:'POST',response_status:200,response_body:await fact(root,responsePath)},{request_id:'restored',at:at(2500),url:origin+'/game-api/synthetic-game/GameInfo/Get',method:'POST',response_status:200,response_body:await fact(root,responsePath)}]});
  const recordPath=PRIVATE+'/synthetic-ui.json';await writeJson(root,recordPath,{version:1,kind:'local-ui-record',synthetic:true,feature_id:feature.id,game_code:feature.game_code,capture_session_id:session,implementation_sha256:hash(canonical(implementation)),started_at:at(0),finished_at:at(3000),browser:{name:'synthetic',version:'fixture'},network:await fact(root,networkPath),events:[{at:at(100),action:'navigate',url:origin+'/game',artifact:framePath},{at:at(500),action:'trigger-feature',request_id:'trigger',artifact:framePath},{at:at(1000),action:'observe-result',request_id:'trigger',artifact:framePath},{at:at(2000),action:'reload',artifact:framePath},{at:at(2500),action:'observe-restored',request_id:'restored',artifact:framePath}]});
  const acceptancePath=PRIVATE+'/acceptance/'+featureKey(feature)+'.json';
  await writeJson(root,acceptancePath,{version:1,kind:'integrated-feature-acceptance',synthetic:true,feature:{id:feature.id,game_id:feature.game_id,game_code:feature.game_code,name:feature.name},capture:{session_id:session,candidate:await fact(root,candidatePath)},implementation,ui:{record:await fact(root,recordPath),attachments:[await fact(root,framePath)]},created_at:at(4000)});
  await put(feature.test_files[0],testBody??`import {test} from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';test('synthetic actual execution',()=>{const a=JSON.parse(fs.readFileSync(process.env.GTT_FEATURE_ACCEPTANCE_PATH));assert.equal(a.synthetic,true);assert.equal(process.env.GTT_FEATURE_SYNTHETIC,'1');fs.writeFileSync('actual-test-ran.txt','synthetic');});`);
  return {root,feature,workbook,candidatePath,acceptancePath,recordPath,framePath,put,verify:(extra={})=>verifyFeature({root,featureId:feature.id,candidatePath,acceptancePath,allowSynthetic:true,...extra})};
}

test('合成完成案例：实际执行登记测试，报告严格且不修改任何真实工作簿',async t=>{
  const f=await fixture(t),before=await fact(f.root,f.workbook),result=await f.verify();
  assert.equal(result.status,'verified',JSON.stringify(result));assert.equal(await fs.readFile(path.join(f.root,'actual-test-ran.txt'),'utf8'),'synthetic');
  assert.deepEqual(Object.keys(result.report).sort(),['version','status','feature','target','workbook_sha256','evidence','implementation','validation','created_at'].sort());
  assert.equal(result.report.validation.passed,true);assert.ok(result.report.validation.files.some(x=>x.path.endsWith('node-test.tap')));assert.deepEqual(await fact(f.root,f.workbook),before);
});
test('未实现项目即使提供完成声明仍保持pending',async t=>{const f=await fixture(t,{included:false}),result=await f.verify();assert.equal(result.status,'pending');assert.match(result.reasons.join(),/readiness/);await assert.rejects(fs.access(path.join(f.root,'actual-test-ran.txt')));});
test('candidate未完整不得执行专项或标绿',async t=>{const f=await fixture(t),candidate=await readJson(f.root,f.candidatePath);candidate.result.features[0].status='candidate';await writeJson(f.root,f.candidatePath,candidate);assert.equal((await f.verify()).status,'pending');await assert.rejects(fs.access(path.join(f.root,'actual-test-ran.txt')));});
test('源码hash过期保持pending',async t=>{const f=await fixture(t);await f.put('games/synthetic-game/backend/engine.mjs','export const changed=true;');const result=await f.verify();assert.equal(result.status,'pending');assert.match(result.reasons.join(),/hash/);});
test('仅passed布尔没有UI产物不能通过',async t=>{const f=await fixture(t),acceptance=await readJson(f.root,f.acceptancePath);acceptance.ui={passed:true};await writeJson(f.root,f.acceptancePath,acceptance);const result=await f.verify();assert.equal(result.status,'pending');assert.match(result.reasons.join(),/UI附件/);});
test('UI附件被替换保持pending',async t=>{const f=await fixture(t);await f.put(f.framePath,Buffer.from('changed'));const result=await f.verify();assert.equal(result.status,'pending');assert.match(result.reasons.join(),/已变化/);});
test('未显式启用隔离测试模式时拒绝synthetic记录',async t=>{const f=await fixture(t),result=await f.verify({allowSynthetic:false});assert.equal(result.status,'pending');assert.match(result.reasons.join(),/合成/);});
test('空测试或skip不能冒充实际验收通过',async t=>{const f=await fixture(t,{testBody:"import {test} from 'node:test';test.skip('synthetic skipped',()=>{});"}),result=await f.verify();assert.equal(result.status,'pending');assert.match(result.reasons.join(),/没有实际全部通过/);});
test('测试期间源码变化会被最终复查拒绝',async t=>{const f=await fixture(t,{testBody:"import {test} from 'node:test';import fs from 'node:fs';test('synthetic mutation',()=>{fs.writeFileSync('games/synthetic-game/backend/engine.mjs','changed during test');});"}),result=await f.verify();assert.equal(result.status,'pending');assert.match(result.reasons.join(),/已变化/);});
test('watch一次轮询无证据时只记录pending且不写表',async t=>{
  const f=await fixture(t),before=await fact(f.root,f.workbook),server=createServer((req,res)=>{res.setHeader('Content-Type','application/json');res.end('[]');});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>server.close(resolve)));
  const state=await watchOnce({root:f.root,captureUrl:'http://127.0.0.1:'+server.address().port});assert.equal(state.features[f.feature.id].status,'pending');assert.deepEqual(await fact(f.root,f.workbook),before);
});
test('监控互斥锁拒绝第二实例且退出后可重新获取',async t=>{const f=await fixture(t),release=await acquireLock(f.root);await assert.rejects(acquireLock(f.root),/已有监控/);await release();await (await acquireLock(f.root))();});
test('抓取快照仅保留相关API字段并移除查询参数和请求头',()=>{
  const features=[{game_code:'wild-bandito'}],row={id:1,url:'https://api.example/game-api/wild-bandito/v4/Spin?token=secret',method:'POST',state:'complete',status:200,mime:'application/octet-stream',body:'bodies/1.bin',request_body:'bodies/1.req',request_headers:{Authorization:'secret'},response_headers:{'set-cookie':'secret'}};
  const safe=sanitizeDetail({id:'session',url:'https://capture.example/game?secret',rows:[row,{...row,id:2,url:'https://assets.example/icon.png'}]},features,[{game_codes:['wild-bandito'],launch_origins:['https://capture.example'],api_origins:['https://api.example']}]);
  assert.deepEqual(safe,{id:'session',url:'https://capture.example/game',rows:[{url:'https://api.example/game-api/wild-bandito/v4/Spin',id:1,method:'POST',state:'complete',status:200,mime:'application/octet-stream',body:'bodies/1.bin',request_body:'bodies/1.req'}]});
});
test('实际网关g数字.localhost界面入口可验收',async t=>{
  const f=await fixture(t),record=await readJson(f.root,f.recordPath),network=await readJson(f.root,record.network.path);
  network.origin='http://g901.localhost:8110';for(const request of network.records)request.url=request.url.replace('http://127.0.0.1:12345',network.origin);
  await writeJson(f.root,record.network.path,network);record.network=await fact(f.root,record.network.path);record.events[0].url=network.origin+'/game';await writeJson(f.root,f.recordPath,record);
  const acceptance=await readJson(f.root,f.acceptancePath);acceptance.ui.record=await fact(f.root,f.recordPath);await writeJson(f.root,f.acceptancePath,acceptance);
  const result=await f.verify();assert.equal(result.status,'verified',JSON.stringify(result));
});
test('停止轮询不丢失已经保存的候选状态',async t=>{
  const f=await fixture(t),previous={version:1,sessions:{},features:{[f.feature.id]:{candidatePath:f.candidatePath,capture_status:'evidence_complete',status:'pending'}}};
  await writeJson(f.root,PRIVATE+'/status.json',previous);const controller=new AbortController();controller.abort();
  const state=await watchOnce({root:f.root,captureUrl:'http://127.0.0.1:1',signal:controller.signal});assert.equal(state.features[f.feature.id].candidatePath,f.candidatePath);
});
test('尚未保存完成manifest时只保留完整协议候选',async t=>{
  const f=await fixture(t),candidate=await readJson(f.root,f.candidatePath);await fs.unlink(path.join(f.root,candidate.source.capture_root,'manifest.json'));
  const result=await f.verify();assert.equal(result.status,'pending');assert.match(result.reasons.join(),/manifest/);
});
test('本机模拟响应即使协议完整也不能当作原始抓取',async t=>{
  const f=await fixture(t),candidate=await readJson(f.root,f.candidatePath),manifestPath=candidate.source.capture_root+'/manifest.json',manifest=await readJson(f.root,manifestPath);
  manifest.rows[0].url='http://g901.localhost:8110/game-api/synthetic-game/v4/Spin';await writeJson(f.root,manifestPath,manifest);
  const result=await f.verify();assert.equal(result.status,'pending');assert.match(result.reasons.join(),/本机响应/);
});
test('watch拒绝本机启动来源及未登记原站',()=>{
  const policy=[{game_codes:['wild-bandito'],launch_origins:['https://capture.example'],api_origins:['https://api.example']}];
  assert.throws(()=>sanitizeDetail({id:'x',url:'http://localhost:8110/game',rows:[]},[{game_code:'wild-bandito'}],policy),/启动来源/);
  assert.throws(()=>sanitizeDetail({id:'x',url:'https://capture.example/game',rows:[{url:'http://g4.localhost:8110/game-api/wild-bandito/v4/Spin'}]},[{game_code:'wild-bandito'}],policy),/API来源/);
});
test('未支持来源的PP保持pending，不猜测或自动接纳API域名',()=>{
  const policy=[{game_codes:['wild-bandito'],launch_origins:['https://capture.example'],api_origins:['https://api.example']}];
  const detail=sanitizeDetail({id:'x',url:'https://capture.example/',rows:[{url:'https://unknown.example/game-api/sweet-bonanza-pop/v3/Spin'}]},[{game_code:'sweet-bonanza-pop'}],policy);
  assert.deepEqual(detail.rows,[]);
});
test('--once正常pending退出0，API失败退出非0且清理锁',async t=>{
  const f=await fixture(t);for(const name of ['watch.mjs','update-workbook.mjs'])await f.put('other/tooling/feature-maintenance/'+name,await fs.readFile(path.join(DEFAULT_ROOT,'other/tooling/feature-maintenance',name)));
  let failed=false;const server=createServer((req,res)=>{res.statusCode=failed?500:200;res.setHeader('Content-Type','application/json');res.end('[]');});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>server.close(resolve)));
  const args=[path.join(f.root,'other/tooling/feature-maintenance/watch.mjs'),'--once','--capture-url','http://127.0.0.1:'+server.address().port];
  assert.equal((await runFile(process.execPath,args,{cwd:f.root})).code,0);failed=true;assert.notEqual((await runFile(process.execPath,args,{cwd:f.root})).code,0);
  await assert.rejects(fs.access(path.join(f.root,PRIVATE,'.watch.lock')));
});
test('自动子进程通过固定stop行或EOF优雅退出并清理自己的锁',async t=>{
  const f=await fixture(t);for(const name of ['watch.mjs','update-workbook.mjs'])await f.put('other/tooling/feature-maintenance/'+name,await fs.readFile(path.join(DEFAULT_ROOT,'other/tooling/feature-maintenance',name)));
  const server=createServer((req,res)=>{res.setHeader('Content-Type','application/json');res.end('[]');});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>server.close(resolve)));
  const args=[path.join(f.root,'other/tooling/feature-maintenance/watch.mjs'),'--parent-pipe','--capture-url','http://127.0.0.1:'+server.address().port];
  for(const input of ['stop\n','']){const result=await runFile(process.execPath,args,{cwd:f.root,input,timeout:5000});assert.equal(result.code,0);await assert.rejects(fs.access(path.join(f.root,PRIVATE,'.watch.lock')));}
});
