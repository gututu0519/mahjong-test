import concurrent.futures
import hashlib
import json
import secrets
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
from unittest.mock import patch

from server.core.contracts import ServiceError
from server.merchant.admin import build_admin
from server.merchant.common import encode, signed_headers
from server.merchant.control import ControlStore, MerchantDirectory
from server.merchant.http import build_gateway, build_platform
from server.merchant.sandbox import initialize, load_config
from server.tests.test_buffalo_engine import Scripted
from server.tests.test_gtt_merchant import configuration, wallet_payload


PASSWORD = 'A-test-password-only-123!'


class GTTAdminTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.control = ControlStore(self.root / 'merchants.sqlite3')
        self.config = configuration()
        self.control.migrate(self.config['merchants'])
        self.config['merchants'] = MerchantDirectory(self.control)
        self.platform = build_platform(0, self.root / 'wallet.sqlite3', self.config)
        for merchant in self.control.merchants():
            self.control.save_merchant('system', {**merchant, 'wallet_url': 'http://127.0.0.1:' + str(self.platform.server_port)}, {'buffalo-win'})
        self.gateway = build_gateway(0, self.root / 'game.sqlite3', self.config, Scripted())
        self.service = self.gateway.service
        self.admin = build_admin(0, self.control, self.service)
        self.servers = (self.platform, self.gateway, self.admin)
        self.threads = [threading.Thread(target=http.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True) for http in self.servers]
        for thread in self.threads:
            thread.start()
        for name, role in (('admin', 'admin'), ('operator', 'operator'), ('viewer', 'viewer')):
            self.control.create_user('system', name, role, PASSWORD)
        self.sessions = {}

    def tearDown(self):
        for http, thread in zip(self.servers, self.threads):
            http.shutdown()
            thread.join()
            http.server_close()
        self.directory.cleanup()

    def request(self, path, payload=None, user='admin', headers=None, method='POST', port=None):
        port = port or self.admin.server_port
        data = None if method == 'GET' else encode(payload or {}).encode()
        fields = {'Content-Type': 'application/json'}
        if user in self.sessions:
            cookie, session = self.sessions[user]
            fields.update(Cookie=cookie, **{'X-GTT-CSRF': session['csrf_token']})
        fields.update(headers or {})
        request = Request(f'http://127.0.0.1:{port}' + path, data=data, headers=fields, method=method)
        try:
            response = urlopen(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            body = response.read()
            return response.status, json.loads(body) if 'application/json' in response.headers.get('Content-Type', '') else body, response.headers

    def login(self, name='admin'):
        code, result, headers = self.request('/api/admin/login', {'username': name, 'password': PASSWORD}, user=None)
        self.assertEqual(code, 200, result)
        self.sessions[name] = (headers['Set-Cookie'].split(';', 1)[0], result['data'])
        return result['data']

    def post(self, path, payload=None, user='admin', expected=200):
        if user not in self.sessions:
            self.login(user)
        code, result, _ = self.request('/api/admin/' + path, payload, user)
        self.assertEqual(code, expected, result)
        return result['data'] if expected < 400 else result['error']

    def gateway_request(self, secret=None, merchant='alpha'):
        path = '/gtt/v1/games/list'
        body = encode({}).encode()
        fields = signed_headers(merchant, secret or self.config['merchants'][merchant]['api_secret'], path, body)
        return self.request(path, {}, None, fields, port=self.gateway.server_port)

    def launch(self):
        launched = self.service.launch('alpha', {'player_id': 'same-player'})
        return parse_qs(urlsplit(launched['launch_url']).query)['ops'][0]

    def pending(self):
        token = self.launch()
        delegate = self.service.wallet_client

        class LostReply:
            def call(self, merchant_id, action, payload):
                result = delegate.call(merchant_id, action, payload)
                if action == 'debit':
                    raise ServiceError('WALLET_UNCERTAIN', 'reply lost', 503)
                return result

        self.service.wallet_client = LostReply()
        with self.assertRaises(ServiceError):
            self.service.spin(token, 'buffalo-win', 'pending-spin', '0', {})
        self.service.wallet_client = delegate
        with self.service.connection() as db:
            return dict(db.execute('SELECT * FROM game_operations').fetchone())

    def test_login_cookie_csrf_origin_host_and_logout(self):
        code, body, _ = self.request('/api/admin/me', method='GET')
        self.assertEqual(code, 401)
        code, body, headers = self.request('/api/admin/login', {'username': 'admin', 'password': PASSWORD}, user=None)
        self.assertEqual(code, 200)
        for flag in ('HttpOnly', 'SameSite=Strict', 'Max-Age=28800'):
            self.assertIn(flag, headers['Set-Cookie'])
        self.sessions['admin'] = (headers['Set-Cookie'].split(';', 1)[0], body['data'])
        self.assertEqual(self.request('/api/admin/overview', headers={'X-GTT-CSRF': ''})[0], 403)
        self.assertEqual(self.request('/api/admin/overview', headers={'Origin': 'https://elsewhere.example'})[0], 403)
        self.assertEqual(self.request('/api/admin/overview', headers={'Host': 'bad.example'})[0], 403)
        self.assertEqual(self.request('/api/admin/overview', headers={'Content-Type': 'text/plain'})[0], 415)
        self.assertEqual(self.request('/api/admin/overview?x=1')[0], 400)
        self.assertEqual(self.request('/api/admin/me', method='GET')[0], 200)
        self.post('logout')
        self.assertEqual(self.request('/api/admin/me', method='GET')[0], 401)

    def test_password_hash_lockout_and_session_expiration(self):
        for _ in range(5):
            self.assertEqual(self.request('/api/admin/login', {'username': 'admin', 'password': 'bad'}, user=None)[0], 401)
        self.assertEqual(self.request('/api/admin/login', {'username': 'admin', 'password': PASSWORD}, user=None)[0], 429)
        self.login('viewer')
        with self.control.connection(True) as db:
            user = db.execute("SELECT password_hash FROM admin_users WHERE username='viewer'").fetchone()[0]
            self.assertTrue(user.startswith('pbkdf2_sha256$600000$'))
            self.assertNotIn(PASSWORD, user)
            stored = db.execute('SELECT token_hash FROM admin_sessions').fetchone()[0]
            self.assertEqual(stored, hashlib.sha256(self.sessions['viewer'][0].split('=', 1)[1].encode()).hexdigest())
            db.execute('UPDATE admin_sessions SET last_seen=?', (int(time.time()) - 1801,))
        self.assertEqual(self.request('/api/admin/me', user='viewer', method='GET')[0], 401)
        self.login('viewer')
        with self.control.connection(True) as db:
            db.execute('UPDATE admin_sessions SET expires_at=?', (int(time.time()) - 1,))
        self.assertEqual(self.request('/api/admin/me', user='viewer', method='GET')[0], 401)

    def test_roles_are_enforced_by_api_not_only_buttons(self):
        for name in ('viewer', 'operator'):
            self.post('merchants/list', user=name)
            self.post('games', user=name)
            self.post('transactions/list', user=name)
            self.post('prebet/list', user=name)
            self.post('audit', user=name)
            for path in ('merchants/create', 'merchants/update', 'merchants/rotate', 'users/create', 'users/list', 'users/update', 'users/reset'):
                self.assertEqual(self.post(path, user=name, expected=403)['code'], 'FORBIDDEN')
        self.post('transactions/retry', user='viewer', expected=403)
        self.assertEqual(self.post('transactions/retry', user='operator', expected=400)['code'], 'INVALID_ARGUMENT')
        self.assertTrue(any(row['action'] == 'permission.denied' for row in self.control.audits({})))

    def test_merchant_create_live_authorization_rotation_and_no_secret_leaks(self):
        result = self.post('merchants/create', {'name': 'New Platform', 'enabled': True,
                           'wallet_url': 'http://127.0.0.1:' + str(self.platform.server_port), 'currency': 'USD', 'games': ['buffalo-win']}, expected=201)
        merchant_id = result['merchant']['id']
        self.assertRegex(merchant_id, r'^GTT[0-9A-F]{16}$')
        secret = result['keys']['api_secret']
        self.assertNotEqual(secret, result['keys']['wallet_secret'])
        self.platform.wallet.seed(merchant_id, 'new-player', 10000)
        self.assertEqual(self.gateway_request(merchant=merchant_id)[0], 200)
        # A second process/store connection sees updates without a service restart.
        second = MerchantDirectory(ControlStore(self.control.path))
        self.assertEqual(second[merchant_id]['api_secret'], secret)
        launched = self.service.launch(merchant_id, {'player_id': 'new-player'})
        self.assertEqual((launched['balance_minor'], launched['currency'], launched['minor_unit']), (10000, 'USD', 100))
        token = parse_qs(urlsplit(launched['launch_url']).query)['ops'][0]
        self.assertEqual(self.service.spin(token, 'buffalo-win', 'usd-paid', '0', {})['wallet']['after_minor'], 9400)
        self.assertEqual(self.service.wallet(token)['currency'], 'USD')
        merchant = result['merchant']
        updated = self.post('merchants/update', {**merchant, 'games': []})['merchant']
        self.assertEqual(self.gateway_request(merchant=merchant_id)[1]['data']['games'], [])
        with self.assertRaises(ServiceError) as denied:
            self.service.launch(merchant_id, {'player_id': 'new-player'})
        self.assertEqual(denied.exception.code, 'GAME_FORBIDDEN')
        self.assertEqual(self.post('merchants/update', merchant, expected=409)['code'], 'VERSION_CONFLICT')
        rotated = self.post('merchants/rotate', {'id': merchant['id'], 'version': updated['version'], 'reason': 'rotation test'})
        self.assertEqual(self.gateway_request(secret, merchant_id)[0], 401)
        self.assertEqual(self.gateway_request(rotated['keys']['api_secret'], merchant_id)[0], 200)
        disabled = self.post('merchants/update', {**rotated['merchant'], 'enabled': False})['merchant']
        self.assertEqual(self.gateway_request(merchant=merchant_id)[0], 401)
        self.assertFalse(second[merchant_id]['enabled'])
        public = encode(self.post('merchants/list')) + encode(self.post('audit'))
        for value in [*result['keys'].values(), *rotated['keys'].values(), PASSWORD]:
            self.assertNotIn(value, public)
        self.assertEqual(disabled['key_version'], 2)

    def test_new_merchants_only_accept_usd_and_default_to_usd(self):
        payload = {'name': 'USD Only', 'enabled': True,
                   'wallet_url': 'http://127.0.0.1:' + str(self.platform.server_port), 'games': ['buffalo-win']}
        for currency in ('DEMO', 'EUR', 'CNY', 'usd', '', None, 123):
            with self.subTest(currency=currency):
                error = self.post('merchants/create', {**payload, 'currency': currency}, expected=400)
                self.assertEqual(error['code'], 'CURRENCY_INVALID')
                self.assertEqual(len(self.control.merchants()), 2)
        created = self.post('merchants/create', payload, expected=201)['merchant']
        self.assertEqual((created['currency'], created['minor_unit']), ('USD', 100))
        self.assertEqual(self.post('merchants/update', {**created, 'currency': 'EUR'}, expected=400)['code'], 'CURRENCY_IMMUTABLE')

    def test_automatic_merchant_ids_handle_collisions_concurrency_and_legacy_records(self):
        payload = {'name': 'Automatic ID', 'enabled': False, 'wallet_url': 'https://wallet.example.com', 'currency': 'USD', 'games': []}
        for requested_id in ('alpha', 'custom-id', '', None):
            error = self.post('merchants/create', {**payload, 'id': requested_id}, expected=400)
            self.assertEqual(error['code'], 'MERCHANT_ID_AUTOMATIC')
        first = self.post('merchants/create', payload, expected=201)['merchant']
        random_hex = secrets.token_hex
        candidates = iter([first['id'][3:].lower(), '0' * 16])

        def collide_once(size):
            return next(candidates) if size == 8 else random_hex(size)

        with patch('server.merchant.control.secrets.token_hex', side_effect=collide_once):
            second = self.post('merchants/create', payload, expected=201)['merchant']
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(self.control.merchant(first['id']), first)
        # A persistent collision fails cleanly rather than overwriting records.
        with patch('server.merchant.control.secrets.token_hex', return_value='0' * 16):
            self.post('merchants/create', payload, expected=503)
        self.assertEqual(len(self.control.merchants()), 4)
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            generated = list(pool.map(lambda index: self.control.save_merchant(
                'admin', {**payload, 'name': 'Concurrent ' + str(index)}, {'buffalo-win'}, create=True)['merchant'], range(12)))
        ids = [first['id'], second['id'], *(merchant['id'] for merchant in generated)]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(self.control.merchant(merchant_id) for merchant_id in ids))
        self.assertEqual(self.control.merchant('alpha')['id'], 'alpha')
        self.assertEqual(self.control.merchant('alpha')['currency'], 'DEMO')
        self.assertEqual({row['target'] for row in self.control.audits({'action': 'merchant.create'})}, set(ids))

    def test_validation_currency_conflicts_and_invalid_inputs(self):
        merchant = self.control.merchant('alpha')
        for origin in ('http://remote.example', 'https://name:secret@example.com', 'https://example.com/path', 'https://example.com?token=1', 'file:///tmp/wallet', 'https://example.com:invalid'):
            self.post('merchants/update', {**merchant, 'wallet_url': origin}, expected=400)
        self.post('merchants/update', {**merchant, 'games': ['unknown-game']}, expected=400)
        self.post('merchants/update', {**merchant, 'enabled': 1}, expected=400)
        self.post('merchants/update', {**merchant, 'currency': 'USD'}, expected=400)
        self.post('transactions/list', {'before_seq': -1}, expected=400)
        self.post('audit', {'limit': 101}, expected=400)
        self.post('merchants/rotate', {'id': 'alpha', 'version': merchant['version'], 'reason': 'x'}, expected=400)
        self.assertEqual(self.control.merchant('alpha')['version'], merchant['version'])

    def test_pending_recovery_after_disable_and_revoke_never_debits_twice(self):
        pending = self.pending()
        self.assertEqual(self.platform.wallet.call('alpha', 'balance', wallet_payload())['balance_minor'], 199400)
        merchant = self.control.merchant('alpha')
        self.post('merchants/update', {**merchant, 'enabled': False, 'games': []})
        self.assertEqual(self.gateway_request()[0], 401)
        payload = {'merchant_id': 'alpha', 'operation_id': pending['id'], 'reason': 'reconcile lost debit reply'}
        self.post('transactions/retry', payload, user='viewer', expected=403)
        response = self.post('transactions/retry', payload, user='operator')
        self.assertEqual(response['sid'], pending['id'])
        self.assertEqual(self.platform.wallet.call('alpha', 'balance', wallet_payload())['balance_minor'], 199400)
        with self.platform.wallet.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM transactions WHERE kind='debit'").fetchone()[0], 1)
        self.post('transactions/retry', payload, user='operator', expected=409)
        audit = self.control.audits({'actor': 'operator', 'target': pending['id']})
        self.assertEqual({row['action'] for row in audit}, {'transaction.retry.request', 'transaction.retry.result'})
        self.assertTrue(all(row['outcome'] == 'success' for row in audit))
        with self.service.connection() as db:
            self.assertEqual(db.execute('SELECT candidate_json FROM game_operations').fetchone()[0], pending['candidate_json'])

    def test_failed_recovery_remains_queryable_and_audited(self):
        pending = self.pending()
        with patch.object(self.service.wallet_client, 'call', side_effect=ServiceError('WALLET_UNCERTAIN', 'offline', 503)):
            self.post('transactions/retry', {'merchant_id': 'alpha', 'operation_id': pending['id'], 'reason': 'retry offline wallet'}, user='operator', expected=503)
        audit = self.control.audits({'actor': 'operator', 'action': 'transaction.retry.result'})
        self.assertEqual(audit[0]['outcome'], 'failed')
        rows = self.post('transactions/list', {'merchant_id': 'alpha', 'player_id': 'same-player', 'status': 'prepared'})['transactions']
        self.assertEqual(len(rows), 1)
        self.assertNotIn('candidate_json', encode(rows))
        self.assertNotIn('state', rows[0])
        detail = self.post('transactions/detail', {'operation_id': pending['id'] + ':debit'})
        self.assertIsNone(detail['result'])
        self.assertIn('request', detail)
        self.assertNotIn('candidate', detail)
        self.assertEqual(self.post('transactions/list', {'merchant_id': 'beta'})['transactions'], [])

    def test_transaction_pagination_detail_and_overview(self):
        pending = self.pending()
        self.post('transactions/retry', {'merchant_id': 'alpha', 'operation_id': pending['id'], 'reason': 'pagination setup'})
        with self.service.connection(True) as db:
            row = db.execute('SELECT * FROM game_operations').fetchone()
            columns = list(row.keys()); placeholders = ','.join('?' for _ in columns)
            for index in range(30):
                values = dict(row); values.update(seq=index + 2, id='page-' + str(index), request_key='key-' + str(index))
                db.execute('INSERT INTO game_operations(' + ','.join(columns) + ') VALUES (' + placeholders + ')', list(values.values()))
        first = self.post('transactions/list', {'limit': 25})['transactions']
        second = self.post('transactions/list', {'before_seq': first[-1]['seq'], 'limit': 25})['transactions']
        self.assertEqual((len(first), len(second)), (25, 6))
        self.assertFalse({r['id'] for r in first} & {r['id'] for r in second})
        overview = self.post('overview')
        self.assertEqual((overview['settled'], overview['pending']), (31, 0))
        self.assertEqual(len(overview['recent']), 5)
        detail = self.post('transactions/detail', {'operation_id': pending['id'], 'merchant_id': 'alpha'})
        self.assertEqual(detail['result']['sid'], pending['id'])
        self.post('transactions/detail', {'operation_id': pending['id'], 'merchant_id': 'beta'}, expected=404)
        audit1 = self.control.audits({'limit': 3})
        audit2 = self.control.audits({'limit': 3, 'before_seq': audit1[-1]['seq']})
        self.assertFalse({r['seq'] for r in audit1} & {r['seq'] for r in audit2})

    def test_transaction_currency_matches_merchant_and_wallet_payout_without_conversion(self):
        merchant = self.post('merchants/create', {'name': 'USD Settlement', 'enabled': True,
            'wallet_url': 'http://127.0.0.1:' + str(self.platform.server_port), 'currency': 'USD',
            'games': ['buffalo-win']}, expected=201)['merchant']
        merchant_id = merchant['id']
        self.platform.wallet.seed(merchant_id, 'usd-player', 200000)
        game = self.service.registry.get('buffalo-win')
        game.boards = [([3,3,3,3,2,0,2,3,0,0,2,7], 3, {'1': [0,1,2,3]}, {'1': 8})]
        game.columns = [[3,3,2,5], [0,0,2,3], [2,8,8,2]]
        launched = self.service.launch(merchant_id, {'player_id': 'usd-player'})
        token = parse_qs(urlsplit(launched['launch_url']).query)['ops'][0]
        sid = '0'
        for index in range(4):
            result = self.service.spin(token, 'buffalo-win', 'usd-' + str(index), sid, {})
            sid = result['sid']
        self.assertEqual(result['wallet']['credit_minor'], 20400)
        self.assertEqual(self.service.wallet(token)['balance_minor'], 219800)
        with self.platform.wallet.connection() as db:
            payout = db.execute("SELECT request_json,response_json FROM transactions WHERE merchant_id=? AND kind='credit'",
                                (merchant_id,)).fetchone()
        self.assertEqual(json.loads(payout['request_json'])['amount_minor'], 20400)
        self.assertEqual(json.loads(payout['response_json'])['applied_minor'], 20400)
        self.pending()  # Include an existing DEMO merchant in the same response.
        rows = self.post('transactions/list')['transactions']
        self.assertEqual(len(rows), 5)
        for row in rows:
            self.assertEqual(row['currency'], 'USD' if row['merchant_id'] == merchant_id else 'DEMO')
            self.assertEqual(row['minor_unit'], 100)
        detail = self.post('transactions/detail', {'operation_id': sid})
        self.assertEqual((detail['credit_minor'], detail['currency'], detail['minor_unit']), (20400, 'USD', 100))
        self.assertEqual(detail['result'], result)
        self.assertEqual({row['currency'] for row in self.post('overview')['recent']}, {'USD', 'DEMO'})
        # Never relabel a historical operation as USD if its merchant is missing.
        with self.control.connection(True) as db:
            db.execute('DELETE FROM merchants WHERE id=?', (merchant_id,))
        unknown = self.post('transactions/detail', {'operation_id': sid})
        self.assertIsNone(unknown['currency'])
        self.assertIsNone(unknown['minor_unit'])
        self.assertEqual(unknown['credit_minor'], 20400)

    def test_users_passwords_revocation_and_last_admin(self):
        self.login('operator')
        self.post('users/update', {'username': 'admin', 'role': 'viewer', 'enabled': True}, expected=409)
        self.post('users/update', {'username': 'operator', 'role': 'viewer', 'enabled': True})
        self.assertEqual(self.request('/api/admin/me', user='operator', method='GET')[0], 401)
        self.login('operator')
        self.post('transactions/retry', user='operator', expected=403)
        self.post('users/update', {'username': 'operator', 'role': 'viewer', 'enabled': False})
        self.assertEqual(self.request('/api/admin/login', {'username': 'operator', 'password': PASSWORD}, user=None)[0], 401)
        created = self.post('users/create', {'username': 'reviewer', 'role': 'viewer'}, expected=201)
        self.assertEqual(self.request('/api/admin/login', {'username': 'reviewer', 'password': created['temporary_password']}, user=None)[0], 200)
        reset = self.post('users/reset', {'username': 'viewer'})
        self.assertNotIn(reset['temporary_password'], encode(self.post('audit')))
        self.assertNotIn('password', encode(self.post('users/list')))
        self.post('password', {'current_password': 'wrong', 'new_password': 'New-password-test-only!'}, expected=403)
        self.post('password', {'current_password': PASSWORD, 'new_password': 'New-password-test-only!'})
        self.assertEqual(self.request('/api/admin/me', method='GET')[0], 401)
        self.assertEqual(self.request('/api/admin/login', {'username': 'admin', 'password': 'New-password-test-only!'}, user=None)[0], 200)

    def test_static_assets_are_allowlisted_and_no_cache(self):
        for path in ('/', '/admin.js', '/admin.css'):
            code, body, headers = self.request(path, method='GET', user=None)
            self.assertEqual(code, 200)
            self.assertTrue(body)
            self.assertEqual(headers['Cache-Control'], 'no-store')
            self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        for path in ('/../control.py', '/control.py', '/sandbox.json', '/?file=control.py'):
            self.assertIn(self.request(path, method='GET', user=None)[0], (400, 404))


