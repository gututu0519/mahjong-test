import { test } from "node:test";
import assert from "node:assert/strict";
import {
  mkdtempSync,
  mkdirSync,
  existsSync,
  copyFileSync,
  writeFileSync,
  readFileSync,
  rmSync,
} from "node:fs";
import { join, resolve } from "node:path";
import { tmpdir } from "node:os";
import { execFileSync } from "node:child_process";
import { request } from "node:http";
import { Control } from "../shared/control.js";
import { Provider } from "../../gateway/src/provider.js";
import { GameClient } from "../../gateway/src/game-client.js";
import { gatewayServer } from "../../gateway/src/http.js";
import { adminServer } from "../../admin/backend/admin.js";
import {GameAvailabilityChecks} from '../../admin/backend/game-availability.js';
import {Trials} from '../../gateway/src/trials.js';
import {GAME_CODES} from '../../gateway/src/catalog.js';
import { computeServer } from "../shared/services/compute.js";
import { platformServer } from "../shared/services/platform.js";
import { listen } from "../shared/http.js";
import { readFrontendManifest,frontendMarker } from "../shared/frontend-manifest.js";
import {sha} from "../shared/core.js";
import { pathToFileURL } from "node:url";
import { runInNewContext } from "node:vm";

async function fixture(t: any) {
  const dir = mkdtempSync(join(tmpdir(), "frontend-versions-")),
    source = join(dir, "source"),
    installed = join(dir, "installed");
  mkdirSync(join(source, "fixtures"), { recursive: true });
  for (const name of [
    "index.html",
    "local-auth-bootstrap.js",
    "local-frame-clock.js",
    "fixtures/auth-metadata.json",
    "fixtures/game-rule.json",
  ])
    copyFileSync(resolve("../clients/buffalo-win", name), join(source, name));
  mkdirSync(join(source, "assets"), { recursive: true });
  writeFileSync(join(source, "private.json"), '{"secret":"ROOT_PRIVATE"}');
  writeFileSync(join(source, "assets/marker.json"), '{"version":"old"}');
  writeFileSync(
    join(source, "fixtures/secret.json"),
    '{"secret":"PRIVATE_SENTINEL"}',
  );
  mkdirSync(join(source, "diagnostics/profile"), { recursive: true });
  writeFileSync(
    join(source, "diagnostics/profile/secret.json"),
    '{"secret":"PRIVATE_PROFILE"}',
  );
  const control = new Control(
    join(dir, "control.db"),
    resolve("config/control.sql"),
  );
  const created = control.saveMerchant(
      "test",
      {
        name: "frontend-merchant",
        enabled: true,
        wallet_url: "http://127.0.0.1:8111",
        games: [1],
      },
      true,
    ),
    mid = created.merchant.id;
  const config: any = {
    environment: "development",
    game_services_mode: "remote",
    frontend_releases_directory: installed,
    game_database: join(dir, "games.db"),
    platform_database: join(dir, "wallet.db"),
    gateway_origin: "http://127.0.0.1",
    sandbox_merchant: mid,
    sandbox_player: "p1",
    sandbox_balance_minor: 100000000,
  };
  const servers = new Set<any>();
  const { server: wallet } = platformServer(config, control);
  servers.add(wallet);
  const wp = await listen(wallet);
  control.saveMerchant("test", {
    ...control.merchant(mid),
    wallet_url: "http://127.0.0.1:" + wp,
  });
  control.setGameAvailability("test", {
    game_id: 1,
    enabled: true,
    version: 0,
  });
  const secret = "frontend-test-key-".repeat(4),
    game = computeServer(
      "buffalo-win",
      resolve("../services/buffalo-win/config/buffalo-win.json"),
      secret,
      { release: "v1.0" },
    );
  servers.add(game);
  const gp = await listen(game);
  let p: Provider,
    gateway: any,
    port = 0;
  const start = async () => {
    p = new Provider(
      config.game_database,
      control,
      new GameClient("http://127.0.0.1:1", secret, {}),
      resolve("config/game.sql"),
      config.gateway_origin,
    );
    p.enableGames(config);
    await p.initialize();
    gateway = gatewayServer(p, config, resolve("../clients/buffalo-win"));
    servers.add(gateway);
    port = await listen(gateway, port);
    p.playOrigin = config.gateway_origin = "http://127.0.0.1:" + port;
  };
  await start();
  const backend = await p!.multi!.remote!.register("test", {
    code: "buffalo-win",
    origin: "http://127.0.0.1:" + gp,
    secret,
  });
  assert.equal(backend.release, "v1.0");
  await p!.multi!.remote!.activate("test", { id: backend.id, revision: 0 });
  const stop = async (server: any) => {
    server.closeAllConnections();
    await new Promise<void>((ok) => server.close(() => ok()));
    servers.delete(server);
  };
  let buildSequence=0;
  const f: any = {
    dir,
    source,
    installed,
    control,
    config,
    mid,
    created,
    servers,
    compute: game,
    stop,
    get p() {
      return p!;
    },
    get versions() {
      return p!.multi!.frontends;
    },
    get port() {
      return port;
    },
    build: (version=`v1.${buildSequence++}`,remote=false,cdnEntry=false) => {
      const result = JSON.parse(
        execFileSync(
          process.execPath,
          [
            resolve("tools/build-frontend.mjs"),
            "--game",
            "buffalo-win",
            remote?"--remote-version":"--component-version",version,
            ...(cdnEntry?['--cdn-entry']:[]),
            "--source",
            source,
            "--output",
            join(dir, "builds"),
          ],
          { encoding: "utf8", windowsHide: true },
        ),
      );
      execFileSync(
        process.execPath,
        [
          resolve("tools/install-frontend.mjs"),
          result.bundle,
          "--destination",
          installed,
        ],
        { windowsHide: true, stdio: "pipe" },
      );
      return { ...result, bundle: result.release };
    },
    launch: async () => p!.launch(mid, { game_id: 1, player_id: "p1" }),
    restart: async () => {
      await gateway.protocolPool.close();
      await stop(gateway);
      p!.close();
      await start();
    },
    http: (host: string, path: string, form?:URLSearchParams, sessionToken?:string) =>
      new Promise<any>((ok, fail) => {
        const req = request(
          { host: "127.0.0.1", port, path, method:form?'POST':'GET',headers: { host,...(form?{'content-type':'application/x-www-form-urlencoded',authorization:'Bearer '+sessionToken,'x-local-game-session':sessionToken}:{} ) }, agent: false },
          (res) => {
            const chunks: Buffer[] = [];
            res.on("data", (b) => chunks.push(b));
            res.on("end", () =>
              ok({
                status: res.statusCode,
                headers: res.headers,
                body: Buffer.concat(chunks).toString(),
              }),
            );
          },
        );
        req.on("error", fail);
        req.end(form?.toString());
      }),
  };
  t.after(async () => {
    await gateway.protocolPool.close();
    for (const server of [...servers]) await stop(server);
    p!.close();
    control.close();
    rmSync(dir, { recursive: true, force: true });
  });
  return f;
}

