import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from server.games.catalog import create_registry
from server.services.game_api import build_server


class ServiceBoundaryTests(unittest.TestCase):
    def test_api_process_does_not_import_legacy_client_or_provider(self):
        code = '''
import sys
from server.services.game_api import build_server
from server.games.catalog import create_registry
create_registry()
assert 'serve_local' not in sys.modules
assert 'local_spin' not in sys.modules
assert not any(k.startswith('server.adapters.') for k in sys.modules)
'''
        subprocess.run([sys.executable, '-c', code], check=True,
                       cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True)

    def test_catalog_selection_and_classification(self):
        game = create_registry(['mahjong-ways2']).catalog()[0]
        self.assertEqual(game['category'], 'slots')
        self.assertEqual(game['interaction'], 'request_steps')
        self.assertIn('free_retrigger', game['features'])
        for selected in ([], ['unknown'], ['mahjong-ways2', 'mahjong-ways2']):
            with self.assertRaises(ValueError):
                create_registry(selected)
        with self.assertRaises(ValueError):
            create_registry(configs={'unknown': 'missing.json'})

    def test_api_only_routes_and_settlement(self):
        with tempfile.TemporaryDirectory() as directory:
            with build_server(0, Path(directory) / 'api.sqlite3') as http:
                thread = threading.Thread(target=http.serve_forever, daemon=True)
                thread.start()
                base = f'http://127.0.0.1:{http.server_port}'

                def request(path, payload=None, headers=None):
                    data = None if payload is None else json.dumps(payload).encode()
                    req = Request(base + path, data=data, headers={
                        'Content-Type': 'application/json', **(headers or {})})
                    try:
                        with urlopen(req, timeout=5) as response:
                            return response.status, json.load(response)
                    except HTTPError as error:
                        with error:
                            return error.code, json.load(error)

                try:
                    self.assertEqual(request('/health')[0], 200)
                    for path in ('/', '/local-auth-bootstrap.js', '/fixtures/spin-rounds.json'):
                        self.assertEqual(request(path)[0], 404)
                    self.assertEqual(request('/game-api/74/v4/Spin', {})[0], 404)
                    self.assertEqual(request('/api/v1/wallet', headers={
                        'Authorization': 'Bearer local-demo-session'})[0], 401)
                    status, session = request('/api/v1/sessions', {})
                    self.assertEqual(status, 201)
                    headers = {'Authorization': 'Bearer ' + session['token'],
                               'Idempotency-Key': 'independent-api'}
                    payload = {'previous_sid': '0', 'bet': {'coin_minor': 1, 'level': 5}}
                    status, result = request('/api/v1/games/mahjong-ways2/spin', payload, headers)
                    self.assertEqual(status, 200)
                    self.assertEqual(request('/api/v1/games/mahjong-ways2/spin', payload, headers)[1], result)
                    self.assertEqual(request('/api/v1/wallet', headers=headers)[1]['balance_minor'],
                                     result['wallet']['after_minor'])
                finally:
                    http.shutdown()
                    thread.join()
