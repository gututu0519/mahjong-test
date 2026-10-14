import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

from server.services.olympus_preview import build_server
from server.run import ROOT, load_profile


class OlympusPreviewTests(unittest.TestCase):
    def setUp(self):
        self.http = build_server(0)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.http.server_port}'

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()

    def request(self, path, data=None, mime='application/x-www-form-urlencoded'):
        req = Request(self.base + path, data=data, headers={'Content-Type': mime})
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.read()

    def launch(self):
        status, body = self.request('/api/v1/games/gates-of-olympus/launch', b'{"language":"zh"}', 'application/json')
        self.assertEqual(status, 201)
        result = json.loads(body)
        self.assertEqual(result['mode'], 'frontend-preview')
        self.assertEqual(result['language'], 'en')
        return parse_qs(urlsplit(result['launch_url']).query)['ops'][0]

    def test_initialization_and_no_settlement(self):
        token = self.launch()
        route = '/hub-demo/ge/v3/gameService'
        form = {'mgckey': token, 'symbol': 'vs20olympgate', 'action': 'doInit', 'index': '9', 'counter': '17'}
        status, body = self.request(route, urlencode(form).encode())
        self.assertEqual(status, 200)
        initial = parse_qs(body.decode())
        self.assertEqual(initial['balance'], ['2,000.00'])
        self.assertEqual(initial['index'], ['9'])
        self.assertIn('paytable', initial)
        self.assertEqual(self.request(route, urlencode({**form, 'action': 'doSpin'}).encode())[0], 501)
        self.assertEqual(self.request(route, urlencode({**form, 'mgckey': 'invalid'}).encode())[0], 401)
        self.assertFalse(hasattr(self.http, 'service'))

    def test_settings_isolation_and_private_files(self):
        a, b = self.launch(), self.launch()
        route = '/hub-demo/ge/v3/saveSettings.do'
        self.request(route, urlencode({'mgckey': a, 'id': 'game', 'settings': 'Volume=0.5'}).encode())
        self.assertEqual(self.request(route, urlencode({'mgckey': a, 'id': 'game', 'method': 'load'}).encode()), (200, b'Volume=0.5'))
        self.assertEqual(self.request(route, urlencode({'mgckey': b, 'id': 'game', 'method': 'load'}).encode()), (200, b''))
        for path in ('/fixtures/init.txt', '/fixtures/asset-sources.json', '/local-deserializer.js', '/hub-demo/common/'):
            self.assertEqual(self.request(path)[0], 404)
        status, html = self.request('/')
        self.assertEqual(status, 200)
        self.assertNotIn(b'__LOCAL_CONFIG__', html)
        self.assertNotIn(b'pragmaticplay.net', html)

    def test_profile_loads_no_engines(self):
        profile, configs = load_profile(ROOT / 'services/gates-of-olympus')
        self.assertEqual(profile['games'], [])
        self.assertEqual(configs, {})


if __name__ == '__main__':
    unittest.main()