test("frontend builds generate a new immutable version every time, without publishing private bootstrap or browser profiles", async (t) => {
  const f = await fixture(t),
    first = f.build(),
    second = f.build();
  assert.notEqual(first.release, second.release);
  assert.equal(first.content_hash, second.content_hash);
  const m = readFrontendManifest(join(f.installed, first.release));
  assert.ok(m.files.some((row) => row.path === "assets/marker.json"));
  assert.ok(
    !m.files.some(
      (row) =>
        row.path.endsWith(".html") ||
        row.path === "private.json" ||
        row.path.includes("fixtures") ||
        row.path.includes("diagnostics"),
    ),
  );
  assert.ok(!m.bootstrap.some((row) => row.path.endsWith("secret.json")));
  assert.ok(m.bootstrap.some((row) => row.path.endsWith("index.html")));
  const registered = f.versions.register("test", { bundle: first.bundle });
  assert.equal(registered.id, first.release);
  assert.throws(
    () => f.versions.activate("test", { id: first.release, revision: 0 }),
    { code: "FRONTEND_NOT_VERIFIED" },
  );
  writeFileSync(
    join(f.installed, first.release, "objects/assets/marker.json"),
    "corrupted",
  );
  await assert.rejects(f.versions.probe("test", first.release), {
    code: "FRONTEND_FILE_CHANGED",
  });
});

test('试玩邀请独立会话、隔离钱包、幂等结算、停用过期和版本绑定',async t=>{
  const f=await fixture(t),build=f.build();f.versions.register('test',{bundle:build.bundle});await f.versions.probe('test',build.release);f.versions.activate('test',{id:build.release,revision:0});
  const trials=new Trials(f.p.multi),invite=trials.create('test',{game_id:1,credits:100,language:'en'}),open=()=>fetch(invite.url,{redirect:'manual'});
  const a=await open(),b=await open();assert.equal(a.status,303);assert.equal(a.headers.get('cache-control'),'private, no-store');
  const first=new URL(a.headers.get('location')!),ta=first.searchParams.get('ops')!,tb=new URL(b.headers.get('location')!).searchParams.get('ops')!;
  assert.notEqual(ta,tb);assert.equal(trials.list(1)[0].starts,2);
  const initial=trials.wallet(ta);assert.notEqual(initial.player_id,trials.wallet(tb).player_id);assert.equal(initial.balance_minor,100*initial.minor_unit);
  const page=await f.http(first.host,first.pathname+first.search);assert.equal(page.status,200,page.body.slice(0,200));assert.ok(page.body.includes(ta));
  const pg=async(path:string,fields:Record<string,string>={})=>{
    const response=await f.http(first.host,path,new URLSearchParams({atk:tb,btt:'1',...fields}),tb);
    assert.equal(response.status,200,path+': '+response.body);const reply=JSON.parse(response.body);
    assert.equal(reply.err,null,path+': '+response.body);return reply.dt;
  };
  assert.equal((await pg('/web-api/auth/session/v2/verifyOperatorPlayerSession')).tk,tb);
  const info=await pg('/game-api/buffalo-win/v2/GameInfo/Get');
  assert.equal(info.bl,100);
  const spinFields={wk:'0_C',pf:'1',cs:'0.1',ml:'1',id:info.ls.si.sid};
  const played=await pg('/game-api/buffalo-win/v2/Spin',spinFields);assert.ok(played.si.sid);
  const nextInfo=await pg('/game-api/buffalo-win/v2/GameInfo/Get');assert.equal(nextInfo.ls.si.sid,played.si.sid);
  const independentBalance=trials.wallet(tb).balance_minor;
  const {snapshot}=await trials.snapshot(ta);
  const spin=await trials.spin(ta,'test-spin',snapshot.raw_state.sid,{cs:0.1,ml:1});
  const legacy=JSON.parse(f.control.get('SELECT candidate_json FROM trial_operations WHERE player_id=?',initial.player_id).candidate_json);
  delete legacy.ruleset_id;
  f.control.run('UPDATE trial_operations SET candidate_json=? WHERE player_id=?',JSON.stringify(legacy),initial.player_id);
  const recovered=await f.http(first.host,'/game-api/buffalo-win/v2/GameInfo/Get',new URLSearchParams({atk:ta,btt:'1'}),ta);
  assert.equal(recovered.status,200,recovered.body);
  assert.equal(JSON.parse(recovered.body).dt.ls.si.sid,spin.sid);
  assert.deepEqual(await trials.spin(ta,'test-spin',snapshot.raw_state.sid,{cs:0.1,ml:1}),spin);
  assert.equal(trials.wallet(ta).balance_minor,initial.balance_minor-spin.wallet.debit_minor+spin.wallet.credit_minor);
  assert.equal(trials.wallet(tb).balance_minor,independentBalance);
  assert.equal(f.p.get('SELECT COUNT(*) AS n FROM game_operations').n,0);assert.equal(f.p.get('SELECT COUNT(*) AS n FROM merchant_sessions').n,0);
  assert.throws(()=>f.p.session(ta));trials.disable('test',invite.id);assert.equal((await open()).status,410);assert.equal(trials.history(ta).length,1);
  const other=trials.create('test',{game_id:1});f.control.run('UPDATE trial_links SET expires_at=0 WHERE id=?',other.id);
  await assert.rejects(trials.redeem(other.id),{code:'TRIAL_EXPIRED'});
  const changed=trials.create('test',{game_id:1}),next=f.build();
  f.versions.register('test',{bundle:next.bundle});await f.versions.probe('test',next.release);f.versions.activate('test',{id:next.release,revision:1});
  await assert.rejects(trials.redeem(changed.id),{code:'TRIAL_VERSION_CHANGED'});
  f.control.setGameAvailability('test',{game_id:1,enabled:false,version:f.control.gameAvailability(1).version});assert.throws(()=>trials.create('test',{game_id:1}),{code:'GAME_CLOSED'});
});