class GTTMigrationTests(unittest.TestCase):
    def test_fresh_sandbox_uses_usd(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sandbox.json'
            with patch('builtins.print'):
                initialize(path)
            loaded, store = load_config(path)
            self.assertEqual(loaded['merchants']['demo-platform']['currency'], 'USD')
            platform = build_platform(0, Path(directory) / 'wallet.sqlite3', loaded)
            try:
                account = platform.wallet.call('demo-platform', 'balance', {
                    'player_id': 'demo-player', 'currency': 'USD', 'minor_unit': 100})
                self.assertEqual((account['balance_minor'], account['currency']), (200000, 'USD'))
            finally:
                platform.server_close()

    def test_legacy_configuration_migrates_once_without_overwriting_live_changes(self):
        with tempfile.TemporaryDirectory(dir='.') as directory:
            path = Path(directory) / 'sandbox.json'  # Exercise relative --config as well.
            original = configuration()
            path.write_bytes(encode(original).encode())
            loaded, store = load_config(path)
            self.assertNotIn('api_secret', path.read_text())
            self.assertEqual(json.loads(path.with_name('sandbox.before-admin.json').read_bytes()), original)
            self.assertTrue(Path(store.path).is_file())
            record = store.merchant('alpha')
            store.save_merchant('admin', {**record, 'name': 'Changed live', 'enabled': False}, {'buffalo-win'})
            loaded2, store2 = load_config(path)
            self.assertFalse(loaded2['merchants']['alpha']['enabled'])
            self.assertEqual(store2.merchant('alpha')['name'], 'Changed live')
            self.assertEqual(loaded2['merchants']['alpha']['currency'], 'DEMO')
            # Re-importing an old backup never replaces rotated keys/live settings.
            store2.migrate(original['merchants'])
            self.assertEqual(store2.merchant('alpha')['name'], 'Changed live')
            self.assertEqual(len(store2.audits({'action': 'merchant.migrate'})), 2)


if __name__ == '__main__':
    unittest.main()
