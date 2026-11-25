import {
  readFileSync,
  writeFileSync,
  mkdirSync,
  readdirSync,
  copyFileSync,
  statSync,
  existsSync,
  constants,
  unlinkSync,
} from "node:fs";
import { resolve, dirname, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash,randomBytes } from "node:crypto";
import { execFileSync } from "node:child_process";
import { repairModule } from "../dist/gateway/assets.js";
import {createZip} from './archive.mjs';
import {packageAdmin} from './package-admin.mjs';
import {GAME_CODES} from '../dist/gateway/catalog.js';
import {verifyFrontendBundle,frontendFile} from '../dist/shared/frontend-manifest.js';

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repo = resolve(root, "..");
const args = process.argv.slice(2);
const withDependencies=args.includes('--with-dependencies');
function option(name, fallback) {
  const at = args.indexOf(name);
  if (at < 0) return fallback;
  if (!args[at + 1] || args[at + 1].startsWith("--"))
    throw new Error(`Missing ${name}`);
  return args[at + 1];
}
const selectedArtifact=option('--artifact');
const allArtifacts=args.includes('--all');
if(allArtifacts&&selectedArtifact)throw Error('Use either --artifact <one product> or explicit --all, not both');
if(!allArtifacts&&!selectedArtifact)throw Error('默认不批量打包。请指定 --artifact <单个产物>；只有明确需要全量时才使用 --all。单游戏前后端使用 npm run game:package -- --game <代码> ...');
if(selectedArtifact&&!['gateway','admin','mock-platform','buffalo-win','all-services','frontend','infra',...GAME_CODES.map(code=>'game-'+code)].includes(selectedArtifact))throw Error('Unknown artifact: '+selectedArtifact);
const sha = (data) => createHash("sha256").update(data).digest("hex");
const write = (path, data) => {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(
    path,
    typeof data === "string" ? data : JSON.stringify(data, null, 2) + "\n",
    { flag: "wx" },
  );
};
const buildId = option(
  "--build-id",
  `gtt-node-${new Date().toISOString().replace(/[-:.]/g, "")}-${randomBytes(3).toString("hex")}`,
);
if (buildId.length>96 || !/^gtt-node-[A-Za-z0-9_-]+$/.test(buildId))
  throw new Error("Invalid build id");
const serviceVersion=option('--service-version');
if(serviceVersion&&(!/^v[1-9]\d{0,7}\.(0|[1-9]\d{0,7})$/.test(serviceVersion)||!GAME_CODES.some(c=>selectedArtifact==='game-'+c)))throw Error('正式服务版本仅用于单款游戏');
const runtimeRelease=serviceVersion??buildId;
const manifestPath = option("--assets-manifest");
if (!manifestPath)
  throw new Error(
    "Supply --assets-manifest with the verified Buffalo S3 manifest",
  );
const raw = readFileSync(resolve(manifestPath));
const assets = JSON.parse(raw);
const remoteAssets=typeof assets.component_version==='string'&&/^v[1-9]\d{0,7}\.(0|[1-9]\d{0,7})$/.test(assets.component_version)&&
  assets.release===`fe-${assets.component_version.replace('.','-')}-g${GAME_CODES.indexOf('buffalo-win')+1}`;
const frontendRelease = assets.format === 3 && assets.kind === "game-client" &&
  (remoteAssets||/^fe-\d{17}-[a-f0-9]{8}-[a-f0-9]{6}$/.test(assets.release)) &&
  /^[a-f0-9]{64}$/.test(assets.manifest_sha256);
if (
  assets.game !== "buffalo-win" ||
  (!frontendRelease && !/^[a-f0-9]{20}$/.test(assets.release)) ||
  !assets.files?.length ||
  assets.prefix !== `releases/buffalo-win/${remoteAssets?assets.component_version:assets.release}`
)
  throw new Error("Invalid S3 manifest");
const client = resolve(repo, "clients/buffalo-win");
const seen = new Set();
// Check actual Node-prepared bytes against the existing published asset version.
// This reads local assets only; packaging never uploads or changes S3.
for (const file of assets.files) {
  if (
    typeof file.path !== "string" ||
    file.path.includes("\\") ||
    file.path.split("/").some((x) => !x || x === ".." || x === ".") ||
    seen.has(file.path)
  )
    throw new Error("Unsafe or duplicate asset path");
  seen.add(file.path);
  let data = readFileSync(resolve(client, file.path));
  if (file.path.startsWith("shared/") && file.path.endsWith("/index.js"))
    data = Buffer.from(repairModule(data.toString("utf8")));
  if (data.length !== file.size || sha(data) !== file.sha256)
    throw new Error(`Asset version is incompatible: ${file.path}`);
}
const workspace=resolve(process.env.GTT_WORKSPACE_ROOT??resolve(repo,'../..'));
const output=resolve(workspace,'other/diagnostics/releases',buildId);
const archiveDirectory=serviceVersion?resolve(output,'archives'):resolve(workspace,'update');
if (existsSync(output))
  throw new Error("Build directory exists; choose a new build id");
