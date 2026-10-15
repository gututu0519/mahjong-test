import concurrent.futures
import json
import tempfile
import threading
import unittest
from unittest.mock import patch
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen
from server.services.big_bass_bonanza_demo import build_server


class BigBassHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.database = Path(self.tmp.name) / 'game.sqlite3'
        self.start()

    def start(self):
        self.http = build_server(0, self.database)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.http.server_port)

    def stop(self):
        self.http.shutdown(); self.http.server_close(); self.thread.join()

    def tearDown(self):
        self.stop(); self.tmp.cleanup()

    def request(self, path, data=None, headers=None):
        req = Request(self.base + path, data=data, headers=headers or {})
        try:
            response = urlopen(req, timeout=10)
        except HTTPError as e:
            response = e
        with response:
            return response.status, response.read()

    def launch(self):
        code, raw = self.request('/api/v1/games/big-bass-bonanza/launch', b'{}')
        self.assertEqual(code, 201)
        return parse_qs(urlsplit(json.loads(raw)['launch_url']).query)['ops'][0]

    def form(self, token, **kw):
        return urlencode(dict(symbol='vs10bbbonanza', mgckey=token, index=2, counter=3, **kw)).encode()

    def test_language_launch_and_packages(self):
        for language in ('zh', 'en'):
            code, raw = self.request('/api/v1/games/big-bass-bonanza/launch',
                                     json.dumps({'language': language}).encode())
            self.assertEqual(code, 201)
            result = json.loads(raw)
            self.assertEqual(result['language'], language)
            self.assertEqual(parse_qs(urlsplit(result['launch_url']).query)['lang'], [language])
            code, html = self.request(result['launch_url'])
            self.assertEqual(code, 200)
            self.assertIn(('"lang": "'+language+'"').encode(), html)
        base = '/hub-demo/common/v3/games-html5/games/vs/vs10bbbonanza/'
        for layout in ('desktop', 'mobile'):
            for gui in ('', 'GUI_'):
                code, body = self.request(base + layout + '/packages/zh_' + gui + layout + '.json')
                self.assertEqual(code, 200)
                self.assertTrue(json.loads(body))

    def test_durable_idempotency_and_isolation(self):
        token, other = self.launch(), self.launch()
        route = '/hub-demo/ge/v3/gameService'
        body = self.form(token, action='doSpin', c='0.1', l='10', bl='0')
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.request(route, body), range(4)))
        self.assertTrue(all(r == results[0] for r in results))
        self.assertEqual(results[0][0], 200)
        self.assertEqual(self.http.service.wallet(other)['balance_minor'], 200000)
        self.assertEqual(self.http.service.wallet(token)['balance_minor'], 199900)
        self.stop(); self.start()
        self.assertEqual(self.request(route, body), results[0])
        code, raw = self.request(route, self.form(token, action='doInit'))
        self.assertEqual(code, 200)
        init = parse_qs(raw.decode())
        self.assertEqual(init['ver'], ['2'])
        self.assertEqual(init['sh'], ['3'])
        self.assertEqual(init['l'], ['10'])
        self.assertNotIn('rtp', init)
        self.assertGreaterEqual(int(init['index'][0]), 2)
        self.assertEqual(self.request(route, self.form(token, action='doSpin', c='0.2', l='10', bl='0'))[0], 409)
        with self.http.service.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM ledger WHERE kind='spin'").fetchone()[0], 1)

    def test_free_restart_collect_and_assets(self):
        token = self.launch()
        route = '/hub-demo/ge/v3/gameService'
        def command(index, action='doSpin'):
            return urlencode(dict(symbol='vs10bbbonanza', mgckey=token, index=index,
                                  counter=index * 2, action=action, c='.20', l='10')).encode()
        game = self.http.service.registry.get('big-bass-bonanza')
        trigger = ([1,1,1,4,5,6,8,9,10,11,12,3,4,5,6], [3]*5, [4]*5)
        with patch.object(game, '_draw', return_value=trigger):
            first = self.request(route, command(2))
        self.assertEqual(first[0], 200)
        self.assertEqual(parse_qs(first[1].decode())['fsmax'], ['10'])
        self.stop(); self.start()
        restored = parse_qs(self.request(route, command(3, 'doInit'))[1].decode())
        self.assertEqual(restored['s'], ['1,1,1,4,5,6,8,9,10,11,12,3,4,5,6'])
        self.assertEqual(restored['fsmax'], ['10'])
        self.assertEqual(self.request(route, command(2)), first)
        game = self.http.service.registry.get('big-bass-bonanza')
        losing = ([3,4,5,6,8,9,10,11,12,3,4,5,6,8,9], [3]*5, [4]*5)
        with patch.object(game, '_draw', return_value=losing):
            for index in range(4, 14):
                result = self.request(route, command(index))
                self.assertEqual(result[0], 200)
        self.assertEqual(parse_qs(result[1].decode())['fsend_total'], ['1'])
        collected = self.request(route, command(14, 'doCollect'))
        self.assertEqual(collected[0], 200)
        self.assertEqual(self.request(route, command(14, 'doCollect')), collected)
        self.assertEqual(self.http.service.wallet(token)['balance_minor'], 199800)
        self.assertEqual(self.request('/fixtures/init.txt')[0], 404)
        html = self.request('/')[1]
        self.assertIn(b'vs10bbbonanza', html)
        self.assertNotIn(b'vs20olympgate', html)