test('paired activation rejects cross-generation and stale revisions without changing either route',async t=>{
  const f=await fixture(t),checks=new GameAvailabilityChecks(f.p,f.p.multi.remote,f.versions,f.config);
  t.after(()=>checks.close());
  const service=f.control.get('SELECT * FROM game_service_routes WHERE code=?','buffalo-win');
  const base={game_id:1,service_id:service.release_id,service_revision:service.revision,frontend_revision:0};
  for(const version of ['v2.0','v1.4']){
    const build=f.build(version);f.versions.register('test',{bundle:build.bundle});await f.versions.probe('test',build.release);
    const q={...base,frontend_id:build.release};
    if(version==='v2.0'){
      await assert.rejects(checks.activatePair('test',q),{code:'GAME_MAJOR_MISMATCH'});
      assert.ok(!f.control.get('SELECT * FROM frontend_routes WHERE code=?','buffalo-win'));
    }else{
      await checks.activatePair('test',q);
      await assert.rejects(checks.activatePair('test',q),{code:'VERSION_CONFLICT'});
      assert.equal(f.control.get('SELECT * FROM frontend_routes WHERE code=?','buffalo-win').release_id,build.release);
    }
    assert.deepEqual(f.control.get('SELECT * FROM game_service_routes WHERE code=?','buffalo-win'),service);
  }
});

async function preparedOpening(t:any) {
  const f=await fixture(t),build=f.build();
  f.versions.register('test',{bundle:build.bundle});
  await f.versions.probe('test',build.release);
  f.versions.activate('test',{id:build.release,revision:0});
  const availability=f.control.setGameAvailability('test',{game_id:1,enabled:false,version:f.control.gameAvailability(1).version});
  const checks=new GameAvailabilityChecks(f.p,f.p.multi.remote,f.versions,f.config);
  t.after(()=>checks.close());
  const request={game_id:1,enabled:true,version:availability.version};
  const wait=async(id:string,owner='test')=>{
    for(let i=0;i<500;i++){const result=checks.status(owner,id);if(result.status!=='checking')return result;await new Promise(ok=>setTimeout(ok,20));}
    throw Error('Availability check timeout');
  };
  return {...f,buildCandidate:f.build,build,checks,request,wait};
}

test('一键开放对候选版本执行检查并原子提交，修订冲突不激活候选前端',async t=>{
  const f=await preparedOpening(t),s=f.control.get('SELECT * FROM game_service_routes WHERE code=?','buffalo-win'),route=f.control.get('SELECT * FROM frontend_routes WHERE code=?','buffalo-win');
  const candidate=f.buildCandidate('v1.8');
  f.versions.register('test',{bundle:candidate.bundle});
  const pick={service_id:s.release_id,component_version:'v1.8',frontend_revision:route.revision,service_revision:s.revision};
  const stale=f.checks.begin('test',f.request,{...pick});
  f.control.run('UPDATE frontend_routes SET revision=revision+1 WHERE code=?','buffalo-win');
  assert.equal((await f.wait(stale.id)).error?.code,'VERSION_CONFLICT');
  assert.equal(f.control.gameAvailability(1).enabled,false);
  assert.equal(f.control.get('SELECT release_id FROM frontend_routes WHERE code=?','buffalo-win').release_id,route.release_id);
  assert.equal(f.versions.release(candidate.release).status,'staged');
  const ready=f.checks.begin('test',f.request,{...pick,frontend_revision:route.revision+1});
  assert.equal((await f.wait(ready.id)).status,'applied');
  assert.equal(f.control.gameAvailability(1).enabled,true);
  assert.equal(f.control.get('SELECT release_id FROM frontend_routes WHERE code=?','buffalo-win').release_id,candidate.release);
  assert.equal(f.versions.release(candidate.release).status,'verified');
});

