import {readFileSync,writeFileSync,existsSync,mkdirSync,cpSync,copyFileSync,constants,rmSync,readdirSync} from 'node:fs';
import {resolve,dirname,relative} from 'node:path';
import {fileURLToPath} from 'node:url';
import {randomBytes} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {artifactPath,extractArchive} from './archive.mjs';
import {digest,verifyInventory,verifyPair,inventory} from './game-bundle.mjs';
import {GAME_CODES} from '../dist/gateway/catalog.js';
import {verifyFrontendBundle} from '../dist/shared/frontend-manifest.js';

const args=process.argv.slice(2),tools=dirname(fileURLToPath(import.meta.url));
if(args.includes('--legacy')){await import('./package-game-legacy.mjs');process.exit(0);}
/** 读取命令行选项，拒绝缺值。 */
function option(key){const i=args.indexOf(key);if(i<0)return;if(!args[i+1]||args[i+1].startsWith('--'))throw Error('Missing '+key);return args[i+1];}
const game=option('--game'),front=option('--client-version'),back=option('--service-version');
const pattern=/^v([1-9]\d{0,7})\.(0|[1-9]\d{0,7})$/;
if(!GAME_CODES.includes(game)||!pattern.test(front)||!pattern.test(back)||front.split('.')[0]!==back.split('.')[0])throw Error('请指定游戏与同主版本组件，例如 --game buffalo-win --client-version v1.0 --service-version v1.0');
const workspace=resolve(process.env.GTT_WORKSPACE_ROOT),releases=resolve(workspace,'other/diagnostics/releases'),delivery=resolve(workspace,'update','game-'+game);
const id=option('--build-id')??`gtt-node-${game}-${Date.now()}-${randomBytes(3).toString('hex')}`;
if(!/^gtt-node-[A-Za-z0-9_-]{1,78}$/.test(id))throw Error('Invalid build id');
const out=resolve(releases,id),clientName=`${game}-client-${front}`,serveName=`${game}-serve-${back}`,zip=serveName+'.zip';
const clientTarget=resolve(delivery,clientName),serveTarget=resolve(delivery,zip);
mkdirSync(releases,{recursive:true});mkdirSync(out);
const previous=readdirSync(releases).flatMap(name=>{
  const path=resolve(releases,name,'RELEASE.json');if(!existsSync(path))return [];
  const r=JSON.parse(readFileSync(path));return r.format===4&&r.game===game&&existsSync(resolve(dirname(path),'verification.json'))?[{r,path:dirname(path)}]:[];
});
const oldFront=previous.find(({r})=>r.client.release===front),oldBack=previous.find(({r})=>r.serve.release===back);
if((existsSync(clientTarget)&&!oldFront)||(existsSync(serveTarget)&&!oldBack))throw Error('目标版本没有已验证的来源记录，拒绝覆盖');
const client=resolve(out,'publication-bundle');
const supplied=option('--client-bundle');
const original=supplied??JSON.parse(execFileSync(process.execPath,[resolve(tools,'build-frontend.mjs'),'--game',game,'--remote-version',front,'--output',resolve(out,'frontend-build'),...(args.includes('--cdn-entry')?['--cdn-entry']:[]),...(option('--source')?['--source',option('--source')]:[])],{encoding:'utf8'})).bundle;
const built=verifyFrontendBundle(original);
if(built.game!==game||built.component_version!==front||!built.release.startsWith('fe-v'))throw Error('前端不是指定的固定路径版本');
if(oldFront){
  const prior=resolve(oldFront.path,'publication-bundle');
  if(digest(readFileSync(resolve(prior,'manifest.json')))!==oldFront.r.client.manifest_sha256||verifyFrontendBundle(prior).content_hash!==built.content_hash)throw Error('同版本前端文件已变化，请增加次版本');
  cpSync(prior,client,{recursive:true});
}else cpSync(original,client,{recursive:true});
let sourceDir=option('--service-release')??oldBack?.r.service_source;
if(!sourceDir){
  const assets=option('--assets-manifest');if(!assets)throw Error('首次构建计算版本需提供 --assets-manifest');
  execFileSync(process.execPath,[resolve(tools,'package.mjs'),'--artifact','game-'+game,'--service-version',back,'--build-id',id+'-compute','--assets-manifest',assets,...(args.includes('--with-dependencies')?['--with-dependencies']:[])],{stdio:'inherit'});
  sourceDir=resolve(releases,id+'-compute');
}else sourceDir=resolve(releases,sourceDir);
const source=JSON.parse(readFileSync(resolve(sourceDir,'release.json'))),artifact=source.artifacts.find(a=>a.name==='game-'+game);
const archive=artifactPath(sourceDir,source,artifact),bytes=readFileSync(archive);
if(artifact.format!=='zip'||bytes.length!==artifact.size||digest(bytes)!==artifact.sha256||(oldBack&&oldBack.r.serve.sha256!==artifact.sha256))throw Error('计算包来源校验失败');
const unpack=resolve(out,'unpacked');mkdirSync(unpack);extractArchive(archive,unpack);
const flat=existsSync(resolve(unpack,'package.json'));
const service=flat?unpack:resolve(unpack,artifact.name),pair=verifyPair(service,client,game),sm=readFileSync(resolve(service,'release-manifest.json'));
if(pair.identity.release!==back||JSON.parse(sm).build_id!==source.build_id)throw Error('计算包身份或来源版本不符');
verifyInventory(service,JSON.parse(sm).files,['release-manifest.json']);
const objects=resolve(client,'objects'),files=inventory(objects);
verifyInventory(objects,pair.manifest.files);
const c={directory:clientName,release:front,format:'directory',files,manifest_sha256:digest(readFileSync(resolve(client,'manifest.json'))),s3_prefix:pair.manifest.prefix};
const s={directory:serveName,release:back,format:'zip',file:zip,archive_root:flat?'':artifact.name,size:artifact.size,sha256:artifact.sha256,source_manifest_sha256:digest(sm)};
const record={format:4,kind:'game-component-delivery',game,build_id:id,client:c,serve:s,components:{client:c,serve:s},service_source:relative(releases,sourceDir),artifact_directory:relative(out,delivery),artifacts:[{file:zip,size:s.size,sha256:s.sha256}],private_prefix:`private/frontend/${game}/${front}`};
if(existsSync(clientTarget))verifyInventory(clientTarget,files);
if(existsSync(serveTarget)&&digest(readFileSync(serveTarget))!==s.sha256)throw Error('同版本计算 ZIP 不一致');
mkdirSync(delivery,{recursive:true});
let addedClient=false,addedServe=false;
try{
  if(!existsSync(clientTarget)){mkdirSync(clientTarget);addedClient=true;cpSync(objects,clientTarget,{recursive:true,errorOnExist:true,force:false});}
  if(!existsSync(serveTarget)){copyFileSync(archive,serveTarget,constants.COPYFILE_EXCL);addedServe=true;}
  writeFileSync(resolve(out,'RELEASE.json'),JSON.stringify(record,null,2)+'\n',{flag:'wx'});
  execFileSync(process.execPath,[resolve(tools,'smoke-game-bundle.mjs'),out],{stdio:'inherit'});
}catch(error){
  if(addedClient)rmSync(clientTarget,{recursive:true});if(addedServe)rmSync(serveTarget);throw error;
}
rmSync(unpack,{recursive:true});
writeFileSync(resolve(out,'START.md'),`# ${game} 前端 ${front} / 计算 ${back}\n\n在源码仓库根目录发布（不会由打包自动执行）：\n\n\`\`\`sh\nnode other/tooling/run.mjs publish-frontend other/diagnostics/releases/${id}/publication-bundle --bucket <私有桶> --owner <账号ID>\n\`\`\`\n\n服务器只上传 ${zip}。${flat?`解压到 games/${game}/${back}/，共享配置放在 games/${game}/game.env。在版本目录直接执行 npm start。`:`解压后进入 ${artifact.name}/ 配置 game.env 并执行 npm start。`} 后台按 ${front} 读取 S3，配对 ${back} 计算版本，再检查并开放。\n`);
console.log(JSON.stringify({client:clientTarget,serve:serveTarget,record:out}));
