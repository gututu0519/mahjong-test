"""Offline diagnostic: fulfill every browser request exclusively from the local capture."""
import json,pathlib,asyncio,urllib.parse
from playwright.async_api import async_playwright
ROOT=pathlib.Path(__file__).resolve().parents[2]
CAP=ROOT/'response-capture/captures/d15806bcacc3496aade5a3f080feb2c6'
OUT=ROOT/'clients/super-ace/diagnostics'
async def main():
 m=json.loads((CAP/'manifest.json').read_text(encoding='utf8')); rows=m['rows']; by={}
 for r in rows:
  if r.get('body'):by.setdefault(urllib.parse.urlsplit(r['url'])._replace(query='',fragment='').geturl(),[]).append(r)
 counts={};errors=[];missing=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(channel='msedge',headless=True,args=['--enable-webgl','--ignore-gpu-blocklist'])
  page=await browser.new_page(viewport={'width':1100,'height':800})
  await page.add_init_script('''window.__wasmBytes=[];const wm=WebAssembly.Module;WebAssembly.Module=new Proxy(wm,{construct(t,a){window.__wasmBytes.push(Array.from(new Uint8Array(a[0].buffer||a[0])));return Reflect.construct(t,a);}});const wc=WebAssembly.compile;WebAssembly.compile=function(b){window.__wasmBytes.push(Array.from(new Uint8Array(b.buffer||b)));return wc.call(this,b);};const wi=WebAssembly.instantiate;WebAssembly.instantiate=function(bytes,imports){if(bytes instanceof ArrayBuffer||ArrayBuffer.isView(bytes))window.__wasmBytes.push(Array.from(new Uint8Array(bytes.buffer||bytes)));return wi.call(this,bytes,imports);};''')
  page.on('pageerror',lambda e:errors.append(str(e)))
  async def route(rt):
   req=rt.request;u=urllib.parse.urlsplit(req.url)._replace(query='',fragment='').geturl(); matches=by.get(u,[])
   if not matches:
    missing.append(u);await rt.fulfill(status=404,body='');return
   i=counts.get(u,0);counts[u]=i+1;r=matches[min(i,len(matches)-1)]
   if req.method=='POST':
    body=req.post_data_buffer or b''
    candidates=[x for x in matches if x.get('request_body') and (CAP/x['request_body']).read_bytes()[:2]==body[:2]]
    if candidates:r=candidates[-1]
   headers={'content-type':r.get('mime') or ('application/javascript' if urllib.parse.urlsplit(u).path.endswith('.js') else 'application/octet-stream'),'access-control-allow-origin':'*'}
   await rt.fulfill(status=r.get('status') or 200,headers=headers,body=(CAP/r['body']).read_bytes())
  await page.route('**/*',route)
  await page.route_web_socket('**/*',lambda ws:ws.close())
  url=next(r['url'] for r in rows if r['id']==1440)
  await page.goto(url,wait_until='domcontentloaded');await page.wait_for_timeout(20000)
  details=await page.evaluate('''() => Object.fromEntries([...System.entries()].filter(([k])=>k.startsWith('chunks:///')&&!/main.js|game.js|extra.js|other.js/.test(k)).map(([k,v])=>[k,Object.fromEntries(Object.entries(v).map(([n,x])=>[n,{name:x?.name,keys:x?Object.getOwnPropertyNames(x):[],proto:typeof x==='function'?Object.getOwnPropertyNames(x.prototype||{}):[],source:typeof x==='function'?x.toString().slice(0,1200):null}]))]))''')
  (OUT/'exports.json').write_text(json.dumps(details,ensure_ascii=False,indent=2),encoding='utf8')
  cdp=await page.context.new_cdp_session(page)
  fn=await cdp.send('Runtime.evaluate',{'expression':"System.get('chunks:///index-2059667d.js').x.SendCommand"})
  props=await cdp.send('Runtime.getProperties',{'objectId':fn['result']['objectId']})
  scope=next(x['value']['objectId'] for x in props['internalProperties'] if x['name']=='[[Scopes]]')
  scopes=await cdp.send('Runtime.getProperties',{'objectId':scope,'ownProperties':True})
  dump={}
  for sc in scopes['result']:
   oid=sc.get('value',{}).get('objectId')
   if not oid:continue
   vals=await cdp.send('Runtime.getProperties',{'objectId':oid,'ownProperties':True})
   dump[sc['name']]=vals['result']
   for prop in vals['result']:
    if prop['name'] in ['C1B','H5s','G6G','F542'] and prop.get('value',{}).get('objectId'):
     await cdp.send('Runtime.callFunctionOn',{'objectId':prop['value']['objectId'],'functionDeclaration':"function(n){window['__'+n]=this;}",'arguments':[{'value':prop['name']}]})
  (OUT/'scopes.json').write_text(json.dumps(dump,ensure_ascii=False,indent=2),encoding='utf8')
  for label,expression in [('send', 'window.__G6G'),('http','window.__H5s'),('generator','window.__send_c93'),('schema','window.__C1B.serverProto.SpinResponse.encode')]:
   fn2=await cdp.send('Runtime.evaluate',{'expression':expression})
   pp=await cdp.send('Runtime.getProperties',{'objectId':fn2['result']['objectId']})
   so=next(x['value']['objectId'] for x in pp['internalProperties'] if x['name']=='[[Scopes]]')
   ss=await cdp.send('Runtime.getProperties',{'objectId':so,'ownProperties':True})
   dd={}
   for sc in ss['result']:
    oid=sc.get('value',{}).get('objectId')
    if not oid:continue
    vv=await cdp.send('Runtime.getProperties',{'objectId':oid,'ownProperties':True});dd[sc['name']]=vv['result']
    for prop in vv['result']:
     if prop['name'] in ['c93','y4_','p5E','K$q','g09'] and prop.get('value',{}).get('objectId'):
      await cdp.send('Runtime.callFunctionOn',{'objectId':prop['value']['objectId'],'functionDeclaration':"function(n){window['__'+n]=this;}",'arguments':[{'value':label+'_'+prop['name']}]})
   (OUT/(label+'-scopes.json')).write_text(json.dumps(dd,ensure_ascii=False,indent=2),encoding='utf8')
  secrets=await page.evaluate('''() => ({proto:window.__C1B?Object.keys(__C1B):[],send:window.__G6G?.toString(),http:window.__H5s?.toString(),generator:window.__send_c93?.toString(),httpimpl:window.__http_y4_?.toString(),wasmExports:window.__http_K$q?Object.keys(window.__http_K$q):[],request:window.__generator_p5E?.toString(),serverProto:Object.fromEntries(Object.entries(__C1B.serverProto).map(([k,v])=>[k,{keys:Object.keys(v),decode:v?.decode?.toString(),encode:v?.encode?.toString()}]))})''')
  (OUT/'protocol.json').write_text(json.dumps(secrets,ensure_ascii=False,indent=2),encoding='utf8')
  (OUT/'wasm-memory.bin').write_bytes(bytes(await page.evaluate('Array.from(new Uint8Array(window.__http_K$q.memory.buffer))')))
  strings=await page.evaluate('''() => {const out={};for(let i=0;i<16000;i++){try{out[i]=__F542.k4T_(i);}catch{}}return out;}''')
  (OUT/'strings.json').write_text(json.dumps(strings,ensure_ascii=False),encoding='utf8')
  for i,b in enumerate(await page.evaluate('window.__wasmBytes')):(OUT/('network'+str(i)+'.wasm')).write_bytes(bytes(b))
  methods=await page.evaluate('''() => {const m={...System.get('chunks:///index-2059667d.js')};const out={};m.APP=m.e.APP;for(const n of ['v','x','e','j','APP']){out[n]={};let o=m[n];for(let i=0;i<3&&o;i++,o=Object.getPrototypeOf(o)){for(const k of Object.getOwnPropertyNames(o)){try{let v=m[n][k];if(typeof v==='function')out[n][k]=v.toString();else if(v===null||['string','number','boolean'].includes(typeof v))out[n][k]=v;}catch{}}}} const w=System.get('chunks:///WASM-6e26b0b0.js');out.wasm=Object.fromEntries(Object.entries(w).map(([k,v])=>[k,v.toString()]));return out;}''')
  (OUT/'methods.json').write_text(json.dumps(methods,ensure_ascii=False,indent=2),encoding='utf8')
  await page.screenshot(path=str(OUT/'offline.png'))
  result=await page.evaluate('''() => ({text:document.body.innerText, globals:Object.keys(window).filter(k=>/proto|app|system|cc/i.test(k)), modules:typeof System!=='undefined'?[...System.entries()].map(([k,v])=>({name:k,keys:Object.keys(v)})):[]})''')
  (OUT/'runtime.json').write_text(json.dumps({'errors':errors,'missing':missing,'counts':counts,'result':result},ensure_ascii=False,indent=2),encoding='utf8')
  print(json.dumps({'errors':errors[:8],'missing':missing[:15],'modules':len(result['modules'])}))
  await browser.close()
asyncio.run(main())
