import base64
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from server.app import build_server
from server.adapters.pg.protocol import field, text_field, double_field, pack, unpack, fields


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.server = build_server(0, Path(self.temp.name) / 'http.sqlite3')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path, data=None, headers=None):
        request = Request(self.base + path, data=data, headers=headers or {})
        try:
            with urlopen(request, timeout=10) as response:
                return response.status, response.read(), response.headers
        except HTTPError as error:
            return error.code, error.read(), error.headers

    def post_json(self, path, data, headers=None):
        return self.request(path, json.dumps(data).encode(), {'Content-Type': 'application/json', **(headers or {})})

    def test_platform_http_and_history(self):
        status, body, _ = self.post_json('/api/v1/sessions', {})
        self.assertEqual(status, 201)
        session = json.loads(body)
        headers = {'Authorization': 'Bearer ' + session['token'], 'Idempotency-Key': 'first'}
        payload = {'previous_sid': '0', 'bet': {'coin_minor': 1, 'level': 5}}
        status, body, _ = self.post_json('/api/v1/games/mahjong-ways2/spin', payload, headers)
        self.assertEqual(status, 200, body)
        result = json.loads(body)
        self.assertEqual(json.loads(self.post_json('/api/v1/games/mahjong-ways2/spin', payload, headers)[1]), result)
        history = json.loads(self.request('/api/v1/history', headers=headers)[1])
        self.assertEqual(history['spins'], [result])
        self.assertEqual(self.request('/api/v1/wallet')[0], 401)
        self.assertEqual(self.request('/fixtures/spin-rounds.json')[0], 404)
        self.assertEqual(self.request('/local_spin.py')[0], 404)
        self.assertEqual(self.post_json('/api/v1/sessions', {}, {'Origin': 'https://other.example'})[0], 403)

    def test_legacy_protocol_generated_without_replay(self):
        with patch('local_spin.LocalSpin.__init__', side_effect=AssertionError('Replay must not run')):
            info_body = urlencode({'atk': 'local-demo-session', 'btt': 1, 'pf': 1}).encode()
            status, body, _ = self.request('/game-api/74/v4/GameInfo/Get', info_body)
            self.assertEqual(status, 200, body)
            info = json.loads(body)
            self.assertEqual(info['engineMode'], 'generated')
            raw = base64.b64decode(info['localSpin'])
            self.assertEqual(next(v for n, w, v in fields(raw) if n == 1), b'0')
            request = (text_field(1, 'local-demo-session') + field(2, 0, 1) + field(3, 0, 1)
                       + text_field(5, '0') + text_field(12, '0_C')
                       + double_field(21, 0.01) + field(22, 0, 5))
            status, first, headers = self.request('/game-api/74/v4/Spin', pack(request, 42))
            self.assertEqual(status, 200, first)
            self.assertEqual(headers['X-Game-Engine'], 'generated')
            status, retry, _ = self.request('/game-api/74/v4/Spin', pack(request, 91))
            self.assertEqual(status, 200)
            self.assertEqual(unpack(first)[0], unpack(retry)[0])
            reply_fields = list(fields(unpack(first)[0]))
            self.assertEqual(next(v for n, w, v in reply_fields if n == 1), b'1')
            self.assertEqual(len([v for n, w, v in reply_fields if n == 103]), 35)
            self.assertEqual(len(self.server.service.history('local-demo-session')), 1)


if __name__ == '__main__':
    unittest.main()
