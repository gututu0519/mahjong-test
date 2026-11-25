import {readFileSync,writeFileSync,mkdirSync,copyFileSync,existsSync,constants,unlinkSync,rmSync,readdirSync,lstatSync} from 'node:fs';
import {resolve,dirname,relative,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {randomBytes} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {createZip,extractArchive,artifactPath} from './archive.mjs';
import {digest,inventory,verifyInventory,verifyPair} from './game-bundle.mjs';
import {GAME_CODES} from '../dist/gateway/catalog.js';

const tools=dirname(fileURLToPath(import.meta.url)),args=process.argv.slice(2);
const option=(key,fallback)=>{const at=args.indexOf(key);if(at<0)return fallback;if(!args[at+1]||args[at+1].startsWith('--'))throw Error('Missing '+key);return args[at+1];};
const game=option('--game');if(!GAME_CODES.includes(game))throw Error('Supply a supported --game code');
const sourceRelease=option('--service-release');if(!sourceRelease)throw Error('Supply --service-release with a verified compute release directory');
const sourceDir=resolve(sourceRelease),source=JSON.parse(readFileSync(resolve(sourceDir,existsSync(resolve(sourceDir,'release.json'))?'release.json':'RELEASE.json'),'utf8'));
const artifact=source.artifacts.find(item=>item.name==='game-'+game);
if(!artifact||source.kind==='game-deployment-bundle')throw Error('Selected release has no independent compute package for '+game);
const workspace=resolve(process.env.GTT_WORKSPACE_ROOT??resolve(tools,'../../..'));
const buildId=option('--build-id',`gtt-node-game-bundle-${new Date().toISOString().replace(/[-:.]/g,'')}-${randomBytes(3).toString('hex')}`);
if(buildId.length>96||!/^gtt-node-[A-Za-z0-9_-]+$/.test(buildId))throw Error('Invalid build id');
const output=resolve(workspace,'other/diagnostics/releases',buildId);
const delivery=resolve(workspace,'update','game-'+game);
if(existsSync(output))throw Error('Build directory already exists; choose a new build id');
mkdirSync(output,{recursive:true});
const archive=artifactPath(sourceDir,source,artifact),archiveBytes=readFileSync(archive);
if(digest(archiveBytes)!==artifact.sha256||archiveBytes.length!==artifact.size)throw Error('Source compute archive checksum mismatch');
const unpack=resolve(output,'source-service');mkdirSync(unpack);
extractArchive(archive,unpack);
const serveSource=resolve(unpack,artifact.name),serviceManifest=JSON.parse(readFileSync(resolve(serveSource,'release-manifest.json'),'utf8'));
verifyInventory(serveSource,serviceManifest.files,['release-manifest.json']);
if(serviceManifest.build_id!==source.build_id)throw Error('Compute manifest release mismatch');
let client=option('--client-bundle');
if(!client) {
  const command=[resolve(tools,'build-frontend.mjs'),'--game',game,'--output',resolve(output,'frontend-build')];
  if(option('--source'))command.push('--source',resolve(option('--source')));
  client=JSON.parse(execFileSync(process.execPath,command,{cwd:resolve(tools,'..'),env:process.env,encoding:'utf8',windowsHide:true,maxBuffer:1024*1024})).bundle;
}
client=resolve(client);
const pair=verifyPair(serveSource,client,game);
if(pair.identity.release!==source.build_id)throw Error('Compute identity differs from source release record');
const clientName=`${game}-client-${pair.manifest.release}`,serveName=`${game}-serve-${pair.identity.release}`;
const tree=resolve(output,'bundle');mkdirSync(tree);
/** 独占复制交付文件，保留已存在的版本。 */
function copyFile(from,to) {mkdirSync(dirname(to),{recursive:true});copyFileSync(from,to,constants.COPYFILE_EXCL);}
for(const file of inventory(serveSource))copyFile(resolve(serveSource,file.path),resolve(tree,serveName,file.path));
const privateName=`gateway-${pair.manifest.release}`,privateStage=resolve(tree,privateName);
copyFile(resolve(client,'manifest.json'),resolve(privateStage,'manifest.json'));
for(const file of pair.manifest.files)copyFile(resolve(client,'objects',file.path),resolve(tree,clientName,file.path));
for(const file of pair.manifest.bootstrap)copyFile(resolve(client,'bootstrap',file.path),resolve(privateStage,'bootstrap',file.path));
copyFile(resolve(tools,'install-delivery-frontend.mjs'),resolve(privateStage,'install-delivery-frontend.mjs'));
verifyInventory(resolve(tree,serveName),serviceManifest.files,['release-manifest.json']);
const startup=[
  '# 单游戏分目录交付', '', `游戏：${game}。`, '',
  `- 客户端目录：${clientName}`,`- 计算服务目录：${serveName}`,
  '- 两个目录保留各自真实版本；外层交付编号不是游戏服务或前端版本。RELEASE.json 记录配套关系。',
  '', '## 计算服务',
  `解压 ${serveName}.zip，进入包含 package.json 的 ${artifact.name}/ 配置实例并执行 npm start。相邻的 gateway 资料供网关安装，不放进计算实例。`,
  '建议在 serve 目录创建 game.env，仅放实例设置。游戏代码、版本和默认 config/game.json 由本包读取，不必将旧版本的 GAME_RELEASE/GAME_CONFIG 复制进新实例。',
  '```dotenv','GAME_BIND=127.0.0.1','GAME_PORT=8211',`GAME_SECRET_FILE=/www/wwwroot/gtt-node/config/secrets/${game}.key`,'```',
  '端口是示例；同机新旧版本并行时必须分配不同端口。密钥文件单独生成，不能包含平台数据库凭据。也可通过 npm start -- --env-file <实际路径> 指定配置。',
  '计算服务启动后在后台登记并激活；升级时保留旧计算版本直到已绑定回合结束。',
  '', '## 客户端',
  `把 ${clientName}/ 内全部内容原样上传到私有 S3 的 ${pair.manifest.prefix}/，不加 client 或 objects 路径层。配置该版本的 CloudFront 路由。`,
  `私有资料在 ${serveName}/${privateName}/。把两个交付目录并排放在服务器，从共同父目录执行（替换最后两个路径）：`,
  `\`\`\`sh\nnode ${serveName}/${privateName}/install-delivery-frontend.mjs /实际网关/tools/install-frontend.mjs /实际网关前端版本存储根目录\n\`\`\``,
  '安装脚本自动读取相邻 client 素材以满足现有网关安装器的完整校验；若素材在别处，追加该素材目录作为最后一个参数。',
  '前端目录生成不代表已经上传 S3 或开通 CDN。完成发布、登记与激活后，再在后台点击“检查并开放”。',
  '', '## 单独升级与验收边界',
  '仍可独立构建/发布客户端或计算服务；复用已有组件需通过构建时配套校验。完整包不自动部署数据库、商户钱包、域名、CDN 或开放游戏。',
  'serve ZIP 复用指定发布记录中已校验的计算包；本次目录调整不宣称已完成新的服务端依赖精简。',
  '本地清单、规则配置和协议匹配不能代替实际完整回合、钱包与生产 CDN 验收。',
].join('\n')+'\n';
writeFileSync(resolve(output,'START.md'),startup,{flag:'wx'});
writeFileSync(resolve(privateStage,'START.md'),startup,{flag:'wx'});
const privateFiles=inventory(privateStage);
const clientFiles=inventory(resolve(tree,clientName));
const serveFilename=serveName+'.zip';
let serveBytes=archiveBytes;
if(!archive.endsWith('.zip')) {
  const converted=resolve(output,serveFilename);createZip(serveSource,artifact.name,converted);
  serveBytes=readFileSync(converted);unlinkSync(converted);
}
const serveArchive={path:serveFilename,size:serveBytes.length,sha256:digest(serveBytes)};
const clientTarget=resolve(delivery,clientName),serveTarget=resolve(delivery,serveName);
// Reuse an immutable component only when its entire inventory is unchanged.
// Never replace an existing version or remove user files from update/.
const reuseClient=existsSync(clientTarget),reuseServe=existsSync(serveTarget);
if(reuseClient)verifyInventory(clientTarget,clientFiles);
const privateTarget=resolve(serveTarget,privateName);
if(reuseServe) {
  for(const entry of readdirSync(serveTarget,{withFileTypes:true}))if(!(entry.isFile()&&entry.name===serveFilename)&&!(entry.isDirectory()&&/^gateway-fe-[\w-]+$/.test(entry.name)))throw Error('Unexpected serve entry: '+entry.name);
  if(lstatSync(serveTarget).isSymbolicLink())throw Error('Unexpected serve link');
  const zip=readFileSync(resolve(serveTarget,serveFilename));
  if(zip.length!==serveArchive.size||digest(zip)!==serveArchive.sha256)throw Error('Existing compute ZIP differs');
}
if(existsSync(privateTarget))verifyInventory(privateTarget,privateFiles);
mkdirSync(delivery,{recursive:true});
if(!reuseClient) {
  mkdirSync(clientTarget);
  for(const file of clientFiles)copyFile(resolve(tree,clientName,file.path),resolve(clientTarget,file.path));
}
if(!reuseServe) {
  mkdirSync(serveTarget);
  writeFileSync(resolve(serveTarget,serveFilename),serveBytes,{flag:'wx'});
}
if(!existsSync(privateTarget))for(const file of privateFiles)copyFile(resolve(privateStage,file.path),resolve(privateTarget,file.path));
verifyInventory(clientTarget,clientFiles);verifyInventory(privateTarget,privateFiles);
const manifest={format:3,kind:'game-component-delivery',build_id:buildId,game,
  sources:{serve:source.source??null,client:pair.manifest.source??null},
  gateway:{directory:privateName,files:privateFiles},
  client:{directory:clientName,release:pair.manifest.release,format:'directory',files:clientFiles,manifest_sha256:digest(readFileSync(resolve(privateStage,'manifest.json'))),client_contract:pair.contract,s3_prefix:pair.manifest.prefix},
  serve:{directory:serveName,release:pair.identity.release,format:'zip',file:serveFilename,archive_root:artifact.name,sha256:serveArchive.sha256,size:serveArchive.size,entry_point:pair.service.entry_point,source_archive:artifact.file,source_sha256:artifact.sha256,source_manifest_sha256:digest(readFileSync(resolve(serveSource,'release-manifest.json')))},
  compatibility:{client_contract:pair.contract,rule_configuration:'matched',runtime_probe:'run smoke-game-bundle; see verification.json',production_cdn_verified:false},
  reused:{client:reuseClient,serve:reuseServe}};
// One canonical record: RELEASE.json and release.json cannot coexist on Windows.
writeFileSync(resolve(output,'RELEASE.json'),JSON.stringify({...manifest,built_at:new Date().toISOString(),artifact_directory:relative(output,delivery).split(sep).join('/'),artifacts:[{name:'game-'+game+'-serve',directory:serveName,file:serveFilename,format:'zip',size:serveBytes.length,sha256:digest(serveBytes)}],components:{client:manifest.client,serve:manifest.serve},validation:{manifest_and_rules:'verified',runtime:'pending',production_cdn:'not-deployed-by-builder'}},null,2)+'\n',{flag:'wx'});
rmSync(unpack,{recursive:true});
console.log(JSON.stringify({release_directory:output,client_directory:clientTarget,serve_directory:serveTarget,serve_archive:resolve(serveTarget,serveFilename),reused:manifest.reused}));
