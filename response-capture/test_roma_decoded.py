"""Test the Roma observer and plaintext decoder without launching a browser."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import app

sys.path.insert(0, str(app.ROOT.parent))
from server.adapters.jili.roma_x_10000 import pack


class RomaCaptureTests(unittest.TestCase):
    def test_original_promise_and_decoded_bonus(self):
        fixture = json.loads((app.ROOT.parent/'server/tests/fixtures/roma-x-10000-spins.json').read_text(encoding='utf-8'))[-1]
        response = dict(type=0, ret=0, data=pack('SpinResponse', {'data': pack('SpinAck', fixture['spin'])}))
        script = r"""
const fs=require('fs'), vm=require('vm');const input=JSON.parse(fs.readFileSync(0,'utf8'));
(async()=>{
 const events=[],ctx={location:{pathname:'/rx10000/'},__captureDecoded:event=>events.push(event)};
 vm.createContext(ctx);vm.runInContext('var window=globalThis;',ctx);vm.runInContext(input.hook,ctx);
 ctx.fixture=input.response;ctx.request=input.request;
 const result=await vm.runInContext(`(async()=>{
   let published;class Loader{register(){throw Error('named register is not installed yet')}}
   window.System=new Loader();
   Loader.prototype.register=function(name,deps,factory){factory(value=>published=value,{}).execute()};
   let expected=Promise.resolve(fixture);
   System.register('chunks:///WASM-fb1f222b.js',[],function(publish,context){return {execute(){publish({c:function(){return expected}})}}});
   const actual=published.c(0,new Uint8Array(request)),same=actual===expected;await actual;
   expected=Promise.reject(new Error('fixture rejection'));
   try{await published.c(0,new Uint8Array())}catch(error){return {same,rejected:error.message}}
 })()`,ctx);
 await Promise.resolve();process.stdout.write(JSON.stringify({result,events}));
})().catch(error=>{console.error(error);process.exit(1)});
"""
        data = dict(hook=(app.ROOT/'decoded-hook.js').read_text(encoding='utf-8'), response=response,
                    request=pack('SpinReq', fixture['request']))
        result = json.loads(subprocess.run([shutil.which('node'), '-e', script], input=json.dumps(data),
                                          capture_output=True, text=True, check=True).stdout)
        self.assertEqual(result['result'], dict(same=True, rejected='fixture rejection'))
        previous = app.DATA
        with tempfile.TemporaryDirectory() as temp:
            app.DATA = Path(temp)
            try:
                capture = app.Capture('http://capture.test/rx10000/')
                frame = type('Frame', (), {'url': capture.url})()
                for event in result['events']:
                    capture.decoded_event({'frame': frame}, event)
                self.assertEqual(capture.decoded, dict(ready=True, game='Roma X 10000', spins=1,
                                                       errors=1, scatter_wins=0, feature_spins=1))
                records = [json.loads(line) for line in (capture.folder/'decoded-rounds.jsonl').read_text().splitlines()]
                self.assertEqual(next(row for row in records if row['kind']=='spin')['spin'], fixture['spin'])
            finally:
                app.DATA = previous


if __name__ == '__main__':
    unittest.main()
