import asyncio,json,pathlib
from playwright.async_api import async_playwright
OUT=pathlib.Path('clients/super-ace/diagnostics')
OUT.mkdir(parents=True,exist_ok=True)
async def main():
 async with async_playwright() as p:
  b=await p.chromium.launch(channel='msedge',headless=True);page=await b.new_page(viewport={'width':1100,'height':800});errors=[];bad=[]
  page.on('pageerror',lambda e:errors.append(e.stack));page.on('response',lambda r:bad.append([r.status,r.url.split('?')[0]]) if r.status>=400 else None)
  await page.goto('http://127.0.0.1:8088/',wait_until='domcontentloaded');await page.wait_for_timeout(18000)
  await page.screenshot(path=str(OUT/'local.png'))
  state=await page.evaluate('''()=>{const m=window.System?.get('chunks:///index-2059667d.js');return {text:document.body.innerText,state:m?.j?.m_currState,login:m?.e?.APP?.IsLoginSuccess(),info:m?.x?.IsGetInfo};}''')
  print(json.dumps({'errors':errors[:6],'bad':bad[:20],'state':state}));await b.close()
asyncio.run(main())