mkdirSync(output, { recursive: true });
function copy(src, dest, filter = () => true) {
  if (statSync(src).isDirectory()) {
    for (const name of readdirSync(src).sort())
      copy(resolve(src, name), resolve(dest, name), filter);
  } else if (filter(src)) {
    mkdirSync(dirname(dest), { recursive: true });
    copyFileSync(src, dest);
  }
}
const pkg = JSON.parse(readFileSync(resolve(root, "package.json"), "utf8"));
const dependencyLock=JSON.parse(readFileSync(resolve(workspace,'other/tooling/package-lock.json'),'utf8'));
const runtimeDependencies = new Map();
function collectDependency(name, parent = root) {
  const local = resolve(parent, 'node_modules', name);
  const directory = existsSync(resolve(local, 'package.json')) ? local : resolve(root, 'node_modules', name);
  const data = JSON.parse(readFileSync(resolve(directory, 'package.json'), 'utf8'));
  const key = relative(resolve(root, 'node_modules'), directory).split(sep).join('/');
  if (runtimeDependencies.has(key)) return;
  runtimeDependencies.set(key, {directory, version:data.version});
  for (const child of Object.keys(data.dependencies ?? {})) collectDependency(child,directory);
  for (const child of Object.keys(data.optionalDependencies ?? {}))
    if(existsSync(resolve(root,'node_modules',child,'package.json'))) collectDependency(child,directory);
}
collectDependency('pg');
const pgDependencies=new Set(runtimeDependencies.keys());
collectDependency('pm2');
const pm2Dependencies=[...runtimeDependencies.keys()].filter(name=>!pgDependencies.has(name));
function postgresRuntime(dest,bundle=true) {
  if(bundle)for (const [name, dependency] of runtimeDependencies)
    copy(dependency.directory,resolve(dest,'node_modules',name),p=>!/(?:^|[\\/])(?:tests?|testing|__tests__|sample-apps)(?:[\\/])|\.test\.[cm]?[jt]s$|\.ts$|\.map$|\.py$/.test(p));
  copy(resolve(root,'migrations'),resolve(dest,'migrations'));
  const filename=resolve(dest,'package.json'), definition=JSON.parse(readFileSync(filename,'utf8'));
  definition.dependencies={pg:runtimeDependencies.get('pg').version};
  writeFileSync(filename,JSON.stringify(definition,null,2)+'\n');
}
function startupExamples(dest,role,name,entryPoint) {
  const base='/www/wwwroot/gtt-node';
  const envFile=role==='game'?`${base}/config/games/${name}/${runtimeRelease}.env`:`${base}/config/platform.env`;
  if(role==='game') {
    const template=readFileSync(resolve(root,'deploy/game.env.example'),'utf8')
      .replaceAll('buffalo-win',name).replaceAll('REPLACE_WITH_BUILD_ID',runtimeRelease)
      .replaceAll('/opt/gtt-node',base).replaceAll('/etc/gtt-node/secrets',`${base}/config/secrets`)
      .replace('# 生产安装到 /etc/gtt-node/games/<游戏代码>/<发布版本>.env。',`# 复制到 ${envFile}，填写实际端口及密钥文件路径。`);
    write(resolve(dest,'game.env.example'),template);
  } else {
    const remap=text=>text.replaceAll('/etc/gtt-node',`${base}/config`).replaceAll('/var/lib/gtt-node',`${base}/data`).replaceAll('/opt/gtt-node/gateway/current',`${base}/gateway`);
    write(resolve(dest,'platform.env.example'),remap(readFileSync(resolve(root,'deploy/platform.env.example'),'utf8')));
    const production=JSON.parse(remap(readFileSync(resolve(root,'deploy/production.example.json'),'utf8')));
    production.protocol_directory=`${base}/data/merchant-protocols`;
    production.frontend_releases_directory=`${base}/frontend-releases`;
    write(resolve(dest,'production.example.json'),production);
    write(resolve(dest,'postgres.example.json'),remap(readFileSync(resolve(root,'config/postgres.example.json'),'utf8')));
  }
  write(resolve(dest,'ecosystem.config.example.cjs'),`// Copy to ecosystem.config.cjs in the package root; edit env path and Node interpreter if needed.\nmodule.exports = { apps: [{\n  name: ${JSON.stringify(role==='game'?name+'-'+runtimeRelease:name)},\n  cwd: __dirname,\n  script: ${JSON.stringify('./'+entryPoint)},\n  interpreter: 'node',\n  args: ['--env-file', ${JSON.stringify(envFile)}],\n  exec_mode: 'fork',\n  instances: 1,\n  watch: false,\n  autorestart: true,\n  restart_delay: 5000,\n  max_memory_restart: '1G'\n}] };\n`);
  return envFile;
}
function startupPackage(dest,role,action,commands,startActions=[action]) {
  const filename=resolve(dest,'package.json'),definition=JSON.parse(readFileSync(filename,'utf8'));
  const entryName=role==='game'?JSON.parse(readFileSync(resolve(dest,'GAME.json'),'utf8')).code:role;
  if(!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(entryName))throw Error('Invalid startup entry name: '+entryName);
  const entryPoint=`tools/${entryName}.mjs`;
  const exampleEnv=startupExamples(dest,role,entryName,entryPoint);
  definition.dependencies={...definition.dependencies,pm2:runtimeDependencies.get('pm2').version};
  if(withDependencies)for(const name of pm2Dependencies)copy(runtimeDependencies.get(name).directory,resolve(dest,'node_modules',name),p=>!/(?:^|[\\/])(?:tests?|testing|__tests__|sample-apps)(?:[\\/]|$)|\.test\.[cm]?[jt]s$|\.ts$|\.map$|\.py$/.test(p));
  definition.scripts={start:'node tools/start-pm2.mjs','start:foreground':`node ${entryPoint}`,migrate:'node tools/migrate-service.mjs',serve:'node dist/cli.js '+action};
  writeFileSync(filename,JSON.stringify(definition,null,2)+'\n');
  const lock={name:definition.name,version:definition.version,lockfileVersion:3,requires:true,packages:{'':{name:definition.name,version:definition.version,engines:definition.engines,...(definition.dependencies?{dependencies:definition.dependencies}:{})}}};
  for(const name of definition.dependencies?.pg?runtimeDependencies.keys():pm2Dependencies) {
    const entry=dependencyLock.packages['node_modules/'+name];
    if(!entry)throw Error('Missing locked production dependency '+name);
    lock.packages['node_modules/'+name]={...entry};delete lock.packages['node_modules/'+name].dev;
  }
  write(resolve(dest,'package-lock.json'),lock);
  write(resolve(dest,'SERVICE.json'),{role,action,commands,start_actions:startActions,release:runtimeRelease,entry_point:entryPoint,configuration_examples:true,process_manager:'pm2',dependencies_bundled:withDependencies,...(role==='admin'?{data_directory:'dist/data',layout:'admin-slim-v1',opening_checks:true}:{}),startup:['dependencies','migrations','serve']});
  write(resolve(dest,'START.md'),[
    '# 服务启动', '', `服务类型：${role}；构建版本：${buildId}。`, '',
    role==='admin'?`精简后台采用独立 admin CLI，保留平台和商户网页及所有管理 API。交付顶层目录为 frontend、dist、migrations、tools${withDependencies?'、node_modules':''}。dist/data 保留管理目录、协议文档、SQL 与 RTP 模型管理所需元数据；不携带原游戏资源目录和各款游戏引擎。独立包按当前 remote 游戏服务拓扑部署；历史 embedded 部署使用原完整兼容包。`:'',
    withDependencies?'此包通过 --with-dependencies 构建，附带生产依赖；启动仍执行依赖检查，不能保证完全断网时无需 npm 缓存。':'此包不附带 node_modules。首次 npm start 自动安装 package-lock.json 锁定的生产依赖（包括 PM2），需要可访问 npm registry 或具备完整安装缓存；安装后生成 node_modules。保留 package.json 和 package-lock.json，不要手工删除其中一个。安装失败不会启动迁移或服务。',
    '在解压后的本目录执行 `npm start`，自动交给 PM2 后台运行，并等待依赖安装、适用迁移和服务启动成功后返回终端。已有同目录同入口实例会重新读取本次实际配置并重启，包括已停止或失败的实例；允许更换 --env-file 和启动参数。同名但属于其他目录/入口的进程拒绝覆盖。',
    '每次先解析本次配置，再停止原实例并以全新 PM2 进程定义启动，避免 PM2 合并旧环境变量。当前命令行环境变量仍按既有规则优先于 env 文件；如果终端 export 了同名变量，应更新或取消 export。删除的 env 文件配置项恢复 JSON/程序默认值，不沿用上次进程值。单实例重启有短暂中断，共享 env 修改后各服务分别执行 npm start。',
    '前台调试使用 `npm run start:foreground`；宝塔直接管理命名脚本，systemd 使用 start:foreground，不能再嵌套执行后台 npm start。',
    'PM2 使用 package-lock 锁定的项目本地依赖并连接当前用户的 PM2_HOME（默认 ~/.pm2）；缺失时先安装。始终使用同一用户管理，不自动切换 root/www。依赖安装后可运行 npx --no-install pm2 list 或 npx --no-install pm2 logs <名称>。后台启动不会自动配置开机自启或保存 PM2 列表。',
    '首次部署先运行 npm start 或 npm run start:foreground 完成安装；直接执行 admin-init、npm run migrate 等维护命令前也需要已安装依赖。',
    '平台配置自动查找顺序：显式 --env-file、GTT_PLATFORM_ENV_FILE、包根 platform.env、同级 config/platform.env、/etc/gtt-node/platform.env。游戏包支持显式配置、包根 game.env、同名游戏父目录的共享 game.env，再查找 config/games/<代码>/<版本>.env。共享配置只填监听地址、端口及密钥文件路径，版本和规则由包提供；在版本目录直接运行 npm start。示例文件不自动作为实际配置。',
    `PM2 启动文件选择 \`${entryPoint}\`，运行目录为本包根目录；显式传入下述 env 参数。命名入口与 npm start 共用启动流程，旧 tools/start-service.mjs 继续有效。`,
    '依赖由 package-lock.json 锁定；安装使用 npm install --omit=dev --ignore-scripts --no-audit --no-fund。缺少缓存或依赖时需要可用的 npm registry。',
    '安装或迁移失败会停止后续步骤。运行账号须能写入本目录和 npm 缓存目录。', '',
    role==='game'?'游戏计算服务没有玩家数据库；迁移阶段检查版本、规则配置及密钥，不读取平台数据库凭据。':'平台服务执行 PostgreSQL 版本化 schema migration，不导入 SQLite，不重置账号、交易或游戏数据。',
    role==='game'?'通过 GAME_* 环境变量，或 `npm start -- --env-file /etc/gtt-node/games/<game>/<release>.env` 指定实例配置。':'通过共享平台 env，或 `npm start -- --env-file /etc/gtt-node/platform.env` 指定配置。',
    role==='admin'?'首次创建管理员使用 `node dist/cli.js admin-init --env-file /etc/gtt-node/platform.env`；已有管理员不会被覆盖。':'',
    role==='admin'?'开放游戏使用“检查并开放”：必须先登记激活计算服务和前端版本，验证私有启动资料、协议兼容性及资源清单（生产模式实际验证 CDN）。后台显示进度；检查通过后复核版本并开放。检查票据一分钟有效，后台重启后需重做检查；关闭游戏不依赖检查。首页游戏目录不是已部署数量。':'',
    role==='gateway'?'RTP worker 使用同一包执行 `npm start -- rtp-worker --env-file /etc/gtt-node/platform.env`。管理后台使用独立 admin 包。':'',
    '', '## 本包自带的配置示例（宝塔目录方案）',
    role==='game'?`将根目录 game.env.example 复制为 ${exampleEnv}；游戏代码和版本已填好，检查 GAME_CONFIG 对应实际解压路径。示例端口 8211 不是自动分配值，同机每个实例须选择独立端口。创建 GAME_SECRET_FILE 指向的随机密钥文件（至少 32 字符）。`:
      '将根目录 platform.env.example、production.example.json、postgres.example.json 复制到 /www/wwwroot/gtt-node/config/，分别去掉 .example；即 platform.env、production.json、postgres.json。网关、后台和 RTP worker 共用同一份配置，升级时不要覆盖已填写的配置。',
    role==='game'?'游戏配置只含 GAME_* 字段，不要复制平台数据库凭据。':
      '填写实际 PostgreSQL 连接、随机内部密钥、真实公开域名；先创建数据库及账号，启动只迁移表结构。按 JSON 路径创建 data/、data/merchant-protocols/、frontend-releases/ 并授权运行用户。带 .sqlite3 后缀的路径是 PostgreSQL 路由标识，不用创建 SQLite 文件。',
    '示例使用 /www/wwwroot/gtt-node/；换目录时同步修改 env、JSON 和 PM2 配置里的路径。实际配置必须可被运行用户读取；不要将公共 config/ 目录暴露为静态网站。',
    '', '## PM2 启动',
    '在本包根目录将 ecosystem.config.example.cjs 复制为 ecosystem.config.cjs。cwd 使用 __dirname，配置文件应保留在包根目录；Node 解释器须为 24.17.0 或更新版本，可修改为绝对路径。',
    '使用选定的同一个运行用户管理 PM2。已有实例应先停止并移除旧进程登记（保留部署文件），避免宝塔和命令行重复启动；然后在包根目录运行：',
    '```bash', 'pm2 start ecosystem.config.cjs', '```',
    `也可执行 npm start -- --env-file ${exampleEnv}。宝塔脚本参数栏填写 --env-file ${exampleEnv}，不加额外的 --。`,
    '用 pm2 describe <名称> 核对 script args 和 exec cwd，不能只看 online；保存 PM2 进程列表前先确认日志已通过安装、迁移并成功启动。',
    role==='gateway'?'按示例端口在服务器执行 curl -i --max-time 10 http://127.0.0.1:8110/health，预期 HTTP 200、status 为 ok。这不代表所有游戏或外部域名已验收。':'',
    '', '实际 env、数据库数据和密钥文件不随包发布。Node.js 需要 24.17.0 或更新版本，并安装 npm。', '',
  ].filter(line=>line!==undefined).join('\n'));
   for(const tool of ['start-pm2.mjs','start-service.mjs','migrate-service.mjs','service-context.mjs','install-dependencies.mjs'])copy(resolve(root,'tools',tool),resolve(dest,'tools',tool));
  if(role==='gateway')copy(resolve(root,'tools/gateway.mjs'),resolve(dest,'tools/gateway.mjs'));
  else write(resolve(dest,entryPoint),"// Named service entry; preserve the shared startup pipeline and arguments.\nimport './start-service.mjs';\n");
}
const adminModules=new Set(['admin.js','catalog-export.js','game-availability.js']);
const gatewayModule=path=>path.endsWith('.js')&&!adminModules.has(path.split(sep).at(-1));
function runtime(name, gameFiles) {
  const dest = resolve(output, name);
  write(resolve(dest, "package.json"), {
    name: `gtt-${name}`,
    version: pkg.version,
    private: true,
    type: "module",
    engines: pkg.engines,
  });
  copy(resolve(root, "dist/cli.js"), resolve(dest, "dist/cli.js"));
  copy(resolve(root, "dist/shared"), resolve(dest, "dist/shared"), (p) =>
    p.endsWith(".js"),
  );
  for (const name of gameFiles)
    copy(
      resolve(root, `dist/games/buffalo-win/${name}.js`),
      resolve(dest, `dist/games/buffalo-win/${name}.js`),
    );
  copy(
    resolve(root, "config/buffalo-win.json"),
    resolve(dest, "config/buffalo-win.json"),
  );
  return dest;
}
const profiles=[];
const gameArtifacts=[];
const descriptors=JSON.parse(readFileSync(resolve(root,'config/game-descriptors.json'),'utf8'));
let resources;
if(!selectedArtifact?.startsWith('game-')) {
const gateway = runtime("gateway", [
  "engine",
  "random",
  "calibration",
  "worker",
]);
copy(resolve(root, "dist/games/round-model.js"), resolve(gateway, "dist/games/round-model.js"));
copy(resolve(root, "dist/games/embedded-catalog.js"), resolve(gateway, "dist/games/embedded-catalog.js"));
copy(resolve(root, "dist/gateway"), resolve(gateway, "dist/gateway"), gatewayModule);
copy(
  resolve(root, "config"),
  resolve(gateway, "config"),
  (p) => !p.endsWith("buffalo-win.json")&&!/^(?:guide\.(?:md|html)|integration\.json|openapi\.json)$/.test(p.split(sep).at(-1)),
);
runtime("buffalo-win", ["engine", "random", "service"]);
copy(resolve(root, "frontend/admin"), resolve(output, "frontend/admin"));
// All migrated services, with private protocol/bootstrap resources. Large
// client assets remain an independently mounted/published frontend artifact.
const all = resolve(output, "all-services");
write(resolve(all, "package.json"), {
  name: "gtt-all-services",
  version: pkg.version,
  private: true,
  type: "module",
  engines: pkg.engines,
});
for (const name of [
  "cli.js",
  "shared",
  "gateway",
  "games",
  "compat",
  "migrated",
  "services",
])
  copy(resolve(root, "dist", name), resolve(all, "dist", name), (p) =>
    p.endsWith(".js"),
  );
copy(resolve(root, "config"), resolve(all, "config"));
copy(resolve(root, "frontend"), resolve(all, "frontend"));
copy(
  resolve(root, "migrated/sources.json"),
  resolve(all, "migration-sources.json"),
);
resources = resolve(all, "resources");
copy(
  resolve(repo, "py"),
  resolve(resources, "py"),
  (p) =>
    /\.(json|sql)$/.test(p) &&
    !relative(resolve(repo, "py"), p).split(sep).some(part=>["tests","data","logs","__pycache__"].includes(part)),
);
copy(
  resolve(repo, "py/merchant/sandbox.html"),
  resolve(resources, "py/merchant/sandbox.html"),
);
for (const id of readdirSync(resolve(repo, "services")).sort()) {
  const service = resolve(repo, "services", id);
  if (!existsSync(resolve(service, "service.json"))) continue;
  profiles.push(
    JSON.parse(readFileSync(resolve(service, "service.json"), "utf8")),
  );
  copy(
    resolve(service, "service.json"),
    resolve(resources, "services", id, "service.json"),
  );
  copy(
    resolve(service, "config"),
    resolve(resources, "services", id, "config"),
    (p) => p.endsWith(".json"),
  );
}
const fixtureNames = new Set([
  "auth-metadata.json",
  "game-rule.json",
  "game-info.json",
  "game-names.en.json",
  "init.txt",
  "login.json",
  "info.json",
  "authenticate.json",
  "partner-settings.json",
  "launcher.html",
  "game.json",
  "prelaunch.json",
  "configuration.json",
  "help.html",
  "help-zh.html",
]);
for (const id of profiles.filter((s) => s.id !== "game-api").map((s) => s.id)) {
  const src = resolve(repo, "clients", id);
  copy(src, resolve(resources, "clients", id), (p) => {
    const parts = relative(src, p).split(sep);
    return (
      (parts.length === 1 && /\.(html|js|css)$/.test(p)) ||
      (!parts.includes("fixtures") && p.endsWith(".html")) ||
      (parts.length === 2 &&
        parts[0] === "fixtures" &&
        fixtureNames.has(parts[1]))
    );
  });
}
copy(
  resolve(repo, "demo"),
  resolve(resources, "demo"),
  (p) => !/(?:\.py|\.bat|\.md|\.har)$/.test(p),
);
write(resolve(all, "SERVICES.json"), profiles);
write(
  resolve(all, "ASSETS.md"),
  "# Client resources\n\nThis package contains runtime bootstrap metadata, not the full game assets. Mount the matching complete resource tree with GTT_RESOURCE_ROOT, or merge the existing clients/ assets into resources/clients/. Do not publish private fixtures. New gateway deliveries use gateway-<build-id>.zip and the bound asset manifest. Other games require their own verified CDN routing before production publication.\n",
);
// Unified gateway loads all engines and protocol workers. Keep its artifact self-contained.
for (const name of ["compat", "migrated", "services"])
  copy(resolve(root, "dist", name), resolve(gateway, "dist", name), (p) =>
    p.endsWith(".js")&&!(name==='services'&&p.endsWith(sep+'platform.js'))&&!p.endsWith(sep+'merchant'+sep+'mock_wallet.js'),
  );
copy(resources, resolve(gateway, "resources"),p=>{
  const path=relative(resources,p).split(sep).join('/');
  return path!=='py/merchant/sandbox.html';
});
postgresRuntime(gateway,withDependencies);
postgresRuntime(all);
startupPackage(gateway,'gateway','gateway',['gateway','rtp-worker','init','launch','transactions','retry'],['gateway','rtp-worker']);
// Administration and the simulator are separate deployment artifacts. Shared
// business modules remain available, but HTTP/UI entrypoints are not mixed.
const admin=resolve(output,'admin'),mock=resolve(output,'mock-platform');
for(const [dest,role,action]of [[admin,'admin','admin'],[mock,'mock-platform','platform']]) {
  write(resolve(dest,'package.json'),{name:'gtt-'+role,version:pkg.version,private:true,type:'module',engines:pkg.engines});
  if(role==='admin') {
    packageAdmin(root,dest);
    copy(resolve(root,'frontend/admin'),resolve(dest,'frontend/admin'));
    postgresRuntime(dest,withDependencies);
    startupPackage(dest,role,action,['admin','admin-init']);
    continue;
  }
  copy(resolve(root,'dist/cli.js'),resolve(dest,'dist/cli.js'));
  for(const directory of ['shared','gateway','games','compat','migrated','services'])
    copy(resolve(root,'dist',directory),resolve(dest,'dist',directory),p=>p.endsWith('.js')&&!(directory==='gateway'&&['http.js','protocol-pool.js','protocol-worker.js','pg.js'].includes(p.split(sep).at(-1)))&&!(role==='mock-platform'&&adminModules.has(p.split(sep).at(-1)))&&!(role==='admin'&&(p.endsWith(sep+'services'+sep+'platform.js')||p.endsWith(sep+'merchant'+sep+'mock_wallet.js'))));
  copy(resolve(root,'config'),resolve(dest,'config'));
  copy(resolve(resources,'py'),resolve(dest,'resources/py'),p=>role!=='admin'||!p.endsWith(sep+'sandbox.html'));
  if(role==='admin')copy(resolve(root,'frontend/admin'),resolve(dest,'frontend/admin'));
  else copy(resolve(root,'frontend/platform'),resolve(dest,'frontend/platform'));
  postgresRuntime(dest,withDependencies);
  startupPackage(dest,role,action,role==='admin'?['admin','admin-init']:['platform','sandbox-init']);
}
copy(resolve(root, "deploy"), resolve(output, "infra"));
for(const tool of ["install-frontend.mjs","publish-frontend.mjs","render-frontend-edge.mjs","render-game-env.mjs"])
  for(const dest of [gateway,admin])copy(resolve(root,"tools",tool),resolve(dest,"tools",tool));
} else {
  resources=resolve(output,'compute-resources');
  copy(resolve(repo,'py'),resolve(resources,'py'),p=>/\.(json|sql)$/.test(p)&&!relative(resolve(repo,'py'),p).split(sep).some(part=>['tests','data','logs','__pycache__'].includes(part)));
}
for(const code of Object.keys(descriptors)) {
  const name="game-"+code, dest=resolve(output,name);
  if(!allArtifacts&&selectedArtifact!==name&&selectedArtifact!=='infra')continue;
  gameArtifacts.push(name);
  write(resolve(dest,"package.json"),{name:"gtt-"+name,version:pkg.version,private:true,type:"module",engines:pkg.engines});
  copy(resolve(root,"dist/cli.js"),resolve(dest,"dist/cli.js"));
  for(const directory of ["shared","gateway","games","compat","migrated","services"])
    copy(resolve(root,"dist",directory),resolve(dest,"dist",directory),p=>p.endsWith(".js")&&!adminModules.has(p.split(sep).at(-1))&&!(directory==='services'&&p.endsWith(sep+'platform.js'))&&!p.endsWith(sep+'merchant'+sep+'mock_wallet.js'));
  copy(resolve(repo,`services/${code}/config/${code}.json`),resolve(dest,"config/game.json"));
  copy(resolve(resources,"py"),resolve(dest,"resources/py"),p=>!p.endsWith(sep+'sandbox.html'));
  write(resolve(dest,"GAME.json"),{code,release:runtimeRelease,descriptor:descriptors[code],command:["node","dist/cli.js","game","--game-id",code,"--game-config","config/game.json","--secret-file","<private-key-file>","--release",runtimeRelease,"--port","<private-port>"]});
  startupPackage(dest,'game','game',['game']);
  if(allArtifacts||selectedArtifact==='infra')
  write(resolve(output,"infra",`gtt-game-${code}@.service`),`[Unit]\nDescription=GTT ${code} game release %i\nAfter=network.target\n\n[Service]\nType=simple\nUser=gtt-node\nGroup=gtt-node\nWorkingDirectory=/opt/gtt-node/games/${code}/%i\nEnvironmentFile=/etc/gtt-node/games/${code}/%i.env\nCacheDirectory=gtt-node-npm\nEnvironment=NPM_CONFIG_CACHE=/var/cache/gtt-node-npm\nExecStart=/usr/bin/npm start -- --game-id ${code} --release %i\nRestart=on-failure\nRestartSec=3\nNoNewPrivileges=true\nPrivateTmp=true\nProtectSystem=strict\nProtectHome=true\nReadWritePaths=/opt/gtt-node/games/${code}/%i\nUMask=0077\n\n[Install]\nWantedBy=multi-user.target\n`);
}
for(const name of (existsSync(resolve(output,'infra'))?readdirSync(resolve(output,'infra')):[]).filter(name=>name.endsWith('.service'))) {
  const path=resolve(output,'infra',name);
  writeFileSync(path,readFileSync(path,'utf8').replaceAll('/usr/bin/npm start','/usr/bin/npm run start:foreground'));
}
copy(resolve(root, "README.md"), resolve(output, "README.md"));
copy(resolve(repo, "docs/node-migration.md"), resolve(output, "MIGRATION.md"));
copy(resolve(repo, "docs/unified-merchant-games.md"), resolve(output, "UNIFIED-MERCHANT.md"));
copy(resolve(repo, "docs/rtp-inheritance.md"), resolve(output, "RTP-INHERITANCE.md"));
copy(resolve(manifestPath), resolve(output, "assets-manifest.json"));
const git = (...params) =>
  execFileSync("git", params, { cwd: repo, encoding: "utf8" }).trim();
