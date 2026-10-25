"""GTT management API and static UI. Credentials never reach public merchant views."""
import json
import logging
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from server.core.contracts import ServiceError
from .common import encode, identifier, limit, read_object
from .http import JSONRoutes


class AdminApplication:
    def __init__(self, control, provider):
        self.control, self.provider = control, provider

    def games(self):
        return [{**game, 'target_rtp': None, 'rtp_status': 'not_calibrated'} for game in self.provider.registry.catalog()]

    def transactions(self, payload, detail=False):
        clauses, params = [], []
        for field in ('merchant_id', 'player_id', 'game_id', 'status'):
            value = payload.get(field, '')
            if value:
                identifier(value, field)
                if field == 'status' and value not in ('prepared', 'debited', 'settled', 'rejected'):
                    raise ServiceError('INVALID_ARGUMENT', '交易状态无效。')
                clauses.append(field + '=?')
                params.append(value)
        operation_id = payload.get('operation_id', '')
        if operation_id:
            identifier(operation_id, 'operation_id')
            if operation_id.endswith((':debit', ':credit')):
                operation_id = operation_id.rsplit(':', 1)[0]
            clauses.append('id=?')
            params.append(operation_id)
        if detail and not operation_id:
            raise ServiceError('INVALID_ARGUMENT', '请输入操作 ID。')
        before = payload.get('before_seq', 0)
        if type(before) is not int or not 0 <= before <= 9_000_000_000_000_000:
            raise ServiceError('INVALID_ARGUMENT', '分页参数无效。')
        if before:
            clauses.append('seq<?')
            params.append(before)
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        with self.provider.connection() as db:
            rows = db.execute('SELECT * FROM game_operations' + where + ' ORDER BY seq DESC LIMIT ?',
                              (*params, 1 if detail else limit(payload.get('limit', 25)))).fetchall()
        entries = []
        for row in rows:
            candidate = json.loads(row['candidate_json'])
            value = {key: row[key] for key in ('seq', 'id', 'merchant_id', 'player_id', 'game_id', 'status', 'error_code', 'created_at')}
            value.update(debit_minor=candidate['debit_minor'], credit_minor=candidate['credit_minor'],
                         round_id=candidate['event']['round_id'], ruleset_id=candidate['ruleset_id'])
            if detail:
                value.update(request=json.loads(row['request_json']),
                             result=json.loads(row['response_json']) if row['response_json'] else None)
            entries.append(value)
        if detail:
            if not entries:
                raise ServiceError('NOT_FOUND', '交易不存在。', 404)
            return entries[0]
        return entries

    def overview(self):
        merchants = self.control.merchants()
        with self.provider.connection() as db:
            counts = dict(db.execute('SELECT status,COUNT(*) FROM game_operations GROUP BY status').fetchall())
        return {'merchants': len(merchants), 'active_merchants': sum(m['enabled'] for m in merchants),
                'games': len(self.games()), 'settled': counts.get('settled', 0),
                'pending': counts.get('prepared', 0) + counts.get('debited', 0),
                'rejected': counts.get('rejected', 0), 'recent': self.transactions({'limit': 5})}

    def retry(self, actor, payload):
        merchant_id = identifier(payload.get('merchant_id'), 'merchant_id')
        operation_id = identifier(payload.get('operation_id'), 'operation_id')
        reason = self.control.reason(payload)
        with self.provider.connection() as db:
            operation = db.execute('SELECT status FROM game_operations WHERE merchant_id=? AND id=?',
                                   (merchant_id, operation_id)).fetchone()
        if not operation:
            raise ServiceError('NOT_FOUND', '交易不存在。', 404)
        if operation['status'] not in ('prepared', 'debited'):
            raise ServiceError('NOT_PENDING', '该交易不需要恢复。', 409)
        with self.control.connection(True) as db:
            self.control.audit(db, actor, 'transaction.retry.request', operation_id,
                               details={'merchant_id': merchant_id, 'reason': reason, 'status': operation['status']})
        try:
            result = self.provider.retry(merchant_id, operation_id, allow_disabled=True)
        except ServiceError as error:
            with self.control.connection(True) as db:
                self.control.audit(db, actor, 'transaction.retry.result', operation_id, 'failed',
                                   {'merchant_id': merchant_id, 'code': error.code})
            raise
        with self.control.connection(True) as db:
            self.control.audit(db, actor, 'transaction.retry.result', operation_id,
                               details={'merchant_id': merchant_id, 'status': 'settled'})
        return result


