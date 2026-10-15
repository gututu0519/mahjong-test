"""Capture decoded messages from the public trial client for protocol validation."""
import asyncio,json,pathlib,urllib.parse
from playwright.async_api import async_playwright
ROOT=pathlib.Path(__file__).resolve().parents[2]
OUT=ROOT/'clients/super-ace/diagnostics'
async def main():
 cap=ROOT/'response-capture/captures/d15806bcacc3496aade5a3f080feb2c6'
 m=json.loads((cap/'manifest.json').read_text(encoding='utf8'))
 url=next(r['url'] for r in m['rows'] if r['id']==1440)
 assert 'demo=true' in url and 'loginFrom=trial' in url
 async with async_playwright() as p:
  browser=await p.chromium.launch(channel='msedge',headless=True)
  page=await browser.new_page(viewport={'width':1100,'height':800});errors=[]
  page.on('requestfailed',lambda r:errors.append(urllib.parse.urlsplit(r.url).path+': '+str(r.failure)))
  page.on('pageerror',lambda e:errors.append(e.stack))
  await page.add_init_script('''window.__decoded=[];const watch=setInterval(()=>{if(!window.System?.register||System.__hooked)return;System.__hooked=true;const orig=System.register;System.register=function(...args){const factory=args.pop();args.push(function(exp,context){return factory.call(this,function(k,v){const o=typeof k==='object'?k:{[k]:v};if(o.x&&typeof o.x.OnRecvAck==='function'){const x=o.x,recv=x.OnRecvAck;x.OnRecvAck=function(...a){window.__decoded.push(JSON.parse(JSON.stringify(a)));return recv.apply(this,a);};window.__gameApi=x;}return exp(k,v);},context);});return orig.apply(this,args);};clearInterval(watch);},1);''')
  assets={urllib.parse.urlsplit(r['url']).path:r for r in m['rows'] if r.get('body') and urllib.parse.urlsplit(r['url']).hostname=='casino-wbgame.jiligames.com'}
  async def route(rt):
   u=urllib.parse.urlsplit(rt.request.url)
   if u.hostname=='casino-wbgame.jiligames.com':
    r=assets.get(u.path)
    if r:await rt.fulfill(status=200,content_type=r.get('mime') or ('application/javascript' if u.path.endswith('.js') else 'application/octet-stream'),body=(cap/r['body']).read_bytes());return
   await rt.continue_()
  await page.route('**/*',route)
  url=next(r['url'] for r in m['rows'] if r['id']==704)
  await page.goto(url,wait_until='domcontentloaded',timeout=45000)
  await page.wait_for_timeout(25000)
  state0=await page.evaluate('''()=>{const x=window.System?.get('chunks:///index-2059667d.js')?.x;if(x){window.__gameApi=x;const f=x.OnRecvAck;x.OnRecvAck=function(...a){window.__decoded.push(JSON.parse(JSON.stringify(a)));return f.apply(this,a);};return {info:x.IsGetInfo};}return null;}''')
  await page.mouse.click(550,640);await page.wait_for_timeout(4000)
  await page.mouse.click(550,470);await page.wait_for_timeout(2500)
  await page.mouse.click(550,710);await page.wait_for_timeout(8000)
  await page.screenshot(path=str(OUT/'live.png'))
  scene=await page.evaluate('''()=>{const m=System.get('chunks:///index-2059667d.js');return {state:m.j.m_currState,commonKeys:Object.keys(m.x.m_iGameCommon||{}),assets:(()=>{const a=[];cc.assetManager.assets.forEach((v,k)=>{if(v?.json)a.push({name:v.name,uuid:k,json:v.json});});return a;})(),bottom:Object.getOwnPropertyNames(Object.getPrototypeOf(m.h))};}''')
  (OUT/'scene.json').write_text(json.dumps(scene,ensure_ascii=False,indent=2),encoding='utf8')
  state=await page.evaluate('''()=>({messages:window.__decoded,api:window.__gameApi?{info:__gameApi.IsGetInfo,state:__gameApi.m_spinAck}:null,text:document.body.innerText})''')
  (OUT/'live.json').write_text(json.dumps({'state':state,'errors':errors},ensure_ascii=False,indent=2),encoding='utf8')
  print(json.dumps({'count':len(state['messages']),'errors':errors[:4],'info':state.get('api')}))
  await browser.close()
asyncio.run(main())