test('opening check requires active compute and frontend, rejects forged tickets and preserves closure',async t=>{
  const f=await preparedOpening(t);
  assert.throws(()=>f.checks.enable('test',{...f.request,check_id:'forged'}),{code:'GAME_CHECK_EXPIRED'});
  const route=f.control.get('SELECT * FROM game_service_routes WHERE code=?','buffalo-win');
  f.control.run('DELETE FROM game_service_routes WHERE code=?','buffalo-win');
  let job=f.checks.begin('test',f.request);
  assert.equal((await f.wait(job.id)).error?.code,'GAME_SERVICE_REQUIRED');
  f.control.run('INSERT INTO game_service_routes VALUES(?,?,?,?)',route.code,route.release_id,route.revision,route.updated_at);
  const front=f.control.get('SELECT * FROM frontend_routes WHERE code=?','buffalo-win');
  f.control.run('DELETE FROM frontend_routes WHERE code=?','buffalo-win');
  job=f.checks.begin('test',f.request);assert.equal((await f.wait(job.id)).error?.code,'FRONTEND_VERSION_REQUIRED');
  f.control.run('INSERT INTO frontend_routes VALUES(?,?,?,?)',front.code,front.release_id,front.revision,front.updated_at);
  f.control.run("UPDATE game_service_releases SET status='retired' WHERE id=?",route.release_id);
  job=f.checks.begin('test',f.request);assert.equal((await f.wait(job.id)).error?.code,'GAME_SERVICE_NOT_READY');
  f.control.run("UPDATE game_service_releases SET status='ready' WHERE id=?",route.release_id);
  f.control.run("UPDATE frontend_releases SET status='staged' WHERE id=?",front.release_id);
  job=f.checks.begin('test',f.request);assert.equal((await f.wait(job.id)).error?.code,'FRONTEND_NOT_VERIFIED');
  f.control.run("UPDATE frontend_releases SET status='verified' WHERE id=?",front.release_id);
  assert.equal(f.control.gameAvailability(1).enabled,false);
  job=f.checks.begin('test',f.request);
  assert.equal((await f.wait(job.id)).status,'ready');
  assert.equal(f.control.gameAvailability(1).enabled,false,'Checking must not open a game without confirmation');
  assert.throws(()=>f.checks.enable('other-admin',{...f.request,check_id:job.id}),{code:'GAME_CHECK_EXPIRED'});
  assert.equal(f.checks.enable('test',{...f.request,check_id:job.id}).enabled,true);
  assert.throws(()=>f.checks.enable('test',{...f.request,check_id:job.id}),{code:'GAME_CHECK_REQUIRED'});
});

test('opening check refuses unavailable, changed and unauthenticated compute services',async t=>{
  const f=await preparedOpening(t),service=f.p.multi.remote.active('buffalo-win');
  f.control.run('UPDATE game_service_releases SET secret=? WHERE id=?','wrong-key',service.id);
  let job=f.checks.begin('test',f.request);assert.equal((await f.wait(job.id)).status,'failed');
  f.control.run('UPDATE game_service_releases SET secret=? WHERE id=?',service.secret,service.id);
  const changed={...service.descriptor,title:'different-description'};
  f.control.run('UPDATE game_service_releases SET descriptor_json=? WHERE id=?',JSON.stringify(changed),service.id);
  job=f.checks.begin('test',f.request);assert.equal((await f.wait(job.id)).error?.code,'GAME_RELEASE_CHANGED');
  f.control.run('UPDATE game_service_releases SET descriptor_json=? WHERE id=?',JSON.stringify(service.descriptor),service.id);
  await f.stop(f.compute);
  job=f.checks.begin('test',f.request);assert.equal((await f.wait(job.id)).error?.code,'GAME_UNAVAILABLE');
  assert.equal(f.control.gameAvailability(1).enabled,false);
  assert.equal(f.control.setGameAvailability('test',{...f.request,enabled:false}).enabled,false,'Closing does not require services');
});

