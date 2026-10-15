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
from server.services.olympus_demo import build_server


class OlympusHTTPTests(unittest.TestCase):
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
        code, raw = self.request('/api/v1/games/gates-of-olympus/launch', b'{}')
        self.assertEqual(code, 201)
        return parse_qs(urlsplit(json.loads(raw)['launch_url']).query)['ops'][0]

    def form(self, token, **kw):
        return urlencode(dict(symbol='vs20olympgate', mgckey=token, index=2, counter=3, **kw)).encode()

    def test_durable_idempotency_and_isolation(self):
        token, other = self.launch(), self.launch()
        route = '/hub-demo/ge/v3/gameService'
        body = self.form(token, action='doSpin', c='0.1', l='20', bl='0')
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.request(route, body), range(4)))
        self.assertTrue(all(r == results[0] for r in results))
        self.assertEqual(results[0][0], 200)
        self.assertEqual(self.http.service.wallet(other)['balance_minor'], 200000)
        self.assertEqual(self.http.service.wallet(token)['balance_minor'], 199800)
        self.stop(); self.start()
        self.assertEqual(self.request(route, body), results[0])
        code, raw = self.request(route, self.form(token, action='doInit'))
        self.assertEqual(code, 200)
        init = parse_qs(raw.decode())
        self.assertIn('purInit', init)
        self.assertEqual(init['purInit_e'], ['1'])
        self.assertNotIn('rtp', init)
        self.assertGreaterEqual(int(init['index'][0]), 2)
        self.assertEqual(self.request(route, self.form(token, action='doSpin', c='0.2', l='20', bl='0'))[0], 409)
        with self.http.service.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM ledger WHERE kind='spin'").fetchone()[0], 1)

    def test_purchase_restart_retry_and_free_settlement(self):
        token = self.launch()
        route = '/hub-demo/ge/v3/gameService'
        def body(index, **kw):
            return urlencode(dict(symbol='vs20olympgate', mgckey=token, index=index,
                                  counter=index * 2 - 1, **kw)).encode()
        purchase = body(2, action='doSpin', c='0.1', l='20', bl='0', pur='0')
        first = self.request(route, purchase)
        self.assertEqual(first[0], 200)
        data = parse_qs(first[1].decode())
        self.assertEqual((data['purtr'], data['puri'], data['fsmax'], data['tw']),
                         (['1'], ['0'], ['15'], ['6.00']))
        self.assertEqual(self.http.service.wallet(token)['balance_minor'], 180000)
        self.stop(); self.start()
        self.assertEqual(self.request(route, purchase), first)
        init = parse_qs(self.request(route, body(3, action='doInit'))[1].decode())
        self.assertEqual(init['puri'], ['0'])
        self.assertEqual(init['fsmax'], ['15'])
        self.assertEqual(self.request(route, body(3, action='doSpin', c='0.1', l='20', pur='0'))[0], 409)
        game = self.http.service.registry.get('gates-of-olympus')
        plain = [3 + i % 9 for i in range(30)]
        with patch.object(game, '_new_board', return_value=(plain, {}, [3] * 6, [4] * 6)):
            for index in range(3, 18):
                self.assertEqual(self.request(route, body(index, action='doSpin', c='0.1', l='20'))[0], 200)
        self.assertEqual(self.http.service.wallet(token)['balance_minor'], 180000)
        collect = body(18, action='doCollect')
        settled = self.request(route, collect)
        self.assertEqual(settled[0], 200)
        self.assertEqual(self.request(route, collect), settled)
        self.assertEqual(self.http.service.wallet(token)['balance_minor'], 180600)
        # A rejected unaffordable purchase must leave both state and wallet untouched.
        before = self.http.service.state(token, 'gates-of-olympus')
        self.assertNotEqual(self.request(route, body(19, action='doSpin', c='12', l='20', pur='0'))[0], 200)
        self.assertEqual(self.http.service.state(token, 'gates-of-olympus'), before)
        self.assertEqual(self.request(route, body(19, action='doSpin', c='0.1', l='20', bl='1', pur='0'))[0], 409)

    def test_chinese_and_english_launch_assets(self):
        for language in ('zh', 'en'):
            code, raw = self.request('/api/v1/games/gates-of-olympus/launch', json.dumps({'language': language}).encode())
            self.assertEqual(code, 201)
            launch = json.loads(raw)
            self.assertEqual(launch['language'], language)
            self.assertEqual(parse_qs(urlsplit(launch['launch_url']).query)['lang'], [language])
            code, html = self.request(launch['launch_url'])
            self.assertEqual(code, 200)
            self.assertIn(('"lang": "' + language + '"').encode(), html)
            if language == 'en':
                continue  # English is embedded in the base game resources.
            for mode in ('desktop', 'mobile'):
                for name in (language + '_' + mode, language + '_GUI_' + mode):
                    path = '/hub-demo/common/v3/games-html5/games/vs/vs20olympgate/' + mode + '/packages/' + name + '.json'
                    self.assertEqual(self.request(path)[0], 200)
        self.assertEqual(self.request('/?lang=invalid')[0], 400)

    def test_endpoints_and_validation(self):
        token = self.launch()
        self.assertEqual(json.loads(self.request('/health')[1])['mode'], 'generated')
        self.assertEqual(self.request('/?ops=invalid')[0], 401)
        body = self.form(token, action='doSpin', c='0.1', l='20', pur='1')
        self.assertEqual(self.request('/hub-demo/ge/v3/gameService', body)[0], 400)
        self.assertEqual(self.request('/hub-demo/ge/v3/gameService', body, {'Origin': 'https://example.com'})[0], 403)
        self.assertEqual(self.request('/hub-demo/ge/v3/gameService', body + b'&c=1')[0], 400)
        self.assertEqual(self.request('/fixtures/init.txt')[0], 404)
        route = '/hub-demo/ge/v3/saveSettings.do'
        self.request(route, urlencode({'mgckey': token, 'settings': 'Volume=0.2'}).encode())
        self.stop(); self.start()
        self.assertEqual(self.request(route, urlencode({'mgckey': token}).encode()), (200, b'Volume=0.2'))
        self.assertEqual(self.request('/hub-demo/ge/v3/reloadBalance.do?mgckey=' + token)[0], 200)

    def test_pending_tumble_restart_and_collect_exactly_once(self):
        token = self.launch()
        route = '/hub-demo/ge/v3/gameService'
        game = self.http.service.registry.get('gates-of-olympus')
        board = [11] * 8 + [3 + i % 8 for i in range(22)]
        body = self.form(token, action='doSpin', c='0.1', l='20', bl='0')
        with patch.object(game, '_new_board', return_value=(board, {}, [3] * 6, [4] * 6)):
            self.assertEqual(self.request(route, body)[0], 200)
        self.stop(); self.start()
        init = parse_qs(self.request(route, self.form(token, action='doInit'))[1].decode())
        self.assertEqual(init['tw'], ['0.50'])
        self.assertIn('tmb', init)
        game = self.http.service.registry.get('gates-of-olympus')
        plain = [3 + i % 9 for i in range(30)]
        continuation = urlencode({'symbol': 'vs20olympgate', 'mgckey': token, 'action': 'doSpin',
                                  'index': 3, 'counter': 5, 'c': '0.1', 'l': 20, 'bl': 0}).encode()
        with patch.object(game, '_cascade', return_value=(plain, {}, [3] * 6, [4] * 6)):
            result = parse_qs(self.request(route, continuation)[1].decode())
        self.assertEqual(result['na'], ['c'])
        self.assertEqual(self.http.service.wallet(token)['balance_minor'], 199800)
        collect = urlencode({'symbol': 'vs20olympgate', 'mgckey': token, 'action': 'doCollect', 'index': 4, 'counter': 7}).encode()
        first = self.request(route, collect)
        self.assertEqual(first[0], 200)
        self.assertEqual(self.request(route, collect), first)
        self.assertEqual(self.http.service.wallet(token)['balance_minor'], 199850)


if __name__ == '__main__':
    unittest.main()
