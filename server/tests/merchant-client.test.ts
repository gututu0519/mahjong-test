import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { merchantClientHTML, merchantClientURL, merchantPGAuth, type MerchantClient } from "../gateway/merchant-client.js";

const client: MerchantClient = {code:"buffalo-win",token:"signed-session",operator:"GTT000001",player_id:"platform-player",currency:"USD"};

test("Super Ace captured modules initialize after their embedded deadline without changing the browser clock", () => {
  const adapter=readFileSync('../clients/super-ace/local-adapter.js','utf8');
  const bootstrap=adapter.slice(0,adapter.indexOf('  const params'))+'})();';
  const future=Date.UTC(2027,0,1);
  let registrations=0;
  const box:any={location:{hostname:'g15.localhost'},
    Date:class extends Date {constructor(){super(future);} static now(){return future;}},
    System:{register(){registrations++;}},
    setInterval(){throw new Error('Captured destructive date-lock branch executed');},setTimeout(){}};
  runInNewContext('window=globalThis;'+bootstrap,box,{timeout:1000});
  for(const path of ['src/chunks/bundle.0c125.js','assets/other/index.22b2c.js']) {
    runInNewContext(readFileSync('../clients/super-ace/astarte2/3.6/web-mobile/'+path,'utf8'),box,{timeout:3000});
  }
  assert.ok(registrations>=2);
  assert.equal(runInNewContext('Date.now()',box),future);
  assert.equal(runInNewContext('typeof JSON',box),'object');
  assert.equal(runInNewContext('Object.getOwnPropertyDescriptor(Function.prototype,"109620")',box),undefined);
});

test("PP merchant bootstrap uses its public game origin for assets and API requests", () => {
  for(const code of ["big-bass-bonanza","sweet-bonanza-pop","gates-of-olympus"]){
    const html=merchantClientHTML('<html><head><script>Html5GameManager.init({gameConfig:JSON.stringify({"datapath":"http://127.0.0.1:8110/hub-demo/assets/","gameService": "http://127.0.0.1:8110/hub-demo/ge/v3/gameService"})})</script></head></html>', '/?ops=signed-session','https://game.example',{...client,code});
    assert.ok(html.includes('"datapath":"https://game.example/hub-demo/assets/"'),code);
    assert.ok(html.includes('"gameService": "https://game.example/hub-demo/ge/v3/gameService"'),code);
    assert.ok(!html.includes('http://127.0.0.1:8110'),code);
  }
});

test("PG bootstrap uses the authenticated merchant mode and preserves standalone game launch behavior", () => {
  for (const [code,file] of [["buffalo-win","local-auth-bootstrap.js"],["captains-bounty","local-bootstrap.js"],["fortune-rabbit","local-bootstrap.js"],["wild-bandito","local-bootstrap.js"],["mahjong-ways2","local-auth-bootstrap.js"]]) {
    for (const merchant of [false,true]) {
      const location = {href:"http://g1.localhost:8110/?mock=1&btt=2&ops=original",origin:"http://g1.localhost:8110"};
      const box: any = {URL,URLSearchParams,Headers,Request,location,history:{state:null,replaceState(_state:any,_title:any,href:any){location.href=String(href);}},
        XMLHttpRequest:class{open(){}send(){}setRequestHeader(){}},fetch(){},setInterval(){return 1;},console:{info(){}},
        ...(merchant ? {__GTT_MERCHANT__:{...client,code}} : {})};
      box.window=box;box.parent=box;
      runInNewContext(readFileSync(`../clients/${code}/${file}`,"utf8"),box,{timeout:1000});
      const url = new URL(location.href);
      assert.equal(url.searchParams.get("btt"),merchant || code === "mahjong-ways2" ? "1" : "2",code);
      assert.equal(url.searchParams.get("ot"),merchant ? client.operator : "local-demo",code);
      assert.equal(url.searchParams.get("ops"),merchant ? client.token : "original",code);
      assert.equal(url.searchParams.has("mock"),!merchant,code);
    }
  }
});

