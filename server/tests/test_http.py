import base64
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit, parse_qs
from urllib.request import Request, urlopen

from server.app import build_server
from server.adapters.pg.protocol import field, text_field, double_field, pack, unpack, fields


class HTTPTests(unittest.TestCase):
    def test_pg_cached_json_key_order_does_not_change_wire_response(self):
        from server.adapters.pg.mahjong_ways2 import transaction, encode_response, idle_event
        from server.games.mahjong_ways2.engine import MahjongWays2
        game = MahjongWays2()
        event = idle_event(game.initial_state('wire-order'))
        event.update(gold_before={'9': 1, '10': 1, '3': 1}, gold_after={'9': 1, '10': 1},
                     winning_positions={'9': [0, 7, 14], '3': [1, 8, 15]},
                     rates={'9': 5, '3': 1}, ways={'9': 1, '3': 1},
                     base_awards_minor={'9': 25, '3': 5})
        cached = json.loads(json.dumps(event, sort_keys=True))
        wallet = dict(before_minor=200000, after_minor=200000, debit_minor=0)
        first = encode_response(transaction(event, wallet, game.config['win_thresholds']))
        retry = encode_response(transaction(cached, wallet, game.config['win_thresholds']))
        self.assertEqual(first, retry)

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

    def test_demo_launch_and_isolated_client_session(self):
        for path in ('/demo', '/demo/', '/demo/style.css', '/demo/app.js', '/demo/i18n.js'):
            self.assertEqual(self.request(path)[0], 200)
        status, body, headers = self.post_json('/api/v1/games/mahjong-ways2/launch', {})
        self.assertEqual(status, 201)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        launch = json.loads(body)
        self.assertEqual(launch['balance_minor'], 200000)
        self.assertEqual(launch['currency'], 'DEMO')
        query = parse_qs(urlsplit(launch['launch_url']).query)
        self.assertEqual(query['l'], ['zh'])
        token = query['ops'][0]
        self.assertNotEqual(token, 'local-demo-session')
        other = json.loads(self.post_json('/api/v1/games/mahjong-ways2/launch', {})[1])
        other_token = parse_qs(urlsplit(other['launch_url']).query)['ops'][0]
        self.assertNotEqual(token, other_token)
        self.assertEqual(self.request(launch['launch_url'])[0], 200)

        auth = urlencode({'otk': 'local-demo', 'os': token, 'gi': '74', 'btt': '1'}).encode()
        status, body, _ = self.request('/web-api/auth/session/v2/verifyOperatorPlayerSession', auth)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['dt']['tk'], token)
        self.assertEqual(json.loads(body)['dt']['bl'], 2000)
        for endpoint in ('GameName', 'GameRule'):
            self.assertEqual(self.request('/web-api/game-proxy/v2/' + endpoint + '/Get',
                                          urlencode({'atk': token, 'gid': '74'}).encode())[0], 200)
        self.assertEqual(self.request('/game-api/74/v4/GameInfo/Get',
                                      urlencode({'atk': token, 'btt': 1, 'pf': 1}).encode())[0], 200)
        raw = (text_field(1, token) + field(2, 0, 1) + field(3, 0, 1)
               + text_field(5, '0') + text_field(12, '0_C')
               + double_field(21, 0.01) + field(22, 0, 5))
        self.assertEqual(self.request('/game-api/74/v4/Spin', pack(raw, 42))[0], 200)
        self.assertEqual(len(self.server.service.history(token)), 1)
        for untouched in (other_token, 'local-demo-session'):
            self.assertEqual(self.server.service.history(untouched), [])
            self.assertEqual(self.server.service.wallet(untouched)['balance_minor'], 200000)

    def test_demo_rejects_invalid_launch_and_expired_session(self):
        self.assertEqual(self.post_json('/api/v1/games/missing/launch', {})[0], 404)
        self.assertEqual(self.post_json('/api/v1/games/mahjong-ways2/launch', {},
                                       {'Origin': 'https://other.example'})[0], 403)
        launch = json.loads(self.post_json('/api/v1/games/mahjong-ways2/launch', {})[1])
        token = parse_qs(urlsplit(launch['launch_url']).query)['ops'][0]
        with self.server.service.connection(True) as db:
            db.execute('UPDATE sessions SET expires_at=0 WHERE token_hash=?',
                       (self.server.service.sessions._token_hash(token),))
        for invalid in (token, 'not-a-session'):
            auth = urlencode({'otk': 'local-demo', 'os': invalid, 'gi': '74', 'btt': '1'}).encode()
            self.assertEqual(self.request('/web-api/auth/session/v2/verifyOperatorPlayerSession', auth)[0], 401)
            form = urlencode({'atk': invalid, 'gid': '74'}).encode()
            self.assertEqual(self.request('/web-api/game-proxy/v2/GameRule/Get', form)[0], 401)

    def test_demo_launch_language(self):
        for language in ('zh', 'en'):
            status, body, _ = self.post_json('/api/v1/games/mahjong-ways2/launch', {'language': language})
            self.assertEqual(status, 201)
            launch = json.loads(body)
            self.assertEqual(launch['language'], language)
            self.assertEqual(parse_qs(urlsplit(launch['launch_url']).query)['l'], [language])
            self.assertEqual(self.request(launch['launch_url'])[0], 200)
        for language in ('fr', 'EN', '', None, ['en'], {'l': 'en'}):
            status, body, _ = self.post_json('/api/v1/games/mahjong-ways2/launch', {'language': language})
            self.assertEqual(status, 400)
            self.assertEqual(json.loads(body)['err']['cd'], 'LANGUAGE_INVALID')


if __name__ == '__main__':
    unittest.main()
