"""Isolated Fortune Gems 2 client, original-message adapter and transaction wallet."""
import html
import json
import logging
import mimetypes
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from server.adapters.tada.fortune_gems2 import Adapter, CLIENT
from server.core.contracts import ServiceError
from server.core.service import GameService
from server.games.catalog import create_registry
from server.transport.http import PlatformRoutes

ROOT = Path(__file__).resolve().parents[2]

PAGE_BACK = ('<button type="button" aria-label="Back to game" '
             'style="position:fixed;right:12px;top:12px;z-index:10;padding:8px 14px;'
             'border:1px solid #c79b45;border-radius:6px;background:#24180d;color:#f9dfaa;cursor:pointer" '
             'onclick="parent.postMessage(\'CloseWebView\',location.origin)">Back to game</button>')


class Handler(SimpleHTTPRequestHandler):
    _json = PlatformRoutes._json
    _response = PlatformRoutes._response
    _token = PlatformRoutes._token

    def log_message(self, format, *args):
        import re
        logging.info('%s %s', self.address_string(), re.sub(r'\?[^ ]*', '', format % args))

    def respond(self, status, data, mime='application/json; charset=utf-8'):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "connect-src 'self' blob: data:; frame-src 'self'; img-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; worker-src 'self' blob:")
        self.end_headers()
        self.wfile.write(data)

    def guard(self, action):
        try:
            action()
        except ServiceError as error:
            self.respond(error.status, {'error': error.code, 'message': str(error)})
        except (ValueError, TypeError, KeyError, UnicodeError):
            self.respond(400, {'error': 'INVALID_REQUEST'})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            logging.exception('Fortune Gems 2 request failed')
            self.respond(500, {'error': 'INTERNAL_ERROR'})

    def launch(self, token):
        return '/fgp/?' + urlencode(dict(ops=token, ssoKey='local', lang='en-US', legalLang='true',
            gameId=223, loginFrom='trial', gs=self.headers['Host'][::-1], domain_platform=self.headers['Host'][::-1],
            domain_gs='localhost', be=self.headers['Host'][::-1], iu='true', apiId=2, demo='true', skin=1))

    def do_GET(self):
        self.guard(self.get)

    def get(self):
        url = urlsplit(self.path)
        path = url.path
        if path == '/':
            token = parse_qs(url.query).get('ops', [''])[0]
            if token:
                self.server.service.wallet(token)
            else:
                token = self.server.service.create_session()['token']
            self.send_response(302)
            self.send_header('Location', self.launch(token))
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        if path == '/health' or path.startswith('/api/'):
            return PlatformRoutes._get(self)
        if path == '/history':
            token = parse_qs(url.query).get('ops', [''])[0]
            rows = self.server.service.history(token, 100)
            body = ''.join('<tr><td>{}</td><td>{:.4f}</td><td>{:.4f}</td><td>{:.4f}</td></tr>'.format(
                html.escape(row['round_id']), row['wallet']['debit_minor']/10000,
                row['wallet']['credit_minor']/10000, row['wallet']['after_minor']/10000) for row in rows)
            return self.respond(200, ('<!doctype html><meta name="viewport" content="width=device-width"><title>Fortune Gems 2 History</title>'
                '<style>body{background:#24180d;color:#f9dfaa;font:16px system-ui;padding:20px}table{width:100%;border-collapse:collapse}td,th{padding:12px;text-align:right;border-bottom:1px solid #70532c}</style>'
                + PAGE_BACK + '<h1>Fortune Gems 2</h1><table><tr><th>Round</th><th>Bet</th><th>Win</th><th>Balance</th></tr>' + body + '</table>').encode(), 'text/html; charset=utf-8')
        if path in ('/rules', '/en-US/intro'):
            document = (CLIENT/'rules.html').read_text(encoding='utf-8').replace('<h1>', PAGE_BACK + '<h1>', 1)
            return self.respond(200, document.encode(), 'text/html; charset=utf-8')
        relative = path.lstrip('/')
        if path == '/fgp/':
            token = parse_qs(url.query).get('ops', [''])[0]
            # Original connectivity monitor requests the bare launch path.
            # A probe returns no session data and never creates a new account.
            if not token and self.headers.get('Sec-Fetch-Dest') == 'empty':
                return self.respond(204, b'')
            self.server.service.wallet(token)
            document = (CLIENT/'fgp/index.html').read_text(encoding='utf-8')
            document = document.replace('<head>', '<head><script src="/local-adapter.js"></script>', 1)
            document = document.replace('<!-- Import map -->', '<script>installFortuneGems2Adapter()</script><!-- Import map -->', 1)
            # Analytics is outside the local game protocol and has no gameplay role.
            import re
            document = re.sub(r'<script[^>]+src="https://www\.googletagmanager\.com/[^>]+></script>', '', document)
            return self.respond(200, document.encode(), 'text/html; charset=utf-8')
        allowed = relative.startswith(('fgp/', 'astarte2/', 'smallicon/', 'static/', 'api-documents/')) or relative == 'local-adapter.js'
        target = (CLIENT/relative).resolve()
        if allowed and target.is_relative_to(CLIENT.resolve()) and target.is_file():
            mime = mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
            if target.suffix == '.js':
                mime = 'application/javascript'
            return self.respond(200, target.read_bytes(), mime)
        # Captured trial UI's telemetry destinations; no changes to game state.
        if path.startswith(('/webservice/event/', '/g/collect', '/lifeservice/')):
            return self.respond(200, {})
        raise ServiceError('NOT_FOUND', 'Unknown resource.', 404)

    def do_POST(self):
        self.guard(self.post)

    def post(self):
        if self.headers.get('Origin') and self.headers['Origin'] != 'http://' + self.headers.get('Host', ''):
            raise ServiceError('ORIGIN_REJECTED', 'Cross-origin writes are not enabled.', 403)
        length = int(self.headers.get('Content-Length', 0))
        if not 0 <= length <= 131072:
            raise ServiceError('BODY_TOO_LARGE', 'Request exceeds limit.', 413)
        body = self.rfile.read(length)
        path = urlsplit(self.path).path
        if path.startswith(('/webservice/event/', '/g/collect', '/subagentservice/')):
            return self.respond(200, {})
        data = json.loads(body or b'{}')
        if not isinstance(data, dict):
            raise ValueError()
        if path in ('/api/v1/sessions', '/api/v1/games/fortune-gems2/launch'):
            if data.get('language', 'en') not in ('en', 'zh'):
                raise ValueError()
            session = self.server.service.create_session()
            return self.respond(201, {'game_id': 'fortune-gems2', 'language': data.get('language', 'en'),
                'client_language': 'en', 'mode': 'generated', 'launch_url': '/?' + urlencode({'mock': '1', 'ops': session['token']}),
                **{k:v for k,v in session.items() if k not in ('token', 'player_id')}} if path.endswith('/launch') else session)
        token = data.get('token', '')
        if path == '/tada/login':
            return self.respond(200, self.server.tada.login(token))
        if path == '/tada/command':
            return self.respond(200, self.server.tada.handle(token, data['ack'], data.get('payload', []), data.get('key')))
        if path == '/api/v1/games/fortune-gems2/spin':
            return self.respond(200, self.server.service.spin(self._token(), 'fortune-gems2',
                self.headers.get('Idempotency-Key'), data.get('previous_sid'), data.get('bet', {})))
        raise ServiceError('NOT_FOUND', 'Unknown endpoint.', 404)


def build_server(port=8089, database=None, config=None):
    service = GameService(database or ROOT/'services/fortune-gems2/data/games.sqlite3',
        create_registry(['fortune-gems2'], {'fortune-gems2': config or ROOT/'services/fortune-gems2/config/fortune-gems2.json'}))
    http = ThreadingHTTPServer(('127.0.0.1', port), partial(Handler, directory=str(CLIENT)))
    http.daemon_threads = True
    http.service, http.tada = service, Adapter(service)
    http.generated, http.service_id = True, 'fortune-gems2'
    return http
