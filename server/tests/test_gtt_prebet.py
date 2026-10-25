import concurrent.futures
import json
import secrets
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from server.core.contracts import ServiceError
from server.games.buffalo_win.engine import BuffaloWin
from server.merchant.admin import build_admin
from server.merchant.common import encode
from server.merchant.control import ControlStore, MerchantDirectory
from server.merchant.http import build_gateway, build_platform
from server.merchant.mock_wallet import MockWallet
from server.merchant.prebet import PreBetClient
from server.merchant.provider import MerchantService
from server.tests.test_gtt_merchant import configuration


class GTTPreBetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.control = ControlStore(self.root / 'control.sqlite3')
        config = configuration()
        for merchant in config['merchants'].values():
            merchant['currency'] = 'USD'
        self.control.migrate(config['merchants'])
        config['merchants'] = MerchantDirectory(self.control)
        self.config = config
        self.platform = build_platform(0, self.root / 'wallet.sqlite3', config)
        self.settings = {'enabled': True, 'url': f'http://127.0.0.1:{self.platform.server_port}/api/v1/callbacks/gtt/preBetDecision',
                         'operator_token': 'test-platform-operator', 'secret_key': 'test-platform-secret-' + 'a' * 40}
        self.control.save_merchant('system', {**self.control.merchant('alpha'),
            'wallet_url': f'http://127.0.0.1:{self.platform.server_port}', 'pre_payout': self.settings}, {'buffalo-win'})
        self.platform.wallet.bind_prebet_player('alpha', 'same-player', 'external-platform-alice')
        self.gateway = build_gateway(0, self.root / 'game.sqlite3', config, BuffaloWin())
        self.service = self.gateway.service
        self.admin = build_admin(0, self.control, self.service)
        self.servers = (self.platform, self.gateway, self.admin)
        self.threads = [threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True) for server in self.servers]
        for thread in self.threads:
            thread.start()

    def tearDown(self):
        for server, thread in zip(self.servers, self.threads):
            server.shutdown(); thread.join(); server.server_close()
        self.temp.cleanup()

    def launch(self, **payload):
        result = self.service.launch('alpha', {'player_id': 'same-player', 'external_username': 'external-platform-alice', **payload})
        return parse_qs(urlsplit(result['launch_url']).query)['ops'][0]

    def round(self, bounds, buy=False, restart=False):
        self.platform.wallet.prebet_policy('alpha', bounds)
        token = self.launch()
        previous, total, debit, root = '0', 0, 0, None
        for index in range(256):
            bet = {'coin_minor': 2, 'level': 1, **({'buy_free': True} if buy and index == 0 else {})}
            result = self.service.spin(token, 'buffalo-win', 'step-' + str(index), previous, bet)
            self.assertEqual(self.service.spin(token, 'buffalo-win', 'step-' + str(index), previous, bet), result)
            root = root or result['round_id']
            self.assertEqual(result['round_id'], root)
            total += result['wallet']['credit_minor']; debit += result['wallet']['debit_minor']
            previous = result['sid']
            if restart and index == 0:
                self.service = MerchantService(self.root / 'game.sqlite3', self.config['merchants'], BuffaloWin())
            if result['outcome']['next_phase'] == 'ready':
                break
        else:
            self.fail('Round did not finish')
        self.assertEqual(debit, 1500 if buy else 20)
        self.assertEqual(self.service.wallet(token)['balance_minor'], 200000 - debit + total)
        with self.platform.wallet.connection() as db:
            rows = db.execute('SELECT * FROM prebet_decisions').fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['player_name'], 'external-platform-alice')
        self.assertEqual(rows[0]['bet_amount_minor'], debit)
        self.assertEqual(rows[0]['type'], 'BUY_FREE_SPIN' if buy else 'NORMAL')
        with self.service.connection() as db:
            record = db.execute('SELECT * FROM prebet_rounds').fetchone()
        plan = json.loads(record['plan_json'])
        self.assertEqual(plan['total_credit_minor'], total)
        self.assertEqual(plan['basis_minor'], debit)
        self.assertNotIn(self.settings['secret_key'], record['prebet_request_json'])
        self.assertNotIn('plan_json', encode(self.service.state(token, 'buffalo-win')))
        return total, debit, plan

    def test_zero_payout_normal_and_purchased_free_preserve_features(self):
        # Separate instances ensure each case starts with its own round/account.
        total, debit, plan = self.round([0, 0], buy=True, restart=True)
        self.assertEqual(total, 0)
        self.assertGreaterEqual(sum(step['candidate']['event']['phase'] == 'free_start' for step in plan['steps']), 10)
        self.assertTrue(plan['steps'][0]['candidate']['event']['bought_feature'])

    def test_zero_payout_normal(self):
        self.assertEqual(self.round([0, 0])[0], 0)

    def test_random_range_caps_complete_normal_round(self):
        total, debit, _ = self.round([-1, 10], restart=True)
        self.assertLessEqual(total, 10 * debit)

    def test_random_range_caps_complete_purchase(self):
        total, debit, _ = self.round([-1, 10], buy=True)
        self.assertLessEqual(total, 10 * debit)

    def test_guaranteed_five_to_ten_paid(self):
        total, debit, _ = self.round([5, 10])
        self.assertLessEqual(5 * debit, total); self.assertLessEqual(total, 10 * debit)

    def test_guaranteed_five_to_ten_purchase(self):
        total, debit, _ = self.round([5, 10], buy=True, restart=True)
        self.assertLessEqual(5 * debit, total); self.assertLessEqual(total, 10 * debit)

    def test_unlimited_sentinel_is_not_zero_cap(self):
        original = secrets.token_hex
        with patch('server.merchant.prebet.secrets.token_hex', side_effect=lambda size: ('1' * 64) if size == 32 else original(size)):
            total, _, plan = self.round([-1, 0], buy=True)
        self.assertGreater(total, 0)
        self.assertEqual(plan['attempts'], 1)

    def test_exact_range_and_fractional_precision(self):
        # Pin planning seeds so an exact range cannot make this test probabilistic.
        counter = iter(range(100000))
        original = secrets.token_hex
        with patch('server.merchant.prebet.secrets.token_hex', side_effect=lambda size: str(next(counter)) if size == 32 else original(size)):
            total, debit, _ = self.round([10, 10])
        self.assertEqual(total, 10 * debit)

    def test_fractional_multiplier_range(self):
        total, debit, _ = self.round([.9, 1.1])
        self.assertGreaterEqual(total * 10, debit * 9)
        self.assertLessEqual(total * 10, debit * 11)

    def test_prebet_settings_validation_retains_private_credentials(self):
        before = self.control.merchant('alpha')
        for url in ('http://remote.example/preBetDecision', 'https://user:key@example.com/api', 'https://example.com/api?secret=x'):
            with self.assertRaises(ServiceError):
                self.control.save_merchant('system', {**before, 'pre_payout': {**before['pre_payout'], 'url': url}}, {'buffalo-win'})
        self.assertEqual(self.control.merchant('alpha')['version'], before['version'])
        saved = self.control.save_merchant('system', before, {'buffalo-win'})['merchant']
        self.assertTrue(saved['pre_payout']['credentials_configured'])
        private = self.control.merchant('alpha', private=True)['pre_payout']
        self.assertEqual(private['operator_token'], self.settings['operator_token'])
        self.assertEqual(private['secret_key'], self.settings['secret_key'])
        with self.assertRaises(ServiceError) as error:
            self.control.save_merchant('system', {**self.control.merchant('beta'), 'pre_payout': {'enabled': True, 'url': self.settings['url']}}, {'buffalo-win'})
        self.assertEqual(error.exception.code, 'PREBET_CONFIG_INVALID')

    def test_lost_decision_reply_survives_draft_schema_migration_and_restart(self):
        token = self.launch()
        client = self.service.prebet.client
        opener = client.opener.open
        bodies = []
        def lose_response(request, **kwargs):
            bodies.append(json.loads(request.data))
            with opener(request, **kwargs) as response:
                response.read()
            raise URLError('simulated response loss')
        with patch.object(client.opener, 'open', side_effect=lose_response):
            with self.assertRaises(ServiceError) as error:
                self.service.spin(token, 'buffalo-win', 'lost', '0', {'coin_minor': 2, 'level': 1})
        self.assertEqual(error.exception.code, 'PREBET_UNCERTAIN')
        with self.service.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM game_operations').fetchone()[0], 0)
            request = json.loads(db.execute('SELECT prebet_request_json FROM prebet_rounds').fetchone()[0])
        self.assertEqual(self.service.wallet(token)['balance_minor'], 200000)
        # Simulate an accepted decision from the previous, incorrectly named
        # draft. Migration must keep its deduplication tuple and credentials.
        with self.control.connection(True) as db:
            db.execute('ALTER TABLE merchant_prebet_settings RENAME TO merchant_fp_settings')
        with self.platform.wallet.connection(True) as db:
            for old, new in (('prebet_players', 'fp_players'), ('prebet_policies', 'fp_policies'), ('prebet_decisions', 'fp_decisions')):
                db.execute('ALTER TABLE ' + old + ' RENAME TO ' + new)
        with self.service.connection(True) as db:
            db.execute('ALTER TABLE prebet_rounds RENAME COLUMN prebet_request_json TO fp_request_json')
        self.control = ControlStore(self.root / 'control.sqlite3')
        self.config['merchants'] = MerchantDirectory(self.control)
        self.assertEqual(self.control.merchant('alpha', private=True)['pre_payout'], self.settings | {
            'credentials_configured': True,
            'credentials_fingerprint': self.control.merchant('alpha')['pre_payout']['credentials_fingerprint']})
        self.platform.wallet = MockWallet(self.root / 'wallet.sqlite3', self.config['merchants'])
        self.service = MerchantService(self.root / 'game.sqlite3', self.config['merchants'], BuffaloWin())
        next_open = self.service.prebet.client.opener.open
        def capture(request, **kwargs):
            bodies.append(json.loads(request.data)); return next_open(request, **kwargs)
        with patch.object(self.service.prebet.client.opener, 'open', side_effect=capture):
            self.service.spin(token, 'buffalo-win', 'lost', '0', {'coin_minor': 2, 'level': 1})
        self.assertEqual(bodies[0], bodies[1])
        self.assertEqual(request, {k: bodies[0][k] for k in ('player_name', 'timestamp', 'bet_amount', 'type')})
        with self.platform.wallet.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM prebet_decisions').fetchone()[0], 1)

    def test_concurrent_retry_and_policy_changes_do_not_redraw_decision(self):
        self.platform.wallet.prebet_policy('alpha', [0, 0])
        token = self.launch()
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: self.service.spin(token, 'buffalo-win', 'same-key', '0', {'coin_minor': 2, 'level': 1}), range(12)))
        self.assertTrue(all(value == results[0] for value in results))
        self.platform.wallet.prebet_policy('alpha', [5, 10])
        self.assertEqual(self.service.spin(token, 'buffalo-win', 'same-key', '0', {'coin_minor': 2, 'level': 1}), results[0])
        with self.platform.wallet.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM prebet_decisions').fetchone()[0], 1)
        with self.service.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM game_operations').fetchone()[0], 1)

    def test_lost_wallet_commits_preserve_the_entire_preplanned_round(self):
        self.platform.wallet.prebet_policy('alpha', [5, 10])
        token = self.launch()
        delegate = self.service.wallet_client
        class LostReply:
            action = 'debit'
            def call(self, merchant_id, action, payload):
                result = delegate.call(merchant_id, action, payload)
                if action == self.action:
                    self.action = None
                    raise ServiceError('WALLET_UNCERTAIN', 'reply lost after commit', 503)
                return result
        fault = LostReply()
        self.service.wallet_client = fault
        with self.assertRaises(ServiceError):
            self.service.spin(token, 'buffalo-win', 'wallet-0', '0', {'coin_minor': 2, 'level': 1})
        with self.service.connection() as db:
            plan_before = db.execute('SELECT plan_json FROM prebet_rounds').fetchone()[0]
        self.service = MerchantService(self.root / 'game.sqlite3', self.config['merchants'], BuffaloWin())
        fault.action = 'credit'
        self.service.wallet_client = fault
        sid, total = '0', 0
        for index in range(256):
            try:
                result = self.service.spin(token, 'buffalo-win', 'wallet-' + str(index), sid, {'coin_minor': 2, 'level': 1})
            except ServiceError as error:
                self.assertEqual(error.code, 'WALLET_UNCERTAIN')
                result = self.service.spin(token, 'buffalo-win', 'wallet-' + str(index), sid, {'coin_minor': 2, 'level': 1})
            sid = result['sid']; total += result['wallet']['credit_minor']
            if result['outcome']['next_phase'] == 'ready':
                break
        self.assertGreaterEqual(total, 100); self.assertLessEqual(total, 200)
        self.assertEqual(self.service.wallet(token)['balance_minor'], 200000 - 20 + total)
        with self.service.connection() as db:
            self.assertEqual(db.execute('SELECT plan_json FROM prebet_rounds').fetchone()[0], plan_before)
        with self.platform.wallet.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM prebet_decisions').fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM transactions WHERE kind='debit'").fetchone()[0], 1)

    def test_invalid_response_and_unreachable_range_never_debit(self):
        token = self.launch()
        for bounds in ([True, 10], [2, 1], [-2, 10], [0], [0, 'NaN']):
            with patch.object(self.platform.wallet, 'prebet_decision', return_value={'code': 0, 'data': {'maxWinMulti': bounds}, 'msg': None}):
                with self.assertRaises(ServiceError) as error:
                    self.service.spin(token, 'buffalo-win', 'invalid', '0', {'coin_minor': 2, 'level': 1})
                self.assertEqual(error.exception.code, 'PREBET_RANGE_INVALID')
        self.platform.wallet.prebet_policy('alpha', [.001, .001])
        with self.assertRaises(ServiceError) as error:
            self.service.spin(token, 'buffalo-win', 'invalid', '0', {'coin_minor': 2, 'level': 1})
        self.assertEqual(error.exception.code, 'PREBET_RANGE_UNREACHABLE')
        self.assertEqual(self.service.wallet(token)['balance_minor'], 200000)
        with self.service.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM game_operations').fetchone()[0], 0)

    def test_business_codes_credentials_alias_and_no_secret_disclosure(self):
        with self.assertRaises(ServiceError) as error:
            self.service.launch('alpha', {'player_id': 'same-player'})
        self.assertEqual(error.exception.code, 'PREBET_PLAYER_REQUIRED')
        token = self.launch(prebet_type='SURE_WIN')
        payload = {'player_name': 'external-platform-alice', 'timestamp': 1792886400000, 'bet_amount': '1.00', 'type': 'NORMAL'}
        with self.assertRaises(ServiceError) as invalid:
            PreBetClient().decision({**self.settings, 'secret_key': 'wrong'}, payload)
        self.assertEqual(invalid.exception.code, 'PREBET_1204')
        self.assertNotIn('wrong', str(invalid.exception))
        # The callback uses main currency units, never cents.
        with patch.object(self.platform.wallet, 'prebet_decision', return_value={'code': 3202, 'data': None, 'msg': self.settings['secret_key']}):
            with self.assertRaises(ServiceError) as rejected:
                self.service.spin(token, 'buffalo-win', 'rejected', '0', {'coin_minor': 2, 'level': 1})
        self.assertEqual(rejected.exception.code, 'PREBET_3202')
        self.assertNotIn(self.settings['secret_key'], str(rejected.exception))
        self.service.spin(token, 'buffalo-win', 'affordable', '0', {'coin_minor': 2, 'level': 1})
        with self.service.connection() as db:
            rows = db.execute('SELECT prebet_request_json FROM prebet_rounds ORDER BY rowid').fetchall()
        self.assertEqual(len(rows), 2)
        self.assertGreater(json.loads(rows[1][0])['timestamp'], json.loads(rows[0][0])['timestamp'])
        self.assertEqual(json.loads(rows[1][0])['type'], 'SURE_WIN')
        public = encode(self.control.merchants()) + encode(self.control.audits({})) + encode(self.admin.app.prebet_decisions({}))
        self.assertNotIn(self.settings['operator_token'], public)
        self.assertNotIn(self.settings['secret_key'], public)
        self.assertNotIn('candidate', public)


if __name__ == '__main__':
    unittest.main()
