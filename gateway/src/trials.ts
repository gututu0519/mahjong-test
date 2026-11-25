import {amount,check,encode,hex,now,sha,token} from '../../other/shared/core.js';
import {trialDDL} from '../../other/shared/database/trial-migration.js';
import {gameCode,gameNumber,gameUnit} from './catalog.js';
import {merchantLaunchQuery} from './merchant-client.js';
import type {MerchantGames} from './merchant-games.js';

/** 试玩使用独立邀请、会话、钱包及幂等流水；不创建商户，不调用正式钱包。 */
export class Trials{
  constructor(private games:Pick<MerchantGames,'p'|'remote'|'config'|'frontends'>){
    const db=this.db;
    if(db.db.sqlite&&!db.get("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trial_links'"))db.tx(()=>db.db.exec(trialDDL));
  }
  get db(){return this.games.p.control;}
  /** 只读本游戏当前已经开放且通过验证的配套版本。 */
  private pair(code:string){
    check(this.db.gameAvailability(gameNumber(code)).enabled,'GAME_CLOSED','游戏未开放',409);
    const s=this.games.remote?.active(code),f=this.db.get('SELECT r.* FROM frontend_routes a JOIN frontend_releases r ON a.release_id=r.id WHERE a.code=?',code);
    check(s?.status==='ready'&&f?.status==='verified'&&f.code===code,'TRIAL_NOT_READY','游戏未激活可用的前后端版本',409);
    return {s:s!,f};
  }
  /** 生成可重复使用的邀请，而不是复用玩家令牌。 */
  create(actor:string,q:any){
    const code=gameCode(q.game_id),hours=q.hours??24,credits=q.credits??1000,language=q.language??'zh',note=q.note??'';
    check([1,24,168].includes(hours)&&[100,1000,10000].includes(credits)&&['zh','en'].includes(language)&&typeof note==='string'&&note.length<=120,'INVALID_ARGUMENT');
    return this.db.tx(()=>{
      const {s,f}=this.pair(code),id=hex(24),at=now();
      this.db.run('INSERT INTO trial_links VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',id,code,f.id,s.id,language,credits,note,actor,at,at+hours*3600,0,0);
      this.db.audit(actor,'trial.create',code,'success',{hours,credits,frontend:f.id,service:s.id});
      return this.view(this.db.get('SELECT * FROM trial_links WHERE id=?',id));
    });
  }
  /** 管理页面只返回邀请信息，运行会话永不暴露。 */
  private view(r:any){
    const frontend=this.games.frontends.release(r.frontend_id),service=this.games.remote!.release(r.service_id);
    return {...r,url:new URL('/trial/'+r.id,this.games.config.public_origins?.play??this.games.p.playOrigin).href,
      frontend_version:frontend.manifest.component_version??frontend.id,service_version:service.release,
      status:r.disabled?'disabled':r.expires_at<=now()?'expired':!this.db.gameAvailability(gameNumber(r.code)).enabled?'closed':
        !this.db.get('SELECT 1 FROM frontend_routes f JOIN game_service_routes s ON s.code=f.code WHERE f.code=? AND f.release_id=? AND s.release_id=?',r.code,r.frontend_id,r.service_id)?'changed':'active'};
  }
  /** 按游戏查询最近的邀请。 */
  list(id:number){return this.db.all('SELECT * FROM trial_links WHERE code=? ORDER BY created_at DESC,id DESC LIMIT 100',gameCode(id)).map(r=>this.view(r));}
  /** 停用邀请仅阻止后续兑换，不修改已生成的会话。 */
  disable(actor:string,id:string){
    return this.db.tx(()=>{const r=this.db.get('SELECT code FROM trial_links WHERE id=?',id);check(r,'TRIAL_NOT_FOUND','邀请不存在',404);this.db.run('UPDATE trial_links SET disabled=1 WHERE id=?',id);this.db.audit(actor,'trial.disable',r.code,'success',{reference:sha(id)});return {disabled:true};});
  }
  /** 兑换前及网络调用后都重新检查邀请状态和实际路由。 */
  private usable(id:string){
    const r=this.db.get('SELECT * FROM trial_links WHERE id=?',id);
    check(r&&!r.disabled&&r.expires_at>now(),'TRIAL_EXPIRED','试玩邀请已失效',410);
    const {s,f}=this.pair(r.code);check(s.id===r.service_id&&f.id===r.frontend_id,'TRIAL_VERSION_CHANGED','游戏版本已变更，请重新生成试玩邀请',409);
    return {r,s,f};
  }
  /** 每次兑换生成独立试玩余额，启动地址与正式游戏沿用同一协议。 */
  async redeem(id:string){
    const {r,s}=this.usable(id),state=await this.games.remote!.request(s,'invoke',{method:'initial_state',args:[hex(32)]});
    return this.db.tx(()=>{
      const {f}=this.usable(id),tk='trial.'+token(),pid='trial-'+hex();
      this.db.run('INSERT INTO trial_sessions VALUES(?,?,?,?,?,?,?,?,?)',sha(tk),pid,id,r.code,f.id,s.id,now()+86400,r.credits*gameUnit(r.code),encode(state));
      this.db.run('UPDATE trial_links SET starts=starts+1 WHERE id=?',id);
      return f.origin+'/?'+merchantLaunchQuery(r.code,tk,r.language,'GTT-TRIAL');
    });
  }
  /** 验证试玩令牌与游戏、前端绑定；不接受其作为商户令牌。 */
  session(tk:string,code?:string,frontend?:string){
    const r=this.db.get('SELECT * FROM trial_sessions WHERE token_hash=?',sha(tk));
    check(r&&r.expires_at>now()&&(!code||code===r.code)&&(!frontend||frontend===r.frontend_id),'TRIAL_SESSION_INVALID','试玩会话无效，请重新打开邀请',403);
    return r;
  }
  /** 返回协议层所需的虚拟钱包，单位始终与引擎一致。 */
  wallet(tk:string){const r=this.session(tk);return {player_id:r.player_id,balance_minor:r.balance,currency:'USD',minor_unit:gameUnit(r.code)};}
  /** 试玩历史不查询正式交易表。 */
  history(tk:string,n=20){const r=this.session(tk);check(Number.isInteger(n)&&n>=1&&n<=100,'LIMIT_INVALID');return this.db.all('SELECT response_json FROM trial_operations WHERE player_id=? ORDER BY seq DESC LIMIT ?',r.player_id,n).map(x=>JSON.parse(x.response_json));}
  /** 向独立试玩协议工作进程提供其绑定版本的状态与增量回合。 */
  async snapshot(tk:string,after=0){
    const r=this.session(tk),s=this.games.remote!.release(r.service_id),raw=JSON.parse(r.state_json),d=s.descriptor,wallet=this.wallet(tk);
    const state=await this.games.remote!.request(s,'invoke',{method:'public_state',args:[raw]});
    return {mirror:{player_id:r.player_id,expires_at:r.expires_at,operations:this.db.all('SELECT * FROM trial_operations WHERE player_id=? AND seq>? ORDER BY seq',r.player_id,after)},
      snapshot:{expires_at:r.expires_at,state:{game_id:r.code,engine_version:d.version,ruleset_id:d.ruleset_id,state,balance_minor:r.balance},raw_state:raw,engine:{config:d.config,version:d.version,ruleset_id:d.ruleset_id},wallet}};
  }
  /** 调用绑定的计算服务，以同一事务提交试玩积分、回合状态和幂等记录。 */
  async spin(tk:string,key:string,previous:string,payload:any){
    check(typeof key==='string'&&key.length>0&&key.length<=128&&typeof previous==='string'&&previous.length<=64,'REQUEST_KEY_INVALID');
    const r=this.session(tk),s=this.games.remote!.release(r.service_id),invoke=(method:string,args:any[])=>this.games.remote!.request(s,'invoke',{method,args});
    const bet=await invoke('normalize_bet',[payload]),request=encode({previous_sid:previous,bet});
    const prior=()=>{const row=this.db.get('SELECT * FROM trial_operations WHERE player_id=? AND request_key=?',r.player_id,key);if(row){check(row.request_json===request,'IDEMPOTENCY_CONFLICT');return JSON.parse(row.response_json);}};
    const old=prior();if(old)return old;
    const raw=JSON.parse(r.state_json);check(raw.sid===previous,'STALE_STATE','请刷新试玩状态',409);
    const eligible=()=>{if(raw.phase==='ready'){const active=this.pair(r.code);check(active.s.id===s.id&&active.f.id===r.frontend_id,'TRIAL_VERSION_CHANGED','游戏版本已变更，不能开始新回合',409);}};
    eligible();
    const seq=this.db.tx(()=>{this.db.run('UPDATE trial_counter SET value=value+1 WHERE id=1');return this.db.get('SELECT value FROM trial_counter WHERE id=1').value;});
    const c=await invoke('step',[raw,bet,hex(32),String(seq*4096)]);
    const debit=amount(c.debit_minor),credit=amount(c.credit_minor);
    return this.db.tx(()=>{
      const done=prior();if(done)return done;
      const current=this.session(tk);check(current.state_json===r.state_json,'STALE_STATE','请刷新试玩状态',409);eligible();
      check(current.balance>=debit,'INSUFFICIENT_FUNDS','试玩余额不足',409);const balance=amount(current.balance-debit+credit);
      const result={game_id:gameNumber(r.code),sid:c.state.sid,round_id:c.event.round_id,engine_version:s.descriptor.version,ruleset_id:s.descriptor.ruleset_id,minor_unit:gameUnit(r.code),outcome:c.event,
        wallet:{before_minor:current.balance,debit_minor:debit,credit_minor:credit,after_minor:balance}};
      this.db.run('INSERT INTO trial_operations VALUES(?,?,?,?,?,?,?)',seq,r.player_id,key,request,encode({...c,ruleset_id:s.descriptor.ruleset_id}),encode(result),now());
      this.db.run('UPDATE trial_sessions SET balance=?,state_json=? WHERE token_hash=?',balance,encode(c.state),sha(tk));return result;
    });
  }
}
