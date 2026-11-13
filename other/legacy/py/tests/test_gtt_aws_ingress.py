"""Exercise the actual Nginx ALB ingress against isolated production-mode apps."""
import http.client
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.parse import parse_qs, urlsplit

from deploy.gttgames.aws.render_nginx import render
from py.merchant.common import encode, signed_headers
from py.merchant.deployment import Deployment
from py.tests import test_gtt_admin as fixtures

ROOT = Path(__file__).absolute().parents[2]
NGINX = shutil.which('nginx') or str(ROOT / 'diagnostics/nginx-validation/nginx-1.30.6/nginx.exe')


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


@unittest.skipUnless(Path(NGINX).is_file(), 'Nginx binary required for ingress integration checks')
class AwsIngressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = fixtures.GTTAdminTests()
        cls.qa.setUp()
        cls.qa.tenant_accounts()
        cls.config = json.loads((ROOT / 'deploy/gttgames/production.json').read_bytes())
        cls.qa.gateway.deployment = Deployment(cls.config)
        cls.qa.service.play_origin = cls.config['public_origins']['play']
        cls.qa.admin.deployment = Deployment(cls.config)
        cls.qa.admin.app.gateway_origin = cls.config['public_origins']['api']
        cls.qa.admin.app.play_origin = cls.config['public_origins']['play']
        (ROOT / 'diagnostics').mkdir(exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(prefix='aws-ingress-', dir=ROOT / 'diagnostics')
        cls.folder = Path(cls.temporary.name)
        (cls.folder / 'logs').mkdir()
        (cls.folder / 'temp').mkdir()
        cls.gateway_port, cls.console_port = free_port(), free_port()
        text = render().replace('listen 8080', 'listen 127.0.0.1:' + str(cls.gateway_port))
        text = text.replace('listen 8081', 'listen 127.0.0.1:' + str(cls.console_port))
        text = text.replace('127.0.0.1:8110', '127.0.0.1:' + str(cls.qa.gateway.server_port))
        text = text.replace('127.0.0.1:8112', '127.0.0.1:' + str(cls.qa.admin.server_port))
        text = text.replace('/www/wwwlogs/gtt-alb-access.log', (cls.folder / 'logs/access.log').as_posix())
        text = text.replace('/dev/null', (cls.folder / 'logs/request-errors.log').as_posix())
        (cls.folder / 'ingress.conf').write_text(text, encoding='utf-8', newline='\n')
        (cls.folder / 'nginx.conf').write_text(
            'worker_processes 1;\nerror_log "' + (cls.folder / 'logs/nginx-errors.log').as_posix() + '" crit;\n'
            'pid "' + (cls.folder / 'nginx.pid').as_posix() + '";\nevents { worker_connections 128; }\n'
            'http { include "' + (cls.folder / 'ingress.conf').as_posix() + '"; }\n', encoding='utf-8', newline='\n')
        cls.command = [NGINX, '-p', cls.folder.as_posix() + '/', '-c', (cls.folder / 'nginx.conf').as_posix()]
        cls.flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        syntax = subprocess.run(cls.command + ['-t'], capture_output=True, text=True, creationflags=cls.flags)
        if syntax.returncode:
            cls.qa.tearDown()
            cls.temporary.cleanup()
            raise AssertionError(syntax.stderr)
        cls.process = subprocess.Popen(cls.command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=cls.flags)
        for _ in range(50):
            try:
                with socket.create_connection(('127.0.0.1', cls.gateway_port), timeout=.1):
                    break
            except OSError:
                time.sleep(.1)
        else:
            cls.tearDownClass()
            raise AssertionError('Nginx did not start')

    @classmethod
    def tearDownClass(cls):
        if cls.process.poll() is None:
            subprocess.run(cls.command + ['-s', 'quit'], capture_output=True, creationflags=cls.flags)
            try:
                cls.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                cls.process.terminate()
                cls.process.wait(timeout=5)
        cls.qa.tearDown()
        cls.temporary.cleanup()

    def request(self, role, path='/', body=None, headers=None, trusted=True):
        port = self.console_port if role in ('merchant', 'admin', 'console-health') else self.gateway_port
        host = '127.0.0.1:' + str(port) if role.endswith('-health') else role + '.gttgames.com'
        fields = {'Host': host}
        if trusted:
            fields.update({'X-GTT-Client-IP': '198.51.100.20', 'X-Forwarded-Proto': 'https'})
        fields.update(headers or {})
        conn = http.client.HTTPConnection('127.0.0.1', port, timeout=15)
        try:
            conn.request('POST' if body is not None else 'GET', path, body=body, headers=fields)
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def test_target_group_health_reaches_both_apps_without_public_host(self):
        for role, service in [('gateway-health', 'gtt-gateway'), ('console-health', 'gtt-admin')]:
            code, _, body = self.request(role, '/health', trusted=False)
            self.assertEqual(code, 200)
            self.assertIn(service, body.decode())
        for role in ('play', 'api', 'merchant', 'admin'):
            self.assertEqual(self.request(role, '/health')[0], 404)

    def test_untrusted_proxy_metadata_is_rejected(self):
        self.assertEqual(self.request('merchant', '/', trusted=False)[0], 403)
        self.assertEqual(self.request('merchant', '/', headers={'X-Forwarded-Proto': 'http'})[0], 403)

    def test_console_login_has_secure_cookie_and_preserves_namespace_isolation(self):
        for role, name in [('merchant', 'alpha'), ('admin', 'admin')]:
            payload = encode({'username': name, 'password': fixtures.PASSWORD}).encode()
            code, headers, body = self.request(role, '/api/' + role + '/login', payload,
                {'Content-Type': 'application/json', 'Origin': 'https://' + role + '.gttgames.com'})
            self.assertEqual(code, 200, body)
            cookie = headers['Set-Cookie']
            for flag in ('__Host-', 'Secure', 'HttpOnly', 'SameSite=Strict', 'Path=/'):
                self.assertIn(flag, cookie)
            self.assertNotIn('Domain=', cookie)
            audit = self.qa.control.audits({'action': 'auth.login'})
            self.assertTrue(audit)
            self.assertEqual(audit[0]['details']['remote'], '198.51.100.20')
            cookie = cookie.split(';', 1)[0]
            self.assertEqual(self.request(role, '/api/' + role + '/me', headers={'Cookie': cookie})[0], 200)
        self.assertEqual(self.request('merchant', '/api/admin/me')[0], 404)
        self.assertEqual(self.request('admin', '/api/merchant/me')[0], 404)
        self.assertEqual(self.request('play', '/gtt/v1/games/list', b'{}')[0], 404)
        self.assertEqual(self.request('merchant', '/api/merchant/login', b'{}', {
            'Content-Type': 'application/json', 'Origin': 'https://admin.gttgames.com'})[0], 403)

    def test_hmac_launch_and_player_wallet_keep_original_body_host_and_session(self):
        path = '/gtt/v1/games/launch'
        payload = encode({'player_id': 'same-player', 'game_id': 1, 'language': 'en'}).encode()
        secret = self.qa.control.merchant('alpha', private=True)['merchant_secret']
        headers = signed_headers('alpha', secret, path, payload)
        code, _, body = self.request('api', path, payload, headers)
        self.assertEqual(code, 201, body)
        launch = json.loads(body)['data']['launch_url']
        self.assertTrue(launch.startswith('https://play.gttgames.com/?'))
        token = parse_qs(urlsplit(launch).query)['ops'][0]
        code, headers, body = self.request('play', '/api/v1/wallet?probe=' + token,
            headers={'Authorization': 'Bearer ' + token})
        self.assertEqual(code, 200, body)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertNotIn(token, (self.folder / 'logs/access.log').read_text())


if __name__ == '__main__':
    unittest.main()
