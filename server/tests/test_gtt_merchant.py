import concurrent.futures
import json
import io
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen
from unittest.mock import patch

from server.core.contracts import ServiceError
from server.merchant.common import encode, signed_headers
from server.merchant.http import build_gateway, build_platform
from server.merchant.mock_wallet import MockWallet
from server.merchant.provider import MerchantService
from server.merchant.wallet import WalletClient
from server.tests.test_buffalo_feature_buy import CapturedBuy, FIXTURE
from server.tests.test_buffalo_engine import Scripted


def configuration():
    merchant = {'enabled': True, 'api_secret': 'a' * 64, 'wallet_secret': 'w' * 64,
                'wallet_url': 'http://127.0.0.1:8111', 'currency': 'DEMO', 'minor_unit': 100,
                'games': ['buffalo-win']}
    return {'merchants': {'alpha': merchant, 'beta': {**merchant, 'api_secret': 'b' * 64, 'wallet_secret': 'v' * 64}},
            'gateway_origin': '', 'sandbox_merchant': 'alpha', 'sandbox_player': 'same-player',
            'sandbox_balance_minor': 200000}


def wallet_payload(transaction_id='test-debit', **extra):
    return {'player_id': 'same-player', 'currency': 'DEMO', 'minor_unit': 100,
            'transaction_id': transaction_id, 'round_id': 'round-1', 'amount_minor': 100, **extra}


class GTTWalletTests(unittest.TestCase):
    def test_atomic_dedupe_refund_tombstone_and_merchant_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            wallet = MockWallet(Path(directory) / 'wallet.sqlite3', configuration()['merchants'])
            for merchant in ('alpha', 'beta'):
                wallet.seed(merchant, 'same-player', 1000)
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda _: wallet.call('alpha', 'debit', wallet_payload()), range(16)))
            self.assertTrue(all(result == results[0] for result in results))
            self.assertEqual(results[0]['balance_minor'], 900)
            self.assertEqual(wallet.call('beta', 'balance', wallet_payload())['balance_minor'], 1000)
            with self.assertRaises(ServiceError) as conflict:
                wallet.call('alpha', 'debit', wallet_payload(amount_minor=101))
            self.assertEqual(conflict.exception.code, 'TRANSACTION_CONFLICT')
            refund = wallet_payload('refund-1', reference_id='test-debit')
            self.assertEqual(wallet.call('alpha', 'refund', refund)['balance_minor'], 1000)
            self.assertEqual(wallet.call('alpha', 'refund', refund)['balance_minor'], 1000)
            with self.assertRaises(ServiceError) as twice:
                wallet.call('alpha', 'refund', {**refund, 'transaction_id': 'refund-2'})
            self.assertEqual(twice.exception.code, 'ALREADY_REFUNDED')
            early = wallet_payload('early-refund', reference_id='late-debit')
            self.assertEqual(wallet.call('alpha', 'refund', early)['applied_minor'], 0)
            with self.assertRaises(ServiceError) as late:
                wallet.call('alpha', 'debit', wallet_payload('late-debit'))
            self.assertEqual(late.exception.code, 'TRANSACTION_CANCELED')
            with self.assertRaises(ServiceError):
                wallet.call('alpha', 'credit', wallet_payload('late-credit', reference_id='late-debit'))
            wallet.seed('alpha', 'same-player', 999999)
            self.assertEqual(wallet.call('alpha', 'balance', wallet_payload())['balance_minor'], 1000)
            restarted = MockWallet(Path(directory) / 'wallet.sqlite3', configuration()['merchants'])
            self.assertEqual(restarted.call('alpha', 'refund', refund)['balance_minor'], 1000)

    def test_rejected_debit_stays_rejected_and_refund_cannot_undo_paid_round(self):
        with tempfile.TemporaryDirectory() as directory:
            wallet = MockWallet(Path(directory) / 'wallet.sqlite3', configuration()['merchants'])
            wallet.seed('alpha', 'same-player', 50)
            for _ in range(2):
                with self.assertRaises(ServiceError) as error:
                    wallet.call('alpha', 'debit', wallet_payload())
                self.assertEqual(error.exception.code, 'INSUFFICIENT_BALANCE')
            wallet.call('alpha', 'debit', wallet_payload('small', amount_minor=10))
            wallet.call('alpha', 'credit', wallet_payload('win', reference_id='small', amount_minor=20))
            with self.assertRaises(ServiceError) as error:
                wallet.call('alpha', 'refund', wallet_payload('refund', reference_id='small', amount_minor=10))
            self.assertEqual(error.exception.code, 'REFERENCE_INVALID')
            self.assertEqual(wallet.call('alpha', 'balance', wallet_payload())['balance_minor'], 60)


class GTTHTTPTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.config = configuration()
        self.platform = build_platform(0, self.root / 'platform.sqlite3', self.config)
        for merchant in self.config['merchants'].values():
            merchant['wallet_url'] = 'http://127.0.0.1:' + str(self.platform.server_port)
        self.platform.wallet.seed('beta', 'same-player', 200000)
        self.game = CapturedBuy()
        self.gateway = build_gateway(0, self.root / 'provider.sqlite3', self.config, self.game)
        self.config['gateway_origin'] = 'http://127.0.0.1:' + str(self.gateway.server_port)
        self.threads = [threading.Thread(target=http.serve_forever, daemon=True) for http in (self.platform, self.gateway)]
        for thread in self.threads:
            thread.start()

    def tearDown(self):
        for http, thread in zip((self.platform, self.gateway), self.threads):
            http.shutdown()
            thread.join()
            http.server_close()
        self.directory.cleanup()

    def request(self, path, payload=None, merchant='alpha', raw=None, headers=None, port=None):
        body = raw if raw is not None else encode(payload or {}).encode()
        port = self.gateway.server_port if port is None else port
        if headers is None:
            headers = signed_headers(merchant, self.config['merchants'][merchant]['api_secret'], path, body)
        request = Request(f'http://127.0.0.1:{port}' + path, data=body, headers=headers)
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def test_auth_tampering_replay_disabled_access_and_json_validation(self):
        path = '/gtt/v1/games/list'
        body = b'{}'
        headers = signed_headers('alpha', self.config['merchants']['alpha']['api_secret'], path, body)
        self.assertEqual(self.request(path, raw=b'{"changed":1}', headers=headers)[0], 401)
        self.assertEqual(self.request(path, raw=body, headers=headers)[0], 200)
        self.assertEqual(self.request(path, raw=body, headers=headers)[1]['error']['code'], 'AUTH_REPLAY')
        expired = signed_headers('alpha', self.config['merchants']['alpha']['api_secret'], path, body, timestamp=1000000000)
        self.assertEqual(self.request(path, headers=expired)[0], 401)
        self.assertEqual(self.request(path, raw=b'{"x":1,"x":2}')[0], 400)
        self.assertEqual(self.request(path, raw=b'{"x":NaN}')[0], 400)
        self.assertEqual(self.request('/api/v1/sessions', headers={'Content-Type': 'application/json'})[0], 401)
        self.config['merchants']['beta']['enabled'] = False
        self.assertEqual(self.request(path, merchant='beta')[0], 401)
        self.config['merchants']['beta']['enabled'] = True
        self.config['merchants']['beta']['games'] = []
        self.assertEqual(self.request('/gtt/v1/games/launch', {'player_id': 'same-player'}, merchant='beta')[0], 403)

    def test_original_buy_complete_external_wallet_and_reconciliation(self):
        status, catalog = self.request('/gtt/v1/games/list')
        self.assertEqual(status, 200)
        self.assertIsNone(catalog['data']['games'][0]['target_rtp'])
        status, launch = self.request('/gtt/v1/games/launch', {'player_id': 'same-player'})
        self.assertEqual(status, 201)
        token = parse_qs(urlsplit(launch['data']['launch_url']).query)['ops'][0]
        with patch('server.merchant.http.logging.info') as log:
            with urlopen(self.config['gateway_origin'] + launch['data']['launch_url'], timeout=5) as response:
                self.assertEqual(response.status, 200)
            messages = str(log.call_args_list)
            self.assertNotIn(token, messages)
            self.assertIn('[redacted]', messages)
        api_headers = {'Content-Type': 'application/x-www-form-urlencoded', 'X-Local-Game-Session': token}
        previous = '0'
        fixture = json.loads(FIXTURE.read_bytes())
        for case in fixture['spins']:
            self.game.case = case
            body = urlencode({'id': previous, 'btt': 2, 'wk': '0_C', 'pf': 1, **case['request']}).encode()
            status, result = self.request('/game-api/buffalo-win/v2/Spin', raw=body, headers=api_headers)
            self.assertEqual(status, 200, result)
            tx = result['dt']['si']
            self.assertEqual(tx['fs'], case['si'].get('fs'))
            self.assertEqual(tx['tb'], case['si']['tb'])
            self.assertEqual(tx['tw'], case['si']['tw'])
            self.assertEqual(self.request('/game-api/buffalo-win/v2/Spin', raw=body, headers=api_headers)[1], result)
            previous = tx['sid']
        self.assertEqual(self.gateway.service.wallet(token)['balance_minor'], 200196)
        self.assertEqual(self.platform.wallet.call('alpha', 'balance', wallet_payload())['balance_minor'], 200196)
        self.assertEqual(self.platform.wallet.call('beta', 'balance', wallet_payload())['balance_minor'], 200000)
        _, transactions = self.request('/gtt/v1/transactions/list', {'limit': 100})
        operations = transactions['data']['operations']
        self.assertEqual(len(operations), 25)
        self.assertTrue(all(op['status'] == 'settled' for op in operations))
        operation_id = operations[0]['operation_id']
        self.assertEqual(self.request('/gtt/v1/transactions/retry', {'operation_id': operation_id})[0], 200)
        self.assertEqual(self.request('/gtt/v1/transactions/retry', {'operation_id': operation_id}, merchant='beta')[0], 404)
        with self.platform.wallet.connection() as db:
            rows = db.execute('SELECT kind,response_json FROM transactions WHERE merchant_id=?', ('alpha',)).fetchall()
        self.assertEqual(sum(json.loads(row['response_json'])['amount_minor'] for row in rows if row['kind'] == 'debit'), 1500)
        self.assertEqual(sum(json.loads(row['response_json'])['amount_minor'] for row in rows if row['kind'] == 'credit'), 1696)
        self.assertEqual(len(rows), 5)  # one purchase debit plus four free-spin credits

    def test_lost_debit_and_credit_replies_recover_without_regeneration(self):
        class LostReply:
            def __init__(self, delegate):
                self.delegate, self.action = delegate, None

            def call(self, merchant_id, action, payload):
                result = self.delegate.call(merchant_id, action, payload)
                if action == self.action:
                    self.action = None
                    raise ServiceError('WALLET_UNCERTAIN', 'Injected reply loss after platform commit.', 503)
                return result

        game = Scripted([([3, 2, 2, 2] * 3, 3, {}, {})], [[2] * 4])
        service = MerchantService(self.root / 'fault.sqlite3', self.config['merchants'], game)
        launch = service.launch('alpha', {'player_id': 'same-player'})
        token = parse_qs(urlsplit(launch['launch_url']).query)['ops'][0]
        fault = LostReply(WalletClient(self.config['merchants']))
        service.wallet_client = fault
        fault.action = 'debit'
        with self.assertRaises(ServiceError) as unknown:
            service.spin(token, 'buffalo-win', 'paid', '0', {})
        self.assertEqual(unknown.exception.code, 'WALLET_UNCERTAIN')
        with service.connection() as db:
            pending = db.execute('SELECT id,candidate_json FROM game_operations').fetchone()
        candidate = pending['candidate_json']
        with self.assertRaises(ServiceError) as blocked:
            service.spin(token, 'buffalo-win', 'different-request', '0', {})
        self.assertEqual(blocked.exception.code, 'OPERATION_PENDING')
        self.assertEqual(service.wallet(token)['balance_minor'], 199400)
        # New service instance simulates restart while the debit outcome is unknown.
        service = MerchantService(self.root / 'fault.sqlite3', self.config['merchants'], game)
        first = service.spin(token, 'buffalo-win', 'paid', '0', {})
        self.assertEqual(first['wallet']['debit_minor'], 600)
        with service.connection() as db:
            self.assertEqual(db.execute('SELECT candidate_json FROM game_operations WHERE id=?', (pending['id'],)).fetchone()[0], candidate)
        service.wallet_client = fault
        fault.action = 'credit'
        with self.assertRaises(ServiceError):
            service.spin(token, 'buffalo-win', 'extension', first['sid'], {})
        self.assertEqual(service.wallet(token)['balance_minor'], 201200)
        service = MerchantService(self.root / 'fault.sqlite3', self.config['merchants'], game)
        # GameInfo/state refresh also recovers the pending payout.
        restored = service.state(token, 'buffalo-win')
        self.assertEqual(restored['state']['phase'], 'ready')
        final = service.spin(token, 'buffalo-win', 'extension', first['sid'], {})
        self.assertEqual(final['wallet']['credit_minor'], 1800)
        self.assertEqual(service.wallet(token)['balance_minor'], 201200)

    def test_malformed_success_after_remote_commit_stays_pending(self):
        game = Scripted()
        service = MerchantService(self.root / 'malformed.sqlite3', self.config['merchants'], game)
        launch = service.launch('alpha', {'player_id': 'same-player'})
        token = parse_qs(urlsplit(launch['launch_url']).query)['ops'][0]
        client = service.wallet_client
        original_open = client.opener.open

        class Response(io.BytesIO):
            status = 200

        def corrupt_response(request, **kwargs):
            with original_open(request, **kwargs) as response:
                data = json.load(response)
            data['data']['balance_minor'] = True
            return Response(encode(data).encode())

        with patch.object(client.opener, 'open', side_effect=corrupt_response):
            with self.assertRaises(ServiceError) as error:
                service.spin(token, 'buffalo-win', 'malformed', '0', {})
        self.assertEqual(error.exception.code, 'WALLET_UNCERTAIN')
        with service.connection() as db:
            self.assertEqual(db.execute('SELECT status FROM game_operations').fetchone()[0], 'prepared')
        self.assertEqual(service.wallet(token)['balance_minor'], 199400)
        restored = MerchantService(self.root / 'malformed.sqlite3', self.config['merchants'], game)
        self.assertEqual(restored.spin(token, 'buffalo-win', 'malformed', '0', {})['wallet']['after_minor'], 199400)

    def test_concurrent_provider_retry_generates_once_and_insufficient_buy_does_not_advance(self):
        class CountingGame(Scripted):
            steps = 0

            def step(self, *args):
                self.steps += 1
                return super().step(*args)

        game = CountingGame()
        service = MerchantService(self.root / 'concurrent.sqlite3', self.config['merchants'], game)
        launch = service.launch('alpha', {'player_id': 'same-player'})
        token = parse_qs(urlsplit(launch['launch_url']).query)['ops'][0]
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: service.spin(token, 'buffalo-win', 'same-request', '0', {}), range(12)))
        self.assertEqual(game.steps, 1)
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(service.wallet(token)['balance_minor'], 199400)
        self.platform.wallet.seed('alpha', 'poor-player', 1499)
        poor_launch = service.launch('alpha', {'player_id': 'poor-player'})
        poor = parse_qs(urlsplit(poor_launch['launch_url']).query)['ops'][0]
        before = service.state(poor, 'buffalo-win')
        for _ in range(2):
            with self.assertRaises(ServiceError) as error:
                service.spin(poor, 'buffalo-win', 'unaffordable', '0', {'cs': 0.02, 'ml': 1, 'buy_free': True})
            self.assertEqual(error.exception.code, 'INSUFFICIENT_BALANCE')
        self.assertEqual(before, service.state(poor, 'buffalo-win'))


if __name__ == '__main__':
    unittest.main()