test('opening check refuses changed private files, contracts, routes and availability revisions',async t=>{
  const f=await preparedOpening(t),path=join(f.installed,f.build.release,'bootstrap/resources/clients/buffalo-win/index.html'),original=readFileSync(path);
  writeFileSync(path,'changed');
  let job=f.checks.begin('test',f.request);assert.equal((await f.wait(job.id)).error?.code,'FRONTEND_FILE_CHANGED');
  writeFileSync(path,original);
  rmSync(path);
  job=f.checks.begin('test',f.request);assert.equal((await f.wait(job.id)).error?.code,'FRONTEND_BOOTSTRAP_UNAVAILABLE');
  writeFileSync(path,original);
  const release=f.versions.release(f.build.release),bad={...release.manifest,client_contract:'different-contract'};
  f.control.run('UPDATE frontend_releases SET manifest_json=? WHERE id=?',JSON.stringify(bad),release.id);
  job=f.checks.begin('test',f.request);assert.equal((await f.wait(job.id)).error?.code,'FRONTEND_CONTRACT_MISMATCH');
  f.control.run('UPDATE frontend_releases SET manifest_json=? WHERE id=?',JSON.stringify(release.manifest),release.id);
  job=f.checks.begin('test',f.request);assert.equal((await f.wait(job.id)).status,'ready');
  f.control.run('UPDATE frontend_routes SET revision=revision+1 WHERE code=?','buffalo-win');
  assert.throws(()=>f.checks.enable('test',{...f.request,check_id:job.id}),{code:'VERSION_CONFLICT'});
  job=f.checks.begin('test',f.request);assert.equal((await f.wait(job.id)).status,'ready');
  f.control.setGameAvailability('test',{...f.request,enabled:false});
  assert.throws(()=>f.checks.enable('test',{...f.request,check_id:job.id}),{code:'VERSION_CONFLICT'});
  assert.equal(f.control.gameAvailability(1).enabled,false);
});

test('opening check expires and closing during a check prevents confirmation',async t=>{
  const f=await preparedOpening(t);
  let job=f.checks.begin('test',f.request);assert.equal((await f.wait(job.id)).status,'ready');
  const future=Date.now()+61000,clock=t.mock.method(Date,'now',()=>future);
  assert.throws(()=>f.checks.enable('test',{...f.request,check_id:job.id}),{code:'GAME_CHECK_REQUIRED'});
  clock.mock.restore();
  job=f.checks.begin('test',f.request);
  f.control.setGameAvailability('test',{...f.request,enabled:false});f.checks.cancel(1);
  assert.equal((await f.wait(job.id)).status,'failed');
  assert.throws(()=>f.checks.enable('test',{...f.request,check_id:job.id}),{code:'GAME_CHECK_REQUIRED'});
  assert.equal(f.control.gameAvailability(1).enabled,false);
});

test('生产开放只请求一次 CDN 版本清单，拒绝缺失、错版或检查期间的版本切换',async t=>{
  const f=await preparedOpening(t),bundle=join(f.installed,f.build.release),manifest=readFrontendManifest(bundle);
  const origin='https://'+manifest.release+'.example.test';
  const marker={format:3,kind:manifest.kind,game:manifest.game,release:manifest.release,prefix:manifest.prefix,manifest_sha256:f.versions.release(manifest.release).manifest_sha256,files:manifest.files};
  f.control.run('UPDATE frontend_releases SET origin=? WHERE id=?',origin,manifest.release);
  rmSync(join(bundle,'objects'),{recursive:true});
  let mode='ok',calls=0;
  const actualFetch=globalThis.fetch;
  t.mock.method(globalThis,'fetch',async(input:any,init:any)=>{
    const url=String(input);
    if(!url.startsWith(origin+'/'))return actualFetch(input,init);
    assert.equal(url,origin+'/_gtt-manifest.json');
    assert.equal(init.redirect,'manual');assert.equal(init.credentials,'omit');assert.equal(init.headers,undefined);
    calls++;
    if(mode==='missing')return new Response('missing',{status:404});
    if(mode==='changed')return new Response(JSON.stringify({...marker,game:'other-game'},null,2)+'\n');
    if(mode==='timeout')throw new DOMException('test timeout','TimeoutError');
    if(mode==='switch'){mode='ok';f.control.run('UPDATE game_service_routes SET revision=revision+1 WHERE code=?','buffalo-win');}
    return new Response(JSON.stringify(marker,null,2)+'\n');
  });
  const checks=new GameAvailabilityChecks(f.p,f.p.multi.remote,f.versions,{...f.config,environment:'production'});t.after(()=>checks.close());
  const wait=async(id:string)=>{for(let i=0;i<500;i++){const result=checks.status('test',id);if(result.status!=='checking')return result;await new Promise(ok=>setTimeout(ok,20));}throw Error('timeout');};
  for(const [scenario,expected]of [['missing','FRONTEND_CDN_UNAVAILABLE'],['changed','FRONTEND_CDN_CHANGED'],['timeout','GAME_DEPLOYMENT_CHECK_FAILED'],['switch','VERSION_CONFLICT']]){
    mode=scenario;const job=checks.begin('test',f.request);assert.equal((await wait(job.id)).error?.code,expected);assert.equal(f.control.gameAvailability(1).enabled,false);
  }
  mode='ok';calls=0;const job=checks.begin('test',f.request);assert.equal((await wait(job.id)).status,'ready');
  assert.equal(calls,1);
  assert.equal(checks.enable('test',{...f.request,check_id:job.id}).enabled,true);
});

