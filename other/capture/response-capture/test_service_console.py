"""独立服务控制台的 HTTP 与浏览器回归，所有服务均使用隔离夹具。"""
import asyncio
import json
from pathlib import Path
import re
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import unittest

import control_server
from app import launch_browser
from playwright.async_api import async_playwright
from service_registry import build_registry


class FixtureManager:
    def __init__(self, capture_port):
        self.capture_port = capture_port
        self.calls = []
        self.prepares, self.confirmations, self.prepared = [], [], {}
        self.failure = None

    def snapshot(self):
        return {'services':[{'id':'fixed.capture', 'name':'抓取服务', 'status':'stopped'}],
                'categories':[], 'instances':[]}

    def prepare(self, identifier, action):
        self.prepares.append((action, identifier))
        return self.prepared.get((action, identifier), {'requires_confirmation':False, 'warnings':[],
                                                       'targets':[], 'execution_label':'正常操作'})

    def start(self, identifier, confirmation_id=None):
        self.calls.append(('start', identifier))
        if confirmation_id is not None:
            self.confirmations.append(('start', identifier, confirmation_id))
        if self.failure:
            raise ValueError(self.failure)
        return {'ok':True, 'state':'starting', 'id':identifier}

    def stop(self, identifier, confirmation_id=None):
        self.calls.append(('stop', identifier))
        if confirmation_id is not None:
            self.confirmations.append(('stop', identifier, confirmation_id))
        return {'ok':True, 'state':'stopped', 'id':identifier}

    def logs(self, identifier):
        self.calls.append(('logs', identifier))
        return {'id':identifier, 'text':'仅包含本次夹具日志'}


class FixtureOriginals:
    def catalog(self):
        return {'games':[], 'errors':[]}


class FixtureCleanup:
    def __init__(self):
        self.calls = []

    def options(self, origin):
        self.calls.append(('options', origin))
        return {'items':[], 'current_capture_port':49123}

    def prepare(self, keep_ids, origin):
        self.calls.append(('prepare', keep_ids, origin))
        return {'requires_confirmation':True, 'confirmation_id':'c'*64, 'expires_at':9999999999,
                'targets':[], 'warnings':[], 'close_count':0, 'kept_count':len(keep_ids), 'keep_ids':keep_ids}

    def execute(self, token, origin):
        self.calls.append(('execute', token, origin))
        return {'ok':True, 'results':[], 'submitted_count':0, 'failed_count':0, 'skipped_count':0}


class FixtureCapture(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, status, body, content_type='application/json', extra=None):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.server.visits.append(('GET', self.path))
        if self.path == '/':
            document = "<!doctype html><title>Response Capture</title><script>const $=id=>document.getElementById(id), token='" + self.server.token + "';</script>"
            return self.respond(200, document.encode(), 'text/html; charset=utf-8')
        if self.path.endswith('/download'):
            return self.respond(200, b'PK\x03\x04fixture-archive', 'application/zip',
                                {'Content-Disposition':'attachment; filename="fixture.zip"'})
        return self.respond(200, [{'id':'a'*32, 'state':'completed'}])

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.visits.append(('POST', self.path))
        self.server.posts.append({'path':self.path, 'body':body, 'token':self.headers.get('X-Capture-Token'),
                                  'origin':self.headers.get('Origin'), 'host':self.headers.get('Host')})
        if self.headers.get('X-Capture-Token') != self.server.token:
            return self.respond(403, {'error':'夹具令牌已经变更'})
        return self.respond(200, {'ok':True, 'id':body.get('id')})


