"""Isolated Dr Zappo original-client host, port 8097."""
import html
import json
import logging
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, unquote, urlsplit
from server.adapters.hacksaw.dr_zappo import Adapter, CLIENT
from server.core.contracts import ServiceError
from server.core.service import GameService
from server.games.catalog import create_registry
from server.transport.http import PlatformRoutes

PREFIX = '/2253/1.49.1/'


class Handler(PlatformRoutes, BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        import re
        logging.info('%s %s', self.address_string(), re.sub(r'\?[^ ]*', '', format % args))

    def _response(self, status, body, content_type):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self' blob: data:; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; style-src 'self' 'unsafe-inline'; connect-src 'self' blob: data:; worker-src 'self' blob:; frame-src 'self';")
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, url):
        self.send_response(302)
        self.send_header('Location', url)
        self.send_header('Content-Length', '0')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.end_headers()

    def launch_game(self, game_id, language='zh'):
        if game_id != 'dr-zappo':
            raise ServiceError('NOT_FOUND', 'Unknown game.', 404)
        if language not in ('en', 'zh'):
            raise ServiceError('LANGUAGE_INVALID', 'Supported languages: en, zh.')
        session = self.server.service.create_session()
        return {'game_id': game_id, 'language': language, 'client_language': 'zh-cn' if language == 'zh' else 'en-us',
                'launch_url': '/?'+urlencode(dict(mock=1, ops=session['token'], lang=language)),
                **{k:v for k,v in session.items() if k not in ('token','player_id')}}

    def _get(self):
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        if url.path == '/':
            token = query.get('ops', [''])[0] or self.server.service.create_session()['token']
            self.server.service.wallet(token)
            with self.server.service.connection() as db:
                player = self.server.service.sessions._player(db, token)
                keys = db.execute("SELECT request_key FROM spins WHERE player_id=? AND game_id='dr-zappo'", (player['id'],)).fetchall()
                sequence = max((int(row['request_key'].split(':')[1]) for row in keys if row['request_key'].startswith('hacksaw:')), default=0)
            lang = 'zh-cn' if query.get('lang') == ['zh'] else 'en-us'
            args = dict(gameid=2253, token=token, sessionuuid=token, seq=sequence, language=lang, currency='EUR', country='US', partner='demo',
                        mode=2, backend=1, env='/api', apienv='/api',
                        channel=query.get('channel', ['desktop'])[0], branding='default', disableddemotext='true',
                        historyurl='/history?'+urlencode({'ops':token}), lobbyurl='http://127.0.0.1:8080/demo/')
            return self.redirect(PREFIX+'index.html?'+urlencode(args))
        if url.path == '/api/meta/gameInfo':
            return self._json(200, self.server.hacksaw.info)
        if url.path == '/history':
            token = query.get('ops',[''])[0]
            rows = self.server.service.history(token, 100)
            pending = self.server.service.state(token,'dr-zappo')['state']['pending']
            grouped = {}
            for row in rows:
                rid = row['round_id']
                if pending and rid == pending['round_id']:
                    continue
                item = grouped.setdefault(rid, {'round_id':rid,'wallet':{'debit_minor':0,'credit_minor':0,
                                                                      'after_minor':row['wallet']['after_minor']}})
                item['wallet']['debit_minor'] += row['wallet']['debit_minor']
                item['wallet']['credit_minor'] += row['wallet']['credit_minor']
            rows = list(grouped.values())
            body = ''.join('<tr><td>{}</td><td>{:.2f}</td><td>{:.2f}</td><td>{:.2f}</td></tr>'.format(
                html.escape(row['round_id']), row['wallet']['debit_minor']/100,
                row['wallet']['credit_minor']/100, row['wallet']['after_minor']/100) for row in rows)
            document = '<!doctype html><meta name="viewport" content="width=device-width"><title>Dr Zappo History</title><style>body{font:16px system-ui;background:#141414;color:#fff;padding:24px}td,th{padding:12px;text-align:right}table{width:100%}</style><h1>Dr Zappo</h1><table><tr><th>Round</th><th>Bet</th><th>Paid</th><th>Balance</th></tr>'+body+'</table>'
            return self._response(200, document.encode(), 'text/html; charset=utf-8')
        return super()._get()

    def serve_assets(self):
        relative = unquote(urlsplit(self.path).path).lstrip('/')
        target = (CLIENT/relative).resolve()
        allowed = relative.startswith(('2253/', 'integrations/')) or relative == 'local-adapter.js'
        if not allowed or not target.is_relative_to(CLIENT.resolve()) or not target.is_file():
            raise ServiceError('NOT_FOUND', 'Unknown resource.', 404)
        data = target.read_bytes()
        if relative == PREFIX.lstrip('/')+'index.html':
            document = data.decode('utf-8').replace('<head>', '<head><script src="/local-adapter.js"></script>', 1)
            # Do not send original analytics, player data or launch credentials off-machine.
            import re
            document = re.sub(r'<script[^>]+src="https://static\.cloudflareinsights\.com/[^>]*></script>', '', document)
            data = document.encode('utf-8')
        mime = {'.js':'application/javascript', '.wasm':'application/wasm', '.ktx2':'image/ktx2',
                '.json':'application/json'}.get(target.suffix, mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
        self._response(200, data, mime)

    def _post(self):
        path = urlsplit(self.path).path
        if not path.startswith(('/api/play/', '/telemetry/')):
            return super()._post()
        self._guard_origin()
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 <= length <= 65536:
            raise ServiceError('BODY_TOO_LARGE', 'Request exceeds 64 KiB.', 413)
        data = json.loads(self.rfile.read(length) or b'{}')
        if not isinstance(data, dict):
            raise ValueError('Expected an object')
        adapter = self.server.hacksaw
        endpoint = path.rsplit('/',1)[-1]
        if path.startswith('/telemetry/'):
            result = adapter.response()
        elif endpoint == 'authenticate':
            result = adapter.authenticate(data.get('token'))
            result['languageCode'] = data.get('languageCode', 'en-us')
        elif endpoint == 'partnerSettings':
            result = adapter.partner
        elif endpoint == 'bet':
            result = adapter.bet(data)
        elif endpoint == 'keepAlive':
            # The original client also uses this endpoint for anonymous clock
            # checks with the captured all-zero UUID. No wallet is exposed.
            token = data.get('sessionUuid')
            if token != '00000000-0000-0000-0000-000000000000':
                self.server.service.wallet(token)
            result = adapter.response()
        elif endpoint in ('balance', 'gameLaunch', 'endSessionBeacon', 'logError', 'logEvent', 'gameError'):
            if endpoint == 'gameError':
                details = {k:v for k,v in data.items() if k not in ('token','sessionUuid','playerId')}
                logging.warning('Dr Zappo client error: %s', json.dumps(details)[:8000])
            result = adapter.response(data.get('sessionUuid') or data.get('token'))
        else:
            raise ServiceError('NOT_FOUND', 'Unknown Hacksaw endpoint.', 404)
        self._json(200, result)

    def do_POST(self):
        if not urlsplit(self.path).path.startswith('/api/play/'):
            return super().do_POST()
        try:
            self._post()
        except ServiceError as error:
            codes = {'INSUFFICIENT_BALANCE':5, 'BET_INVALID':13, 'REQUEST_INVALID':11,
                     'IDEMPOTENCY_CONFLICT':14, 'STALE_STATE':14, 'ROUND_PENDING':14,
                     'ROUND_INVALID':14, 'ORIGIN_REJECTED':11}
            self._json(200, dict(statusCode=codes.get(error.code,2 if error.status==401 else 1),
                                 statusMessage=str(error), accountBalance=None))
        except (ValueError, TypeError, KeyError, UnicodeError):
            self._json(200, dict(statusCode=11,statusMessage='Invalid request.',accountBalance=None))
        except (BrokenPipeError,ConnectionResetError):
            pass
        except Exception:
            logging.exception('Dr Zappo request failed')
            self._json(200, dict(statusCode=1,statusMessage='Request was not committed.',accountBalance=None))


def build_server(port=8097, database=None, config=None):
    root = CLIENT.parents[1]
    service_dir = root/'services/dr-zappo'
    service = GameService(database or service_dir/'data/games.sqlite3',
                          create_registry(['dr-zappo'], {'dr-zappo':config} if config else {}))
    http = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    http.service, http.hacksaw = service, Adapter(service)
    http.service_id, http.engine_mode = 'dr-zappo', 'generated'
    return http
