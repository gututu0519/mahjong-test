import {createHash,randomUUID} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {check,encode,sha,ServiceError} from '../../other/shared/core.js';
import {readFrontendManifest,frontendFile} from '../../other/shared/frontend-manifest.js';
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
};

// Checks are deliberately transient, never an alternative durable source of
// availability. A restart loses check tickets; clients must recheck before open.
export class GameAvailabilityChecks {
  private jobs=new Map<string,Job>();
  private closed=false;
  constructor(private p:Provider,private services:GameServices,private frontends:FrontendVersions,private config:any) {}
  private snapshot(id:number) {
    const code=gameCode(id),db=this.p.control;
    const serviceRoute=db.get('SELECT * FROM game_service_routes WHERE code=?',code);
    check(serviceRoute,'GAME_SERVICE_REQUIRED','请先登记并激活游戏计算服务',409);
    const service=db.get('SELECT * FROM game_service_releases WHERE id=?',serviceRoute.release_id);
    check(service?.status==='ready','GAME_SERVICE_NOT_READY','当前游戏计算版本不可用或已退役',409);
    const frontendRoute=db.get('SELECT * FROM frontend_routes WHERE code=?',code);
    check(frontendRoute,'FRONTEND_VERSION_REQUIRED','请先登记、校验并激活游戏前端版本',409);
    const frontend=db.get('SELECT * FROM frontend_releases WHERE id=?',frontendRoute.release_id);
    check(frontend?.status==='verified','FRONTEND_NOT_VERIFIED','当前前端版本未通过校验或已退役',409);
    const descriptor=JSON.parse(service.descriptor_json),manifest=JSON.parse(frontend.manifest_json);
    check(service.code===code&&frontend.code===code&&manifest.game===code,'GAME_RELEASE_CHANGED','登记版本与游戏身份不一致',409);
    check(descriptor.client_contract===manifest.client_contract,'FRONTEND_CONTRACT_MISMATCH','前端与游戏计算服务的协议契约不匹配',409);
    return {code,service,frontend,fingerprint:sha(encode({serviceRoute,service,frontendRoute,frontend}))};
  }
  private view(job:Job) {
    return {id:job.id,game_id:job.game_id,version:job.version,status:job.status,stage:job.stage,completed:job.completed,total:job.total,
      ...(job.error?{error:job.error}:{}),...(job.finished?{expires_at:Math.floor((job.finished+60000)/1000)}:{})};
  }
  private prune() {
    for(const [id,job]of this.jobs)if(job.status!=='checking'&&Date.now()-(job.finished??job.created)>15*60*1000)this.jobs.delete(id);
  }
  begin(actor:string,q:any) {
    gameCode(q.game_id);
    check(q.enabled===true&&Number.isInteger(q.version)&&q.version>=0,'INVALID_ARGUMENT');
    check(this.p.control.gameAvailability(q.game_id).version===q.version,'VERSION_CONFLICT','开放状态已变化，请刷新后重试',409);
    this.prune();
    const existing=[...this.jobs.values()].find(job=>job.actor===actor&&job.game_id===q.game_id&&job.version===q.version&&job.status==='checking');
    if(existing)return this.view(existing);
    check([...this.jobs.values()].filter(job=>job.status==='checking').length<4&&this.jobs.size<100,'GAME_CHECK_BUSY','检查任务繁忙，请稍后再试',429);
    const job:Job={id:randomUUID(),actor,game_id:q.game_id,version:q.version,status:'checking',stage:'service',completed:0,total:0,created:Date.now(),controller:new AbortController()};
    this.jobs.set(job.id,job);
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
    check(manifest.bootstrap.some(file=>file.path===`resources/clients/${manifest.game}/index.html`),'FRONTEND_ENTRY_REQUIRED','前端缺少当前游戏的启动页面 index.html',409);
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
      const initial=this.snapshot(job.game_id);
      job.fingerprint=initial.fingerprint;job.service_id=initial.service.id;job.frontend_id=initial.frontend.id;
      await this.serviceProbe(initial.service.id);
      job.controller.signal.throwIfAborted();job.stage='private';
      const {release,bundle,manifest}=this.verifyPrivate(initial.frontend.id);
      if(this.config.environment==='production') {
        const origin=new URL(release.origin);
        check(origin.protocol==='https:'&&origin.origin===release.origin,'FRONTEND_ORIGIN_TEMPLATE_INVALID','生产前端版本必须使用 HTTPS 域名',409);
      }
      job.stage='assets';job.total=manifest.files.length;
      let index=0;
      const worker=async()=>{
        while(index<manifest.files.length) {
          job.controller.signal.throwIfAborted();const file=manifest.files[index++];
          if(this.config.environment==='production') {
            const response=await fetch(release.origin+'/'+file.path.split('/').map(encodeURIComponent).join('/'),{
              redirect:'manual',credentials:'omit',signal:AbortSignal.any([job.controller.signal,AbortSignal.timeout(15000)])});
            if(response.status!==200){await response.body?.cancel();throw new ServiceError('FRONTEND_CDN_UNAVAILABLE','前端资源无法访问：'+file.path,409);}
            check(response.body,'FRONTEND_CDN_UNAVAILABLE','前端资源没有响应内容：'+file.path,409);
            const reader=response.body.getReader(),hash=createHash('sha256');let size=0;
            try {while(true){const chunk=await reader.read();if(chunk.done)break;size+=chunk.value.byteLength;check(size<=file.size,'FRONTEND_CDN_CHANGED','前端资源大小不符：'+file.path,409);hash.update(chunk.value);}}
            finally {await reader.cancel().catch(()=>{});}
            check(size===file.size&&hash.digest('hex')===file.sha256,'FRONTEND_CDN_CHANGED','前端资源校验失败：'+file.path,409);
          } else frontendFile(bundle,'objects',file);
          job.completed++;
        }
      };
      await Promise.all(Array.from({length:Math.min(4,job.total)},()=>worker()));
      job.stage='recheck';job.controller.signal.throwIfAborted();
      await this.serviceProbe(initial.service.id);
      job.controller.signal.throwIfAborted();
      check(this.snapshot(job.game_id).fingerprint===job.fingerprint,'VERSION_CONFLICT','检查期间游戏或前端版本已变化，请重新检查',409);
      check(this.p.control.gameAvailability(job.game_id).version===job.version,'VERSION_CONFLICT','检查期间开放状态已变化，请重新检查',409);
      this.verifyPrivate(initial.frontend.id);
      job.status='ready';job.stage='ready';job.finished=Date.now();
      this.p.control.audit(job.actor,'game.availability.check',String(job.game_id),'success',{check_id:job.id,service_id:job.service_id,frontend_id:job.frontend_id,files:job.total});
    } catch(error) {
      job.controller.abort();job.status='failed';job.stage='failed';job.finished=Date.now();
      job.error=error instanceof ServiceError?{code:error.code,message:error.message}:{code:'GAME_DEPLOYMENT_CHECK_FAILED',message:'部署检查失败：服务超时、资源缺失或检查已取消，请检查部署后重试'};
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
