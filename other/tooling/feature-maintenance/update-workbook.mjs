import fs from 'node:fs/promises';
import {existsSync,renameSync} from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {createHash,randomUUID} from 'node:crypto';
import {createRequire} from 'node:module';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
const execFileAsync=promisify(execFile);

const DEFAULT_ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const REGISTRY='other/tooling/feature-maintenance/features.json';
const READINESS='gateway/config/game-readiness.json';
const VERIFIERS='other/tooling/feature-maintenance/verifiers/';
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const assert=(condition,reason)=>{if(!condition)throw Object.assign(new Error(reason),{rejected:true});};
const digest=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
const xmlDecode=value=>value.replace(/&(?:#x([0-9a-f]+)|#([0-9]+)|(amp|lt|gt|quot|apos));/gi,(_,hex,dec,name)=>hex?String.fromCodePoint(parseInt(hex,16)):dec?String.fromCodePoint(Number(dec)):({amp:'&',lt:'<',gt:'>',quot:'"',apos:"'"})[name.toLowerCase()]);
const xmlEscape=value=>value.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
function attributes(tag){return Object.fromEntries([...tag.matchAll(/([\w:.-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')/g)].map(m=>[m[1],xmlDecode(m[2]??m[3])]));}
function within(root,file){const rel=path.relative(root,file);return rel!==''&&!rel.startsWith('..'+path.sep)&&rel!=='..'&&!path.isAbsolute(rel);}
async function repoFile(root,relative){
  assert(typeof relative==='string'&&relative.length>0&&!relative.includes('\0')&&!path.isAbsolute(relative)&&!relative.includes('\\')&&!relative.includes(':'),'文件路径必须为仓库内相对路径');
  const file=path.resolve(root,relative);assert(within(root,file),'文件路径越过仓库边界');
  const real=await fs.realpath(file);assert(within(root,real),'文件链接指向仓库之外');
  assert((await fs.stat(real)).isFile(),'证据路径必须指向文件');return real;
}
async function verifyFiles(root,items,label){
  assert(Array.isArray(items)&&items.length>0,`${label}不能为空`);
  for(const item of items){assert(item&&digest(item.sha256),`${label}缺少有效摘要`);const file=await repoFile(root,item.path);assert(sha(await fs.readFile(file))===item.sha256,`${label}文件已变化：${item.path}`);}
}
async function dependencies(root,moduleDirectory){
  const directory=path.resolve(moduleDirectory||process.env.ARTIFACT_NODE_MODULES||path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'));
  assert(!within(root,directory),'不得使用仓库内依赖为维护表写入');
  const require=createRequire(path.join(directory,'__feature_maintenance__.cjs'));
  const artifact=await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
  const JSZip=require('jszip');return {...artifact,JSZip};
}
async function zipXml(zip,name){const entry=zip.file(name);assert(entry,`工作簿缺少部件：${name}`);return entry.async('string');}
async function worksheetPath(zip,sheet){
  const workbook=await zipXml(zip,'xl/workbook.xml');
  const sheets=[...workbook.matchAll(/<(?:\w+:)?sheet\b[^>]*\/>/g)].map(x=>attributes(x[0])).filter(x=>x.name===sheet);
  assert(sheets.length===1,'工作表名称不唯一或不存在');
  const relations=await zipXml(zip,'xl/_rels/workbook.xml.rels');
  const relation=[...relations.matchAll(/<(?:\w+:)?Relationship\b[^>]*\/>/g)].map(x=>attributes(x[0])).find(x=>x.Id===sheets[0]['r:id']);
  assert(relation&&relation.TargetMode!=='External','工作表关系无效');
  const target=relation.Target.startsWith('/')?relation.Target.slice(1):path.posix.normalize('xl/'+relation.Target);
  assert(target.startsWith('xl/worksheets/')&&!target.includes('..'),'工作表部件越界');return target;
}
function cellNode(xml,address){
  const nodes=[...xml.matchAll(/<(?:\w+:)?c\b[^>]*(?:\/>|>[\s\S]*?<\/(?:\w+:)?c>)/g)].map(x=>x[0]).filter(x=>attributes(x.slice(0,x.indexOf('>')+1)).r===address);
  assert(nodes.length===1,'目标单元格不存在或重复');assert(!/<(?:\w+:)?f\b/.test(nodes[0]),'不能覆盖公式单元格');return nodes[0];
}
async function sharedStrings(zip){
  if(!zip.file('xl/sharedStrings.xml'))return [];
  return [...(await zipXml(zip,'xl/sharedStrings.xml')).matchAll(/<(?:\w+:)?si\b[^>]*>([\s\S]*?)<\/(?:\w+:)?si>/g)].map(x=>[...x[1].matchAll(/<(?:\w+:)?t\b[^>]*>([\s\S]*?)<\/(?:\w+:)?t>/g)].map(t=>xmlDecode(t[1])).join(''));
}
async function cellValue(zip,node){
  const attrs=attributes(node.slice(0,node.indexOf('>')+1));
  if(attrs.t==='s'){const index=Number(node.match(/<(?:\w+:)?v\b[^>]*>(\d+)<\/(?:\w+:)?v>/)?.[1]);return (await sharedStrings(zip))[index];}
  if(attrs.t==='inlineStr')return [...node.matchAll(/<(?:\w+:)?t\b[^>]*>([\s\S]*?)<\/(?:\w+:)?t>/g)].map(x=>xmlDecode(x[1])).join('');
  return xmlDecode(node.match(/<(?:\w+:)?v\b[^>]*>([\s\S]*?)<\/(?:\w+:)?v>/)?.[1]??'');
}
// Artifact Tool 负责编辑值；合并其已验证结果时保留原包全部非目标内容。
// 已确认该版本整包导出会改变原条件格式背景，因此不能直接替换整个导出文件。
async function preserveWorkbook(JSZip,original,authored,target){
  const source=await JSZip.loadAsync(original,{checkCRC32:true}),exported=await JSZip.loadAsync(authored,{checkCRC32:true});
  const part=await worksheetPath(source,target.sheet),exportPart=await worksheetPath(exported,target.sheet);
  const sourceXml=await zipXml(source,part),oldNode=cellNode(sourceXml,target.cell),authoredNode=cellNode(await zipXml(exported,exportPart),target.cell);
  assert(await cellValue(source,oldNode)===target.before,'原始单元格不是登记的未完成标记');
  const after=await cellValue(exported,authoredNode);assert(after===target.after,'Artifact 导出值与验收报告不一致');
  const attrs=attributes(oldNode.slice(0,oldNode.indexOf('>')+1));let nextNode;
  if(attrs.t==='s'){
    const index=(await sharedStrings(source)).indexOf(after);assert(index>=0,'原表不存在目标共享字符串，不能保证最小合并');
    nextNode=oldNode.replace(/(<(?:\w+:)?v\b[^>]*>)\d+(<\/(?:\w+:)?v>)/,(_,start,end)=>start+index+end);
  }else if(attrs.t==='inlineStr'){
    assert([...oldNode.matchAll(/<(?:\w+:)?t\b/g)].length===1,'富文本标记不支持最小合并');
    nextNode=oldNode.replace(/(<(?:\w+:)?t\b[^>]*>)[\s\S]*?(<\/(?:\w+:)?t>)/,`$1${xmlEscape(after)}$2`);
  }else if(attrs.t==='str'){
    nextNode=oldNode.replace(/(<(?:\w+:)?v\b[^>]*>)[\s\S]*?(<\/(?:\w+:)?v>)/,(_,start,end)=>start+xmlEscape(after)+end);
  }else throw Object.assign(new Error('目标单元格不是文本类型'),{rejected:true});
  assert(nextNode!==oldNode,'单元格替换没有生效');
  source.file(part,sourceXml.replace(oldNode,nextNode),{createFolders:false});
  const bytes=await source.generateAsync({type:'nodebuffer',compression:'DEFLATE',compressionOptions:{level:6}});
  const result=await JSZip.loadAsync(bytes,{checkCRC32:true});
  const baseline=await JSZip.loadAsync(original,{checkCRC32:true});
  assert(JSON.stringify(Object.keys(result.files).sort())===JSON.stringify(Object.keys(baseline.files).sort()),'工作簿部件发生增删');
  for(const name of Object.keys(baseline.files)){
    if(baseline.files[name].dir)continue;
    if(name===part){assert(await zipXml(result,name)===sourceXml.replace(oldNode,nextNode),'目标工作表有范围外变化');continue;}
    assert(sha(await baseline.file(name).async('nodebuffer'))===sha(await result.file(name).async('nodebuffer')),`无关部件发生变化：${name}`);
  }
  assert(await cellValue(result,cellNode(await zipXml(result,part),target.cell))===target.after,'合并后目标值验证失败');return bytes;
}
function previewRange(cell){const row=Number(cell.match(/\d+$/)[0]);return `A${Math.max(1,row-2)}:${cell.match(/^[A-Z]+/)[0]}${row+2}`;}
async function stageWorkbook(root,original,target,job,moduleDirectory){
  const {FileBlob,SpreadsheetFile,JSZip}=await dependencies(root,moduleDirectory);
  const source=path.join(job,'source.xlsx');await fs.writeFile(source,original,{flag:'wx'});
  const workbook=await SpreadsheetFile.importXlsx(await FileBlob.load(source));
  const sheet=workbook.worksheets.getItem(target.sheet),range=sheet.getRange(target.cell);
  assert(range.values[0][0]===target.before,'表格当前值不符合登记的未完成标记');
  const before=await workbook.render({sheetName:target.sheet,range:previewRange(target.cell),scale:1,format:'png'});
  await fs.writeFile(path.join(job,'before.png'),new Uint8Array(await before.arrayBuffer()));
  range.values=[[target.after]];workbook.recalculate();assert(range.values[0][0]===target.after,'目标值回读不一致');
  const after=await workbook.render({sheetName:target.sheet,range:previewRange(target.cell),scale:1,format:'png'});
  await fs.writeFile(path.join(job,'after.png'),new Uint8Array(await after.arrayBuffer()));
  const authored=path.join(job,'artifact-authored.xlsx');await (await SpreadsheetFile.exportXlsx(workbook)).save(authored);
  const bytes=await preserveWorkbook(JSZip,original,await fs.readFile(authored),target);
  const verified=path.join(job,'verified.xlsx');await fs.writeFile(verified,bytes,{flag:'wx'});
  const reopened=await SpreadsheetFile.importXlsx(await FileBlob.load(verified));
  assert(reopened.worksheets.getItem(target.sheet).getRange(target.cell).values[0][0]===target.after,'最终文件重新导入核验失败');
  return bytes;
}
async function backup(file,bytes){try{await fs.writeFile(file,bytes,{flag:'wx'});}catch(error){if(error.code!=='EEXIST')throw error;assert(sha(await fs.readFile(file))===sha(bytes),'备份文件摘要不一致');}}
async function writeJson(file,value){await fs.writeFile(file,JSON.stringify(value,null,2)+'\n');}

export async function updateWorkbook(options={}){
  let lockHandle,lockFile;const temporary=[];
  try{
    const root=await fs.realpath(options.root||DEFAULT_ROOT);
    const reportPath=await repoFile(root,path.relative(root,path.resolve(root,options.report||options.reportPath||'')).replaceAll('\\','/'));
    const reportBytes=await fs.readFile(reportPath),report=JSON.parse(reportBytes),reportHash=sha(reportBytes);
    assert(report.version===1&&report.status==='verified'&&report.feature&&report.target&&digest(report.workbook_sha256),'验收报告格式无效');
    assert(typeof report.created_at==='string'&&!Number.isNaN(Date.parse(report.created_at)),'验收报告缺少有效时间');
    const registryFile=await repoFile(root,REGISTRY),registryBytes=await fs.readFile(registryFile),registry=JSON.parse(registryBytes);
    assert(registry.version===1&&Array.isArray(registry.features),'功能登记格式无效');
    const matches=registry.features.filter(x=>x.id===report.feature.id);assert(matches.length===1,'功能必须唯一登记');const registered=matches[0];
    for(const key of ['id','game_id','game_code','name'])assert(registered[key]===report.feature[key],`功能身份不匹配：${key}`);
    for(const key of ['sheet','cell','before','after'])assert(registered[key]===report.target[key],`单元格登记不匹配：${key}`);
    assert(report.target.before==='❌'&&report.target.after==='✅'&&/^[A-Z]{1,3}[1-9]\d{0,6}$/.test(report.target.cell),'只允许登记的未完成格转为验收完成');
    if(!registered.verifier)return {status:'pending',reason:'该功能尚未登记验证器'};
    assert(typeof registered.verifier==='string'&&registered.verifier.startsWith(VERIFIERS)&&registered.verifier.endsWith('.mjs')&&path.posix.normalize(registered.verifier)===registered.verifier,'验证器必须位于登记目录');
    assert(report.validation?.passed===true&&Array.isArray(report.validation.checks)&&report.validation.checks.length>0&&report.validation.checks.every(x=>x&&typeof x.name==='string'&&x.name.length>0&&x.passed===true),'验收检查未全部通过');
    assert(report.validation.verifier?.path===registered.verifier&&digest(report.validation.verifier.sha256),'验证器身份不匹配');
    await verifyFiles(root,[report.validation.verifier],'验证器');
    await verifyFiles(root,report.evidence,'原始证据');await verifyFiles(root,report.implementation,'实现');await verifyFiles(root,report.validation.files,'验收记录');
    assert(report.validation.files.some(x=>x.path===registered.verifier&&x.sha256===report.validation.verifier.sha256),'验收文件必须包含当前验证器');
    const workbookPath=await repoFile(root,registry.workbook),readinessPath=await repoFile(root,READINESS);
    const readinessBytes=await fs.readFile(readinessPath),readiness=JSON.parse(readinessBytes);
    const games=readiness.games.filter(x=>x.id===registered.game_id&&x.code===registered.game_code);
    const features=games.length===1?games[0].special_features.filter(x=>x.name===registered.name):[];
    if(features.length!==1||features[0].implementation!=='included')return {status:'pending',reason:'该玩法尚未在当前实现登记中标记 included'};
    const lockExcel=path.join(path.dirname(workbookPath),'~$'+path.basename(workbookPath));
    if(existsSync(lockExcel))return {status:'pending',reason:'维护表正在 Excel 中打开，保留原文件'};
    const stateDir=path.resolve(root,options.stateDir||'other/diagnostics/feature-maintenance/state');
    assert(within(root,stateDir),'状态目录必须位于当前仓库内');
    try{await execFileAsync('git',['-C',root,'check-ignore','--quiet','--no-index','--',path.relative(root,path.join(stateDir,'.probe'))]);}catch{assert(false,'状态目录必须被当前仓库 Git 忽略');}
    await fs.mkdir(stateDir,{recursive:true});
    assert(within(root,await fs.realpath(stateDir)),'状态目录链接越过仓库边界');
    const receiptFile=path.join(stateDir,`receipt-${reportHash}.json`),original=await fs.readFile(workbookPath),originalHash=sha(original);
    if(originalHash!==report.workbook_sha256){
      if(existsSync(receiptFile)){const receipt=JSON.parse(await fs.readFile(receiptFile,'utf8'));if(receipt.report_sha256===reportHash&&receipt.workbook_sha256===originalHash&&readiness.workbook_sha256===originalHash)return {status:'updated',changed:false,workbook_sha256:originalHash};}
      return {status:'pending',reason:'维护表已变化，需要重新生成对应版本的验收报告'};
    }
    if(readiness.workbook_sha256!==originalHash)return {status:'pending',reason:'维护表摘要与实现登记不一致，需先核对基线'};
    if(options.dryRun===true)return {status:'pending',reason:'只读预检通过，未执行工作簿写入'};
    lockFile=path.join(path.dirname(workbookPath),'.feature-maintenance.lock');
    try{lockHandle=await fs.open(lockFile,'wx');}catch(error){if(error.code==='EEXIST')return {status:'pending',reason:'已有维护表更新操作或未完成事务，请检查锁记录'};throw error;}
    await lockHandle.writeFile(JSON.stringify({pid:process.pid,report_sha256:reportHash,created_at:new Date().toISOString()}));
    const job=path.join(stateDir,`${registered.id.replace(/[^A-Za-z0-9_-]/g,'_')}-${randomUUID()}`);await fs.mkdir(job);
    const nextWorkbook=await stageWorkbook(root,original,report.target,job,options.artifactNodeModules);
    const nextHash=sha(nextWorkbook),nextReadiness={...readiness,workbook_sha256:nextHash};
    const nextReadinessBytes=Buffer.from(JSON.stringify(nextReadiness,null,2)+'\n');
    const backupDir=path.join(stateDir,'backups');await fs.mkdir(backupDir,{recursive:true});
    await backup(path.join(backupDir,`${originalHash}.xlsx`),original);await backup(path.join(backupDir,`${sha(readinessBytes)}.readiness.json`),readinessBytes);
    const workbookStage=path.join(path.dirname(workbookPath),`.feature-${randomUUID()}.tmp.xlsx`),readinessStage=path.join(path.dirname(readinessPath),`.feature-${randomUUID()}.tmp.json`);
    temporary.push(workbookStage,readinessStage);await fs.writeFile(workbookStage,nextWorkbook,{flag:'wx'});await fs.writeFile(readinessStage,nextReadinessBytes,{flag:'wx'});
    if(options.beforeCommit)await options.beforeCommit({workbookPath,readinessPath});
    assert(sha(await fs.readFile(reportPath))===reportHash&&sha(await fs.readFile(registryFile))===sha(registryBytes),'验收报告或功能登记在生成期间发生变化');
    await verifyFiles(root,[report.validation.verifier],'验证器');
    await verifyFiles(root,report.evidence,'原始证据');await verifyFiles(root,report.implementation,'实现');await verifyFiles(root,report.validation.files,'验收记录');
    if(existsSync(lockExcel))return {status:'pending',reason:'写入前发现 Excel 已打开维护表，未覆盖原表'};
    if(sha(await fs.readFile(workbookPath))!==originalHash||sha(await fs.readFile(readinessPath))!==sha(readinessBytes))return {status:'pending',reason:'写入前基线已变化，已取消覆盖'};
    // 最后一次检查后同步提交两份文件；第二步失败则立即恢复第一步。
    const journal=path.join(job,'transaction.json');await writeJson(journal,{state:'prepared',workbook:registry.workbook,before:originalHash,after:nextHash,readiness_before:sha(readinessBytes),readiness_after:sha(nextReadinessBytes)});
    try{renameSync(workbookStage,workbookPath);renameSync(readinessStage,readinessPath);}
    catch(error){
      if(sha(await fs.readFile(workbookPath))===nextHash){const rollback=path.join(path.dirname(workbookPath),`.feature-${randomUUID()}.rollback.xlsx`);temporary.push(rollback);await fs.writeFile(rollback,original,{flag:'wx'});renameSync(rollback,workbookPath);}
      await writeJson(journal,{state:'rolled-back',reason:error.code||error.message});throw error;
    }
    assert(sha(await fs.readFile(workbookPath))===nextHash&&JSON.parse(await fs.readFile(readinessPath,'utf8')).workbook_sha256===nextHash,'提交后摘要核验失败');
    await writeJson(journal,{state:'committed',before:originalHash,after:nextHash});
    await writeJson(receiptFile,{report_sha256:reportHash,workbook_sha256:nextHash,feature:registered.id,target:report.target,updated_at:new Date().toISOString()});
    return {status:'updated',changed:true,workbook_sha256:nextHash,feature_id:registered.id,target:report.target,verification_directory:path.relative(root,job).replaceAll('\\','/')};
  }catch(error){return {status:error.rejected?'rejected':'pending',reason:error.message};}
  finally{for(const file of temporary)await fs.unlink(file).catch(()=>{});if(lockHandle){await lockHandle.close();await fs.unlink(lockFile).catch(()=>{});}}
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const args=process.argv.slice(2),values={};
  for(let i=0;i<args.length;i+=2){if(!['--report','--state-dir'].includes(args[i])||!args[i+1])throw Error('用法：--report <仓库内报告路径> --state-dir <本地忽略目录>');values[args[i]]=args[i+1];}
  const result=await updateWorkbook({report:values['--report'],stateDir:values['--state-dir']});console.log(JSON.stringify(result));if(result.status==='rejected')process.exitCode=1;
}
