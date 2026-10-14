import json
import threading
import unittest
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

from server.services.buffalo_preview import build_server
from server.services.local_demo import Handler as LobbyHandler
from server.core.contracts import ServiceError


class BuffaloLaunchGatewayTests(unittest.TestCase):
    def test_fixed_preview_origin_and_invalid_links(self):
        handler = object.__new__(LobbyHandler)
        with patch('server.services.local_demo.urlopen', return_value=BytesIO(json.dumps({
            'launch_url': '/?mock=1&ops=test&l=zh', 'mode': 'frontend-preview'
        }).encode())) as upstream:
            result = handler.launch_game('buffalo-win', 'zh')
            self.assertEqual(urlsplit(result['launch_url']).netloc, '127.0.0.1:8083')
            self.assertEqual(upstream.call_args.args[0].full_url,
                             'http://127.0.0.1:8083/api/v1/games/buffalo-win/launch')
        for link in ('https://example.com/?mock=1&ops=test', '//example.com/?mock=1&ops=test', '/?mock=1'):
            with patch('server.services.local_demo.urlopen', return_value=BytesIO(json.dumps({'launch_url': link}).encode())):
                with self.assertRaises(ServiceError) as error:
                    handler.launch_game('buffalo-win', 'zh')
                self.assertEqual(error.exception.status, 503)
        with patch('server.services.local_demo.urlopen', return_value=BytesIO(json.dumps({
            'launch_url': '/?mock=1&ops=test&l=en', 'mode': 'generated'
        }).encode())) as upstream:
            result = handler.launch_game('buffalo-win', 'en')
            self.assertEqual(parse_qs(urlsplit(result['launch_url']).query)['l'], ['en'])
            self.assertEqual(json.loads(upstream.call_args.args[0].data)['language'], 'en')
        with self.assertRaises(ServiceError) as error:
            handler.launch_game('buffalo-win', 'xx')
        self.assertEqual(error.exception.code, 'LANGUAGE_INVALID')


class BuffaloPreviewTests(unittest.TestCase):
    def setUp(self):
        self.http = build_server(0)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.http.server_port}'

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()

    def request(self, path, payload=None, token=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['X-Local-Preview-Session'] = token
        req = Request(self.base + path, data=None if payload is None else json.dumps(payload).encode(), headers=headers)
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.read(), response.headers

    def test_preview_session_and_no_settlement(self):
        status, body, headers = self.request('/api/v1/games/buffalo-win/launch', {'language': 'zh'})
        self.assertEqual(status, 201)
        self.assertEqual(headers['X-Game-Engine'], 'frontend-preview')
        result = json.loads(body)
        self.assertEqual(result['mode'], 'frontend-preview')
        token = parse_qs(urlsplit(result['launch_url']).query)['ops'][0]
        route = '/game-api/buffalo-win/v2/GameInfo/Get'
        self.assertEqual(self.request(route, {}, 'invalid')[0], 401)
        status, initial, _ = self.request(route, {}, token)
        self.assertEqual(status, 200)
        status, body, _ = self.request('/game-api/buffalo-win/v2/Spin', {}, token)
        self.assertEqual(status, 501)
        self.assertEqual(json.loads(body)['err']['cd'], 'PREVIEW_ONLY')
        self.assertEqual(self.request(route, {}, token)[1], initial)
        self.assertFalse(hasattr(self.http, 'service'))
        self.assertEqual(self.request('/api/v1/games/buffalo-win/launch', {'language': 'en'})[0], 400)

    def test_private_fixtures_blocked_and_entry_localized(self):
        for path in ('/fixtures/auth-metadata.json', '/fixtures/spin-samples.json', '/fixtures/'):
            self.assertEqual(self.request(path)[0], 404)
        status, body, _ = self.request('/')
        self.assertEqual(status, 200)
        self.assertIn(b'<script src="/local-preview.js">', body)
        self.assertIn(b"xt=new URL(i,location.href).href", body)


if __name__ == '__main__':
    unittest.main()