function inventory(dir) {
  const files = [];
  function walk(at) {
    for (const name of readdirSync(at).sort()) {
      const path = resolve(at, name);
      if (statSync(path).isDirectory()) walk(path);
      else {
        if(name==='.env'||name.endsWith('.env'))throw Error('Private env files cannot enter release artifacts: '+relative(dir,path));
        const bytes = readFileSync(path);
        files.push({
          path: relative(dir, path).split(sep).join("/"),
          size: bytes.length,
          sha256: sha(bytes),
        });
      }
    }
  }
  walk(dir);
  return files;
}
const artifacts = [];
for (const name of [
  "gateway",
  "admin",
  "mock-platform",
  "buffalo-win",
  "all-services",
  "frontend",
  "infra",
  ...gameArtifacts,
].filter(name=>allArtifacts||name===selectedArtifact)) {
  const dir = resolve(output, name);
  const frontendInput=option('--frontend-bundle');
  if(frontendInput){
    if(!['admin','gateway'].includes(selectedArtifact))throw Error('--frontend-bundle 仅适用于独立后台或网关');
    const src=resolve(workspace,frontendInput),m=verifyFrontendBundle(src);
    if(!m.release.startsWith('fe-v'))throw Error('随包资料须使用固定游戏版本');
    const target=resolve(dir,'dist/data/frontend-releases',m.release);
    for(const f of m.bootstrap){
      const to=resolve(target,'bootstrap',f.path);
      mkdirSync(dirname(to),{recursive:true});writeFileSync(to,frontendFile(src,'bootstrap',f),{flag:'wx'});
    }
    copy(resolve(src,'manifest.json'),resolve(target,'manifest.json'));
  }
  write(resolve(dir, "release-manifest.json"), {
    build_id: buildId,
    files: inventory(dir),
  });
  const format='zip';
  const archiveName=gameArtifacts.includes(name)?`${name.slice(5)}-serve`:name;
  const category=gameArtifacts.includes(name)?`${name}/${archiveName}-${buildId}`:name;
  const filename = `${archiveName}-${buildId}.${format}`;
  if(existsSync(resolve(archiveDirectory,filename))||existsSync(resolve(archiveDirectory,category,filename)))throw Error('Release archive already exists: '+filename);
  createZip(dir,serviceVersion?'':name,resolve(output,filename));
  const bytes = readFileSync(resolve(output, filename));
  artifacts.push({
    name,
    archive_name: archiveName,
    file: filename,
    directory: category,
    format,
    size: bytes.length,
    sha256: sha(bytes),
  });
}
// Publish completed archives only. Exclusive copy preserves every previous
// version, including when another build races to publish the same filename.
mkdirSync(archiveDirectory,{recursive:true});
for(const artifact of artifacts) {
  mkdirSync(resolve(archiveDirectory,artifact.directory),{recursive:true});
  copyFileSync(resolve(output,artifact.file),resolve(archiveDirectory,artifact.directory,artifact.file),constants.COPYFILE_EXCL);
  unlinkSync(resolve(output,artifact.file));
}
// This is the completion marker. A failed build leaves no release.json.
write(resolve(output, "release.json"), {
  format: 2,
  archive_format: 'zip',
  selection: allArtifacts?'all':selectedArtifact,
  build_id: buildId,
  built_at: new Date().toISOString(),
  node: process.version,
  source: {
    commit: git("rev-parse", "HEAD"),
    dirty: !!git("status", "--porcelain"),
    checksums: "Each artifact contains release-manifest.json",
  },
  services: allArtifacts?[
    "gateway",
    "admin",
    "buffalo-win-compute",
    "rtp-worker",
    "mock-platform",
    ...profiles.map((s) => s.id),
  ]:[selectedArtifact],
  artifacts,
  artifact_directory:relative(output,archiveDirectory).split(sep).join('/'),
  topology:{mode:"remote",...(allArtifacts||selectedArtifact==='gateway'?{gateway:'gateway'}:{}),...(allArtifacts||selectedArtifact==='admin'?{admin:'admin'}:{}),...(allArtifacts||selectedArtifact==='mock-platform'?{mock_platform:'mock-platform'}:{}),games:gameArtifacts.filter(name=>allArtifacts||selectedArtifact===name),version_switch:"new-rounds-only",legacy_artifacts:['buffalo-win','all-services'].filter(name=>allArtifacts||selectedArtifact===name)},
  startup:{command:'npm start',steps:['npm install --omit=dev --ignore-scripts --no-audit --no-fund','versioned PostgreSQL migrations for stateful services; configuration validation for stateless games','service startup'],lockfile:true},
  configuration:{platform_env:'/etc/gtt-node/platform.env',game_env:'/etc/gtt-node/games/<game>/<release>.env',private_env_packaged:false},
  runtime_dependencies:{driver:'pg',independent_delivery:withDependencies?'bundled':'install-on-start',legacy_delivery:'unchanged',packages:Object.fromEntries([...runtimeDependencies].map(([name,d])=>[name,d.version]))},
  frontend_versions:{manifest_format:3,version_generation:"automatic",binding:"per-session",production_assets:"private-s3-cloudfront"},
  assets: {
    game: assets.game,
    release: assets.release,
    prefix: assets.prefix,
    manifest_sha256: sha(raw),
    files: assets.files.length,
  },
  validation: {
    asset_bytes: "verified",
    tests:
      "Run npm test; packaging does not imply test or production acceptance",
    clean_unpack: "Run tools/smoke-release.mjs against this directory",
  },
});
console.log(output);
console.log('Versioned release archives: '+archiveDirectory);
