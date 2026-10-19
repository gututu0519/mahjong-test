import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

from server.adapters.pg.captains_bounty import SALT, SCHEMA
from server.adapters.pg.protocol import unpack
from server.adapters.pg.wire import decode
from server.services.captains_bounty_demo import build_server
from server.tests.test_captains_bounty import binary_request


class CaptainsBountyHttpTests(unittest.TestCase):
    def test_original_lowercase_spin_launch_history_and_private_asset_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            http = build_server(0, Path(folder) / 'http.sqlite3')
            thread = threading.Thread(target=http.serve_forever, daemon=True)
            thread.start()
            base = 'http://127.0.0.1:' + str(http.server_port)

            def post(path, body, token=None, mime='application/octet-stream'):
                headers = {'Content-Type': mime}
                if token:
                    headers['X-Local-Game-Session'] = token
                with urlopen(Request(base + path, data=body, headers=headers), timeout=5) as response:
                    return response.read()

            try:
                launch = json.loads(post('/api/v1/games/captains-bounty/launch', b'{"language":"zh"}', mime='application/json'))
                token = parse_qs(urlsplit(launch['launch_url']).query)['ops'][0]
                self.assertEqual(launch['client_language'], 'en')
                auth = json.loads(post('/web-api/auth/session/v2/verifySession', b'', token))['dt']
                self.assertEqual(auth['gm'][0]['gid'], 54)
                self.assertEqual(auth['tk'], token)
                wire = post('/game-api/captains-bounty/v4/spin', binary_request(token), token)
                tx = decode(unpack(wire, 17, salt=SALT)[0], SCHEMA['transaction']['nested'])
                self.assertEqual(tx['tb'], 4)
                retry = post('/game-api/captains-bounty/v4/spin', binary_request(token, seed=29), token)
                self.assertEqual(unpack(wire, 17, salt=SALT)[0], unpack(retry, 29, salt=SALT)[0])
                history = json.loads(post('/web-api/game-proxy/v2/BetHistory/Get', b'gid=54', token))['dt']['bh']
                self.assertEqual(len(history), 1)
                self.assertEqual(history[0]['gtba'], 4)
                self.assertEqual(history[0]['gtwa'], tx.get('tw', 0))
                self.assertAlmostEqual(http.service.wallet(token)['balance_minor'] / 100,
                                       2000 - 4 + tx.get('tw', 0))
                with urlopen(base + '/54/index.html?mock=1', timeout=5) as response:
                    entry = response.read()
                self.assertIn(b'/local-bootstrap.js?v=', entry)
                # Every spelling of the original entry must retain local API
                # routing; directory/index resolution must not serve raw HTML.
                for path in ('/', '/54', '/54/', '/54/%69ndex.html'):
                    with self.subTest(entry=path), urlopen(base + path + '?mock=1&l=en', timeout=5) as response:
                        self.assertIn(b'/local-bootstrap.js?v=', response.read())
                for path in ('/fixtures/auth-metadata.json', '/fixtures/spin-evidence.json', '/54/assets/', '/README.md'):
                    with self.subTest(path=path):
                        with self.assertRaises(HTTPError) as error:
                            urlopen(base + path, timeout=5)
                        self.assertEqual(error.exception.code, 404)
            finally:
                http.shutdown()
                thread.join(timeout=5)
                http.server_close()


if __name__ == '__main__':
    unittest.main()
