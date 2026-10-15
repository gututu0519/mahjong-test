"""Local client entry, authenticated history and connection-probe regression."""
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
from server.services.super_ace_demo import build_server, CLIENT
from server.adapters.jili.super_ace import pack


class SuperAceHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.http = build_server(0, Path(self.temp.name) / 'games.sqlite3')
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f'http://127.0.0.1:{self.http.server_port}'

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        self.temp.cleanup()

    def get(self, path, headers=None):
        return urlopen(Request(self.origin + path, headers=headers or {}), timeout=5)

    def test_entry_and_original_script_bytes(self):
        with self.get('/') as response:
            self.assertIn('ops', parse_qs(urlsplit(response.url).query))
            document = response.read().decode()
            self.assertIn('/local-adapter.js', document)
            self.assertIn('installSuperAceAdapter()', document)
        for name in ('astarte2/3.6/web-mobile/src/chunks/bundle.0c125.js',
                     'astarte2/3.6/web-mobile/assets/other/index.22b2c.js'):
            with self.get('/' + name) as response:
                self.assertEqual(response.read(), (CLIENT / name).read_bytes())

    def test_probe_does_not_create_or_disclose_session(self):
        with self.get('/fullhouse/', {'Sec-Fetch-Dest': 'empty'}) as response:
            self.assertEqual(response.status, 204)
            self.assertEqual(response.read(), b'')
        with self.assertRaises(HTTPError) as error:
            self.get('/fullhouse/')
        self.assertEqual(error.exception.code, 401)
        with self.http.service.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM players').fetchone()[0], 0)

    def test_rules_and_nonempty_history_keep_return_navigation(self):
        token = self.http.service.create_session()['token']
        self.http.jili.handle(token, 0, pack('SpinReq', {'bet': 0.5}), 'browser-spin')
        for path in ('/rules', '/history?ops=' + token):
            with self.get(path) as response:
                document = response.read().decode()
                self.assertIn('Back to game', document)
                self.assertIn('CloseWebView', document)
                if path.startswith('/history'):
                    self.assertIn('<td>0.5000</td>', document)
                    self.assertIn('<td>1</td>', document)
        with self.assertRaises(HTTPError) as error:
            self.get('/history')
        self.assertEqual(error.exception.code, 401)


if __name__ == '__main__':
    unittest.main()
