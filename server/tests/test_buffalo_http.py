import json
import hashlib
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

from server.services.buffalo_demo import build_server
from server.services.local_demo import build_server as build_mahjong


class BuffaloHTTPTests(unittest.TestCase):
    def test_launch_spin_resume_and_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            http = build_server(0,Path(directory)/'buffalo.sqlite3')
            mahjong = build_mahjong(0,Path(directory)/'mahjong.sqlite3')
            thread = threading.Thread(target=http.serve_forever,daemon=True)
            thread.start()

            def request(path, data=None, headers=None):
                req=Request(f'http://127.0.0.1:{http.server_port}'+path,data=data,headers=headers or {})
                try:response=urlopen(req,timeout=5)
                except HTTPError as error:response=error
                with response:return response.status,response.read()

            try:
                headers={'Content-Type':'application/json'}
                status,body=request('/api/v1/games/buffalo-win/launch',b'{"language":"zh"}',headers)
                self.assertEqual(status,201)
                launch=json.loads(body)
                self.assertEqual(launch['mode'],'generated')
                token=parse_qs(urlsplit(launch['launch_url']).query)['ops'][0]
                form_headers={'Content-Type':'application/x-www-form-urlencoded','X-Local-Game-Session':token}
                # Original help assets and metadata must be served byte-for-byte;
                # opening help must not mutate the wallet or round state.
                client = Path(__file__).resolve().parents[2] / 'Buffalo Win'
                restored = json.loads((client / 'fixtures/restored-original-help-assets.json').read_text(encoding='utf-8'))
                for asset in restored['assets']:
                    status, content = request('/' + asset['path'])
                    self.assertEqual(status, 200, asset['path'])
                    self.assertEqual(hashlib.sha256(content).hexdigest(), asset['sha256'])
                sources = json.loads((client / 'fixtures/asset-sources.json').read_text(encoding='utf-8'))
                english_assets = [asset for asset in sources if asset['source'].startswith('https://static.pg-demo.com/')]
                self.assertTrue(english_assets)
                for asset in english_assets:
                    status, content = request('/' + asset['path'])
                    self.assertEqual(status, 200, asset['path'])
                    self.assertEqual(hashlib.sha256(content).hexdigest(), asset['sha256'])
                rule_path = '/web-api/game-proxy/v2/GameRule/Get'
                self.assertEqual(request(rule_path, b'gid=108')[0], 401)
                status, content = request(rule_path, b'gid=108', form_headers)
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(content), json.loads((client / 'fixtures/game-rule.json').read_text(encoding='utf-8')))
                self.assertEqual(request(rule_path, b'gid=74', form_headers)[0], 404)
                self.assertEqual(http.service.wallet(token)['balance_minor'], 200000)
                status, english = request('/api/v1/games/buffalo-win/launch', b'{"language":"en"}', headers)
                self.assertEqual(status, 201)
                self.assertEqual(parse_qs(urlsplit(json.loads(english)['launch_url']).query)['l'], ['en'])
                self.assertEqual(request('/api/v1/games/buffalo-win/launch',b'{"language":"xx"}',headers)[0],400)
                self.assertEqual(request('/api/v1/sessions',b'{}',{**headers,'Origin':'http://evil.invalid'})[0],403)
                self.assertEqual(request('/game-api/buffalo-win/v2/GameInfo/Get',b'')[0],401)
                status,body=request('/game-api/buffalo-win/v2/GameInfo/Get',b'',form_headers)
                self.assertEqual(json.loads(body)['dt']['ls']['si']['sid'],'0')
                body=urlencode({'id':'0','cs':0.3,'ml':2,'btt':2,'pf':1,'wk':'0_C'}).encode()
                status,response=request('/game-api/buffalo-win/v2/Spin',body,form_headers)
                self.assertEqual(status,200)
                self.assertEqual(request('/game-api/buffalo-win/v2/Spin',body,form_headers)[1],response)
                tx=json.loads(response)['dt']['si']
                self.assertEqual(tx['blb'],2000)
                self.assertEqual(tx['tb'],6)
                info=json.loads(request('/game-api/buffalo-win/v2/GameInfo/Get',b'',form_headers)[1])
                self.assertEqual(info['dt']['ls']['si'],tx)
                self.assertEqual(info['dt']['bl'],tx['bl'])
                self.assertEqual([g['id'] for g in json.loads(request('/api/v1/games')[1])['games']],['buffalo-win'])
                self.assertEqual([g['id'] for g in mahjong.service.registry.catalog()],['mahjong-ways2'])
                other_token=mahjong.service.create_session()['token']
                self.assertEqual(request('/api/v1/wallet',headers={'Authorization':'Bearer '+other_token})[0],401)
                for path in ('/fixtures/rule-cases.json','/analyze_rules.py','/RULES_ANALYSIS.txt'):
                    self.assertEqual(request(path)[0],404)
                self.assertIn(b'/local-auth-bootstrap.js',request('/')[1])
            finally:
                http.shutdown();thread.join();http.server_close();mahjong.server_close()
