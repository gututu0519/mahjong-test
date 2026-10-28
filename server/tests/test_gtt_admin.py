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
        fields = signed_headers(merchant, secret or self.config['merchants'][merchant]['merchant_secret'], path, body)
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
        secret = result['keys']['merchant_secret']
        self.assertEqual(set(result['keys']), {'merchant_secret'})
        self.assertEqual(result['merchant']['signing_mode'], 'unified')
        self.platform.wallet.seed(merchant_id, 'new-player', 10000)
        self.assertEqual(self.gateway_request(merchant=merchant_id)[0], 200)
        # A second process/store connection sees updates without a service restart.
        second = MerchantDirectory(ControlStore(self.control.path))
        self.assertEqual(second[merchant_id]['merchant_secret'], secret)
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
        self.assertEqual(self.gateway_request(rotated['keys']['merchant_secret'], merchant_id)[0], 200)
        disabled = self.post('merchants/update', {**rotated['merchant'], 'enabled': False})['merchant']
        self.assertEqual(self.gateway_request(merchant=merchant_id)[0], 401)
        self.assertFalse(second[merchant_id]['enabled'])
        public = encode(self.post('merchants/list')) + encode(self.post('audit'))
        for value in [*result['keys'].values(), *rotated['keys'].values(), PASSWORD]:
            self.assertNotIn(value, public)
        self.assertEqual(disabled['merchant_key_version'], 2)

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






    def unified_merchant(self, prebet=False):
        return self.post('merchants/create', {'name': 'Unified Partner', 'enabled': True,
            'wallet_url': f'http://127.0.0.1:{self.platform.server_port}', 'games': ['buffalo-win'],
            'pre_payout': {'enabled': prebet, 'url': f'http://127.0.0.1:{self.platform.server_port}/api/v1/callbacks/gtt/preBetDecision' if prebet else ''}}, expected=201)

    def test_merchant_secret_can_be_viewed_repeatedly_without_claiming_or_rotating(self):
        self.tenant_accounts()
        original = self.control.merchant('alpha', private=True)
        for _ in range(3):
            viewed = self.post('merchants/signing/view', {'id': 'alpha'}, user='alpha-owner')
            self.assertEqual(viewed['keys'], {'merchant_secret': original['merchant_secret']})
            self.assertEqual(viewed['merchant']['version'], original['version'])
            self.assertNotIn('merchant_key_ready', viewed['merchant'])
            self.assertEqual(viewed['merchant']['signing_mode'], 'unified')
        self.assertEqual(self.gateway_request(original['merchant_secret'])[0], 200)
        self.assertEqual(ControlStore(self.control.path).merchant('alpha', private=True)['merchant_secret'], original['merchant_secret'])
        for route in ('merchants/list', 'audit', 'overview'):
            self.assertNotIn(original['merchant_secret'], encode(self.post(route, user='alpha-owner')))

    def test_merchant_secret_view_is_scoped_and_old_flows_do_not_exist(self):
        self.tenant_accounts()
        for action in ('view', 'rotate'):
            payload = {'id': 'alpha', 'version': self.control.merchant('alpha')['version'], 'reason': 'key administration'}
            for user in ('viewer', 'operator', 'alpha-read', 'alpha-ops'):
                self.post('merchants/signing/' + action, payload, user=user, expected=403)
            self.post('merchants/signing/' + action, {**payload, 'id': 'beta'}, user='alpha-owner', expected=403)
        self.post('merchants/signing/view', {'id': 'missing'}, expected=404)
        for route in ('merchants/signing/claim', 'merchants/signing/activate', 'merchants/prebet-credentials', 'merchants/prebet-credentials/claim'):
            self.post(route, {}, expected=404)
        self.post('merchants/create', {'merchant_secret': 'user-selected'}, expected=400)
        self.assertEqual(self.post('merchants/create', {'signing_mode': 'legacy'}, expected=400)['code'], 'SIGNING_MODE_INVALID')
        m = self.control.merchant('alpha')
        self.post('merchants/profile', {'version': m['version'], 'pre_payout': {'enabled': False, 'url': '', 'operator_token': 'unused'}}, user='alpha-owner', expected=400)

    def test_reset_secret_is_immediately_available_for_repeated_view(self):
        self.tenant_accounts()
        before = self.control.merchant('alpha', private=True)
        changed = self.post('merchants/signing/rotate', {'id': 'alpha', 'version': before['version'], 'reason': 'scheduled reset'}, user='alpha-owner')
        self.assertNotEqual(changed['keys']['merchant_secret'], before['merchant_secret'])
        self.assertEqual(self.post('merchants/signing/view', {'id': 'alpha'}, user='alpha-owner')['keys'], changed['keys'])
        self.assertEqual(self.gateway_request(before['merchant_secret'])[0], 401)
        self.assertEqual(self.gateway_request(changed['keys']['merchant_secret'])[0], 200)
        self.post('merchants/signing/rotate', {'id': 'alpha', 'version': before['version'], 'reason': 'stale reset'}, user='alpha-owner', expected=409)

    def test_unified_key_signs_api_wallet_and_prebet_without_transmitting_the_secret(self):
        from server.merchant.common import signature
        created = self.unified_merchant(prebet=True)
        merchant_id, secret = created['merchant']['id'], created['keys']['merchant_secret']
        self.assertRegex(secret, r'^[0-9a-f]{64}$')
        self.assertNotIn('prebet_credentials', created)
        self.assertEqual(self.gateway_request(secret, merchant_id)[0], 200)
        self.platform.wallet.seed(merchant_id, 'unified-player', 200000)
        self.platform.wallet.bind_prebet_player(merchant_id, 'unified-player', 'unified-external')
        calls = []
        wallet_open = self.service.wallet_client.opener.open
        prebet_open = self.service.prebet.client.opener.open
        def capture(delegate):
            def opened(request, **kwargs):
                fields = {k.lower(): v for k, v in request.header_items()}
                path = urlsplit(request.full_url).path
                self.assertEqual(fields['x-gtt-signature'], signature(secret, 'POST', path, fields['x-gtt-timestamp'], fields['x-gtt-nonce'], request.data))
                self.assertNotIn(secret.encode(), request.data)
                self.assertNotIn(b'operator_token', request.data)
                self.assertNotIn(b'secret_key', request.data)
                calls.append((path, fields['x-gtt-nonce']))
                return delegate(request, **kwargs)
            return opened
        with patch.object(self.service.wallet_client.opener, 'open', side_effect=capture(wallet_open)), patch.object(self.service.prebet.client.opener, 'open', side_effect=capture(prebet_open)):
            launched = self.service.launch(merchant_id, {'player_id': 'unified-player', 'external_username': 'unified-external'})
            token = parse_qs(urlsplit(launched['launch_url']).query)['ops'][0]
            result = self.service.spin(token, 'buffalo-win', 'unified-spin', '0', {})
            self.assertEqual(result, self.service.spin(token, 'buffalo-win', 'unified-spin', '0', {}))
        self.assertTrue(any(path.endswith('preBetDecision') for path, _ in calls))
        self.assertTrue(any(path == '/wallet/v1/balance' for path, _ in calls))
        self.assertTrue(any(path == '/wallet/v1/debit' for path, _ in calls))
        self.assertEqual(len(calls), len({nonce for _, nonce in calls}))
        public = encode(self.post('merchants/list')) + encode(self.post('audit')) + encode(self.post('prebet/list'))
        self.assertNotIn(secret, public)
        with self.service.connection() as db:
            records = encode([dict(r) for r in db.execute('SELECT * FROM prebet_rounds WHERE merchant_id=?', (merchant_id,))])
        self.assertNotIn(secret, records)


    def test_unified_key_replay_tampering_rotation_and_legacy_downgrade_rejection(self):
        created = self.unified_merchant()
        merchant_id, secret = created['merchant']['id'], created['keys']['merchant_secret']
        self.platform.wallet.seed(merchant_id, 'unified-player', 200000)
        path = '/wallet/v1/balance'
        payload = {'player_id': 'unified-player', 'currency': 'USD', 'minor_unit': 100}
        fields = signed_headers(merchant_id, secret, path, encode(payload).encode())
        self.assertEqual(self.request(path, payload, None, fields, port=self.platform.server_port)[0], 200)
        self.assertEqual(self.request(path, payload, None, fields, port=self.platform.server_port)[0], 409)
        fields = signed_headers(merchant_id, secret, path, encode(payload).encode())
        self.assertEqual(self.request(path, {**payload, 'player_id': 'tampered'}, None, fields, port=self.platform.server_port)[0], 401)
        with self.control.connection(True) as db:
            db.execute('UPDATE merchants SET api_secret=?,wallet_secret=? WHERE id=?', ('old-api', 'old-wallet', merchant_id))
        self.assertEqual(self.gateway_request('old-api', merchant_id)[0], 401)
        old_wallet = signed_headers(merchant_id, 'old-wallet', path, encode(payload).encode())
        self.assertEqual(self.request(path, payload, None, old_wallet, port=self.platform.server_port)[0], 401)
        rotated = self.post('merchants/signing/rotate', {'id': merchant_id, 'version': created['merchant']['version'], 'reason': 'scheduled rotation'})
        self.assertNotEqual(secret, rotated['keys']['merchant_secret'])
        self.assertEqual(self.gateway_request(secret, merchant_id)[0], 401)
        self.assertEqual(self.gateway_request(rotated['keys']['merchant_secret'], merchant_id)[0], 200)
        old_style = self.request('/api/v1/callbacks/gtt/preBetDecision', {'operator_token': 'unused', 'secret_key': secret}, user=None, port=self.platform.server_port)
        self.assertEqual(old_style[0], 401)


    def tenant_accounts(self):
        for name, role, merchant in [('alpha-owner', 'merchant_admin', 'alpha'),
                                     ('beta-owner', 'merchant_admin', 'beta'),
                                     ('alpha-read', 'merchant_viewer', 'alpha'),
                                     ('alpha-ops', 'merchant_operator', 'alpha')]:
            self.control.create_user('admin', name, role, PASSWORD, merchant_id=merchant)


    def test_merchant_scope_lists_overview_games_audit_and_direct_object_access(self):
        self.tenant_accounts()
        self.platform.wallet.seed('beta', 'same-player', 200000)
        for merchant in ('alpha', 'beta'):
            token = parse_qs(urlsplit(self.service.launch(merchant, {'player_id': 'same-player'})['launch_url']).query)['ops'][0]
            self.service.spin(token, 'buffalo-win', merchant + '-spin', '0', {})
        own = self.post('transactions/list', user='alpha-owner')['transactions']
        self.assertEqual({row['merchant_id'] for row in own}, {'alpha'})
        other = self.post('transactions/list', user='beta-owner')['transactions'][0]
        self.post('transactions/detail', {'operation_id': other['id']}, user='alpha-owner', expected=404)
        self.post('transactions/retry', {'operation_id': other['id'], 'reason': 'cross tenant'}, user='alpha-owner', expected=404)
        for route in ('overview', 'merchants/list', 'games', 'transactions/list', 'transactions/detail', 'prebet/list', 'audit', 'users/list'):
            self.post(route, {'merchant_id': 'beta'}, user='alpha-owner', expected=403)
        self.assertEqual([m['id'] for m in self.post('merchants/list', user='alpha-owner')['merchants']], ['alpha'])
        summary = self.post('overview', user='alpha-owner')
        self.assertEqual((summary['merchants'], summary['settled'], summary['players']), (1, 1, 1))
        self.assertEqual(sum(day['settled'] for day in summary['daily']), 1)
        self.assertEqual(summary['totals'][0]['debit_minor'], own[0]['debit_minor'])
        self.assertEqual(summary['totals'][0]['credit_minor'], own[0]['credit_minor'])
        self.assertNotIn('beta', encode(self.post('audit', user='alpha-owner')))
        merchant = self.control.merchant('alpha')
        self.control.save_merchant('admin', {**merchant, 'games': []}, {'buffalo-win'})
        self.assertEqual(self.post('games', user='alpha-owner')['games'], [])
        self.assertEqual(self.post('overview', user='alpha-owner')['games'], 0)

    def test_merchant_profile_and_rotation_cannot_change_authorization_or_other_tenant(self):
        self.tenant_accounts()
        m = self.control.merchant('alpha')
        self.post('merchants/profile', {'version': m['version'], 'enabled': False}, user='alpha-owner', expected=403)
        self.post('merchants/profile', {'id': 'beta', 'version': 1}, user='alpha-owner', expected=403)
        self.post('merchants/update', {**m, 'games': []}, user='alpha-owner', expected=403)
        self.post('merchants/create', user='alpha-owner', expected=403)
        result = self.post('merchants/profile', {'id': 'alpha', 'version': m['version'], 'name': 'Alpha partner',
                           'wallet_url': m['wallet_url'], 'pre_payout': {'enabled': False, 'url': ''}}, user='alpha-owner')
        self.assertEqual(result['merchant']['name'], 'Alpha partner')
        self.assertEqual(result['merchant']['games'], m['games'])
        self.post('merchants/profile', {'version': m['version'], 'name': 'Stale'}, user='alpha-owner', expected=409)
        self.post('merchants/rotate', {'id': 'beta', 'version': 1, 'reason': 'key rotation'}, user='alpha-owner', expected=403)
        other_secret = self.config['merchants']['beta']['merchant_secret']
        rotated = self.post('merchants/rotate', {'id': 'alpha', 'version': result['merchant']['version'], 'reason': 'key rotation'}, user='alpha-owner')
        self.assertNotIn(rotated['keys']['merchant_secret'], encode(self.post('audit', user='alpha-owner')))
        self.assertEqual(other_secret, self.config['merchants']['beta']['merchant_secret'])

    def test_merchant_team_no_escalation_cross_tenant_reset_or_rebinding(self):
        self.tenant_accounts()
        self.assertEqual({u['username'] for u in self.post('users/list', user='alpha-owner')['users']}, {'alpha-owner', 'alpha-read', 'alpha-ops'})
        created = self.post('users/create', {'username': 'new-staff', 'role': 'merchant_viewer'}, user='alpha-owner', expected=201)
        self.assertEqual(created['user']['merchant_id'], 'alpha')
        self.post('users/create', {'username': 'bad-staff', 'role': 'admin'}, user='alpha-owner', expected=400)
        self.post('users/create', {'username': 'bad-staff', 'role': 'merchant_admin', 'merchant_id': 'beta'}, user='alpha-owner', expected=403)
        for target in ('admin', 'beta-owner'):
            self.post('users/reset', {'username': target}, user='alpha-owner', expected=404)
            self.post('users/update', {'username': target, 'role': 'merchant_viewer', 'enabled': True}, user='alpha-owner', expected=404)
        self.post('users/update', {'username': 'alpha-read', 'role': 'admin', 'enabled': True}, user='alpha-owner', expected=400)
        self.post('users/update', {'username': 'alpha-read', 'role': 'merchant_admin', 'enabled': True, 'merchant_id': 'beta'}, user='alpha-owner', expected=403)
        self.post('users/update', {'username': 'alpha-owner', 'role': 'merchant_viewer', 'enabled': True}, user='alpha-owner', expected=409)
        self.login('alpha-read')
        self.post('users/update', {'username': 'alpha-read', 'role': 'merchant_operator', 'enabled': True}, user='alpha-owner')
        self.assertEqual(self.request('/api/admin/me', user='alpha-read', method='GET')[0], 401)

    def test_platform_admin_can_provision_bound_merchant_accounts(self):
        created = self.post('users/create', {'username': 'merchant-owner', 'role': 'merchant_admin', 'merchant_id': 'alpha'}, expected=201)
        self.assertEqual(created['user']['merchant_id'], 'alpha')
        self.post('users/create', {'username': 'missing-binding', 'role': 'merchant_admin'}, expected=400)
        self.post('users/create', {'username': 'wrong-binding', 'role': 'admin', 'merchant_id': 'alpha'}, expected=400)
        self.post('users/create', {'username': 'bad-binding', 'role': 'merchant_admin', 'merchant_id': 'missing'}, expected=404)

    def test_merchant_read_only_and_operator_permissions(self):
        self.tenant_accounts()
        for user in ('alpha-read', 'alpha-ops'):
            for route in ('overview', 'merchants/list', 'transactions/list', 'prebet/list', 'audit', 'games'):
                self.post(route, user=user)
            for route in ('merchants/profile', 'merchants/rotate', 'merchants/update', 'users/create', 'users/list', 'users/reset'):
                self.post(route, user=user, expected=403)
        self.post('transactions/retry', user='alpha-read', expected=403)
        pending = self.pending()
        self.post('transactions/retry', {'operation_id': pending['id'], 'reason': 'wallet recovered'}, user='alpha-ops')
        self.assertEqual(self.post('transactions/detail', {'operation_id': pending['id']}, user='alpha-read')['status'], 'settled')

    def test_merchant_audit_stays_attributed_after_user_rebinding(self):
        self.tenant_accounts()
        # A username matching another merchant ID must not change audit tenancy.
        self.post('users/create', {'username': 'beta', 'role': 'merchant_viewer'}, user='alpha-owner', expected=201)
        self.post('users/create', {'username': 'moving-staff', 'role': 'merchant_viewer'}, user='alpha-owner', expected=201)
        self.post('users/update', {'username': 'moving-staff', 'role': 'merchant_viewer', 'enabled': True, 'merchant_id': 'beta'})
        alpha = self.post('audit', user='alpha-owner')['audit']
        beta = self.post('audit', user='beta-owner')['audit']
        self.assertTrue(any(a['action'] == 'user.create' and a['target'] == 'moving-staff' for a in alpha))
        self.assertFalse(any(a['action'] == 'user.create' and a['target'] == 'moving-staff' for a in beta))
        self.assertTrue(any(a['action'] == 'user.create' and a['target'] == 'beta' for a in alpha))
        self.assertFalse(any(a['action'] == 'user.create' and a['target'] == 'beta' for a in beta))

    def test_merchant_prebet_rows_are_scoped_and_do_not_expose_future_results(self):
        self.tenant_accounts()
        for merchant in ('alpha', 'beta'):
            record = self.control.merchant(merchant)
            settings = {'enabled': True, 'url': f'http://127.0.0.1:{self.platform.server_port}/api/v1/callbacks/gtt/preBetDecision',
                        }
            self.control.save_merchant('admin', {**record, 'pre_payout': settings}, {'buffalo-win'})
            self.platform.wallet.seed(merchant, 'prebet-player', 200000)
            self.platform.wallet.bind_prebet_player(merchant, 'prebet-player', merchant + '-external')
            token = parse_qs(urlsplit(self.service.launch(merchant, {'player_id': 'prebet-player', 'external_username': merchant + '-external'})['launch_url']).query)['ops'][0]
            self.service.spin(token, 'buffalo-win', 'tenant-prebet', '0', {})
        own = self.post('prebet/list', user='alpha-owner')['decisions']
        self.assertEqual(len(own), 1)
        self.assertEqual(own[0]['merchant_id'], 'alpha')
        self.assertEqual(own[0]['request']['player_name'], 'alpha-external')
        text = encode(own)
        for hidden in ('beta-external', 'alpha-secret', 'alpha-token', 'plan_json', 'total_credit_minor', 'initial_state_json'):
            self.assertNotIn(hidden, text)

    def test_merchant_portal_has_independent_cookie_and_csrf_namespace(self):
        self.tenant_accounts()
        self.login('admin')
        self.assertEqual(self.request('/api/merchant/me', method='GET')[0], 401)
        code, body, fields = self.request('/api/merchant/login', {'username': 'alpha-owner', 'password': PASSWORD}, user=None)
        self.assertEqual(code, 200, body)
        cookie = fields['Set-Cookie'].split(';', 1)[0]
        self.assertTrue(cookie.startswith('gtt_merchant_session='))
        headers = {'Cookie': cookie, 'X-GTT-CSRF': body['data']['csrf_token']}
        self.assertEqual(self.request('/api/merchant/me', user=None, headers=headers, method='GET')[1]['data']['user']['merchant_id'], 'alpha')
        self.assertEqual(self.request('/api/merchant/overview', user=None, headers=headers)[1]['data']['merchants'], 1)
        self.assertEqual(self.request('/api/admin/me', user=None, headers=headers, method='GET')[0], 401)
        self.assertEqual(self.request('/api/merchant/overview', user=None, headers={**headers, 'X-GTT-CSRF': ''})[0], 403)
        self.assertEqual(self.request('/api/merchant/logout', user=None, headers=headers)[0], 200)
        self.assertEqual(self.request('/api/admin/me', method='GET')[0], 200)
        self.assertEqual(self.request('/api/merchant/me', user=None, headers=headers, method='GET')[0], 401)
        self.assertEqual(self.request('/api/merchant/login', {'username': 'admin', 'password': PASSWORD}, user=None)[0], 403)