test("a frontend switch changes new sessions while old pages and assets stay pinned across gateway restart", async (t) => {
  const f = await fixture(t),
    old = f.build();
  f.versions.register("test", { bundle: old.bundle });
  await f.versions.probe("test", old.release);
  f.versions.activate("test", { id: old.release, revision: 0 });
  const a = await f.launch(),
    aURL = new URL(a.launch_url),
    token = aURL.searchParams.get("ops")!;
  assert.ok(aURL.hostname.includes(old.release));
  const page = await f.http(aURL.host, aURL.pathname + aURL.search);
  assert.equal(page.status, 200, page.body);
  assert.match(page.body, /local-auth-bootstrap/);
  const asset = await f.http(aURL.host, "/assets/marker.json");
  assert.equal(asset.status, 200);
  assert.match(asset.body, /old/);
  assert.match(asset.headers["cache-control"], /immutable/);
  writeFileSync(join(f.source, "assets/marker.json"), '{"version":"new"}');
  const next = f.build();
  f.versions.register("test", { bundle: next.bundle });
  await f.versions.probe("test", next.release);
  f.versions.activate("test", { id: next.release, revision: 1 });
  assert.throws(
    () => f.versions.activate("test", { id: old.release, revision: 1 }),
    { code: "VERSION_CONFLICT" },
  );
  const b = await f.launch(),
    bURL = new URL(b.launch_url);
  assert.ok(bURL.hostname.includes(next.release));
  assert.match((await f.http(aURL.host, "/assets/marker.json")).body, /old/);
  assert.match((await f.http(bURL.host, "/assets/marker.json")).body, /new/);
  assert.equal((await f.http(bURL.host, "/?ops=" + token)).status, 403);
  assert.notEqual(
    (await f.http(aURL.host, "/fixtures/secret.json?ops=" + token)).status,
    200,
  );
  await f.restart();
  assert.equal(
    (await f.http(aURL.host, aURL.pathname + aURL.search)).status,
    200,
  );
  assert.match((await f.http(aURL.host, "/assets/marker.json")).body, /old/);
  f.versions.activate("test", { id: old.release, revision: 2 });
  assert.ok(
    new URL((await f.launch()).launch_url).hostname.includes(old.release),
  );
  assert.throws(() => f.versions.retire("test", old.release), {
    code: "FRONTEND_VERSION_ACTIVE",
  });
});

test('CDN 模板新版本无需本机预装，绑定会话后校验原始 HTML 并逐玩家注入',async t=>{
  const f=await fixture(t);
  f.build('v1.0',true);
  const built=f.build('v1.1',true,true),dir=join(f.installed,built.release),m=readFrontendManifest(dir);
  const marker=frontendMarker(m,sha(readFileSync(join(dir,'manifest.json')))),html=readFileSync(join(dir,'objects/index.html'),'utf8');
  assert.ok(!m.bootstrap.some(v=>v.path.endsWith('/index.html')));rmSync(dir,{recursive:true});
  const remote='https://assets.example.test',url=remote+'/'+m.prefix;
  const urls:string[]=[];let tamper=true;
  const actual=globalThis.fetch;
  t.mock.method(globalThis,'fetch',async(input:any,init:any)=>{
    if(!String(input).startsWith(remote+'/'))return actual(input,init);
    assert.equal(init.credentials,'omit');assert.equal(init.headers,undefined);urls.push(String(input));
    if(input===url+'/_gtt-manifest.json')return new Response(JSON.stringify(marker,null,2)+'\n');
    assert.equal(input,url+'/index.html');return new Response(tamper?'corrupt':html);
  });
  f.versions.config={...f.config,environment:'production',frontend_cdn_origin:remote,frontend_origin_template:'https://{release}-g{game_id}.play.example.test'};
  const checks=new GameAvailabilityChecks(f.p,f.p.multi.remote,f.versions,f.versions.config);t.after(()=>checks.close());
  const route=f.control.get('SELECT * FROM game_service_routes WHERE code=?','buffalo-win');
  const job=checks.begin('test',{game_id:1,enabled:true,version:f.control.gameAvailability(1).version},{service_id:route.release_id,component_version:'v1.1',service_revision:route.revision,frontend_revision:0});
  let state=checks.status('test',job.id);while(state.status==='checking'){await new Promise(ok=>setTimeout(ok,20));state=checks.status('test',job.id);}
  assert.equal(state.status,'applied',JSON.stringify(state));
  const a=new URL((await f.launch()).launch_url),b=new URL((await f.launch()).launch_url);
  assert.notEqual((await f.http(a.host,'/index.html')).status,200);assert.ok(!urls.includes(url+'/index.html'));
  assert.notEqual((await f.http(a.host,'/'+a.search)).status,200);tamper=false;
  const page=await f.http(a.host,'/'+a.search);assert.equal(page.status,200,page.body.slice(0,500));assert.ok(page.body.includes(a.searchParams.get('ops')!));assert.match(page.body,/local-auth-bootstrap/);
  const second=await f.http(b.host,'/'+b.search);assert.ok(second.body.includes(b.searchParams.get('ops')!));assert.ok(!second.body.includes(a.searchParams.get('ops')!));
  assert.equal(urls.filter(v=>v===url+'/index.html').length,2);
});

