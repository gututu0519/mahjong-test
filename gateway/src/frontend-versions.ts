import { existsSync, readdirSync, readFileSync, mkdirSync,mkdtempSync,renameSync,rmSync,unlinkSync,writeFileSync } from "node:fs";
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import { resolve, dirname } from "node:path";
import {fileURLToPath} from 'node:url';
import type { IncomingMessage, ServerResponse } from "node:http";
import type { Provider } from "./provider.js";
import { GAME_CODES, gameNumber } from "./catalog.js";
import { check, encode, now, sha,ServiceError } from "../../other/shared/core.js";
import {fetchBounded} from '../../other/shared/http.js';
import {
  readFrontendManifest,
  verifyFrontendBundle,
  frontendFile,
  adapterFiles,
  FRONTEND_VERSION,
  type FrontendManifest,
} from "../../other/shared/frontend-manifest.js";

export class FrontendVersions {
  root: string;
  private readonly bundledRoot=fileURLToPath(new URL('../data/frontend-releases/',import.meta.url));
  private downloads=new Map<string,Promise<string>>();
  /** CDN 固定前缀仅由受信平台配置及已校验的游戏/版本生成，不接收玩家 URL。 */
  cdnURL(m:Pick<FrontendManifest,'release'|'game'|'prefix'>,file:'index.html'|'_gtt-manifest.json',origin:string){
    const configured=this.config.frontend_cdn_origin;
    if(configured){
      const u=new URL(configured);
      check(u.protocol==='https:'&&u.origin===configured,'FRONTEND_CDN_CONFIG','frontend_cdn_origin 须为 HTTPS 素材域名，不含路径');
      return `${u.origin}/${m.prefix}/${file}`;
    }
    check(new URL(origin).protocol==='https:','FRONTEND_CDN_CONFIG','入口模板须从 HTTPS CDN 获取');
    return origin+'/'+(file==='index.html'?'_gtt-entry.html':file);
  }
  /** 按公开标记登记新前端，只复用本机已验证、摘要完全相同的协议资料。 */
  private async discoverEntry(code:string,version:string,id:string,target:string){
    const prefix=`releases/${code}/${version}`,origin=this.config.frontend_cdn_origin||this.origin({game:code,release:id} as FrontendManifest);
    const reply=await fetchBounded(this.cdnURL({game:code,release:id,prefix},'_gtt-manifest.json',origin),{credentials:'omit',timeout:15000},8*1024*1024);
    check(reply.status===200,'FRONTEND_CDN_UNAVAILABLE','CDN 版本清单不存在或不可访问',409);
    const p=JSON.parse(reply.body),e=p.entry;
    check(p.game===code&&code==='buffalo-win'&&p.release===id&&p.component_version===version&&p.prefix===prefix&&p.kind==='game-client'&&p.format===3&&e?.mode==='cdn-html'&&Array.isArray(p.files),'FRONTEND_LOCAL_REQUIRED','此版本不提供 CDN 入口或清单身份不一致',409);
    mkdirSync(this.root,{recursive:true});
    const stage=mkdtempSync(resolve(this.root,'.entry-'));
    try{
      for(const candidate of this.candidates().filter(c=>c.code===code)){
        const base=this.bundle(candidate.bundle),prior=readFrontendManifest(base),bootstrap=adapterFiles(prior);
        if(prior.client_contract!==e.client_contract||sha(encode(bootstrap))!==e.runtime_sha256)continue;
        const m={format:3,kind:p.kind,game:code,release:id,component_version:version,entry_mode:e.mode,created_at:e.created_at,client_contract:e.client_contract,prefix,content_hash:sha(encode({game:code,client_contract:e.client_contract,files:p.files,bootstrap})),source:e.source,files:p.files,bootstrap};
        const raw=encode(m)+'\n';
        check(sha(raw)===p.manifest_sha256,'FRONTEND_MANIFEST_CHANGED','CDN 标记与本机协议资料不配套',409);
        writeFileSync(resolve(stage,'manifest.json'),raw,{flag:'wx'});readFrontendManifest(stage);
        for(const f of bootstrap){const to=resolve(stage,'bootstrap',f.path);mkdirSync(dirname(to),{recursive:true});writeFileSync(to,frontendFile(base,'bootstrap',f),{flag:'wx'});}
        try{renameSync(stage,target);}catch(err){if(!existsSync(target)||sha(readFileSync(resolve(target,'manifest.json')))!==p.manifest_sha256)throw err;}
        return id;
      }
      throw new ServiceError('FRONTEND_ADAPTER_REQUIRED','缺少该游戏匹配的服务端协议资料；请安装适配器，不可跨规则复用',409);
    }finally{rmSync(stage,{recursive:true,force:true});}
  }
  /** 仅缓存通过发布清单校验的原始模板，不缓存注入玩家会话后的 HTML。 */
  async ensureEntry(release:any){
    const m:FrontendManifest=release.manifest;
    if(m.entry_mode!=='cdn-html')return;
    const f=m.files.find(f=>f.path==='index.html')!;
    const target=resolve(this.resources(release),'clients',m.game,'index.html');
    if(existsSync(target)){const bytes=readFileSync(target);check(bytes.length===f.size&&sha(bytes)===f.sha256,'FRONTEND_ENTRY_CHANGED','缓存入口与发布版本不符',409);return;}
    const reply=await fetchBounded(this.cdnURL(m,'index.html',release.origin),{credentials:'omit',timeout:15000},f.size);
    const bytes=Buffer.from(reply.body);
    check(reply.status===200&&bytes.length===f.size&&sha(bytes)===f.sha256,'FRONTEND_ENTRY_CHANGED','CDN 入口不可访问或校验不符',409);
    mkdirSync(dirname(target),{recursive:true});const tmp=mkdtempSync(resolve(dirname(target),'.entry-'));
    try{writeFileSync(resolve(tmp,'html'),bytes);renameSync(resolve(tmp,'html'),target);}finally{rmSync(tmp,{recursive:true,force:true});}
  }
  /** 使用实例 IAM 身份读取固定桶对象，凭据不写入前端或发布记录。 */
  async downloadObject(key:string,path:string) {
    const store=this.config.frontend_s3;
    check(store&&/^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$/.test(store.bucket)&&/^\d{12}$/.test(store.owner)&&/^[a-z0-9-]+$/.test(store.region),'FRONTEND_S3_CONFIG','请配置平台共享的 frontend_s3.bucket/owner/region',409);
    try{
      await promisify(execFile)('aws',['s3api','get-object','--bucket',store.bucket,'--expected-bucket-owner',store.owner,'--region',store.region,'--key',key,'--checksum-mode','ENABLED','--no-cli-pager',path],{timeout:60000,windowsHide:true});
    }catch(error:any){
      const reason=String(error.stderr??'');
      if(error.code==='ENOENT')throw new ServiceError('FRONTEND_AWS_CLI_MISSING','后台找不到 aws 命令。请安装 AWS CLI v2，并确认后台进程的 PATH。',409);
      if(/NoSuchKey|Not Found|\(404\)/i.test(reason))throw new ServiceError('FRONTEND_S3_MISSING','发布文件不存在：'+key+'。请确认版本号或完成发布。',409);
      if(/AccessDenied|Forbidden|credentials|ExpiredToken|\(403\)/i.test(reason))throw new ServiceError('FRONTEND_S3_ACCESS','S3 拒绝读取：请核对服务器 IAM 身份、桶所有者以及前缀读取权限。',409);
      if(/permission denied|read-only file system|no space left/i.test(reason))throw new ServiceError('FRONTEND_CACHE_WRITE','后台无法写入前端缓存，请检查目录权限和剩余空间。',409);
      throw new ServiceError('FRONTEND_S3_READ_FAILED','读取 S3 失败，请检查区域、网络和 AWS CLI v2。对象：'+key,409);
    }
  }
  /** 优先读取本地安装或随包版本；仅显式选择旧 S3 模式时允许回源。 */
  async cacheVersion(game:string,version:string,expected?:string) {
    check(GAME_CODES.includes(game)&&/^v[1-9]\d{0,7}\.(0|[1-9]\d{0,7})$/.test(version),'INVALID_ARGUMENT','无效的游戏或前端版本');
    const id=`fe-${version.replace('.','-')}-g${GAME_CODES.indexOf(game)+1}`,target=this.bundle(id);
    if(!existsSync(target)){
      const discover=this.config.frontend_private_source!=='s3'&&this.config.environment==='production'&&(this.config.frontend_cdn_origin||this.config.frontend_origin_template);
      check(discover||this.config.frontend_private_source==='s3','FRONTEND_LOCAL_REQUIRED',`本地没有 ${game} ${version} 的启动资料，也未配置版本 CDN。`,409);
      if(!this.downloads.has(id)){
        const job=(async()=>{
          if(discover)return this.discoverEntry(game,version,id,target);
          mkdirSync(this.root,{recursive:true});
          const stage=mkdtempSync(resolve(this.root,'.download-')),prefix=`private/frontend/${game}/${version}`;
          try{
            const manifestPath=resolve(stage,'manifest.json'),marker=resolve(stage,'public-marker.json');
            await this.downloadObject(`${prefix}/manifest.json`,manifestPath);
            const manifest=readFrontendManifest(stage),hash=sha(readFileSync(manifestPath));
            check(manifest.release===id&&manifest.game===game&&manifest.component_version===version&&(!expected||expected===hash),'FRONTEND_MANIFEST_CHANGED','下载的清单与所选版本不一致',409);
            await this.downloadObject(`${manifest.prefix}/_gtt-manifest.json`,marker);
            const published=JSON.parse(readFileSync(marker,'utf8'));
            check(published.manifest_sha256===hash&&published.release===id&&published.game===game&&published.prefix===manifest.prefix,'FRONTEND_MANIFEST_CHANGED','公开素材与私有清单不配套',409);
            unlinkSync(marker);
            for(const file of manifest.bootstrap){
              const to=resolve(stage,'bootstrap',file.path);
              mkdirSync(dirname(to),{recursive:true});
              await this.downloadObject(`${prefix}/bootstrap/${file.path}`,to);
              frontendFile(stage,'bootstrap',file);
            }
            try{renameSync(stage,target);}catch(error){if(!existsSync(target)||sha(readFileSync(resolve(target,'manifest.json')))!==hash)throw error;}
            return id;
          }finally{rmSync(stage,{recursive:true,force:true});}
        })().finally(()=>this.downloads.delete(id));
        this.downloads.set(id,job);
      }
      try{await this.downloads.get(id);}catch(error:any){
        if(['EACCES','EPERM','EROFS','ENOSPC'].includes(error.code))throw new ServiceError('FRONTEND_CACHE_WRITE','后台无法写入前端缓存，请检查 frontend_releases_directory 的权限和可用空间。',409);
        if(error instanceof SyntaxError)throw new ServiceError('FRONTEND_MANIFEST_INVALID','该版本的 S3 发布清单不是有效 JSON，请核对发布回执。',409);
        throw error;
      }
    }
    check(existsSync(resolve(target,'manifest.json')),'FRONTEND_LOCAL_REQUIRED','本地启动资料缺少 manifest.json，请检查部署目录',409);
    const manifest=readFrontendManifest(target);
    check(manifest.release===id&&manifest.game===game&&manifest.component_version===version&&(!expected||sha(readFileSync(resolve(target,'manifest.json')))===expected),'FRONTEND_MANIFEST_CHANGED','本地资料不是所选前端版本',409);
    return id;
  }
  /** 远端版本只在本机校验私有资料，生产素材由 CDN 探测逐文件验证。 */
  private installed(path:string) {
    const m=readFrontendManifest(path);
    if(!m.release.startsWith('fe-v'))return verifyFrontendBundle(path);
    check(this.config.environment==='production','FRONTEND_CDN_REQUIRED','固定路径前端需在生产 CDN 模式下登记',409);
    for(const file of m.bootstrap)frontendFile(path,'bootstrap',file);
    return m;
  }
  constructor(
    public p: Provider,
    public config: any,
  ) {
    this.root = resolve(
      config.frontend_releases_directory ??
        resolve(dirname(p.control.path), "frontend-releases"),
    );
    p.control.db.exec(`CREATE TABLE IF NOT EXISTS frontend_releases (
      id TEXT PRIMARY KEY,code TEXT NOT NULL,bundle TEXT NOT NULL,origin TEXT NOT NULL UNIQUE,
      manifest_json TEXT NOT NULL,manifest_sha256 TEXT NOT NULL,status TEXT NOT NULL,created_at INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS frontend_routes(code TEXT PRIMARY KEY,release_id TEXT NOT NULL,revision INTEGER NOT NULL,updated_at INTEGER NOT NULL);`);
    p.db.exec(
      "CREATE TABLE IF NOT EXISTS frontend_sessions(token_hash TEXT PRIMARY KEY,release_id TEXT NOT NULL,expires_at INTEGER NOT NULL);",
    );
  }
  bundle(name: string) {
    check(
      typeof name === "string" &&
        /^[a-zA-Z0-9._-]+$/.test(name) &&
        name !== "." &&
        name !== "..",
      "FRONTEND_BUNDLE_INVALID",
    );
    const installed=resolve(this.root,name),bundled=resolve(this.bundledRoot,name);
    return !existsSync(installed)&&existsSync(bundled)?bundled:installed;
  }
  candidates() {
    const names=new Set([this.root,this.bundledRoot].flatMap(root=>existsSync(root)?readdirSync(root,{withFileTypes:true}).filter(f=>f.isDirectory()&&!f.isSymbolicLink()&&!f.name.startsWith('.')).map(f=>f.name):[]));
    return [...names].flatMap((name) => {
        try {
          const m = readFrontendManifest(this.bundle(name));
          return [
            {
              bundle: name,
              code: m.game,
              release: m.release,
              component_version: m.component_version,
              created_at: m.created_at,
              files: m.files.length,
              registered: !!this.p.control.get(
                "SELECT 1 FROM frontend_releases WHERE id=?",
                m.release,
              ),
            },
          ];
        } catch {
          return [];
        }
      });
  }
  release(id: string) {
    const row = this.p.control.get(
      "SELECT * FROM frontend_releases WHERE id=?",
      id,
    );
    check(row, "FRONTEND_VERSION_REQUIRED", "前端构建版本不存在", 404);
    return {
      ...row,
      manifest: JSON.parse(row.manifest_json) as FrontendManifest,
    };
  }
  origin(manifest: FrontendManifest) {
    const template = this.config.frontend_origin_template;
    let value: string;
    if (template) {
      check(
        typeof template === "string" && template.includes("{release}"),
        "FRONTEND_ORIGIN_TEMPLATE_INVALID",
      );
      value = template
        .replaceAll("{release}", manifest.release)
        .replaceAll("{game}", manifest.game)
        .replaceAll("{game_id}", String(gameNumber(manifest.game)));
    } else {
      check(
        this.config.environment !== "production",
        "FRONTEND_ORIGIN_TEMPLATE_REQUIRED",
        "生产环境须先配置版本域名、TLS 和 CDN 路由",
        409,
      );
      const base = new URL(this.p.multi!.origin(manifest.game));
      base.hostname = manifest.release + "." + base.hostname;
      value = base.origin;
    }
    const url = new URL(value);
    check(
      ["http:", "https:"].includes(url.protocol) &&
        url.pathname === "/" &&
        !url.username &&
        !url.password &&
        !url.search &&
        !url.hash &&
        url.hostname.includes(manifest.release) &&
        (this.config.environment !== "production" || url.protocol === "https:"),
      "FRONTEND_ORIGIN_TEMPLATE_INVALID",
    );
    return url.origin;
  }
  register(actor: string, q: any) {
    const path = this.bundle(q.bundle),
       manifest = this.installed(path),
      origin = this.origin(manifest);
    return this.p.control.tx(() => {
      if(manifest.component_version)check(!this.p.control.all('SELECT manifest_json FROM frontend_releases WHERE code=?',manifest.game)
        .some(row=>JSON.parse(row.manifest_json).component_version===manifest.component_version),'FRONTEND_VERSION_EXISTS','本游戏已登记该前端版本号',409);
      check(
        !this.p.control.get(
          "SELECT 1 FROM frontend_releases WHERE id=?",
          manifest.release,
        ),
        "FRONTEND_VERSION_EXISTS",
        "构建版本已登记",
        409,
      );
      this.p.control.run(
        "INSERT INTO frontend_releases VALUES(?,?,?,?,?,?,?,?)",
        manifest.release,
        manifest.game,
        q.bundle,
        origin,
        encode(manifest),
        sha(readFileSync(resolve(path, "manifest.json"))),
        "staged",
        now(),
      );
      this.p.control.audit(
        actor,
        "frontend.register",
        manifest.release,
        "success",
        { game_id: gameNumber(manifest.game) },
      );
      return { id: manifest.release, code: manifest.game, origin };
    });
  }
  verify(id: string) {
    const release = this.release(id),
      path = this.bundle(release.bundle);
    check(
      sha(readFileSync(resolve(path, "manifest.json"))) ===
        release.manifest_sha256,
      "FRONTEND_MANIFEST_CHANGED",
      "前端清单已变化，请重新构建",
      409,
    );
    this.installed(path);
    return release;
  }
  verifyPrivate(release: any) {
    const bundle = this.bundle(release.bundle);
    check(
      sha(readFileSync(resolve(bundle, "manifest.json"))) ===
        release.manifest_sha256,
      "FRONTEND_MANIFEST_CHANGED",
      "前端清单已变化",
      409,
    );
    for (const file of release.manifest.bootstrap)
      frontendFile(bundle, "bootstrap", file);
  }
  async probe(actor: string, id: string) {
    if(id.startsWith('fe-v')){
      const row=this.release(id);
      await this.cacheVersion(row.code,row.manifest.component_version!,row.manifest_sha256);
    }
    const release = this.verify(id);
    check(release.status !== "retired", "FRONTEND_VERSION_RETIRED");
    if (this.config.environment === "production")
      for (const file of release.manifest.files) {
        const response = await fetch(
          release.manifest.entry_mode==='cdn-html'&&file.path==='index.html'?this.cdnURL(release.manifest,'index.html',release.origin):release.origin +
            "/" +
            file.path.split("/").map(encodeURIComponent).join("/"),
          {
            redirect: "manual",
            credentials: "omit",
            signal: AbortSignal.timeout(15000),
          },
        );
        check(
          response.status === 200,
          "FRONTEND_CDN_UNAVAILABLE",
          "版本 CDN 文件尚未正确发布",
          409,
        );
        const reader = response.body!.getReader(),
          chunks: Buffer[] = [];
        let size = 0;
        try {
          while (true) {
            const r = await reader.read();
            if (r.done) break;
            size += r.value.byteLength;
            check(size <= file.size, "FRONTEND_CDN_CHANGED");
            chunks.push(Buffer.from(r.value));
          }
        } finally {
          await reader.cancel();
        }
        check(
          size === file.size && sha(Buffer.concat(chunks)) === file.sha256,
          "FRONTEND_CDN_CHANGED",
          "版本 CDN 文件与清单不一致",
          409,
        );
      }
    this.p.control.run(
      "UPDATE frontend_releases SET status='verified' WHERE id=? AND status<>'retired'",
      id,
    );
    this.p.control.audit(actor, "frontend.verify", id, "success", {
      mode: this.config.environment === "production" ? "cdn" : "local",
    });
    return {
      id,
      status: "verified",
      mode: this.config.environment === "production" ? "cdn" : "local",
    };
  }
  activate(actor: string, q: any) {
    const selected = this.verify(q.id);
    check(
      selected.status === "verified",
      "FRONTEND_NOT_VERIFIED",
      "请先检查构建和 CDN 文件",
      409,
    );
    check(Number.isInteger(q.revision) && q.revision >= 0, "INVALID_ARGUMENT");
    return this.p.control.tx(() => {
      check(
        this.release(selected.id).status === "verified",
        "FRONTEND_NOT_VERIFIED",
      );
      const route = this.p.control.get(
        "SELECT * FROM frontend_routes WHERE code=?",
        selected.code,
      );
      check(
        (route?.revision ?? 0) === q.revision,
        "VERSION_CONFLICT",
        "前端版本已变化，请刷新后重试",
        409,
      );
      const hasServices = this.p.control.get(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='game_service_releases'",
      );
      const service = hasServices
        ? this.p.control.get(
            "SELECT r.descriptor_json FROM game_service_routes a JOIN game_service_releases r ON r.id=a.release_id WHERE a.code=?",
            selected.code,
          )
        : null;
      if (service)
        check(
          JSON.parse(service.descriptor_json).client_contract ===
            selected.manifest.client_contract,
          "FRONTEND_CONTRACT_MISMATCH",
          "前端与当前游戏服务的协议契约不匹配",
          409,
        );
      if (route)
        check(
          this.release(route.release_id).manifest.client_contract ===
            selected.manifest.client_contract,
          "FRONTEND_CONTRACT_MISMATCH",
          "不兼容的前端不能直接切换",
          409,
        );
      this.p.control.run(
        "INSERT INTO frontend_routes VALUES(?,?,?,?) ON CONFLICT(code) DO UPDATE SET release_id=excluded.release_id,revision=excluded.revision,updated_at=excluded.updated_at",
        selected.code,
        selected.id,
        q.revision + 1,
        now(),
      );
      this.p.control.audit(actor, "frontend.activate", selected.id, "success", {
        previous: route?.release_id ?? null,
        revision: q.revision + 1,
      });
      return { id: selected.id, revision: q.revision + 1 };
    });
  }
  retire(actor: string, id: string) {
    return this.p.control.tx(() => {
      check(
        !this.p.control.get(
          "SELECT 1 FROM frontend_routes WHERE release_id=?",
          id,
        ),
        "FRONTEND_VERSION_ACTIVE",
        "先切换新会话使用的版本",
        409,
      );
      this.release(id);
      this.p.control.run(
        "UPDATE frontend_releases SET status='retired' WHERE id=?",
        id,
      );
      this.p.control.audit(actor, "frontend.retire", id);
      return { id, status: "retired" };
    });
  }
  list() {
    return GAME_CODES.map((code) => {
      const route = this.p.control.get(
        "SELECT * FROM frontend_routes WHERE code=?",
        code,
      );
      const releases = this.p.control
        .all(
           "SELECT id,origin,status,created_at,manifest_sha256,manifest_json FROM frontend_releases WHERE code=? ORDER BY created_at DESC,id",
          code,
        )
         .map(({manifest_json,...row}) => ({
           ...row,
           component_version:JSON.parse(manifest_json).component_version??null,
          sessions: this.p.get(
            "SELECT COUNT(*) AS n FROM frontend_sessions WHERE release_id=? AND expires_at>?",
            row.id,
            now(),
          ).n,
        }));
      return {
        code,
        game_id: gameNumber(code),
        active_id: route?.release_id ?? null,
        revision: route?.revision ?? 0,
        releases,
      };
    });
  }
  bind(tokenHash: string, code: string, expiry: number) {
    const route = this.p.control.get(
      "SELECT release_id FROM frontend_routes WHERE code=?",
      code,
    );
    if (!route) return null;
    const release = this.release(route.release_id);
    this.p.run(
      "INSERT INTO frontend_sessions VALUES(?,?,?)",
      tokenHash,
      release.id,
      expiry,
    );
    return release;
  }
  host(host: string) {
    const row = this.p.control.get(
      "SELECT id FROM frontend_releases WHERE origin IN (?,?)",
      "http://" + host,
      "https://" + host,
    );
    return row ? this.release(row.id) : null;
  }
  session(token: string, release: any) {
    const binding = this.p.get(
      "SELECT release_id FROM frontend_sessions WHERE token_hash=? AND expires_at>?",
      sha(token),
      now(),
    );
    check(
      binding && binding.release_id === release.id,
      "FRONTEND_SESSION_MISMATCH",
      "请使用原游戏启动链接",
      403,
    );
  }
  asset(release: any, req: IncomingMessage, res: ServerResponse) {
    const path = decodeURIComponent(
      new URL(req.url!, "http://local").pathname,
    ).slice(1);
    if(path==='index.html'&&release.manifest.entry_mode==='cdn-html')return false;
    const file = release.manifest.files.find((f: any) => f.path === path);
    if (!file) return false;
    check(
      this.config.environment !== "production",
      "FRONTEND_CDN_REQUIRED",
      "生产素材应由私有 S3 / CloudFront 提供",
      503,
    );
    const bytes = frontendFile(this.bundle(release.bundle), "objects", file);
    res.writeHead(200, {
      "Content-Type": file.type,
      "Content-Length": bytes.length,
      "Cache-Control": "public, max-age=31536000, immutable",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
    });
    res.end(req.method === "HEAD" ? undefined : bytes);
    return true;
  }
  resources(release: any) {
    return resolve(this.bundle(release.bundle), "bootstrap/resources");
  }
}
