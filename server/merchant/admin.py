"""GTT management API and static UI. Credentials never reach public merchant views."""
import json
import logging
from datetime import datetime, timedelta, timezone
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from server.core.contracts import ServiceError
from .common import encode, identifier, limit, read_object
from .http import JSONRoutes
from . import integration_docs
from .identifiers import game_code, game_number, public_result
from .deployment import Deployment


class AdminApplication:
    def __init__(self, control, provider, gateway_origin=None, play_origin=None):
        self.control, self.provider = control, provider
        self.gateway_origin = gateway_origin
        self.play_origin = play_origin

    def games(self, merchant_id=None):
        merchant = self.provider.merchant(merchant_id, allow_disabled=True) if merchant_id else None
        with self.provider.connection() as db:
            policy = self.provider.rtp.resolve(db, merchant_id or '')
            mode = self.provider.rtp.mode(db, merchant_id)[0] if merchant_id else 'rtp'
        target = policy['target_bp'] / 100 if mode == 'rtp' and policy.get('target_bp') is not None else None
        return [{**game, 'id': game_number(game['id']), 'target_rtp': target,
                 'rtp_status': 'active' if target is not None else 'prebet' if mode == 'prebet' else 'not_calibrated'}
                for game in self.provider.registry.catalog() if merchant is None or game['id'] in merchant['games']]

    def transactions(self, payload, detail=False):
        clauses, params = [], []
        for field in ('merchant_id', 'player_id', 'game_id', 'status'):
            value = payload.get(field, '')
            if value:
                if field == 'game_id':
                    value = game_code(value)
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
        # Merchant currencies are immutable. Keep legacy records in their
        # original currency instead of relabelling historical amounts as USD.
        with self.control.connection() as db:
            currencies = {row['id']: (row['currency'], row['minor_unit'])
                          for row in db.execute('SELECT id,currency,minor_unit FROM merchants')}
        entries = []
        for row in rows:
            candidate = json.loads(row['candidate_json'])
            currency, minor_unit = currencies.get(row['merchant_id'], (None, None))
            value = {key: row[key] for key in ('seq', 'id', 'merchant_id', 'player_id', 'game_id', 'status', 'error_code', 'created_at')}
            value.update(debit_minor=candidate['debit_minor'], credit_minor=candidate['credit_minor'],
                         round_id=candidate['event']['round_id'], ruleset_id=candidate['ruleset_id'],
                         currency=currency, minor_unit=minor_unit)
            value['game_id'] = game_number(row['game_id'])
            if detail:
                value.update(request=json.loads(row['request_json']),
                             result=public_result(json.loads(row['response_json'])) if row['response_json'] else None)
            entries.append(value)
        if detail:
            if not entries:
                raise ServiceError('NOT_FOUND', '交易不存在。', 404)
            return entries[0]
        return entries

    def overview(self, merchant_id=None):
        merchants = [self.control.merchant(merchant_id)] if merchant_id else self.control.merchants()
        where, params = (' WHERE merchant_id=?', (merchant_id,)) if merchant_id else ('', ())
        today = datetime.now(timezone.utc).date()
        days = {str(today - timedelta(days=i)): {'date': str(today - timedelta(days=i)), 'settled': 0} for i in reversed(range(7))}
        with self.provider.connection() as db:
            counts = dict(db.execute('SELECT status,COUNT(*) FROM game_operations' + where + ' GROUP BY status', params).fetchall())
            totals = db.execute("SELECT merchant_id,SUM(json_extract(candidate_json,'$.debit_minor')) AS debit,"
                               "SUM(json_extract(candidate_json,'$.credit_minor')) AS credit,COUNT(DISTINCT player_id) AS players "
                               "FROM game_operations" + where + (' AND' if where else ' WHERE') + " status='settled' GROUP BY merchant_id", params).fetchall()
            recent_days = db.execute("SELECT date(created_at,'unixepoch') AS day,COUNT(*) AS count FROM game_operations" + where
                                    + (' AND' if where else ' WHERE') + " status='settled' AND created_at>=? GROUP BY day",
                                    (*params, int(datetime.combine(today - timedelta(days=6), datetime.min.time(), timezone.utc).timestamp()))).fetchall()
        currencies, players = {}, 0
        by_id = {m['id']: m for m in merchants}
        for row in totals:
            merchant = by_id.get(row['merchant_id'])
            if not merchant:
                continue
            bucket = currencies.setdefault(merchant['currency'], {'currency': merchant['currency'], 'minor_unit': merchant['minor_unit'], 'debit_minor': 0, 'credit_minor': 0})
            bucket['debit_minor'] += row['debit']
            bucket['credit_minor'] += row['credit']
            players += row['players']
        for row in recent_days:
            if row['day'] in days:
                days[row['day']]['settled'] = row['count']
        return {'merchants': len(merchants), 'active_merchants': sum(m['enabled'] for m in merchants),
                'games': len([g for g in self.games() if not merchant_id or g['id'] in merchants[0]['games']]), 'settled': counts.get('settled', 0),
                'pending': counts.get('prepared', 0) + counts.get('debited', 0),
                'rejected': counts.get('rejected', 0), 'players': players, 'totals': list(currencies.values()),
                'daily': list(days.values()), 'recent': self.transactions({'limit': 5, **({'merchant_id': merchant_id} if merchant_id else {})})}

    def prebet_decisions(self, payload):
        clauses, params = [], []
        for field in ('merchant_id', 'player_id'):
            if payload.get(field):
                clauses.append(field + '=?')
                params.append(identifier(payload[field], field))
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        with self.provider.connection() as db:
            rows = db.execute('SELECT id,merchant_id,player_id,game_id,prebet_request_json,policy_json,plan_json IS NOT NULL AS planned,error_code,created_at FROM prebet_rounds'
                              + where + ' ORDER BY created_at DESC,rowid DESC LIMIT ?', (*params, limit(payload.get('limit', 25)))).fetchall()
        return [{**{key: row[key] for key in ('id', 'merchant_id', 'player_id', 'game_id', 'error_code', 'created_at')}, 'game_id': game_number(row['game_id']),
                 'request': json.loads(row['prebet_request_json']),
                 'policy': json.loads(row['policy_json']) if row['policy_json'] else None,
                 'status': 'rejected' if row['error_code'] else 'planned' if row['planned'] else 'pending'} for row in rows]

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

    @property
    def cookie_name(self):
        name = 'gtt_merchant_session' if self.path.startswith('/api/merchant/') else 'gtt_admin_session'
        return '__Host-' + name if self.server.deployment.production else name

    @property
    def merchant_api(self):
        return self.path.startswith('/api/merchant/')

    def cookie(self, token, max_age=28800):
        secure = '; Secure' if self.server.deployment.production else ''
        return self.cookie_name + '=' + token + '; HttpOnly; SameSite=Strict; Path=/; Max-Age=' + str(max_age) + secure

    def authenticate_session(self, permission=None, csrf=None):
        result = self.server.app.control.session(self.token(), permission, csrf)
        if self.merchant_api and not result['user']['merchant_id']:
            raise ServiceError('MERCHANT_LOGIN_REQUIRED', '请使用绑定商户的账号登录商户工作台。', 403)
        return result

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
            return cookies[self.cookie_name].value if self.cookie_name in cookies else ''
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
        if self.path in ('/api/admin/me', '/api/merchant/me'):
            return self.json_response(200, self.authenticate_session())
        if self.path == '/deployment.json':
            return self.json_response(200, self.server.deployment.browser_config(self))
        if self.server.deployment.production and self.path == '/merchant/':
            self.send_response(308)
            self.send_header('Location', self.server.deployment.origins['merchant'] + '/')
            self.send_header('Content-Length', '0')
            self.security_headers()
            self.end_headers()
            return
        downloads = {
            prefix + suffix: (kind, content_type, filename)
            for prefix in ('/api/admin/integration/', '/api/merchant/integration/')
            for suffix, kind, content_type, filename in (
                ('guide.md', 'markdown', 'text/markdown; charset=utf-8', 'GTT-Integration-v1.md'),
                ('openapi.json', 'openapi', 'application/json; charset=utf-8', 'GTT-OpenAPI-v1.json'))
        }
        if self.path in downloads:
            self.authenticate_session('merchants.read')
            kind, content_type, filename = downloads[self.path]
            value = getattr(integration_docs, kind)(app.gateway_origin, app.play_origin)
            data = (value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Disposition', 'attachment; filename="' + filename + '"')
            self.send_header('Content-Length', str(len(data)))
            self.security_headers()
            self.end_headers()
            return self.wfile.write(data)
        files = {'/': ('admin.html', 'text/html; charset=utf-8'), '/admin.js': ('admin.js', 'application/javascript; charset=utf-8'),
                 '/admin.css': ('admin.css', 'text/css; charset=utf-8'), '/merchant/': ('admin.html', 'text/html; charset=utf-8')}
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
        if path.startswith('/api/merchant/'):
            path = '/api/admin/' + path.removeprefix('/api/merchant/')
        control = app.control
        if path == '/api/admin/login':
            token, result = control.login(payload.get('username'), payload.get('password'), self.server.deployment.remote(self), merchant_login=self.merchant_api)
            if self.merchant_api and not result['user']['merchant_id']:
                control.logout(token, result['user']['username'])
                raise ServiceError('MERCHANT_LOGIN_REQUIRED', '请使用绑定商户的账号登录商户工作台。', 403)
            self.session_cookie = self.cookie(token)
            return self.json_response(200, result)
        routes = {
            '/api/admin/rtp/read': 'rtp.read', '/api/admin/rtp/policy': 'rtp.write', '/api/admin/rtp/mode': 'rtp.write',
            '/api/admin/rtp/job': 'rtp.manage', '/api/admin/rtp/publish': 'rtp.manage',
            '/api/admin/integration/docs': 'merchants.read',
            '/api/admin/overview': 'merchants.read', '/api/admin/merchants/list': 'merchants.read',
            '/api/admin/merchants/create': 'merchants.write', '/api/admin/merchants/update': 'merchants.write',
            '/api/admin/merchants/rotate': 'keys.rotate', '/api/admin/games': 'games.read',
            '/api/admin/transactions/list': 'transactions.read', '/api/admin/transactions/detail': 'transactions.read',
            '/api/admin/transactions/retry': 'transactions.retry', '/api/admin/audit': 'audit.read',
            '/api/admin/prebet/list': 'transactions.read',
            '/api/admin/merchants/profile': 'profile.write',
            '/api/admin/merchants/signing/view': 'keys.rotate',
            '/api/admin/merchants/signing/rotate': 'keys.rotate',
            '/api/admin/users/list': 'users.manage', '/api/admin/users/create': 'users.manage',
            '/api/admin/users/update': 'users.manage', '/api/admin/users/reset': 'users.manage',
            '/api/admin/password': None, '/api/admin/logout': None,
        }
        if path not in routes:
            raise ServiceError('NOT_FOUND', '接口不存在。', 404)
        session = self.authenticate_session(routes[path], self.headers.get('X-GTT-CSRF', ''))
        actor = session['user']['username']
        scope = session['user']['merchant_id']
        # Derive tenancy from the authenticated database session on every request.
        # A missing client-side filter must never widen the merchant's access.
        if scope:
            if payload.get('merchant_id') not in (None, '', scope):
                raise ServiceError('FORBIDDEN', '不能访问其他商户。', 403)
            if path in ('/api/admin/merchants/profile', '/api/admin/merchants/rotate') or path.startswith('/api/admin/merchants/signing/'):
                if payload.get('id', scope) != scope:
                    raise ServiceError('FORBIDDEN', '不能访问其他商户。', 403)
                payload['id'] = scope
            payload['merchant_id'] = scope
        games = {game['id'] for game in app.games()}
        if path == '/api/admin/logout':
            control.logout(self.token(), actor)
            self.session_cookie = self.cookie('', 0)
            result = {'logged_out': True}
        elif path == '/api/admin/password':
            control.change_password(actor, payload.get('current_password'), payload.get('new_password'))
            self.session_cookie = self.cookie('', 0)
            result = {'changed': True}
        elif path.startswith('/api/admin/rtp/'):
            action = path.rsplit('/', 1)[-1]
            if action == 'read':
                result = app.provider.rtp.snapshot(payload, scope)
            elif action == 'policy':
                result = app.provider.rtp.policy(actor, payload, platform='rtp.manage' in session['permissions'])
            elif action == 'mode':
                result = app.provider.rtp.set_mode(actor, payload)
            elif action == 'job':
                result = app.provider.rtp.create_job(actor, payload)
            else:
                result = app.provider.rtp.publish_model(actor, payload)
        elif path == '/api/admin/integration/docs':
            result = integration_docs.document(app.gateway_origin, app.play_origin)
        elif path == '/api/admin/overview':
            result = app.overview(scope)
        elif path == '/api/admin/prebet/list':
            result = {'decisions': app.prebet_decisions(payload)}
        elif path == '/api/admin/merchants/list':
            result = {'merchants': [control.merchant(scope)] if scope else control.merchants()}
        elif path == '/api/admin/merchants/profile':
            profile = {k: v for k, v in payload.items() if k != 'merchant_id'}
            result = control.save_profile(actor, scope, profile)
        elif path in ('/api/admin/merchants/create', '/api/admin/merchants/update'):
            result = control.save_merchant(actor, payload, games, create=path.endswith('/create'))
        elif path == '/api/admin/merchants/rotate':
            result = control.rotate_keys(actor, payload)
        elif path.startswith('/api/admin/merchants/signing/'):
            result = control.manage_signing(actor, payload, path.rsplit('/', 1)[-1])
        elif path == '/api/admin/games':
            result = {'games': app.games(scope)}
        elif path == '/api/admin/transactions/list':
            result = {'transactions': app.transactions(payload)}
        elif path == '/api/admin/transactions/detail':
            result = app.transactions(payload, detail=True)
        elif path == '/api/admin/transactions/retry':
            result = app.retry(actor, payload)
        elif path == '/api/admin/audit':
            result = {'audit': control.audits(payload, scope)}
        elif path == '/api/admin/users/list':
            result = {'users': control.users(scope)}
        elif path == '/api/admin/users/create':
            result = control.create_user(actor, payload.get('username'), payload.get('role'), merchant_id=payload.get('merchant_id') or None, scope=scope)
        elif path == '/api/admin/users/update':
            result = control.update_user(actor, payload, scope=scope)
        else:
            result = control.update_user(actor, payload, reset=True, scope=scope)
        self.json_response(201 if path.endswith('/create') else 200, result)


def build_admin(port, control, provider, gateway_origin=None, config=None):
    deployment = Deployment(config)
    http = ThreadingHTTPServer(('127.0.0.1', port), AdminHandler)
    http.daemon_threads = True
    http.deployment = deployment
    http.app = AdminApplication(control, provider, deployment.origins.get('api', gateway_origin), deployment.origins.get('play'))
    return http