test("frontend management is platform-only and registration reads generated versions instead of accepting handwritten numbers", async (t) => {
  const f = await fixture(t),
    build = f.build();
  const admin = f.control.createUser("test", "frontend-admin", "admin");
  const app = adminServer(
    f.p,
    f.config,
    resolve("frontend/admin"),
    resolve("config"),
  );
  f.servers.add(app);
  const origin = "http://127.0.0.1:" + (await listen(app));
  const login = async (username: string, password: string, tenant = false) => {
    const response = await fetch(
      origin + `/api/${tenant ? "merchant" : "admin"}/login`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ username, password }),
      },
    );
    const result: any = await response.json();
    assert.equal(response.status, 200);
    return {
      cookie: response.headers.get("set-cookie")!.split(";")[0],
      csrf: result.data.csrf_token,
    };
  };
  const a = await login("frontend-admin", admin.temporary_password),
    m = await login(
      f.created.login.name,
      f.created.login.temporary_password,
      true,
    );
  const post = (path: string, q: any, s: any) =>
    fetch(origin + path, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        cookie: s.cookie,
        "x-gtt-csrf": s.csrf,
      },
      body: JSON.stringify(q),
    });
  const response = await post(
    "/api/admin/frontends/register",
    { bundle: build.bundle },
    a,
  );
  assert.equal(response.status, 200, await response.clone().text());
  assert.equal(((await response.json()) as any).data.id, build.release);
  for(const action of ['create','list','disable'])assert.equal((await post('/api/merchant/trials/'+action,{game_id:1},m)).status,403);
  assert.equal((await post('/api/admin/trials/create',{game_id:1},{...a,csrf:'bad'})).status,403);
  for (const action of [
    "list",
    "candidates",
    "register",
    "probe",
    "activate",
    "retire",
  ])
    assert.equal(
      (await post("/api/merchant/frontends/" + action, {}, m)).status,
      403,
    );
  assert.equal(
    (
      await post(
        "/api/admin/frontends/activate",
        { id: build.release, revision: 0 },
        { ...a, csrf: "wrong" },
      )
    ).status,
    403,
  );
  assert.throws(() => f.versions.register("test", { bundle: "../outside" }), {
    code: "FRONTEND_BUNDLE_INVALID",
  });
  const overview:any=await (await post('/api/admin/overview',{},a)).json();
  assert.equal(overview.data.games,GAME_CODES.length);
  assert.equal(overview.data.registered_games,1);
  assert.equal(overview.data.active_games,1);
  for(const action of ['games/availability','games/availability-check'])assert.equal((await post('/api/merchant/'+action,{},m)).status,403);
  const closed=await post('/api/admin/games/availability',{game_id:1,enabled:false,version:f.control.gameAvailability(1).version},a);
  assert.equal(closed.status,200);
  const q={game_id:1,enabled:true,version:f.control.gameAvailability(1).version};
  assert.equal((await post('/api/admin/games/availability',{...q,check_id:'fake'},a)).status,409);
  assert.equal((await post('/api/admin/games/availability',q,{...a,csrf:'bad'})).status,403);
  await f.versions.probe('test',build.release);
  f.versions.activate('test',{id:build.release,revision:0});
  let state:any=(await (await post('/api/admin/games/availability',q,a)).json() as any).data.check;
  for(let i=0;state.status==='checking'&&i<500;i++){
    await new Promise(ok=>setTimeout(ok,20));
    state=(await (await post('/api/admin/games/availability-check',{check_id:state.id},a)).json() as any).data.check;
  }
  assert.equal(state.status,'ready',JSON.stringify(state));
  assert.equal(f.control.gameAvailability(1).enabled,false);
  const opened=await post('/api/admin/games/availability',{...q,check_id:state.id},a);
  assert.equal(opened.status,200,await opened.clone().text());
  assert.equal(f.control.gameAvailability(1).enabled,true);
});