class GTTMigrationTests(unittest.TestCase):
    def test_existing_local_merchants_automatically_use_single_secret_without_delivery_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'merchants.sqlite3'
            store = ControlStore(path)
            store.migrate(configuration()['merchants'])
            before = store.merchant('alpha', private=True)
            with store.connection(True) as db:
                db.execute("UPDATE merchant_signing_credentials SET mode='legacy',ready=1 WHERE merchant_id='alpha'")
                db.execute("UPDATE merchants SET api_secret='obsolete-api',wallet_secret='obsolete-wallet' WHERE id='alpha'")
                db.execute("INSERT INTO merchant_prebet_settings VALUES ('alpha',1,'https://platform.example/callback','obsolete-token','obsolete-secret')")
                db.execute('CREATE TABLE merchant_prebet_deliveries (merchant_id TEXT PRIMARY KEY,fingerprint TEXT)')
                db.execute("INSERT INTO merchant_prebet_deliveries VALUES ('alpha','obsolete')")
            upgraded = ControlStore(path)
            after = upgraded.merchant('alpha', private=True)
            self.assertEqual(after['merchant_secret'], before['merchant_secret'])
            self.assertEqual(after['signing_mode'], 'unified')
            self.assertNotIn('merchant_key_ready', after)
            self.assertEqual(after['pre_payout'], {'enabled': True, 'url': 'https://platform.example/callback'})
            for field in ('enabled', 'currency', 'wallet_url', 'games'):
                self.assertEqual(after[field], before[field])
            with upgraded.connection() as db:
                self.assertEqual(tuple(db.execute("SELECT mode,ready FROM merchant_signing_credentials WHERE merchant_id='alpha'").fetchone()), ('unified', 0))
                self.assertEqual(tuple(db.execute("SELECT operator_token,secret_key FROM merchant_prebet_settings WHERE merchant_id='alpha'").fetchone()), ('', ''))
                self.assertEqual(db.execute('SELECT COUNT(*) FROM merchant_prebet_deliveries').fetchone()[0], 0)
            audit = upgraded.audits({})
            again = ControlStore(path)
            self.assertEqual(again.merchant('alpha', private=True), after)
            self.assertEqual(again.audits({}), audit)

    def test_missing_merchant_secret_is_automatically_created_and_immediately_usable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'merchants.sqlite3'
            store = ControlStore(path)
            store.migrate(configuration()['merchants'])
            beta = store.merchant('beta', private=True)
            with store.connection(True) as db:
                db.execute("DELETE FROM merchant_signing_credentials WHERE merchant_id='alpha'")
            upgraded = ControlStore(path)
            alpha = upgraded.merchant('alpha', private=True)
            self.assertRegex(alpha['merchant_secret'], r'^[0-9a-f]{64}$')
            self.assertNotEqual(alpha['merchant_secret'], beta['merchant_secret'])
            self.assertEqual(upgraded.merchant('beta', private=True), beta)
            self.assertEqual(alpha['pre_payout'], {'enabled': False, 'url': ''})


    def test_legacy_admin_schema_upgrade_preserves_accounts_sessions_and_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'legacy.sqlite3'
            store = ControlStore(path)
            store.migrate(configuration()['merchants'])
            store.create_user('system', 'original-admin', 'admin', PASSWORD)
            token, original = store.login('original-admin', PASSWORD, '127.0.0.1')
            with store.connection(True) as db:
                before = db.execute('SELECT COUNT(*) FROM admin_audit').fetchone()[0]
                db.execute('DROP INDEX audit_merchant_seq')
                db.execute('ALTER TABLE admin_users DROP COLUMN merchant_id')
                db.execute('ALTER TABLE admin_audit DROP COLUMN merchant_id')
            upgraded = ControlStore(path)
            self.assertEqual(upgraded.session(token)['user']['username'], original['user']['username'])
            self.assertIsNone(upgraded.session(token)['user']['merchant_id'])
            self.assertEqual(len(upgraded.audits({})), before)
            self.assertEqual(len(upgraded.merchants()), 2)
            self.assertEqual(len(upgraded.audits({}, 'alpha')), 1)

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