class ServiceConsoleHttpTest(unittest.TestCase):
    def setUp(self):
        self.capture = ThreadingHTTPServer(('127.0.0.1', 0), FixtureCapture)
        self.capture.token, self.capture.visits, self.capture.posts = 'first-fixture-token', [], []
        self.capture_thread = threading.Thread(target=self.capture.serve_forever, daemon=True)
        self.capture_thread.start()
        self.capture_closed = False
        self.manager = FixtureManager(self.capture.server_port)
        self.server = control_server.create_server(address=('127.0.0.1', 0), manager=self.manager,
                                                   capture_port=self.capture.server_port,
                                                   capture_origin_verifier=lambda port: port == self.capture.server_port)
        self.server.original_games = FixtureOriginals()
        self.server.cleanup = FixtureCleanup()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.close_capture()

    def close_capture(self):
        if not self.capture_closed:
            self.capture.shutdown()
            self.capture.server_close()
            self.capture_thread.join(timeout=2)
            self.capture_closed = True

    def request(self, method, path, body=None, headers=None):
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        supplied = {'Content-Type':'application/json', 'X-Capture-Token':self.server.token}
        supplied.update(headers or {})
        try:
            connection.request(method, path, None if body is None else json.dumps(body), supplied)
            response = connection.getresponse()
            raw = response.read()
            mime = response.getheader('Content-Type', '')
            return response.status, json.loads(raw) if 'application/json' in mime else raw, dict(response.getheaders())
        finally:
            connection.close()

    def test_home_and_control_remain_available_after_capture_stops(self):
        status, home, _ = self.request('GET', '/')
        self.assertEqual(200, status)
        self.assertIn(b'data-service-console="1"', home)
        self.assertIn(b'/service-console.js', home)
        self.close_capture()
        self.assertEqual(200, self.request('GET', '/')[0])
        self.assertEqual(200, self.request('GET', '/api/services')[0])
        self.assertEqual(200, self.request('GET', '/api/original-games')[0])
        status, result, _ = self.request('POST', '/api/services/start', {'id':'fixed.capture'})
        self.assertEqual(200, status)
        self.assertEqual('starting', result['state'])
        self.assertEqual([('start', 'fixed.capture')], self.manager.calls)

    def test_mutations_reject_foreign_origins_hosts_and_missing_tokens(self):
        for headers in ({'Origin':'https://outside.invalid'}, {'Origin':'null'},
                        {'Host':'outside.invalid'}, {'X-Capture-Token':''},
                        {'Origin':self.origin, 'Sec-Fetch-Site':'cross-site'}):
            with self.subTest(headers=headers):
                self.assertEqual(403, self.request('POST', '/api/services/stop', {'id':'fixed.capture'}, headers)[0])
        self.assertEqual([], self.manager.calls)
        status, result, _ = self.request('POST', '/api/services/stop', {'id':'fixed.capture'},
                                         {'Origin':self.origin, 'Sec-Fetch-Site':'same-origin'})
        self.assertEqual(200, status)
        self.assertEqual('stopped', result['state'])

    def test_control_only_accepts_service_ids_and_reports_errors(self):
        for body in ([], {'path':'C:\\Windows'}, {'id':'fixed.capture', 'command':'arbitrary'}, {'id':None}):
            with self.subTest(body=body):
                self.assertEqual(400, self.request('POST', '/api/services/start', body)[0])
        self.assertEqual([], self.manager.calls)
        self.manager.failure = '该端口由其他聊天使用'
        status, result, _ = self.request('POST', '/api/services/start', {'id':'fixed.capture'})
        self.assertEqual(400, status)
        self.assertIn('其他聊天', result['error'])
        status, result, _ = self.request('GET', '/api/services/logs?id=fixed.capture')
        self.assertEqual(200, status)
        self.assertIn('夹具日志', result['text'])

    def test_prepare_only_previews_and_execution_forwards_confirmation(self):
        identifier = 'external.fixture-node'
        self.manager.prepared[('stop', identifier)] = {
            'requires_confirmation':True, 'confirmation_id':'a'*64, 'expires_at':9999999999,
            'execution_label':'强制结束指定进程', 'warnings':['此操作将停止其他聊天正在使用的服务。'],
            'targets':[{'id':identifier, 'name':'其他工作区服务', 'pid':971001,
                        'created':'2026-11-24T01:00:00+00:00', 'port':18119,
                        'cwd':'C:/fixture/其他工作区', 'mode':'force'}],
        }
        status, result, _ = self.request('POST', '/api/services/prepare', {'id':identifier, 'action':'stop'})
        self.assertEqual(status, 200)
        self.assertTrue(result['requires_confirmation'])
        self.assertEqual(result['targets'][0]['pid'], 971001)
        self.assertEqual(self.manager.prepares, [('stop', identifier)])
        self.assertFalse(self.manager.calls)
        status, _, _ = self.request('POST', '/api/services/stop',
                                     {'id':identifier, 'confirmation_id':result['confirmation_id']})
        self.assertEqual(status, 200)
        self.assertEqual(self.manager.confirmations, [('stop', identifier, 'a'*64)])
        self.assertEqual(self.manager.calls, [('stop', identifier)])

    def test_prepare_requires_origin_token_and_strict_action_shape(self):
        data = {'id':'fixed.capture', 'action':'stop'}
        for headers in ({'Origin':'https://outside.invalid'}, {'X-Capture-Token':''}, {'Host':'outside.invalid'}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request('POST', '/api/services/prepare', data, headers)[0], 403)
        for body in ([], {'id':'fixed.capture'}, {'id':'fixed.capture', 'action':'restart'},
                     {'id':None, 'action':'start'}, {'id':'fixed.capture', 'action':'start', 'command':'arbitrary'}):
            with self.subTest(body=body):
                self.assertEqual(self.request('POST', '/api/services/prepare', body)[0], 400)
        self.assertFalse(self.manager.prepares)
        self.assertFalse(self.manager.calls)
        origin = 'http://127.0.0.1:' + str(self.capture.server_port)
        status, _, headers = self.request('POST', '/api/services/prepare', data, {'Origin':origin})
        self.assertEqual(status, 200)
        self.assertEqual(headers.get('Access-Control-Allow-Origin'), origin)
        self.assertFalse(self.manager.calls)

    def test_confirmation_payload_cannot_add_arbitrary_execution_parameters(self):
        for confirmation in (None, 123, [], {}):
            with self.subTest(confirmation=confirmation):
                self.assertEqual(self.request('POST', '/api/services/stop',
                    {'id':'external.fixture-node', 'confirmation_id':confirmation})[0], 400)
        self.assertEqual(self.request('POST', '/api/services/start',
            {'id':'fixed.gateway', 'confirmation_id':'fixture-token', 'command':'arbitrary'})[0], 400)
        self.assertFalse(self.manager.calls)

    def test_cleanup_forwards_actual_browser_origin_and_only_executes_after_token(self):
        origin = 'http://127.0.0.1:' + str(self.capture.server_port)
        self.manager.capture_port = 49123
        status, _, headers = self.request('POST', '/api/services/cleanup/options', {}, {'Origin':origin})
        self.assertEqual(status, 200)
        self.assertEqual(headers.get('Access-Control-Allow-Origin'), origin)
        keep = ['external.current-capture', 'advanced.postgres']
        status, prepared, _ = self.request('POST', '/api/services/cleanup/prepare', {'keep_ids':keep}, {'Origin':origin})
        self.assertEqual(status, 200)
        self.assertEqual(self.server.cleanup.calls, [('options',origin), ('prepare',keep,origin)])
        self.assertFalse(self.manager.calls)
        status, _, _ = self.request('POST', '/api/services/cleanup',
                                     {'confirmation_id':prepared['confirmation_id']}, {'Origin':origin})
        self.assertEqual(status, 200)
        self.assertEqual(self.server.cleanup.calls[-1], ('execute','c'*64,origin))
        self.assertFalse(self.manager.calls)

    def test_cleanup_rejects_untrusted_origin_and_arbitrary_target_parameters(self):
        for path, body in [('/api/services/cleanup/options',{}),
                           ('/api/services/cleanup/prepare',{'keep_ids':[]}),
                           ('/api/services/cleanup',{'confirmation_id':'c'*64})]:
            with self.subTest(path=path):
                self.assertEqual(self.request('POST',path,body,{'Origin':'http://outside.invalid'})[0],403)
                self.assertEqual(self.request('POST',path,body,{'X-Capture-Token':''})[0],403)
        for path, body in [('/api/services/cleanup/options',{'path':'C:/Windows'}),
                           ('/api/services/cleanup/prepare',{'keep_ids':'everything'}),
                           ('/api/services/cleanup/prepare',{'keep_ids':[None]}),
                           ('/api/services/cleanup/prepare',{'keep_ids':[],'command':'arbitrary'}),
                           ('/api/services/cleanup',{'confirmation_id':'c'*64,'ids':['external.any']}),
                           ('/api/services/cleanup',{})]:
            with self.subTest(body=body):
                self.assertEqual(self.request('POST',path,body)[0],400)
        self.assertFalse(self.server.cleanup.calls)
        self.assertFalse(self.manager.calls)

    def test_proxy_rewrites_capture_credentials_and_refreshes_rotated_token(self):
        for token in ('first-fixture-token', 'second-fixture-token'):
            self.capture.token = token
            status, result, _ = self.request('POST', '/api/stop', {'id':'a'*32}, {'Origin':self.origin})
            self.assertEqual(200, status)
            self.assertTrue(result['ok'])
            request = self.capture.posts[-1]
            self.assertEqual(token, request['token'])
            self.assertEqual('127.0.0.1:' + str(self.capture.server_port), request['host'])
            self.assertEqual('http://127.0.0.1:' + str(self.capture.server_port), request['origin'])
        self.assertGreaterEqual(sum(path == '/' for method, path in self.capture.visits), 2)

    def test_proxy_download_preserves_archive_and_response_headers(self):
        status, body, headers = self.request('GET', '/api/sessions/' + 'a'*32 + '/download')
        self.assertEqual(200, status)
        self.assertEqual(b'PK\x03\x04fixture-archive', body)
        self.assertEqual('application/zip', headers['Content-Type'])
        self.assertEqual('attachment; filename="fixture.zip"', headers['Content-Disposition'])

    def test_verified_capture_origin_can_bootstrap_preflight_and_start(self):
        origin = 'http://127.0.0.1:' + str(self.capture.server_port)
        status, body, headers = self.request('GET', '/api/services/bootstrap', headers={'Origin':origin})
        self.assertEqual(200, status)
        self.assertEqual(self.server.token, body['token'])
        self.assertEqual(origin, headers.get('Access-Control-Allow-Origin'))
        status, _, headers = self.request('OPTIONS', '/api/services/start', headers={
            'Origin':origin, 'Access-Control-Request-Method':'POST',
            'Access-Control-Request-Headers':'content-type,x-capture-token'})
        self.assertIn(status, (200, 204))
        self.assertEqual(origin, headers.get('Access-Control-Allow-Origin'))
        status, _, headers = self.request('POST', '/api/services/start', {'id':'fixed.capture'},
                                          {'Origin':origin, 'Sec-Fetch-Site':'same-site'})
        self.assertEqual(200, status)
        self.assertEqual(origin, headers.get('Access-Control-Allow-Origin'))
        self.assertEqual([('start', 'fixed.capture')], self.manager.calls)

    def test_unverified_origins_cannot_obtain_token_or_cors_permission(self):
        wrong_port = next(port for port in range(49001, 49010)
                          if port not in (self.capture.server_port, self.server.server_port))
        origins = ['http://127.0.0.1:' + str(wrong_port), 'https://127.0.0.1:' + str(self.capture.server_port),
                   'http://outside.invalid:' + str(self.capture.server_port), 'null']
        for origin in origins:
            for method, path, body in [('GET', '/api/services/bootstrap', None),
                                       ('OPTIONS', '/api/services/stop', None),
                                       ('POST', '/api/services/stop', {'id':'fixed.capture'})]:
                with self.subTest(origin=origin, method=method):
                    status, result, headers = self.request(method, path, body, {'Origin':origin})
                    self.assertEqual(403, status)
                    self.assertNotIn('Access-Control-Allow-Origin', headers)
                    self.assertNotIn(self.server.token, str(result))
        self.assertFalse(self.manager.calls)

    def test_valid_capture_origin_cannot_cross_origin_proxy_or_original_api(self):
        origin = 'http://127.0.0.1:' + str(self.capture.server_port)
        for method, path, body in [('GET', '/api/sessions', None), ('POST', '/api/stop', {'id':'a'*32}),
                                   ('GET', '/api/original-games', None),
                                   ('POST', '/api/original-games/preview', {'id':'anything'})]:
            with self.subTest(path=path):
                status, _, headers = self.request(method, path, body, {'Origin':origin})
                self.assertEqual(403, status)
                self.assertNotIn('Access-Control-Allow-Origin', headers)
        self.assertFalse(self.capture.posts)