class AdminHandler(JSONRoutes, BaseHTTPRequestHandler):
    server_version = 'GTTAdmin/1.0'

    def log_message(self, format, *args):
        # Only method and path are logged; request bodies/cookies are never logged.
        logging.info('GTT admin %s %s', self.command, self.path.split('?', 1)[0])

    def json_response(self, status, data=None, error=None):
        body = encode({'data': data, 'error': error}).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.security_headers()
        if getattr(self, 'session_cookie', None) is not None:
            self.send_header('Set-Cookie', self.session_cookie)
        self.end_headers()
        self.wfile.write(body)

    def security_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")

    def token(self):
        try:
            cookies = SimpleCookie(self.headers.get('Cookie', ''))
            return cookies['gtt_admin_session'].value if 'gtt_admin_session' in cookies else ''
        except CookieError:
            return ''

    def do_GET(self):
        self.execute(self.get)

    def get(self):
        self.guard()
        if '?' in self.path:
            raise ServiceError('BAD_REQUEST', '不支持 URL 查询参数。')
        app = self.server.app
        if self.path == '/health':
            return self.json_response(200, {'status': 'ok', 'service_id': 'gtt-admin'})
        if self.path == '/api/admin/me':
            return self.json_response(200, app.control.session(self.token()))
        files = {'/': ('admin.html', 'text/html; charset=utf-8'), '/admin.js': ('admin.js', 'application/javascript; charset=utf-8'),
                 '/admin.css': ('admin.css', 'text/css; charset=utf-8')}
        if self.path not in files:
            raise ServiceError('NOT_FOUND', '页面不存在。', 404)
        name, content_type = files[self.path]
        data = Path(__file__).with_name(name).read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.security_headers()
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        self.execute(self.post)

    def post(self):
        payload = read_object(self.read_body())
        app, path = self.server.app, self.path
        control = app.control
        if path == '/api/admin/login':
            token, result = control.login(payload.get('username'), payload.get('password'), self.client_address[0])
            self.session_cookie = 'gtt_admin_session=' + token + '; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'
            return self.json_response(200, result)
        routes = {
            '/api/admin/overview': 'merchants.read', '/api/admin/merchants/list': 'merchants.read',
            '/api/admin/merchants/create': 'merchants.write', '/api/admin/merchants/update': 'merchants.write',
            '/api/admin/merchants/rotate': 'keys.rotate', '/api/admin/games': 'games.read',
            '/api/admin/transactions/list': 'transactions.read', '/api/admin/transactions/detail': 'transactions.read',
            '/api/admin/transactions/retry': 'transactions.retry', '/api/admin/audit': 'audit.read',
            '/api/admin/users/list': 'users.manage', '/api/admin/users/create': 'users.manage',
            '/api/admin/users/update': 'users.manage', '/api/admin/users/reset': 'users.manage',
            '/api/admin/password': None, '/api/admin/logout': None,
        }
        if path not in routes:
            raise ServiceError('NOT_FOUND', '接口不存在。', 404)
        session = control.session(self.token(), routes[path], self.headers.get('X-GTT-CSRF', ''))
        actor = session['user']['username']
        games = {game['id'] for game in app.games()}
        if path == '/api/admin/logout':
            control.logout(self.token(), actor)
            self.session_cookie = 'gtt_admin_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'
            result = {'logged_out': True}
        elif path == '/api/admin/password':
            control.change_password(actor, payload.get('current_password'), payload.get('new_password'))
            self.session_cookie = 'gtt_admin_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'
            result = {'changed': True}
        elif path == '/api/admin/overview':
            result = app.overview()
        elif path == '/api/admin/merchants/list':
            result = {'merchants': control.merchants()}
        elif path in ('/api/admin/merchants/create', '/api/admin/merchants/update'):
            result = control.save_merchant(actor, payload, games, create=path.endswith('/create'))
        elif path == '/api/admin/merchants/rotate':
            result = control.rotate_keys(actor, payload)
        elif path == '/api/admin/games':
            result = {'games': app.games()}
        elif path == '/api/admin/transactions/list':
            result = {'transactions': app.transactions(payload)}
        elif path == '/api/admin/transactions/detail':
            result = app.transactions(payload, detail=True)
        elif path == '/api/admin/transactions/retry':
            result = app.retry(actor, payload)
        elif path == '/api/admin/audit':
            result = {'audit': control.audits(payload)}
        elif path == '/api/admin/users/list':
            result = {'users': control.users()}
        elif path == '/api/admin/users/create':
            result = control.create_user(actor, payload.get('username'), payload.get('role'))
        elif path == '/api/admin/users/update':
            result = control.update_user(actor, payload)
        else:
            result = control.update_user(actor, payload, reset=True)
        self.json_response(201 if path.endswith('/create') else 200, result)


def build_admin(port, control, provider):
    http = ThreadingHTTPServer(('127.0.0.1', port), AdminHandler)
    http.daemon_threads = True
    http.app = AdminApplication(control, provider)
    return http
