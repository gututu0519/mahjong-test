import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from server.core.contracts import ServiceError
from server.merchant.common import encode, signed_headers
from server.merchant.deployment import Deployment, public_origin
from server.merchant.sandbox import load_config
from server.tests import test_gtt_admin as fixtures

ROOT = Path(__file__).resolve().parents[2]


def production():
    return json.loads((ROOT / 'deploy/gttgames/production.json').read_bytes())


class DeploymentValidationTests(unittest.TestCase):
    def test_invalid_origins_and_proxy_trust_are_rejected(self):
        for origin in ('http://api.gttgames.com', 'https://name:password@api.gttgames.com',
                       'https://api.gttgames.com/path', 'https://api.gttgames.com?x=1',
                       'https://API.gttgames.com', 'https://bad host.example', 'https://a..example'):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                public_origin(origin)
        config = production()
        with self.assertRaises(ValueError):
            Deployment({**config, 'trusted_proxy_ips': ['0.0.0.0/0']})
        with self.assertRaises(ValueError):
            Deployment({**config, 'trusted_proxy_ips': ['203.0.113.1']})
        with self.assertRaises(ValueError):
            Deployment({**config, 'public_origins': {'api': 'https://api.gttgames.com'}})
        deployment = Deployment(config)
        handler = SimpleNamespace(headers={'Host': 'api.gttgames.com', 'X-Forwarded-Proto': 'https'},
                                  path='/gtt/v1/games/list', command='POST', client_address=('203.0.113.2', 1),
                                  server=SimpleNamespace(server_port=8110))
        with self.assertRaises(ServiceError) as rejected:
            deployment.guard(handler, 'gateway')
        self.assertEqual(rejected.exception.code, 'PROXY_REJECTED')

    def test_production_load_does_not_create_demo_merchants(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = {**production(), 'merchant_database': str(root / 'merchants.sqlite3'),
                      'game_database': str(root / 'gtt.sqlite3'), 'bootstrap_directory': str(root),
                      'log_directory': str(root / 'logs')}
            path = root / 'production.json'
            path.write_text(json.dumps(config))
            loaded, store = load_config(path)
            self.assertEqual(store.merchants(), [])
            self.assertEqual(loaded['gateway_origin'], 'https://api.gttgames.com')
            path.write_text(json.dumps({**config, 'sandbox_player': 'should-not-exist'}))
            with self.assertRaises(ValueError):
                load_config(path)


class PublicDomainHTTPTests(unittest.TestCase):
    def setUp(self):
        self.qa = fixtures.GTTAdminTests()
        self.qa.setUp()
        self.qa.tenant_accounts()
        self.config = production()
        self.qa.gateway.deployment = Deployment(self.config)
        self.qa.service.play_origin = self.config['public_origins']['play']
        self.qa.admin.deployment = Deployment(self.config)
        self.qa.admin.app.gateway_origin = self.config['public_origins']['api']
        self.qa.admin.app.play_origin = self.config['public_origins']['play']

    def tearDown(self):
        self.qa.tearDown()

    def headers(self, role, **extra):
        return {'Host': urlsplit(self.config['public_origins'][role]).netloc,
                'X-Forwarded-Proto': 'https', **extra}

    def login(self, role='merchant'):
        name = 'alpha' if role == 'merchant' else 'admin'
        code, result, headers = self.qa.request('/api/' + role + '/login',
            {'username': name, 'password': fixtures.PASSWORD}, user=None,
            headers=self.headers(role, **{'Origin': self.config['public_origins'][role], 'X-Real-IP': '198.51.100.20'}))
        self.assertEqual(code, 200, result)
        self.qa.sessions[role] = (headers['Set-Cookie'].split(';', 1)[0], result['data'])
        return headers['Set-Cookie']

    def test_console_root_runtime_and_cookie_isolation(self):
        for role in ('merchant', 'admin'):
            cookie = self.login(role)
            self.assertTrue(cookie.startswith('__Host-gtt_' + role + '_session='))
            for flag in ('Secure', 'HttpOnly', 'SameSite=Strict', 'Path=/'):
                self.assertIn(flag, cookie)
            self.assertNotIn('Domain=', cookie)
            self.assertEqual(self.qa.request('/', user=role, headers=self.headers(role), method='GET')[0], 200)
            code, runtime, _ = self.qa.request('/deployment.json', user=role, headers=self.headers(role), method='GET')
            self.assertEqual(code, 200)
            self.assertEqual(runtime['data']['portal'], role)
            self.assertEqual(runtime['data']['merchant_url'], 'https://merchant.gttgames.com/')
            self.assertNotIn('database', encode(runtime))
            self.assertEqual(self.qa.request('/api/' + role + '/me', user=role, headers=self.headers(role), method='GET')[0], 200)
            other = 'admin' if role == 'merchant' else 'merchant'
            self.assertEqual(self.qa.request('/api/' + other + '/me', user=role, headers=self.headers(role), method='GET')[0], 404)
        self.assertEqual(self.qa.request('/api/merchant/overview', user='merchant', headers=self.headers('merchant', **{'X-GTT-CSRF': ''}))[0], 403)
        code, _, headers = self.qa.request('/api/merchant/logout', user='merchant', headers=self.headers('merchant'))
        self.assertEqual(code, 200)
        self.assertIn('Max-Age=0; Secure', headers['Set-Cookie'])

    def test_proxy_scheme_host_and_origin_checks(self):
        self.assertEqual(self.qa.request('/deployment.json', method='GET', user=None)[0], 403)
        self.assertEqual(self.qa.request('/health', method='GET', user=None)[0], 200)
        for headers in (self.headers('merchant', **{'X-Forwarded-Proto': 'http'}),
                        self.headers('merchant', **{'Origin': 'https://admin.gttgames.com'}),
                        self.headers('api'), {'Host': 'evil.example', 'X-Forwarded-Proto': 'https'}):
            self.assertEqual(self.qa.request('/deployment.json', method='GET', headers=headers, user=None)[0], 403)

    def test_launch_returns_play_url_and_player_requests_stay_on_play(self):
        path = '/gtt/v1/games/launch'
        payload = {'player_id': 'same-player', 'game_id': 1, 'language': 'en'}
        secret = self.qa.control.merchant('alpha', private=True)['merchant_secret']
        signed = signed_headers('alpha', secret, path, encode(payload).encode())
        code, result, _ = self.qa.request(path, payload, user=None,
            headers={**signed, **self.headers('api')}, port=self.qa.gateway.server_port)
        self.assertEqual(code, 201, result)
        url = result['data']['launch_url']
        self.assertTrue(url.startswith('https://play.gttgames.com/?'))
        token = parse_qs(urlsplit(url).query)['ops'][0]
        self.assertEqual(self.qa.request('/?'+urlsplit(url).query, method='GET', user=None,
            headers=self.headers('play'), port=self.qa.gateway.server_port)[0], 200)
        code, wallet, headers = self.qa.request('/api/v1/wallet', method='GET', user=None,
            headers=self.headers('play', **{'Authorization': 'Bearer ' + token, 'Origin': 'https://play.gttgames.com'}), port=self.qa.gateway.server_port)
        self.assertEqual(code, 200)
        self.assertEqual(wallet['balance_minor'], 200000)
        self.assertEqual(headers['Referrer-Policy'], 'no-referrer')
        self.assertEqual(self.qa.request('/gtt/v1/games/list', {}, user=None,
            headers=self.headers('play'), port=self.qa.gateway.server_port)[0], 404)
        self.assertEqual(self.qa.request('/', method='GET', user=None,
            headers=self.headers('api'), port=self.qa.gateway.server_port)[0], 404)

    def test_documents_export_production_api_and_play_origins(self):
        self.login()
        code, result, _ = self.qa.request('/api/merchant/integration/docs', user='merchant', headers=self.headers('merchant'))
        self.assertEqual(code, 200)
        self.assertEqual(result['data']['play_origin'], 'https://play.gttgames.com')
        launch = next(endpoint for endpoint in result['data']['endpoints'] if endpoint['id'] == 'games-launch')
        self.assertTrue(launch['response_example']['data']['launch_url'].startswith('https://play.gttgames.com/'))
        code, spec, _ = self.qa.request('/api/merchant/integration/openapi.json', user='merchant', method='GET', headers=self.headers('merchant'))
        self.assertEqual(code, 200)
        self.assertEqual(spec['servers'][0]['url'], 'https://api.gttgames.com')
        self.assertEqual(spec['x-gtt-play-origin'], 'https://play.gttgames.com')


if __name__ == '__main__':
    unittest.main()
