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

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repo = resolve(root, "..");
const args = process.argv.slice(2);
function option(name, fallback) {
  const at = args.indexOf(name);
  if (at < 0) return fallback;
  if (!args[at + 1] || args[at + 1].startsWith("--"))
    throw new Error(`Missing ${name}`);
  return args[at + 1];
}
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
const manifestPath = option("--assets-manifest");
if (!manifestPath)
  throw new Error(
    "Supply --assets-manifest with the verified Buffalo S3 manifest",
  );
const raw = readFileSync(resolve(manifestPath));
const assets = JSON.parse(raw);
if (
  assets.game !== "buffalo-win" ||
  !/^[a-f0-9]{20}$/.test(assets.release) ||
  !assets.files?.length ||
  assets.prefix !== `releases/buffalo-win/${assets.release}`
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
const archiveDirectory=resolve(workspace,'update');
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
function postgresRuntime(dest) {
  for (const [name, dependency] of runtimeDependencies)
    copy(dependency.directory,resolve(dest,'node_modules',name),p=>!/(?:^|[\\/])(?:tests?|testing|__tests__)(?:[\\/])|\.test\.[cm]?[jt]s$|\.ts$|\.map$/.test(p));
  copy(resolve(root,'migrations'),resolve(dest,'migrations'));
  const filename=resolve(dest,'package.json'), definition=JSON.parse(readFileSync(filename,'utf8'));
  definition.dependencies={pg:runtimeDependencies.get('pg').version};
  writeFileSync(filename,JSON.stringify(definition,null,2)+'\n');
}
function startupPackage(dest,role,action,commands,startActions=[action]) {
  const filename=resolve(dest,'package.json'),definition=JSON.parse(readFileSync(filename,'utf8'));
  definition.scripts={start:'node tools/start-service.mjs',migrate:'node tools/migrate-service.mjs',serve:'node dist/cli.js '+action};
  writeFileSync(filename,JSON.stringify(definition,null,2)+'\n');
  const lock={name:definition.name,version:definition.version,lockfileVersion:3,requires:true,packages:{'':{name:definition.name,version:definition.version,engines:definition.engines,...(definition.dependencies?{dependencies:definition.dependencies}:{})}}};
  if(definition.dependencies?.pg)for(const name of runtimeDependencies.keys()) {
    const entry=dependencyLock.packages['node_modules/'+name];
    if(!entry)throw Error('Missing locked production dependency '+name);
    lock.packages['node_modules/'+name]={...entry};delete lock.packages['node_modules/'+name].dev;
  }
  write(resolve(dest,'package-lock.json'),lock);
  write(resolve(dest,'SERVICE.json'),{role,action,commands,start_actions:startActions,release:buildId,startup:['dependencies','migrations','serve']});
  write(resolve(dest,'START.md'),[
    '# 服务启动', '', `服务类型：${role}；构建版本：${buildId}。`, '',
    '在解压后的本目录执行 `npm start`，依次完成生产依赖安装、适用迁移和服务启动。',
    '依赖由 package-lock.json 锁定；安装使用 npm install --omit=dev --ignore-scripts --no-audit --no-fund。缺少缓存或依赖时需要可用的 npm registry。',
    '安装或迁移失败会停止后续步骤。运行账号须能写入本目录和 npm 缓存目录。', '',
    role==='game'?'游戏计算服务没有玩家数据库；迁移阶段检查版本、规则配置及密钥，不读取平台数据库凭据。':'平台服务执行 PostgreSQL 版本化 schema migration，不导入 SQLite，不重置账号、交易或游戏数据。',
    role==='game'?'通过 GAME_* 环境变量，或 `npm start -- --env-file /etc/gtt-node/games/<game>/<release>.env` 指定实例配置。':'通过共享平台 env，或 `npm start -- --env-file /etc/gtt-node/platform.env` 指定配置。',
    role==='admin'?'首次创建管理员使用 `node dist/cli.js admin-init --env-file /etc/gtt-node/platform.env`；已有管理员不会被覆盖。':'',
    role==='gateway'?'RTP worker 使用同一包执行 `npm start -- rtp-worker --env-file /etc/gtt-node/platform.env`。管理后台使用独立 admin 包。':'',
    '', '实际 env、数据库数据和密钥文件不随包发布。Node.js 需要 24.17.0 或更新版本，并安装 npm。', '',
  ].filter(line=>line!==undefined).join('\n'));
  for(const tool of ['start-service.mjs','migrate-service.mjs','service-context.mjs','install-dependencies.mjs'])copy(resolve(root,'tools',tool),resolve(dest,'tools',tool));
}
const adminModules=new Set(['admin.js','catalog-export.js']);
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
const gateway = runtime("gateway", [
  "engine",
  "random",
  "calibration",
  "worker",
]);
copy(resolve(root, "dist/games/round-model.js"), resolve(gateway, "dist/games/round-model.js"));
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
const resources = resolve(all, "resources");
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
const profiles = [];
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
postgresRuntime(gateway);
postgresRuntime(all);
startupPackage(gateway,'gateway','gateway',['gateway','rtp-worker','init','launch','transactions','retry'],['gateway','rtp-worker']);
// Administration and the simulator are separate deployment artifacts. Shared
// business modules remain available, but HTTP/UI entrypoints are not mixed.
const admin=resolve(output,'admin'),mock=resolve(output,'mock-platform');
for(const [dest,role,action]of [[admin,'admin','admin'],[mock,'mock-platform','platform']]) {
  write(resolve(dest,'package.json'),{name:'gtt-'+role,version:pkg.version,private:true,type:'module',engines:pkg.engines});
  copy(resolve(root,'dist/cli.js'),resolve(dest,'dist/cli.js'));
  for(const directory of ['shared','gateway','games','compat','migrated','services'])
    copy(resolve(root,'dist',directory),resolve(dest,'dist',directory),p=>p.endsWith('.js')&&!(directory==='gateway'&&['http.js','protocol-pool.js','protocol-worker.js','pg.js'].includes(p.split(sep).at(-1)))&&!(role==='mock-platform'&&adminModules.has(p.split(sep).at(-1)))&&!(role==='admin'&&(p.endsWith(sep+'services'+sep+'platform.js')||p.endsWith(sep+'merchant'+sep+'mock_wallet.js'))));
  copy(resolve(root,'config'),resolve(dest,'config'));
  copy(resolve(resources,'py'),resolve(dest,'resources/py'),p=>role!=='admin'||!p.endsWith(sep+'sandbox.html'));
  if(role==='admin')copy(resolve(root,'frontend/admin'),resolve(dest,'frontend/admin'));
  else copy(resolve(root,'frontend/platform'),resolve(dest,'frontend/platform'));
  postgresRuntime(dest);
  startupPackage(dest,role,action,role==='admin'?['admin','admin-init']:['platform','sandbox-init']);
}
copy(resolve(root, "deploy"), resolve(output, "infra"));
for(const tool of ["install-frontend.mjs","publish-frontend.mjs","render-frontend-edge.mjs","render-game-env.mjs"])
  for(const dest of [gateway,admin])copy(resolve(root,"tools",tool),resolve(dest,"tools",tool));
const gameArtifacts=[];
const descriptors=JSON.parse(readFileSync(resolve(root,"config/game-descriptors.json"),"utf8"));
for(const code of Object.keys(descriptors)) {
  const name="game-"+code, dest=resolve(output,name);
  gameArtifacts.push(name);
  write(resolve(dest,"package.json"),{name:"gtt-"+name,version:pkg.version,private:true,type:"module",engines:pkg.engines});
  copy(resolve(root,"dist/cli.js"),resolve(dest,"dist/cli.js"));
  for(const directory of ["shared","gateway","games","compat","migrated","services"])
    copy(resolve(root,"dist",directory),resolve(dest,"dist",directory),p=>p.endsWith(".js")&&!adminModules.has(p.split(sep).at(-1))&&!(directory==='services'&&p.endsWith(sep+'platform.js'))&&!p.endsWith(sep+'merchant'+sep+'mock_wallet.js'));
  copy(resolve(repo,`services/${code}/config/${code}.json`),resolve(dest,"config/game.json"));
  copy(resolve(resources,"py"),resolve(dest,"resources/py"),p=>!p.endsWith(sep+'sandbox.html'));
  write(resolve(dest,"GAME.json"),{code,release:buildId,descriptor:descriptors[code],command:["node","dist/cli.js","game","--game-id",code,"--game-config","config/game.json","--secret-file","<private-key-file>","--release",buildId,"--port","<private-port>"]});
  startupPackage(dest,'game','game',['game']);
  write(resolve(output,"infra",`gtt-game-${code}@.service`),`[Unit]\nDescription=GTT ${code} game release %i\nAfter=network.target\n\n[Service]\nType=simple\nUser=gtt-node\nGroup=gtt-node\nWorkingDirectory=/opt/gtt-node/games/${code}/%i\nEnvironmentFile=/etc/gtt-node/games/${code}/%i.env\nCacheDirectory=gtt-node-npm\nEnvironment=NPM_CONFIG_CACHE=/var/cache/gtt-node-npm\nExecStart=/usr/bin/npm start -- --game-id ${code} --release %i\nRestart=on-failure\nRestartSec=3\nNoNewPrivileges=true\nPrivateTmp=true\nProtectSystem=strict\nProtectHome=true\nReadWritePaths=/opt/gtt-node/games/${code}/%i\nUMask=0077\n\n[Install]\nWantedBy=multi-user.target\n`);
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
]) {
  const dir = resolve(output, name);
  write(resolve(dir, "release-manifest.json"), {
    build_id: buildId,
    files: inventory(dir),
  });
  const format=name==='gateway'?'zip':'tar.gz';
  const filename = `${name}-${buildId}.${format}`;
  if(existsSync(resolve(archiveDirectory,filename)))throw Error('Release archive already exists: '+filename);
  if(format==='zip')createZip(dir,name,resolve(output,filename));
  else execFileSync("tar", ["-czf", resolve(output, filename), "-C", output, name], {stdio: "pipe"});
  const bytes = readFileSync(resolve(output, filename));
  artifacts.push({
    name,
    file: filename,
    format,
    size: bytes.length,
    sha256: sha(bytes),
  });
}
// Publish completed archives only. Exclusive copy preserves every previous
// version, including when another build races to publish the same filename.
mkdirSync(archiveDirectory,{recursive:true});
for(const artifact of artifacts) {
  copyFileSync(resolve(output,artifact.file),resolve(archiveDirectory,artifact.file),constants.COPYFILE_EXCL);
  unlinkSync(resolve(output,artifact.file));
}
// This is the completion marker. A failed build leaves no release.json.
write(resolve(output, "release.json"), {
  format: 2,
  build_id: buildId,
  built_at: new Date().toISOString(),
  node: process.version,
  source: {
    commit: git("rev-parse", "HEAD"),
    dirty: !!git("status", "--porcelain"),
    checksums: "Each artifact contains release-manifest.json",
  },
  services: [
    "gateway",
    "admin",
    "buffalo-win-compute",
    "rtp-worker",
    "mock-platform",
    ...profiles.map((s) => s.id),
  ],
  artifacts,
  artifact_directory:relative(output,archiveDirectory).split(sep).join('/'),
  topology:{mode:"remote",gateway:"gateway",admin:"admin",mock_platform:"mock-platform",games:gameArtifacts,version_switch:"new-rounds-only",legacy_artifacts:["buffalo-win","all-services"]},
  startup:{command:'npm start',steps:['npm install --omit=dev --ignore-scripts --no-audit --no-fund','versioned PostgreSQL migrations for stateful services; configuration validation for stateless games','service startup'],lockfile:true},
  configuration:{platform_env:'/etc/gtt-node/platform.env',game_env:'/etc/gtt-node/games/<game>/<release>.env',private_env_packaged:false},
  runtime_dependencies:{driver:'pg',packages:Object.fromEntries([...runtimeDependencies].map(([name,d])=>[name,d.version]))},
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