class CaptureOriginIdentityTest(unittest.TestCase):
    def setUp(self):
        self.manager = FixtureManager(49123)
        self.manager.original_games = FixtureOriginals()
        self.snapshot_error = ''
        self.manager.snapshot = lambda: {'services':[], 'error':self.snapshot_error}
        self.manager.listeners = [{'pid':931001, 'port':49123, 'address':'127.0.0.1'}]
        self.manager.processes = {
            931001: {'pid':931001, 'parent':931000, 'created':'2026-11-24T02:00:00+00:00',
                     'command':['python.exe', 'app.py', '--port', '49123']},
            931000: {'pid':931000, 'created':'2026-11-24T01:00:00+00:00',
                     'executable':str(control_server.ROOT / '.venv/Scripts/python.exe')},
        }
        self.server = control_server.create_server(('127.0.0.1', 0), manager=self.manager, capture_port=49123)
        self.addCleanup(self.server.server_close)

    def test_relative_capture_requires_same_workspace_parent_and_creation_order(self):
        self.assertTrue(self.server.capture_origin_verifier(49123))
        parent = self.manager.processes[931000]
        parent['executable'] = str(control_server.ROOT.parent / 'other-worktree/.venv/Scripts/python.exe')
        self.assertFalse(self.server.capture_origin_verifier(49123))
        parent['executable'] = str(control_server.ROOT / '.venv/Scripts/python.exe')
        parent['created'] = '2026-11-24T03:00:00+00:00'
        self.assertFalse(self.server.capture_origin_verifier(49123))
        parent.pop('created')
        self.assertFalse(self.server.capture_origin_verifier(49123))

    def test_absolute_capture_requires_exact_entry_listener_and_fresh_inventory(self):
        process = self.manager.processes[931001]
        process['command'] = ['python.exe', str(control_server.ROOT / 'app.py')]
        self.assertTrue(self.server.capture_origin_verifier(49123))
        self.assertFalse(self.server.capture_origin_verifier(49124))
        process['command'] = ['python.exe', str(control_server.ROOT.parent / 'other-worktree/app.py')]
        self.assertFalse(self.server.capture_origin_verifier(49123))
        process['command'] = ['python.exe', str(control_server.ROOT / 'app.py')]
        self.snapshot_error = '实时快照失败'
        self.assertFalse(self.server.capture_origin_verifier(49123))
        self.snapshot_error = ''
        self.manager.listeners[0]['pid'] = 999999
        self.assertFalse(self.server.capture_origin_verifier(49123))

    def test_loaded_capture_page_can_restart_after_stop_but_reused_port_revokes_origin(self):
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        headers = {'Origin':'http://127.0.0.1:49123'}
        request = lambda method, path, body=None: ServiceConsoleHttpTest.request(self, method, path, body, headers)
        try:
            self.assertEqual(request('GET', '/api/services/bootstrap')[0], 200)
            self.manager.listeners = []
            self.manager.processes = {}
            self.assertEqual(request('GET', '/api/services/bootstrap')[0], 200)
            self.assertEqual(request('POST', '/api/services/start', {'id':'fixed.capture'})[0], 200)
            self.assertEqual(self.manager.calls, [('start', 'fixed.capture')])
            self.manager.listeners = [{'pid':939999, 'port':49123, 'address':'127.0.0.1'}]
            self.manager.processes = {939999:{'pid':939999, 'command':['python', 'unrelated-server.py']}}
            status, _, response_headers = request('GET', '/api/services/bootstrap')
            self.assertEqual(status, 403)
            self.assertNotIn('Access-Control-Allow-Origin', response_headers)
            self.manager.listeners = []
            self.assertEqual(request('GET', '/api/services/bootstrap')[0], 403)
            self.assertEqual(request('POST', '/api/services/start', {'id':'fixed.capture'})[0], 403)
            self.assertEqual(self.manager.calls, [('start', 'fixed.capture')])
        finally:
            self.server.shutdown()
            thread.join(timeout=2)


class ServiceConsoleBrowserTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.services = []
        for entry in build_registry(Path(__file__).resolve().parents[3]):
            readonly = entry['kind'] == 'readonly'
            self.services.append({**entry, 'status':'stopped', 'port':entry.get('default_port'),
                                  'game_code':entry.get('code'), 'can_start':not readonly,
                                  'can_stop':False, 'can_logs':True})
        self.services += [dict(id='preview.first', name='原版试玩实例甲', category='original-previews',
                              status='running', port=49201, pid=7777, can_start=False, can_stop=True),
                          dict(id='preview.old', name='原版试玩实例乙', category='original-previews',
                              status='stopped', port=49202, pid=8888, can_start=True, can_stop=False)]
        self.actions, self.gates, self.failures, self.errors = [], {}, {}, []
        self.action_results = {}
        self.prepares, self.preparations, self.action_payloads = [], {}, []
        self.prepare_gates = {}
        self.cleanup_calls = []
        self.cleanup_options = {'items':[], 'current_capture_port':18095}
        self.cleanup_prepared = {'requires_confirmation':True, 'confirmation_id':'e'*64,
                                 'warnings':[], 'targets':[], 'keep_ids':[], 'close_count':0, 'kept_count':0}
        self.cleanup_result = {'ok':True, 'results':[], 'submitted_count':0, 'failed_count':0, 'skipped_count':0}
        self.log_gates, self.log_finished = {}, {}
        self.embedded, self.api_requests = False, []
        self.fixture_origin = 'http://127.0.0.1:18095'
        self.pw = await async_playwright().start()
        self.addAsyncCleanup(self.pw.stop)
        self.browser = await launch_browser(self.pw, headless=True)
        self.addAsyncCleanup(self.browser.close)
        self.page = await self.browser.new_page(viewport={'width':1280, 'height':900})
        self.page.set_default_timeout(7000)
        self.page.on('pageerror', lambda error:self.errors.append(str(error)))
        await self.page.route('**/*', self.route)

    async def route(self, route):
        from urllib.parse import parse_qs, urlsplit
        request = route.request
        url = urlsplit(request.url)
        if url.netloc not in ('127.0.0.1:18096', '127.0.0.1:18095', urlsplit(self.fixture_origin).netloc):
            return await route.abort()
        if url.path.startswith('/api/'):
            self.api_requests.append((url.netloc, request.method, url.path))
        async def fulfill(**options):
            options['headers'] = {'Access-Control-Allow-Origin':self.fixture_origin,
                                  'Access-Control-Allow-Methods':'GET, POST, OPTIONS',
                                  'Access-Control-Allow-Headers':'Content-Type, X-Capture-Token'}
            return await route.fulfill(**options)
        if request.method == 'OPTIONS':
            return await fulfill(status=204, body='')
        if url.path == '/':
            baseline = ''.join(re.findall(r'<style>.*?</style>', Path(__file__).with_name('index.html').read_text(encoding='utf-8'), re.S))
            root_attribute = '' if self.embedded else ' data-service-console="1"'
            asset_origin = 'http://127.0.0.1:18096' if self.embedded else ''
            page_token = 'fixture-capture-token' if self.embedded else 'fixture-console-token'
            body = ('<!doctype html><html'+root_attribute+'><head><meta charset="utf-8">'
                    '<meta name="viewport" content="width=device-width,initial-scale=1">'
                    + baseline +
                    '<link rel="stylesheet" href="'+asset_origin+'/service-console.css"><script defer src="'+asset_origin+'/service-console.js"></script>'
                    '</head><body><button id="outside-control">页面其他操作</button><section id="service-console"></section>'
                    '<script>const token="'+page_token+'";</script></body></html>')
            return await fulfill(content_type='text/html; charset=utf-8', body=body)
        if url.path in ('/service-console.js', '/service-console.css'):
            mime = 'text/javascript' if url.path.endswith('.js') else 'text/css'
            return await fulfill(content_type=mime+'; charset=utf-8',
                                       body=Path(__file__).with_name(url.path[1:]).read_bytes())
        if url.path == '/api/services/bootstrap':
            return await fulfill(json={'token':'fixture-console-token', 'control_port':18096})
        if url.path == '/api/services':
            return await fulfill(json={'version':1, 'services':self.services, 'categories':[], 'refreshing':False})
        if url.path == '/api/services/logs':
            identifier = parse_qs(url.query)['id'][0]
            if identifier in self.log_gates:
                await self.log_gates[identifier].wait()
            await fulfill(json={'text':'日志：'+identifier+'\npassword=[已隐藏]\nAuthorization: [已隐藏]'})
            if identifier in self.log_finished:
                self.log_finished[identifier].set()
            return
        if url.path == '/api/services/prepare':
            body = request.post_data_json
            action, identifier = body['action'], body['id']
            self.prepares.append((action, identifier))
            if (action, identifier) in self.prepare_gates:
                await self.prepare_gates[(action, identifier)].wait()
            return await fulfill(json=self.preparations.get((action, identifier),
                {'requires_confirmation':False, 'warnings':[], 'targets':[], 'execution_label':'正常操作'}))
        if url.path in ('/api/services/cleanup/options', '/api/services/cleanup/prepare', '/api/services/cleanup'):
            self.cleanup_calls.append((url.path, request.post_data_json))
            result = (self.cleanup_options if url.path.endswith('/options') else
                      self.cleanup_prepared if url.path.endswith('/prepare') else self.cleanup_result)
            return await fulfill(json=result)
        if url.path in ('/api/services/start', '/api/services/stop'):
            action = url.path.rsplit('/', 1)[-1]
            identifier = request.post_data_json['id']
            self.action_payloads.append(request.post_data_json)
            self.actions.append((action, identifier, request.headers.get('x-capture-token')))
            if (action, identifier) in self.gates:
                await self.gates[(action, identifier)].wait()
            if (action, identifier) in self.failures:
                return await fulfill(status=409, json={'error':self.failures[(action, identifier)]})
            if (action, identifier) in self.action_results:
                return await fulfill(json=self.action_results[(action, identifier)])
            available = self.services + [instance for s in self.services for instance in s.get('instances', [])]
            service = next(s for s in available if s['id'] == identifier)
            service.update(status='running' if action == 'start' else 'stopped',
                           can_start=action != 'start', can_stop=action == 'start')
            return await fulfill(json={'ok':True, 'id':identifier, 'state':service['status']})
        return await fulfill(status=404, json={'error':'夹具没有此接口'})

    async def open(self):
        await self.page.goto('http://127.0.0.1:18096/')
        await self.page.locator('#service-fixed [data-service-id]').first.wait_for()

    async def refresh_snapshot(self):
        async with self.page.expect_response(lambda response: response.url.endswith('/api/services')):
            await self.page.click('#service-refresh')
        await self.page.locator('#service-refresh:enabled').wait_for()

    async def test_access_addresses_distinguish_web_api_workers_and_stopped_services(self):
        gateway = next(s for s in self.services if s['id'] == 'fixed.gateway')
        gateway.update(status='running', can_start=False, can_stop=True, port=18110,
                       open_url='http://127.0.0.1:18110/')
        compute = next(s for s in self.services if s['id'] == 'compute.cash-mania')
        compute.update(status='running', can_start=False, can_stop=True, port=18233,
                       endpoint_url='http://127.0.0.1:18233/')
        worker = next(s for s in self.services if s['id'] == 'fixed.rtp')
        worker.update(status='running', can_start=False, can_stop=True, port=None, no_port=True)
        demo = next(s for s in self.services if s['id'] == 'demo.cash-mania')
        demo.update(status='stopped', open_url='http://127.0.0.1:18120/')
        preview = next(s for s in self.services if s['id'] == 'preview.first')
        preview.update(port=None, pid=None, can_stop=False, running_count=2, instances=[
            dict(id='preview.child-a', status='running', port=49201, open_url='http://127.0.0.1:49201/',
                 can_start=False, can_stop=True),
            dict(id='preview.child-b', status='running', port=49202, open_url='http://127.0.0.1:49202/',
                 can_start=False, can_stop=True),
        ])
        p = self.page
        await self.open()
        gateway_card = p.locator('#service-fixed [data-service-id="fixed.gateway"]')
        self.assertIn('访问地址：', await gateway_card.locator('.sc-address').inner_text())
        self.assertEqual('http://127.0.0.1:18110/', await gateway_card.locator('.sc-address a').get_attribute('href'))
        self.assertEqual('_blank', await gateway_card.locator('.sc-address a').get_attribute('target'))
        self.assertEqual(1, await gateway_card.locator('.sc-open').count())
        worker_card = p.locator('#service-fixed [data-service-id="fixed.rtp"]')
        self.assertEqual('无网页地址', await worker_card.locator('.sc-address').inner_text())
        self.assertEqual(0, await worker_card.locator('.sc-address a, .sc-open').count())
        await p.click('[data-service-category="game-compute"]')
        compute_row = p.locator('#service-rows [data-service-id="compute.cash-mania"]')
        self.assertIn('接口地址：', await compute_row.locator('.sc-address').inner_text())
        self.assertEqual('http://127.0.0.1:18233/', await compute_row.locator('.sc-address a').get_attribute('href'))
        self.assertEqual(0, await compute_row.locator('.sc-open').count())
        await p.keyboard.press('Escape')
        await p.click('[data-service-category="game-demos"]')
        demo_row = p.locator('#service-rows [data-service-id="demo.cash-mania"]')
        self.assertEqual(0, await demo_row.locator('.sc-address a, .sc-open').count())
        await p.keyboard.press('Escape')
        await p.click('[data-service-category="original-previews"]')
        preview_row = p.locator('#service-rows [data-service-id="preview.first"]')
        self.assertEqual('访问地址见下方各实例', await preview_row.locator('.sc-address').inner_text())
        self.assertEqual(0, await preview_row.locator('.sc-address a, .sc-open').count())
        for identifier, port in [('preview.child-a',49201), ('preview.child-b',49202)]:
            child = p.locator('#service-rows [data-service-id="'+identifier+'"]')
            self.assertEqual('http://127.0.0.1:'+str(port)+'/', await child.locator('.sc-address a').get_attribute('href'))
        await p.keyboard.press('Escape')
        await gateway_card.locator('[data-service-action="stop"]').click()
        await gateway_card.locator('.sc-state').filter(has_text='已停止').wait_for()
        self.assertEqual('http://127.0.0.1:18110/', gateway['open_url'])
        self.assertEqual(0, await gateway_card.locator('.sc-address a, .sc-open').count())
        self.assertEqual([], self.errors)

    async def test_pending_operation_tracks_requested_run_and_exact_stopped_instance(self):
        p = self.page
        gateway = next(s for s in self.services if s['id'] == 'fixed.gateway')
        prior = dict(id='run.previous', status='running', port=18110, pid=960001,
                     can_start=False, can_stop=True, logs_available=False)
        unrelated = dict(id='run.unrelated', status='running', port=18111, pid=960002,
                         can_start=False, can_stop=True, logs_available=False)
        target = dict(id='run.requested', status='starting', port=18112, pid=960003,
                      can_start=False, can_stop=False, logs_available=False)
        gateway.update(status='running', can_start=True, can_stop=True, instances=[prior], running_count=1)
        self.action_results[('start','fixed.gateway')] = {'ok':True, 'id':'fixed.gateway',
            'run_id':'requested', 'state':'starting', 'message':'已提交指定批次启动请求'}
        await self.open()
        card = p.locator('#service-fixed [data-service-id="fixed.gateway"]')
        await card.locator('[data-service-action="start"]').click()
        await card.get_by_text('已提交指定批次启动请求', exact=True).wait_for()
        self.assertIn('正在启动', await card.locator('.sc-state').inner_text())
        self.assertTrue(await card.locator('[data-service-action="start"]').is_disabled())
        gateway['instances'].append(unrelated)
        await self.refresh_snapshot()
        self.assertIn('正在启动', await card.locator('.sc-state').inner_text())
        gateway['instances'].append(target)
        await self.refresh_snapshot()
        self.assertIn('正在启动', await card.locator('.sc-state').inner_text())
        self.assertTrue(await card.locator('[data-service-action="start"]').is_disabled())
        target.update(status='running', can_stop=True)
        await self.refresh_snapshot()
        self.assertEqual('运行中', await card.locator('.sc-state').inner_text())
        self.assertTrue(await card.locator('[data-service-action="start"]').is_enabled())
        self.assertIn('服务已启动', await card.inner_text())
        self.action_results[('stop',target['id'])] = {'ok':True, 'id':target['id'],
            'state':'stopping', 'message':'已提交指定实例关闭请求'}
        await card.get_by_role('button', name='查看实例').click()
        row = p.locator('#service-rows [data-service-id="run.requested"]')
        await row.locator('[data-service-action="stop"]').click()
        await row.get_by_text('已提交指定实例关闭请求', exact=True).wait_for()
        unrelated['status'] = 'stopped'
        await p.keyboard.press('Escape')
        await self.refresh_snapshot()
        await card.get_by_role('button', name='查看实例').click()
        self.assertIn('正在停止', await row.locator('.sc-state').inner_text())
        self.assertTrue(await row.locator('[data-service-action="stop"]').is_disabled())
        target['status'] = 'stopping'
        await p.keyboard.press('Escape')
        await self.refresh_snapshot()
        await card.get_by_role('button', name='查看实例').click()
        self.assertIn('正在停止', await row.locator('.sc-state').inner_text())
        target.update(status='stopped', can_stop=False)
        await p.keyboard.press('Escape')
        await self.refresh_snapshot()
        await card.get_by_role('button', name='查看实例').click()
        self.assertEqual('已停止', await row.locator('.sc-state').inner_text())
        self.assertIn('服务已关闭', await row.inner_text())
        self.assertEqual('running', prior['status'])
        self.assertEqual([('start','fixed.gateway','fixture-console-token'),
                          ('stop','run.requested','fixture-console-token')], self.actions)
        self.assertEqual([], self.errors)

    async def test_capture_page_embeds_expanded_console_and_uses_bootstrapped_token(self):
        self.embedded = True
        p = self.page
        await p.goto('http://127.0.0.1:18095/')
        await p.locator('#service-fixed [data-service-id]').first.wait_for()
        self.assertEqual('true', await p.locator('#service-console-toggle').get_attribute('aria-expanded'))
        self.assertTrue(await p.locator('#service-console-body').is_visible())
        await p.click('#service-console-toggle')
        self.assertFalse(await p.locator('#service-console-body').is_visible())
        self.assertEqual('false', await p.locator('#service-console-toggle').get_attribute('aria-expanded'))
        await p.click('#service-console-toggle')
        self.assertTrue(await p.locator('#service-console-body').is_visible())
        await p.click('[data-service-category="game-demos"]')
        self.assertEqual(20, await p.locator('#service-rows > tr').count())
        self.assertEqual('http://127.0.0.1:18095/', p.url)
        self.assertEqual(1, len(p.context.pages))
        await p.keyboard.press('Escape')
        await p.locator('#service-fixed [data-service-id="fixed.capture"] [data-service-action="start"]').click()
        await p.locator('#service-fixed [data-service-id="fixed.capture"] [data-service-action="stop"]:enabled').wait_for()
        self.assertEqual([('start', 'fixed.capture', 'fixture-console-token')], self.actions)
        self.assertIn(('127.0.0.1:18096', 'GET', '/api/services/bootstrap'), self.api_requests)
        self.assertTrue(all(origin == '127.0.0.1:18096' for origin, _, _ in self.api_requests))
        self.assertEqual([], self.errors)

    async def test_current_capture_window_marker_uses_origin_and_persists_in_cleanup_and_warning(self):
        self.embedded = True
        self.fixture_origin = 'http://127.0.0.1:8093'
        current = {'id':'external.capture8093','name':'抓取实例 8093','category':'capture-instances',
                   'status':'running','pid':983001,'port':8093,'can_start':False,'can_stop':True,'logs_available':False}
        other = dict(current,id='external.capture18097',name='抓取实例 18097',pid=983002,port=18097)
        self.services.extend([current,other])
        aggregate = next(s for s in self.services if s['id']=='fixed.capture')
        aggregate.update(status='running',port=None,pid=None,instances=[current,other],running_count=2)
        gateway = next(s for s in self.services if s['id']=='fixed.gateway')
        gateway.update(status='running',port=8093,pid=983003,can_stop=True)
        self.cleanup_options = {'current_capture_port':8093,'items':[
            {'id':current['id'],'name':current['name'],'pid':983001,'port':8093,'status':'running',
             'required_keep':True,'default_keep':True,'keep_reason':'当前页面对应抓取必须保留','dependencies':[]},
            {'id':other['id'],'name':other['name'],'pid':983002,'port':18097,'status':'running',
             'required_keep':False,'default_keep':False,'dependencies':[]},
            {'id':gateway['id'],'name':gateway['name'],'pid':983003,'port':8093,'status':'running',
             'required_keep':False,'default_keep':False,'dependencies':[]},
        ]}
        items = self.cleanup_options['items']
        items.insert(0, dict(items[0], id='cleanup.controller.42', name='当前控制台', port=18096))
        items.append(dict(items[-1], id='advanced.postgres', name='PostgreSQL', port=15432, default_keep=True))
        items.append(dict(items[-1], id='fixed.watch', name='维护表监督器', port=None))
        p = self.page
        await p.goto(self.fixture_origin+'/')
        await p.locator('#service-fixed [data-service-id]').first.wait_for()
        for identifier in ('fixed.capture','fixed.gateway'):
            card = p.locator('#service-fixed [data-service-id="'+identifier+'"]')
            self.assertIsNone(await card.get_attribute('data-current-window'))
            self.assertEqual(0,await card.locator('.sc-current-window-badge').count())
        await p.click('[data-service-category="capture-instances"]')
        row = p.locator('#service-rows [data-service-id="'+current['id']+'"]')
        other_row = p.locator('#service-rows [data-service-id="'+other['id']+'"]')
        self.assertEqual('true',await row.get_attribute('data-current-window'))
        self.assertIn('sc-current-window',(await row.get_attribute('class') or '').split())
        self.assertEqual('目前打开的窗口服务',await row.locator('.sc-current-window-badge').inner_text())
        self.assertIsNone(await other_row.get_attribute('data-current-window'))
        self.assertEqual(0,await other_row.locator('.sc-current-window-badge').count())
        async with p.expect_response(lambda response:response.url.endswith('/api/services')):
            await p.locator('#service-dialog').get_by_role('button',name='刷新',exact=True).click()
        await p.locator('#service-refresh:enabled').wait_for()
        self.assertEqual('true',await row.get_attribute('data-current-window'))
        await row.locator('[data-service-action="stop"]').click()
        await p.locator('#service-confirm-shade').wait_for(state='visible')
        self.assertIn('目前打开的窗口服务',await p.locator('#service-confirm-warnings').inner_text())
        self.assertFalse(self.actions)
        await p.click('#service-confirm-cancel')
        self.assertFalse(self.actions)
        await p.wait_for_function("id=>document.activeElement && document.activeElement.getAttribute('data-focus-key')===id+':stop'",arg=current['id'])
        await p.keyboard.press('Escape')
        await p.locator('#service-dialog-shade').wait_for(state='hidden')
        await p.click('#service-cleanup')
        label = p.locator('[data-keep-id="'+current['id']+'"]').locator('xpath=..')
        await label.locator('.sc-current-window-badge').wait_for()
        self.assertEqual('true',await label.get_attribute('data-current-window'))
        self.assertIn('sc-current-window',(await label.get_attribute('class') or '').split())
        self.assertEqual('目前打开的窗口服务',await label.locator('.sc-current-window-badge').inner_text())
        self.assertTrue(await p.locator('[data-keep-id="'+current['id']+'"]').is_disabled())
        display_order = p.locator('#service-cleanup-items [data-keep-id]')
        expected = [current['id'], 'advanced.postgres', 'fixed.watch', 'cleanup.controller.42', other['id'], gateway['id']]
        read_ids = "inputs => inputs.map(input => input.getAttribute('data-keep-id'))"
        self.assertEqual(expected, await display_order.evaluate_all(read_ids))
        await p.locator('[data-keep-id="fixed.gateway"]').check()
        self.assertEqual(expected[:4]+[gateway['id'],other['id']], await display_order.evaluate_all(read_ids))
        await p.get_by_role('button', name='恢复建议', exact=True).click()
        self.assertEqual(expected, await display_order.evaluate_all(read_ids))
        for identifier in (other['id'],gateway['id']):
            candidate = p.locator('[data-keep-id="'+identifier+'"]').locator('xpath=..')
            self.assertIsNone(await candidate.get_attribute('data-current-window'))
            self.assertEqual(0,await candidate.locator('.sc-current-window-badge').count())
        self.assertFalse(self.actions)
        self.assertEqual([],self.errors)

    async def test_independent_console_does_not_mark_default_capture_as_current_window(self):
        capture = next(s for s in self.services if s['id']=='fixed.capture')
        capture.update(status='running',port=18095,can_start=False,can_stop=True)
        self.services.append({'id':'external.capture18096','name':'测试端口碰撞',
            'category':'capture-instances','status':'running','port':18096,'can_start':False,'can_stop':True})
        await self.open()
        self.assertEqual(0,await self.page.locator('[data-current-window="true"]').count())
        self.assertEqual(0,await self.page.locator('.sc-current-window-badge').count())
        await self.page.click('[data-service-category="capture-instances"]')
        self.assertEqual(0,await self.page.locator('[data-current-window="true"]').count())
        self.assertEqual(0,await self.page.locator('.sc-current-window-badge').count())
        self.assertEqual([],self.errors)

    async def test_categories_include_all_games_and_dialog_keyboard_restores_focus(self):
        p = self.page
        await self.open()
        self.assertEqual(6, await p.locator('#service-fixed [data-service-id]').count())
        self.assertEqual(5, await p.locator('[data-service-category]').count())
        for category in ('game-demos', 'game-compute'):
            trigger = p.locator('[data-service-category="'+category+'"]')
            await trigger.click()
            self.assertEqual(20, await p.locator('#service-rows > tr').count())
            self.assertEqual('dialog', await p.locator('#service-dialog').get_attribute('role'))
            self.assertEqual('true', await p.locator('#outside-control').get_attribute('aria-hidden'))
            await p.fill('#service-search', 'cash-mania')
            self.assertEqual(1, await p.locator('#service-rows > tr').count())
            await p.select_option('#service-filter', 'running')
            self.assertEqual(0, await p.locator('#service-rows > tr').count())
            await p.select_option('#service-filter', 'stopped')
            self.assertEqual(1, await p.locator('#service-rows > tr').count())
            await p.locator('#service-dialog-close').focus()
            await p.keyboard.press('Shift+Tab')
            self.assertTrue(await p.evaluate("document.querySelector('#service-dialog').contains(document.activeElement)"))
            await p.keyboard.press('Tab')
            self.assertTrue(await p.locator('#service-dialog-close').evaluate('node=>node===document.activeElement'))
            await p.keyboard.press('Escape')
            self.assertFalse(await p.locator('#service-dialog-shade').is_visible())
            self.assertTrue(await trigger.evaluate('node=>node===document.activeElement'))
            self.assertIsNone(await p.locator('#outside-control').get_attribute('aria-hidden'))
        self.assertEqual(0, await p.locator('svg, dialog, script[type="importmap"]').count())
        self.assertEqual([], self.errors)

    async def test_pending_failure_retry_stop_and_shared_readonly_controls(self):
        p = self.page
        await self.open()
        await p.locator('[data-service-category="game-demos"]').click()
        await p.fill('#service-search', 'cash-mania')
        row = p.locator('#service-rows [data-service-id="demo.cash-mania"]')
        gate = self.gates[('start', 'demo.cash-mania')] = asyncio.Event()
        self.failures[('start', 'demo.cash-mania')] = '目标端口由其他聊天占用'
        try:
            await row.locator('[data-service-action="start"]').click()
            await row.locator('.sc-state').filter(has_text='正在启动').wait_for()
            self.assertTrue(await row.locator('[data-service-action="start"]').is_disabled())
            self.assertIn('正在启动', await row.inner_text())
            gate.set()
            await row.get_by_text('目标端口由其他聊天占用', exact=True).wait_for()
            self.assertTrue(await row.locator('[data-service-action="start"]').is_enabled())
            del self.failures[('start', 'demo.cash-mania')]
            await row.locator('[data-service-action="start"]').click()
            await row.locator('[data-service-action="stop"]').wait_for()
            await row.locator('[data-service-action="logs"]').click()
            await p.locator('#service-log-content').filter(has_text='[已隐藏]').wait_for()
            self.assertIn('[已隐藏]', await p.locator('#service-log-content').inner_text())
            await row.locator('[data-service-action="stop"]').click()
            await row.locator('[data-service-action="start"]:enabled').wait_for()
        finally:
            gate.set()
        self.assertEqual([('start','demo.cash-mania','fixture-console-token'),
                          ('start','demo.cash-mania','fixture-console-token'),
                          ('stop','demo.cash-mania','fixture-console-token')], self.actions)
        await p.keyboard.press('Escape')
        await p.locator('[data-service-category="advanced"]').click()
        for identifier in ('advanced.postgres', 'advanced.docker'):
            shared = p.locator('#service-rows [data-service-id="'+identifier+'"]')
            self.assertTrue(await shared.locator('[data-service-action="start"]').is_enabled())
        await p.set_viewport_size({'width':390, 'height':844})
        self.assertTrue(await p.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        self.assertEqual([], self.errors)

    async def test_multiple_instances_stop_only_selected_owner_and_ignore_stale_logs(self):
        p = self.page
        gateway = next(s for s in self.services if s['id'] == 'fixed.gateway')
        own = dict(id='instance.fixture-own', status='running', port=18110, pid=7001,
                   can_start=False, can_stop=True, logs_available=True)
        foreign = dict(id='instance.fixture-foreign', status='running', port=18111, pid=7002,
                       can_start=False, can_stop=True, logs_available=True, reason='属于其他聊天，操作前需确认影响')
        gateway.update(status='running', can_start=False, can_stop=False, instances=[own, foreign])
        await self.open()
        await p.locator('#service-fixed [data-service-id="fixed.gateway"]').get_by_role('button', name='查看实例').click()
        own_row = p.locator('#service-rows [data-service-id="instance.fixture-own"]')
        foreign_row = p.locator('#service-rows [data-service-id="instance.fixture-foreign"]')
        self.assertEqual(3, await p.locator('#service-rows > tr').count())
        self.assertTrue(await own_row.locator('[data-service-action="stop"]').is_enabled())
        self.assertTrue(await foreign_row.locator('[data-service-action="stop"]').is_enabled())
        await own_row.locator('[data-service-action="stop"]').click()
        await own_row.locator('.sc-state').filter(has_text='已停止').wait_for()
        self.assertEqual('running', foreign['status'])
        self.assertEqual([('stop','instance.fixture-own','fixture-console-token')], self.actions)
        released = self.log_gates[own['id']] = asyncio.Event()
        finished = self.log_finished[own['id']] = asyncio.Event()
        try:
            await own_row.locator('[data-service-action="logs"]').click()
            await foreign_row.locator('[data-service-action="logs"]').click()
            await p.locator('#service-log-content').filter(has_text=foreign['id']).wait_for()
            released.set()
            await asyncio.wait_for(finished.wait(), timeout=5)
            await p.wait_for_timeout(50)
            self.assertIn(foreign['id'], await p.locator('#service-log-content').inner_text())
            self.assertNotIn(own['id'], await p.locator('#service-log-content').inner_text())
        finally:
            released.set()
        self.assertEqual([], self.errors)

    async def test_external_force_confirmation_cancel_preserves_page_and_executes_once(self):
        p = self.page
        identifier = 'preview.first'
        self.preparations[('stop', identifier)] = {
            'requires_confirmation':True, 'confirmation_id':'fixture-force-confirmation', 'expires_at':9999999999,
            'execution_label':'确认强制结束指定进程',
            'warnings':['将停止其他聊天正在使用的服务。', '此实例没有正常退出通道；强制结束可能中断在途请求。'],
            'targets':[{'id':identifier, 'name':'其他工作区原版服务', 'pid':971001,
                        'created':'2026-11-24T01:00:00+00:00', 'port':49201,
                        'cwd':'C:/fixture/其他工作区', 'mode':'force'}],
        }
        await self.open()
        await p.click('[data-service-category="original-previews"]')
        row = p.locator('#service-rows [data-service-id="'+identifier+'"]')
        stop = row.locator('[data-service-action="stop"]')
        gate = self.prepare_gates[('stop', identifier)] = asyncio.Event()
        self.addCleanup(gate.set)
        await stop.click()
        await stop.filter(has_text='检查中').wait_for()
        self.assertTrue(await stop.is_disabled())
        self.assertEqual('运行中', await row.locator('.sc-state').inner_text())
        self.assertFalse(self.actions)
        gate.set()
        await p.locator('#service-confirm-shade').wait_for(state='visible')
        self.assertTrue(await p.locator('#service-confirm-cancel').evaluate('node=>node===document.activeElement'))
        self.assertEqual('dialog', await p.locator('#service-confirm-dialog').get_attribute('role'))
        self.assertIn('强制结束', await p.locator('#service-confirm-execute').inner_text())
        self.assertIn('在途请求', await p.locator('#service-confirm-warnings').inner_text())
        targets = await p.locator('#service-confirm-targets').inner_text()
        for text in ('971001', '49201', '其他工作区'):
            self.assertIn(text, targets)
        self.assertEqual('运行中', await row.locator('.sc-state').inner_text())
        self.assertFalse(self.actions)
        await p.keyboard.press('Escape')
        self.assertFalse(await p.locator('#service-confirm-shade').is_visible())
        self.assertTrue(await p.locator('#service-dialog-shade').is_visible())
        self.assertTrue(await stop.evaluate('node=>node===document.activeElement'))
        self.assertFalse(self.actions)
        await stop.click()
        await p.click('#service-confirm-cancel')
        self.assertFalse(self.actions)
        await stop.click()
        await p.click('#service-confirm-execute')
        await row.locator('.sc-state').filter(has_text='已停止').wait_for()
        self.assertEqual(self.actions, [('stop', identifier, 'fixture-console-token')])
        self.assertEqual(self.action_payloads, [{'id':identifier, 'confirmation_id':'fixture-force-confirmation'}])
        self.assertEqual(self.prepares, [('stop', identifier)] * 3)
        self.assertEqual([], self.errors)

    async def test_shared_confirmation_lists_impact_and_409_is_not_retried(self):
        p = self.page
        postgres = next(s for s in self.services if s['id'] == 'advanced.postgres')
        postgres.update(status='running', can_start=False, can_stop=True)
        identifier = postgres['id']
        self.preparations[('stop', identifier)] = {
            'requires_confirmation':True, 'confirmation_id':'fixture-shared-confirmation', 'expires_at':9999999999,
            'execution_label':'确认停止共享 PostgreSQL',
            'warnings':['多个聊天的网关、后台和试玩共用此数据库；停止将中断这些服务。'],
            'targets':[{'id':identifier, 'name':'共享 PostgreSQL', 'pid':972001, 'port':15432, 'mode':'shared'},
                       {'id':'external.gateway', 'name':'其他聊天网关', 'pid':972002, 'port':18110, 'mode':'affected'}],
        }
        self.failures[('stop', identifier)] = '影响范围已变化，请重新核对后确认。'
        await self.open()
        await p.click('[data-service-category="advanced"]')
        row = p.locator('#service-rows [data-service-id="'+identifier+'"]')
        await row.locator('[data-service-action="stop"]').click()
        await p.locator('#service-confirm-shade').wait_for(state='visible')
        self.assertIn('共用此数据库', await p.locator('#service-confirm-warnings').inner_text())
        self.assertIn('其他聊天网关', await p.locator('#service-confirm-targets').inner_text())
        self.assertFalse(self.actions)
        await p.click('#service-confirm-execute')
        await row.get_by_text('影响范围已变化，请重新核对后确认。', exact=True).wait_for()
        self.assertEqual(self.actions, [('stop', identifier, 'fixture-console-token')])
        self.assertEqual(self.prepares, [('stop', identifier)])
        self.assertEqual(self.action_payloads, [{'id':identifier, 'confirmation_id':'fixture-shared-confirmation'}])
        self.assertEqual('运行中', await row.locator('.sc-state').inner_text())
        self.assertTrue(await row.locator('[data-service-action="stop"]').is_enabled())
        self.assertEqual([], self.errors)

    async def test_cleanup_keeps_required_dependencies_and_cancel_has_no_effect(self):
        p = self.page
        def item(identifier, name, required=False, default=False, dependencies=None):
            return {'id':identifier, 'name':name, 'status':'running', 'required_keep':required,
                    'default_keep':default, 'keep_reason':'当前页面必需' if required else '',
                    'dependencies':dependencies or []}
        self.cleanup_options['items'] = [item('capture.current','当前页面抓取',True),
            item('control.current','当前控制台',True), item('fixed.watch','维护监督器',default=True),
            item('advanced.postgres','共享 PostgreSQL',default=True,dependencies=['advanced.docker']),
            item('advanced.docker','Docker',default=True),
            item('demo.cash-mania','保留的游戏',dependencies=['advanced.postgres']),
            item('capture.idle','另一空闲抓取')]
        self.cleanup_prepared.update(close_count=2, kept_count=5,
            keep_ids=['capture.current','control.current','demo.cash-mania','advanced.postgres','advanced.docker'],
            warnings=['本次仅关闭未勾选实例，抓取文件和游戏数据不会删除。'],
            targets=[{'id':'capture.idle','name':'另一空闲抓取','port':18097,'mode':'capture'},
                     {'id':'fixed.watch','name':'维护监督器','mode':'force'}])
        self.cleanup_result = {'ok':False, 'submitted_count':1, 'failed_count':1, 'skipped_count':0,
            'results':[{'id':'capture.idle','name':'另一空闲抓取','state':'stopping','message':'已提交正常关闭'},
                       {'id':'fixed.watch','name':'维护监督器','state':'failed','message':'夹具：该进程身份已变化'}]}
        await self.open()
        await p.click('#service-cleanup')
        await p.locator('#service-cleanup-shade').wait_for(state='visible')
        for identifier in ('capture.current','control.current'):
            checkbox = p.locator('[data-keep-id="'+identifier+'"]')
            self.assertTrue(await checkbox.is_checked())
            self.assertTrue(await checkbox.is_disabled())
        for identifier in ('fixed.watch','advanced.postgres','advanced.docker'):
            self.assertTrue(await p.locator('[data-keep-id="'+identifier+'"]').is_checked())
        self.assertFalse(await p.locator('[data-keep-id="capture.idle"]').is_checked())
        await p.click('#service-cleanup-close')
        self.assertEqual([path for path, _ in self.cleanup_calls], ['/api/services/cleanup/options'])
        self.assertFalse(self.actions)
        await p.click('#service-cleanup')
        actionable_plan = self.cleanup_prepared
        self.cleanup_prepared = dict(actionable_plan,close_count=0,targets=[],
            keep_ids=[item['id'] for item in self.cleanup_options['items']])
        await p.get_by_role('button',name='保留全部',exact=True).click()
        self.assertTrue(await p.locator('#service-cleanup-preview').is_disabled())
        await p.locator('[data-keep-id="capture.idle"]').uncheck()
        await p.click('#service-cleanup-preview')
        await p.locator('#service-cleanup-feedback').filter(has_text='没有需要关闭的服务').wait_for()
        self.assertTrue(await p.locator('[data-keep-id="capture.idle"]').is_checked())
        self.assertFalse(await p.locator('#service-confirm-shade').is_visible())
        self.assertFalse(any(path == '/api/services/cleanup' for path,_ in self.cleanup_calls))
        self.cleanup_prepared = actionable_plan
        await p.get_by_role('button',name='仅保留必需',exact=True).click()
        await p.locator('[data-keep-id="demo.cash-mania"]').check()
        for identifier in ('advanced.postgres','advanced.docker'):
            dependency = p.locator('[data-keep-id="'+identifier+'"]')
            self.assertTrue(await dependency.is_checked())
            self.assertTrue(await dependency.is_disabled())
        self.assertFalse(await p.locator('[data-keep-id="fixed.watch"]').is_checked())
        await p.click('#service-cleanup-preview')
        await p.locator('#service-confirm-shade').wait_for(state='visible')
        prepared = [body for path,body in self.cleanup_calls if path.endswith('/prepare')][-1]
        self.assertEqual(set(prepared['keep_ids']), set(self.cleanup_prepared['keep_ids']))
        self.assertIn('抓取文件', await p.locator('#service-confirm-warnings').inner_text())
        await p.click('#service-confirm-cancel')
        self.assertTrue(await p.locator('#service-cleanup-shade').is_visible())
        self.assertFalse(any(path == '/api/services/cleanup' for path,_ in self.cleanup_calls))
        await p.click('#service-cleanup-preview')
        await p.click('#service-confirm-execute')
        await p.locator('#service-cleanup-results').filter(has_text='该进程身份已变化').wait_for()
        results = await p.locator('#service-cleanup-results').inner_text()
        self.assertIn('另一空闲抓取', results)
        self.assertIn('已提交正常关闭', results)
        calls = [body for path,body in self.cleanup_calls if path == '/api/services/cleanup']
        self.assertEqual(calls, [{'confirmation_id':'e'*64}])
        self.assertFalse(self.actions)
        self.assertEqual([], self.errors)


if __name__ == '__main__':
    unittest.main()
