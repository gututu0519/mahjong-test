import {createHash,randomUUID} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {check,encode,sha,ServiceError} from '../../other/shared/core.js';
import {readFrontendManifest,frontendFile,frontendMarker,COMPONENT_VERSION} from '../../other/shared/frontend-manifest.js';
import {gameCode} from '../../gateway/src/catalog.js';
import type {Provider} from '../../gateway/src/provider.js';
import type {GameServices} from '../../gateway/src/game-services.js';
import type {FrontendVersions} from '../../gateway/src/frontend-versions.js';

type Job = {
  id:string; actor:string; game_id:number; version:number;
  status:'checking'|'ready'|'failed'|'applied'; stage:string;
  completed:number; total:number; created:number; finished?:number;
  error?:{code:string;message:string}; fingerprint?:string;
  service_id?:string; frontend_id?:string; controller:AbortController;
  selection?:{service_id:string;component_version:string;frontend_revision:number;service_revision:number;frontend_id?:string};
};

// Checks are deliberately transient, never an alternative durable source of
// availability. A restart loses check tickets; clients must recheck before open.
export class GameAvailabilityChecks {
  private jobs=new Map<string,Job>();
  private closed=false;
  constructor(private p:Provider,private services:GameServices,private frontends:FrontendVersions,private config:any) {}
  /** 核对组件实际版本、在线身份与素材，在同一事务内切换两条路由。 */
  async activatePair(actor:string,q:any) {
    const db=this.p.control,code=gameCode(q.game_id);
    check(typeof q.frontend_id==='string'&&typeof q.service_id==='string'&&Number.isInteger(q.frontend_revision)&&Number.isInteger(q.service_revision),'INVALID_ARGUMENT');
    const f=this.frontends.release(q.frontend_id),s=this.services.release(q.service_id);
    check(f.code===code&&s.code===code,'GAME_RELEASE_CHANGED','所选版本不属于当前游戏',409);
    const major=COMPONENT_VERSION.exec(f.manifest.component_version??'')?.[1];
    check(major&&major===COMPONENT_VERSION.exec(s.release)?.[1],'GAME_MAJOR_MISMATCH','请选择同一主版本的前后端，旧构建不能用于新切换',409);
    check(s.descriptor.client_contract===f.manifest.client_contract,'FRONTEND_CONTRACT_MISMATCH','前后端协议不匹配',409);
    check(f.status==='verified'&&s.status==='ready','GAME_RELEASE_NOT_READY','请先验证前端并登记计算服务',409);
    await this.frontends.probe(actor,f.id);
    await this.serviceProbe(s.id);
    return db.tx(()=>this.applyPair(actor,q,code,f,s,major));
  }
  /** 在调用方事务中复核修订和整局绑定，并一次性应用两条路由。 */
  private applyPair(actor:string,q:any,code:string,f:any,s:any,major:string){
      const db=this.p.control;
      const current=this.frontends.release(f.id),service=this.services.release(s.id);
      check(current.status==='verified'&&service.status==='ready'&&current.manifest_sha256===f.manifest_sha256&&encode(service.descriptor)===encode(s.descriptor),'GAME_RELEASE_CHANGED','版本已变化，请刷新',409);
      this.verifyPrivate(f.id);
      const front=db.get('SELECT * FROM frontend_routes WHERE code=?',code),back=db.get('SELECT * FROM game_service_routes WHERE code=?',code);
      check((front?.revision??0)===q.frontend_revision&&(back?.revision??0)===q.service_revision,'VERSION_CONFLICT','版本已被切换，请刷新后重试',409);
      if(front&&COMPONENT_VERSION.exec(this.frontends.release(front.release_id).manifest.component_version??'')?.[1]!==major){
        for(const row of db.all('SELECT id,manifest_json FROM frontend_releases WHERE code=?',code)){
          if(COMPONENT_VERSION.exec(JSON.parse(row.manifest_json).component_version??'')?.[1]===major)continue;
          check(!this.p.get('SELECT 1 FROM frontend_sessions WHERE release_id=? AND expires_at>? LIMIT 1',row.id,Math.floor(Date.now()/1000)),'GAME_SESSIONS_ACTIVE','跨主版本切换前请先关闭新入口，等待旧版会话结束',409);
        }
        check(!this.p.get('SELECT 1 FROM game_release_rounds WHERE game_id=? AND closed=0 LIMIT 1',code),'GAME_ROUNDS_ACTIVE','跨主版本切换前请等待原整局结算',409);
      }
      if(back&&back.release_id!==s.id){
        const prior=this.services.release(back.release_id);
        if(COMPONENT_VERSION.exec(prior.release)?.[1]===major)check(prior.descriptor.state_contract===s.descriptor.state_contract&&prior.descriptor.client_contract===s.descriptor.client_contract,'GAME_CONTRACT_MISMATCH','同代计算服务的契约不一致',409);
      }
      if(front?.release_id!==f.id)db.run('INSERT INTO frontend_routes VALUES(?,?,?,?) ON CONFLICT(code) DO UPDATE SET release_id=excluded.release_id,revision=excluded.revision,updated_at=excluded.updated_at',code,f.id,q.frontend_revision+1,Math.floor(Date.now()/1000));
      if(back?.release_id!==s.id)db.run('INSERT INTO game_service_routes VALUES(?,?,?,?) ON CONFLICT(code) DO UPDATE SET release_id=excluded.release_id,revision=excluded.revision,updated_at=excluded.updated_at',code,s.id,q.service_revision+1,Math.floor(Date.now()/1000));
      db.audit(actor,'game.version-pair.activate',code,'success',{frontend:f.id,service:s.id,previous_frontend:front?.release_id??null,previous_service:back?.release_id??null});
      return {code,frontend_id:f.id,service_id:s.id};
  }
  private snapshot(id:number,pick?:Job['selection']) {
    const code=gameCode(id),db=this.p.control;
    const serviceRoute=db.get('SELECT * FROM game_service_routes WHERE code=?',code);
    if(pick)check((serviceRoute?.revision??0)===pick.service_revision,'VERSION_CONFLICT','计算版本已切换，请刷新',409);
    check(pick||serviceRoute,'GAME_SERVICE_REQUIRED','请先登记并激活游戏计算服务',409);
    const service=db.get('SELECT * FROM game_service_releases WHERE id=?',pick?.service_id??serviceRoute.release_id);
    check(service?.status==='ready','GAME_SERVICE_NOT_READY','当前游戏计算版本不可用或已退役',409);
    const frontendRoute=db.get('SELECT * FROM frontend_routes WHERE code=?',code);
    if(pick)check((frontendRoute?.revision??0)===pick.frontend_revision,'VERSION_CONFLICT','前端版本已切换，请刷新',409);
    check(pick||frontendRoute,'FRONTEND_VERSION_REQUIRED','请先登记、校验并激活游戏前端版本',409);
    const frontend=db.get('SELECT * FROM frontend_releases WHERE id=?',pick?.frontend_id??frontendRoute.release_id);
    check(frontend?.status==='verified'||(pick&&frontend?.status==='staged'),'FRONTEND_NOT_VERIFIED','前端不可用或已退役',409);
    const descriptor=JSON.parse(service.descriptor_json),manifest=JSON.parse(frontend.manifest_json);
    check(service.code===code&&frontend.code===code&&manifest.game===code,'GAME_RELEASE_CHANGED','登记版本与游戏身份不一致',409);
    check(descriptor.client_contract===manifest.client_contract,'FRONTEND_CONTRACT_MISMATCH','前端与游戏计算服务的协议契约不匹配',409);
    const major=COMPONENT_VERSION.exec(manifest.component_version??'')?.[1];
    check(major&&major===COMPONENT_VERSION.exec(service.release)?.[1],'GAME_MAJOR_MISMATCH','开放游戏需要已配对的同主版本前后端',409);
    if(pick)check(pick.component_version===manifest.component_version,'GAME_RELEASE_CHANGED','所选前端版本不符',409);
    return {code,service,frontend,fingerprint:sha(encode({serviceRoute:serviceRoute??null,service,frontendRoute:frontendRoute??null,frontend}))};
  }
  private view(job:Job) {
    return {id:job.id,game_id:job.game_id,version:job.version,status:job.status,stage:job.stage,completed:job.completed,total:job.total,
      ...(job.error?{error:job.error}:{}),...(job.finished?{expires_at:Math.floor((job.finished+60000)/1000)}:{})};
  }
  private prune() {
    for(const [id,job]of this.jobs)if(job.status!=='checking'&&Date.now()-(job.finished??job.created)>15*60*1000)this.jobs.delete(id);
  }
  begin(actor:string,q:any,selection?:Job['selection']) {
    gameCode(q.game_id);
    check(q.enabled===true&&Number.isInteger(q.version)&&q.version>=0,'INVALID_ARGUMENT');
    check(this.p.control.gameAvailability(q.game_id).version===q.version,'VERSION_CONFLICT','开放状态已变化，请刷新后重试',409);
    this.prune();
    if(selection)check(typeof selection.service_id==='string'&&typeof selection.component_version==='string'&&COMPONENT_VERSION.test(selection.component_version)&&Number.isInteger(selection.frontend_revision)&&Number.isInteger(selection.service_revision),'INVALID_ARGUMENT','请选择有效的前端版本和计算服务');
    const existing=[...this.jobs.values()].find(job=>job.actor===actor&&job.game_id===q.game_id&&job.version===q.version&&job.status==='checking'&&(!selection?!job.selection:job.selection?.service_id===selection.service_id&&job.selection.component_version===selection.component_version&&job.selection.frontend_revision===selection.frontend_revision&&job.selection.service_revision===selection.service_revision));
    if(existing)return this.view(existing);
    check([...this.jobs.values()].filter(job=>job.status==='checking').length<4&&this.jobs.size<100,'GAME_CHECK_BUSY','检查任务繁忙，请稍后再试',429);
    const job:Job={id:randomUUID(),actor,game_id:q.game_id,version:q.version,status:'checking',stage:'service',completed:0,total:0,created:Date.now(),controller:new AbortController()};
    this.jobs.set(job.id,job);
    job.selection=selection;
    void this.run(job);
    return this.view(job);
  }
  status(actor:string,id:string) {return this.view(this.ticket(actor,id));}
  private ticket(actor:string,id:string) {
    this.prune();const job=this.jobs.get(id);
    check(job&&job.actor===actor,'GAME_CHECK_EXPIRED','检查任务不存在或已过期，请重新检查',409);
    return job;
  }
  private async serviceProbe(id:string) {
    const release=this.services.release(id);
    const descriptor=await this.services.request(release,'describe');
    check(encode(descriptor)===encode(release.descriptor),'GAME_RELEASE_CHANGED','计算服务内容与已登记版本不一致',409);
  }
  private verifyPrivate(id:string) {
    try {
    const release=this.frontends.release(id),bundle=this.frontends.bundle(release.bundle);
    const manifest=readFrontendManifest(bundle);
    check(sha(readFileSync(resolve(bundle,'manifest.json')))===release.manifest_sha256&&encode(manifest)===encode(release.manifest),'FRONTEND_MANIFEST_CHANGED','前端清单已变化，请重新登记版本',409);
    check(manifest.entry_mode==='cdn-html'||manifest.bootstrap.some(file=>file.path===`resources/clients/${manifest.game}/index.html`),'FRONTEND_ENTRY_REQUIRED','前端缺少当前游戏的启动页面 index.html',409);
    this.frontends.verifyPrivate(release);
    return {release,bundle,manifest};
    } catch(error) {
      if(error instanceof ServiceError)throw error;
      throw new ServiceError('FRONTEND_BOOTSTRAP_UNAVAILABLE','前端清单或私有启动资料缺失、损坏或不可读，请检查已安装的版本目录',409);
    }
  }
  private async run(job:Job) {
    const deadline=setTimeout(()=>job.controller.abort(),10*60*1000);deadline.unref();
    try {
      const pick=job.selection;
      if(pick){
        job.stage='registration';
        const code=gameCode(job.game_id),service=this.services.release(pick.service_id);
        check(service.status==='ready'&&service.code===code,'GAME_SERVICE_NOT_READY','所选计算服务不属于此游戏或已停用',409);
        check(COMPONENT_VERSION.exec(service.release)?.[1]===COMPONENT_VERSION.exec(pick.component_version)?.[1],'GAME_MAJOR_MISMATCH','前后端主版本不匹配',409);
        const lookup=()=>this.p.control.all('SELECT id,manifest_json FROM frontend_releases WHERE code=?',code).find(row=>JSON.parse(row.manifest_json).component_version===pick.component_version)?.id;
        pick.frontend_id=lookup();
        if(!pick.frontend_id){
          const bundle=await this.frontends.cacheVersion(code,pick.component_version);
          job.controller.signal.throwIfAborted();
          pick.frontend_id=lookup()??this.frontends.register(job.actor,{bundle}).id;
        }
      }
      job.stage='service';
      const initial=this.snapshot(job.game_id,pick);
      job.fingerprint=initial.fingerprint;job.service_id=initial.service.id;job.frontend_id=initial.frontend.id;
       await this.serviceProbe(initial.service.id);
       if(initial.frontend.id.startsWith('fe-v')){
         const row=this.frontends.release(initial.frontend.id);
         await this.frontends.cacheVersion(row.code,row.manifest.component_version!,row.manifest_sha256);
       }
      job.controller.signal.throwIfAborted();job.stage='private';
      const {release,bundle,manifest}=this.verifyPrivate(initial.frontend.id);
      if(this.config.environment==='production') {
        const origin=new URL(release.origin);
        check(origin.protocol==='https:'&&origin.origin===release.origin,'FRONTEND_ORIGIN_TEMPLATE_INVALID','生产前端版本必须使用 HTTPS 域名',409);
        job.stage='manifest';job.total=1;
        // 按发布器生成的原始字节重建版本标记；校验清单，不重新下载素材。
        const marker=Buffer.from(JSON.stringify(frontendMarker(manifest,release.manifest_sha256),null,2)+'\n');
        const response=await fetch(this.frontends.cdnURL(manifest,'_gtt-manifest.json',origin.origin),{cache:'no-store',redirect:'manual',credentials:'omit',signal:AbortSignal.any([job.controller.signal,AbortSignal.timeout(15000)])});
        if(response.status!==200||!response.body){await response.body?.cancel();throw new ServiceError('FRONTEND_CDN_UNAVAILABLE','CDN 版本清单不可访问，请检查版本域名和 _gtt-manifest.json 路由',409);}
        const reader=response.body.getReader(),hash=createHash('sha256');let size=0;
        try {while(true){const chunk=await reader.read();if(chunk.done)break;size+=chunk.value.byteLength;check(size<=marker.length,'FRONTEND_CDN_CHANGED','CDN 版本清单与所选发布不一致',409);hash.update(chunk.value);}}
        finally{await reader.cancel().catch(()=>{});}
        check(size===marker.length&&hash.digest('hex')===sha(marker),'FRONTEND_CDN_CHANGED','CDN 版本清单与所选发布不一致',409);
        job.completed=1;
      }else{
        job.stage='assets';job.total=manifest.files.length;
        for(const file of manifest.files){job.controller.signal.throwIfAborted();frontendFile(bundle,'objects',file);job.completed++;}
      }
      job.stage='recheck';job.controller.signal.throwIfAborted();
      await this.serviceProbe(initial.service.id);
      job.controller.signal.throwIfAborted();
      check(this.snapshot(job.game_id,pick).fingerprint===job.fingerprint,'VERSION_CONFLICT','检查期间游戏或前端版本已变化，请重新检查',409);
      check(this.p.control.gameAvailability(job.game_id).version===job.version,'VERSION_CONFLICT','检查期间开放状态已变化，请重新检查',409);
      this.verifyPrivate(initial.frontend.id);
      if(pick){
        this.p.control.setGameAvailability(job.actor,{game_id:job.game_id,enabled:true,version:job.version},()=>{
          check(this.snapshot(job.game_id,pick).fingerprint===job.fingerprint,'VERSION_CONFLICT','检查结果已过期',409);
          this.p.control.run("UPDATE frontend_releases SET status='verified' WHERE id=? AND status='staged'",initial.frontend.id);
          this.applyPair(job.actor,pick,initial.code,this.frontends.release(initial.frontend.id),this.services.release(initial.service.id),COMPONENT_VERSION.exec(pick.component_version)![1]);
          this.p.control.audit(job.actor,'game.availability.auto-open',initial.code,'success',{check_id:job.id,files:job.total});
        });
        job.status='applied';job.finished=Date.now();return;
      }
      job.status='ready';job.stage='ready';job.finished=Date.now();
      this.p.control.audit(job.actor,'game.availability.check',String(job.game_id),'success',{check_id:job.id,service_id:job.service_id,frontend_id:job.frontend_id,files:job.total});
    } catch(error) {
      const stage=job.stage;job.controller.abort();job.status='failed';job.stage='failed';job.finished=Date.now();
      job.error=error instanceof ServiceError?{code:error.code,message:error.message}:{code:'GAME_DEPLOYMENT_CHECK_FAILED',message:({registration:'启动资料读取失败，请检查前端版本、安装目录和文件权限',manifest:'CDN 版本清单读取失败，请检查版本域名、网络和路由',assets:'素材检查失败，请检查资源响应',service:'计算服务检查失败，请检查服务地址与认证'} as Record<string,string>)[stage]??'部署检查失败：服务超时、资源缺失或检查已取消，请检查部署后重试'};
      if(!this.closed)try {this.p.control.audit(job.actor,'game.availability.check',String(job.game_id),'failed',{check_id:job.id,code:job.error.code});}catch {}
    } finally {clearTimeout(deadline);}
  }
  enable(actor:string,q:any) {
    const job=this.ticket(actor,q.check_id);
    check(q.enabled===true&&q.game_id===job.game_id&&q.version===job.version,'INVALID_ARGUMENT');
    check(job.status==='ready'&&Date.now()-(job.finished??0)<60000,'GAME_CHECK_REQUIRED','请先完成当前版本的部署检查；通过结果仅在一分钟内有效',409);
    const availability=this.p.control.setGameAvailability(actor,q,()=>{
      check(this.snapshot(job.game_id).fingerprint===job.fingerprint,'VERSION_CONFLICT','计算服务或前端版本已变化，请重新检查',409);
      this.verifyPrivate(job.frontend_id!);
      this.p.control.audit(actor,'game.availability.confirm',String(job.game_id),'success',{check_id:job.id,service_id:job.service_id,frontend_id:job.frontend_id,files:job.total});
    });
    job.status='applied';return availability;
  }
  cancel(gameId:number) {for(const job of this.jobs.values())if(job.game_id===gameId){job.controller.abort();if(job.status==='ready'){job.status='failed';job.finished=Date.now();job.error={code:'VERSION_CONFLICT',message:'游戏已关闭，请重新检查'};}}}
  close() {this.closed=true;for(const job of this.jobs.values())job.controller.abort();}
}