test("merchant iframe transport binds fetch, XHR and WebSocket to its session without leaking credentials", async () => {
  const html=merchantClientHTML('<html><head></head><body></body></html>', '/?mock=1&btt=2&ops=old',"http://g1.localhost:8110",client);
  const source=html.match(/<script>([\s\S]*?)<\/script>/)![1],calls:any[]=[];
  const location={href:"http://g1.localhost:8110/?mock=1",origin:"http://g1.localhost:8110",host:"g1.localhost:8110"};
  class XHR {headers:any={};open(..._args:any[]){}send(){}setRequestHeader(k:string,v:string){this.headers[k]=v;}}
  class WS {url:string;constructor(url:string|URL){this.url=String(url);}}
  const box:any={URL,URLSearchParams,Headers,Request,Object,location,XMLHttpRequest:XHR,WebSocket:WS,
    history:{state:null,replaceState(_state:any,_title:any,href:any){location.href=new URL(href,location.href).href;}},
    fetch(input:any,init:any){calls.push({input,init});return Promise.resolve({ok:true});}};
  box.window=box;runInNewContext(source,box,{timeout:1000});
  await box.fetch('/api/wallet');
  assert.equal(calls[0].init.headers.get('Authorization'),'Bearer '+client.token);
  await box.fetch('https://external.example/asset.js');
  assert.equal(calls[1].init,undefined);
  const xhr=new box.XMLHttpRequest();xhr.open('POST','/game-api/spin');xhr.send();
  assert.equal(xhr.headers.Authorization,'Bearer '+client.token);
  const foreign=new box.XMLHttpRequest();foreign.open('GET','https://external.example/asset');foreign.send();
  assert.equal(foreign.headers.Authorization,undefined);
  assert.equal(new URL(new box.WebSocket('ws://g1.localhost:8110/lifeservice/ws2').url).searchParams.get('ops'),client.token);
  assert.equal(new URL(new box.WebSocket('wss://external.example/ws').url).searchParams.has('ops'),false);
  assert.equal(new URL(location.href).searchParams.get('btt'),'1');
  assert.equal(new URL(location.href).searchParams.has('mock'),false);
});

test("merchant PG clients retain the visible WebView frame fallback without a demo flag", () => {
  for (const code of ["buffalo-win","captains-bounty","fortune-rabbit","wild-bandito","mahjong-ways2"]) {
    let nativeFrame: ((timestamp:number)=>void) | undefined, fallback: (()=>void) | undefined;
    const rendered:number[]=[], canceled:number[]=[];
    const box:any={URL,Map,location:{href:"http://g1.localhost:8110/?btt=1"},__GTT_MERCHANT__:{...client,code},
      document:{hidden:false,documentElement:{dataset:{}}},performance:{now:()=>123},
      requestAnimationFrame(callback:any){nativeFrame=callback;return 7;},cancelAnimationFrame(id:number){canceled.push(id);},
      setTimeout(callback:any){fallback=callback;return 8;},clearTimeout(){}};
    box.window=box;
    runInNewContext(readFileSync(`../clients/${code}/local-frame-clock.js`,"utf8"),box,{timeout:1000});
    box.requestAnimationFrame((timestamp:number)=>rendered.push(timestamp));
    assert.ok(fallback,code);fallback();nativeFrame!(124);
    assert.deepEqual(rendered,[123],code);assert.deepEqual(canceled,[7],code);
  }
});

test("merchant PG authentication uses the bound account and retains Buffalo feature buy", () => {
  const auth=merchantPGAuth({uiogc:{bf:0},cc:"PGC"},client,{player_id:"bound-account",balance_minor:12345});
  assert.equal(auth.dt.tk,client.token);assert.equal(auth.dt.pid,"bound-account");
  assert.equal(auth.dt.cc,"USD");assert.equal(auth.dt.bl,123.45);assert.equal(auth.dt.nkn,client.player_id);
  assert.equal(auth.dt.uiogc.bf,1);
  assert.deepEqual(auth.dt.oj,{jid:1});
  const uri = new URL(merchantClientURL('/fullhouse/?demo=true&loginFrom=trial&ssoKey=local','http://g15.localhost:8110',{...client,code:'super-ace'}),'http://g15.localhost:8110');
  assert.equal(uri.searchParams.get('demo'),'false');assert.equal(uri.searchParams.has('loginFrom'),false);assert.equal(uri.searchParams.get('ssoKey'),client.token);
  const vaults=new URL(merchantClientURL('/sss-tbv/?currency=SC&demo=true','http://g12.localhost:8110',{...client,code:'3-billion-vaults'}),'http://g12.localhost:8110');
  assert.equal(vaults.searchParams.get('currency'),'USD');
});