test("frontend publication uploads public files only, checks private bucket protections, and never overwrites differing objects", async (t) => {
  const f = await fixture(t),
    build = f.build(),
    { publishFrontend } = await import(
      pathToFileURL(resolve("tools/publish-frontend.mjs")).href
    );
  const objects = new Map<string, any>();
  let puts = 0,
    blocked = false;
  const run = (operation: string, args: string[]) => {
    const value = (key: string) => args[args.indexOf(key) + 1];
    if (operation === "get-public-access-block")
      return {
        PublicAccessBlockConfiguration: {
          BlockPublicAcls: !blocked,
          IgnorePublicAcls: true,
          BlockPublicPolicy: true,
          RestrictPublicBuckets: true,
        },
      };
    if (operation === "get-bucket-ownership-controls")
      return {
        OwnershipControls: {
          Rules: [{ ObjectOwnership: "BucketOwnerEnforced" }],
        },
      };
    if (operation === "get-bucket-versioning") return { Status: "Enabled" };
    if (operation === "get-bucket-policy")return {Policy:JSON.stringify({Statement:[{Effect:'Allow',Resource:'arn:aws:s3:::test-private-frontend/releases/*'}]})};
    if (operation === "get-bucket-encryption")
      return {
        ServerSideEncryptionConfiguration: {
          Rules: [
            { ApplyServerSideEncryptionByDefault: { SSEAlgorithm: "AES256" } },
          ],
        },
      };
    if (operation === "head-object") {
      const object = objects.get(value("--key"));
      if (!object) throw Error("NotFound");
      return object;
    }
    if (operation === "put-object") {
      assert.equal(value("--if-none-match"), "*");
      assert.equal(value("--expected-bucket-owner"), "123456789012");
      const bytes = readFileSync(value("--body"));
      objects.set(value("--key"), {
        ContentLength: bytes.length,
        ChecksumSHA256: value("--checksum-sha256"),
        ContentType: value("--content-type"),
        CacheControl: value("--cache-control"),
        Metadata: JSON.parse(value("--metadata")),
        bytes,
      });
      puts++;
      return {};
    }
    throw Error("Unexpected cloud operation " + operation);
  };
  const options = {
    bundle: join(f.installed, build.release),
    bucket: "test-private-frontend",
    owner: "123456789012",
    run,
  };
  blocked = true;
  await assert.rejects(() => publishFrontend(options), /protections/);
  assert.equal(puts, 0);
  blocked = false;
  const receipt = await publishFrontend(options);
  assert.equal(receipt.status, "passed");
  assert.equal(receipt.bootstrap_uploaded, false);
  assert.ok(
    [...objects.keys()].every(
      (key) =>
        key.startsWith(`releases/buffalo-win/${build.release}/`) &&
        !key.split("/").includes("bootstrap") &&
        !key.split("/").includes("fixtures"),
    ),
  );
  assert.ok(
    ![...objects.values()].some(
      (o) =>
        o.bytes.includes("PRIVATE_SENTINEL") ||
        o.bytes.includes("PRIVATE_PROFILE"),
    ),
  );
  const count = puts;
  await publishFrontend(options);
  assert.equal(puts, count);
  objects.values().next().value.ChecksumSHA256 = "tampered";
  await assert.rejects(() => publishFrontend(options), /refusing overwrite/);
  assert.equal(puts, count);
  const remote=f.build('v2.1',true),result=await publishFrontend({...options,bundle:join(f.installed,remote.release)});
  assert.equal(result.private_prefix,'private/frontend/buffalo-win/v2.1');
  const cache=f.versions;
  cache.root=join(f.dir,'cold-cache');
  let reads=0;
  cache.downloadObject=async()=>{reads++;throw Error('默认模式不应请求 S3');};
  await assert.rejects(cache.cacheVersion('buffalo-win','v2.1'),{code:'FRONTEND_LOCAL_REQUIRED'});
  assert.equal(reads,0);
  cache.config.frontend_private_source='s3';
  cache.downloadObject=async(key:string,path:string)=>writeFileSync(path,objects.get(key).bytes);
  const privateKey=result.private_prefix+'/bootstrap/resources/clients/buffalo-win/index.html',saved=objects.get(privateKey).bytes;
  objects.get(privateKey).bytes=Buffer.from('changed');
  await assert.rejects(cache.cacheVersion('buffalo-win','v2.1'),{code:'FRONTEND_FILE_CHANGED'});
  objects.get(privateKey).bytes=saved;
  assert.equal(await cache.cacheVersion('buffalo-win','v2.1'),remote.release);
  assert.equal(existsSync(join(cache.root,remote.release,'objects')),false);
  delete cache.config.frontend_private_source;
  cache.bundledRoot=cache.root;cache.root=join(f.dir,'empty-install');
  cache.downloadObject=async()=>{reads++;throw Error('随包版本不应请求 S3');};
  assert.equal(await cache.cacheVersion('buffalo-win','v2.1'),remote.release);
  assert.equal(cache.candidates().some((v:any)=>v.release===remote.release),true);
  assert.equal(reads,0);
  cache.config.environment='production';cache.config.frontend_origin_template='https://{release}-g{game_id}.play.example.com';
  assert.equal(cache.register('test',{bundle:remote.release}).id,remote.release);
});

test("version CDN routing keeps assets in immutable S3 prefixes and preserves authentication on dynamic requests", async () => {
  const { renderFrontendEdge } = await import(
    pathToFileURL(resolve("tools/render-frontend-edge.mjs")).href
  );
  const code = renderFrontendEdge({
    host_suffix: ".play.example.com",
    assets_origin_id: "version-assets-root",
    assets_domain: "private-assets.s3.us-east-1.amazonaws.com",
    dynamic_origin_id: "application",
    dynamic_tls_name: "origin.example.com",
  });
  const calls: any[] = [],
    box: any = {
      cf: {
        selectRequestOriginById: (...args: any[]) => calls.push(args),
        updateRequestOrigin: (...args: any[]) => calls.push(args),
      },
    };
  runInNewContext(
    code.replace(/^import cf[^\n]*\n/, "") + "\nthis.handler=handler;",
    box,
  );
  const version = "fe-20261113000000000-12345678-abcdef",
    host = version + "-g1.play.example.com";
  const request = (uri: string, method = "GET") => ({
    uri,
    method,
    headers: {
      host: { value: host },
      authorization: { value: "Bearer private-session" },
    },
    cookies: { session: { value: "private" } },
    querystring: { ops: { value: "private-session" } },
  });
  const asset = box.handler({ request: request("/assets/picture.png") });
  assert.equal(
    asset.uri,
    `/releases/buffalo-win/${version}/assets/picture.png`,
  );
  assert.equal(asset.headers.authorization, undefined);
  assert.equal(Object.keys(asset.querystring).length, 0);
  assert.equal(Object.keys(asset.cookies).length, 0);
  assert.equal(calls[0][0], "version-assets-root");
  const remote=request('/assets/picture.png');remote.headers.host.value='fe-v2-1-g1-g1.play.example.com';
  assert.equal(box.handler({request:remote}).uri,'/releases/buffalo-win/v2.1/assets/picture.png');
  calls.length = 0;
  const dynamic = box.handler({
    request: request("/game-api/buffalo-win/v2/Spin", "POST"),
  });
  assert.equal(dynamic.headers.authorization.value, "Bearer private-session");
  assert.equal(dynamic.querystring.ops.value, "private-session");
  assert.equal(calls[0][0], "application");
  calls.length = 0;
  box.handler({ request: request("/fixtures/auth-metadata.json") });
  assert.equal(calls[0][0], "application");
  assert.equal(
    box.handler({ request: request("/%2e%2e/secret.json") }).statusCode,
    404,
  );
});
