"""Offline integration test for decoded round capture and untouched command behavior."""
import asyncio
import json
import tempfile
from pathlib import Path
import app

async def test(vaults=False):
    import sys
    sys.path.insert(0, str(app.ROOT.parent))
    if vaults:
        from server.adapters.jili.three_billion_vaults import pack
    else:
        from server.adapters.jili.jokers_fortune_winx import pack
    from playwright.async_api import async_playwright
    old = app.DATA
    with tempfile.TemporaryDirectory() as temp:
        app.DATA = Path(temp)
        try:
            capture = app.Capture('http://capture.test/' + ('sss-tbv/' if vaults else 'sss-jf2/'))
            spin = {'RoundQueue':[{'Symbol':[{'Col':[7,0,1]}]*5, 'AwardDataVec':[], 'ScatterWin':75, 'RoundWin':75}], 'TotalWin':75}
            if vaults:
                spin = {'RoundQueue':[{'PlateSymbol':[{'Column':[0,1,2]}]*5, 'FreeTotalRound':6, 'JPPlate':{'Win':75}, 'RoundWin':75}], 'TotalWin':75}
            response = {'type':0,'ret':0,'data':pack('SpinResponse',{'data':pack('SpinAck',spin),'totalWin':75})}
            async with async_playwright() as pw:
                browser = await app.launch_browser(pw, headless=True)
                page = await browser.new_page()
                await page.expose_binding('__captureDecoded',capture.decoded_event)
                await page.add_init_script(path=str(app.ROOT/'decoded-hook.js'))
                await page.route('**/*',lambda route:route.fulfill(body='<html></html>',content_type='text/html'))
                await page.goto(capture.url)
                check = await page.evaluate("""async ({response,vaults}) => {
                  let published;
                  class Loader {register(deps,factory){if(typeof deps==='string')throw Error('named register not installed')}}
                  window.System=new Loader();
                  Loader.prototype.register=function(name,deps,factory){factory(value=>published=value,{}).execute()};
                  let expected=Promise.resolve(response), original=function(){return expected};
                  System.register(vaults?'chunks:///WASM-80e4c733.js':'chunks:///WASM-b0a7e8f0.js',[],function(publish,context){return {execute(){publish({[vaults?'b':'c']:original})}}});
                  const actual=published[vaults?'b':'c'](0,new Uint8Array([9,154,153,153,153,153,153,185,63]));
                  const same=actual===expected;await actual;
                  expected=Promise.reject(new Error('fixture rejection'));
                  try{await published[vaults?'b':'c'](0,new Uint8Array())}catch(error){return {same,rejected:error.message}}
                }""",dict(response=response,vaults=vaults))
                for _ in range(50):
                    if capture.decoded['spins']==1 and capture.decoded['errors']==1:break
                    await asyncio.sleep(.1)
                assert check=={'same':True,'rejected':'fixture rejection'},check
                expected=dict(ready=True,spins=1,scatter_wins=0 if vaults else 1,errors=1,game='3 Billion Vaults' if vaults else 'Joker')
                if vaults:expected.update(feature_spins=1,jackpot_wins=1)
                assert capture.decoded==expected,capture.decoded
                records=[json.loads(line) for line in (capture.folder/'decoded-rounds.jsonl').read_text().splitlines()]
                assert next(r for r in records if r['kind']=='spin')['scatter_win']==(0 if vaults else 75)
                assert capture.snapshot()['decoded']['scatter_wins']==(0 if vaults else 1)
                await browser.close()
                print('PASS: original Promise identity/rejection preserved; plaintext saved; Scatter detected; errors counted')
        finally:
            app.DATA=old

if __name__=='__main__':
    asyncio.run(test())
    asyncio.run(test(True))
