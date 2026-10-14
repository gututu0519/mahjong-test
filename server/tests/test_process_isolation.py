"""Real processes, private configuration/data, and independent restart behavior."""
import json
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]


class ProcessIsolationTests(unittest.TestCase):
    def test_separate_processes_accounts_config_and_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            processes = []

            def start(directory):
                log = directory / 'logs/service.log'
                offset = log.stat().st_size if log.exists() else 0
                process = subprocess.Popen(
                    [sys.executable, '-m', 'server.run', '--service-dir', str(directory), '--port', '0'],
                    cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                processes.append(process)
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    self.assertIsNone(process.poll(), 'Service exited during startup')
                    if log.exists():
                        with log.open('rb') as stream:
                            stream.seek(offset)
                            match = re.search(rb'listening on http://localhost:(\d+)', stream.read())
                        if match:
                            return process, 'http://127.0.0.1:' + match[1].decode()
                    time.sleep(.05)
                self.fail('Service startup timeout')

            def request(base, path, payload=None, token=None):
                headers = {'Content-Type': 'application/json', 'Idempotency-Key': 'one'}
                if token:
                    headers['Authorization'] = 'Bearer ' + token
                req = Request(base + path, data=None if payload is None else json.dumps(payload).encode(),
                              headers=headers)
                try:
                    with urlopen(req, timeout=5) as response:
                        return response.status, json.load(response)
                except HTTPError as error:
                    with error:
                        return error.code, json.load(error)

            directories = []
            for i in range(2):
                directory = Path(temporary) / f'service-{i}'
                (directory / 'config').mkdir(parents=True)
                (directory / 'service.json').write_text(json.dumps({
                    'id': f'service-{i}', 'entry': 'json_api', 'port': 8082 + i,
                    'games': ['mahjong-ways2']}), encoding='utf-8')
                config = json.loads((ROOT / 'server/games/mahjong_ways2/config.json').read_text())
                config['gold_probability'] = .08 + i * .01
                (directory / 'config/mahjong-ways2.json').write_text(json.dumps(config), encoding='utf-8')
                directories.append(directory)
            try:
                process_a, a = start(directories[0])
                _, b = start(directories[1])
                health_a = request(a, '/health')[1]
                health_b = request(b, '/health')[1]
                self.assertNotEqual(health_a['service_id'], health_b['service_id'])
                self.assertNotEqual(health_a['games'][0]['ruleset_id'], health_b['games'][0]['ruleset_id'])
                token_a = request(a, '/api/v1/sessions', {})[1]['token']
                token_b = request(b, '/api/v1/sessions', {})[1]['token']
                self.assertEqual(request(b, '/api/v1/wallet', token=token_a)[0], 401)
                path = '/api/v1/games/mahjong-ways2/spin'
                payload = {'previous_sid': '0', 'bet': {'coin_minor': 1, 'level': 5}}
                status, spin = request(a, path, payload, token_a)
                self.assertEqual(status, 200)
                self.assertEqual(request(b, '/api/v1/wallet', token=token_b)[1]['balance_minor'], 200000)
                process_a.terminate()
                process_a.wait(timeout=5)
                self.assertEqual(request(b, '/health')[0], 200)
                self.assertEqual(request(b, path, payload, token_b)[0], 200)
                _, a = start(directories[0])
                self.assertEqual(request(a, path, payload, token_a)[1], spin)
                for directory in directories:
                    self.assertTrue((directory / 'data/games.sqlite3').is_file())
                    self.assertTrue((directory / 'logs/service.log').is_file())
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.terminate()
                    process.wait(timeout=5)
