"""Olympus assets + PP adapter + independently persisted virtual wallet."""
import json
import logging
from functools import partial
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit
from server.core.contracts import ServiceError
from server.core.service import GameService
from server.games.catalog import create_registry
from server.adapters.pp.gates_of_olympus import PPAdapter, money
from server.services.olympus_preview import Handler as AssetHandler, CLIENT, ROOT
from server.transport.http import PlatformRoutes


class Handler(AssetHandler):
    _json = PlatformRoutes._json
    _response = PlatformRoutes._response
    _token = PlatformRoutes._token

    def valid_session(self, token):
        if not token:
            return False
        self.server.service.wallet(token)
        return True

    def new_session(self):
        return self.server.service.create_session()['token']

    def guard(self, action):
        try:
            action()
        except ServiceError as e:
            self.respond(e.status, {'error': e.code, 'message': str(e)})
        except (ValueError, UnicodeError, TypeError, KeyError):
            self.respond(400, {'error': 'INVALID_REQUEST'})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            logging.exception('Olympus request failed')
            self.respond(500, {'error': 'INTERNAL_ERROR'})

    def do_GET(self):
        self.guard(self.get)

    def get(self):
        path = urlsplit(self.path).path
        if path == '/hub-demo/ge/v3/reloadBalance.do':
            token = parse_qs(urlsplit(self.path).query).get('mgckey', [''])[0]
            balance = self.server.service.wallet(token)['balance_minor']
            return self.respond(200, urlencode({'balance': money(balance), 'balance_cash': money(balance),
                                                'balance_bonus': '0.00'}).encode(), 'text/plain; charset=utf-8')
        if path == '/health' or path.startswith('/api/'):
            return PlatformRoutes._get(self)
        return AssetHandler.do_GET(self)

    def serve_assets(self):
        return AssetHandler.do_GET(self)

    def do_POST(self):
        self.guard(self.post)

    def post(self):
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + self.headers.get('Host', ''):
            raise ServiceError('ORIGIN_REJECTED', 'Cross-origin writes are not enabled.', 403)
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 <= length <= 16384:
            raise ServiceError('BODY_TOO_LARGE', 'Request exceeds 16 KiB.', 413)
        body = self.rfile.read(length)
        path = urlsplit(self.path).path
        if path in ('/api/v1/sessions', '/api/v1/games/gates-of-olympus/spin'):
            payload = json.loads(body or b'{}')
            if not isinstance(payload, dict):
                raise ValueError()
            if path == '/api/v1/sessions':
                return self.respond(201, self.server.service.create_session())
            result = self.server.service.spin(self._token(), 'gates-of-olympus',
                self.headers.get('Idempotency-Key'), payload.get('previous_sid'), payload.get('bet', {}))
            return self.respond(200, result)
        if path == '/api/v1/games/gates-of-olympus/launch':
            q = json.loads(body or b'{}')
            if not isinstance(q, dict) or q.get('language', 'en') not in ('zh', 'en'):
                raise ValueError()
            session = self.server.service.create_session()
            self.respond(201, {'game_id': 'gates-of-olympus', 'language': q.get('language', 'zh'), 'mode': 'generated',
                              'launch_url': '/?' + urlencode({'mock': 1, 'ops': session['token'], 'lang': q.get('language', 'zh'), 'symbol': 'vs20olympgate'}),
                              **{k: v for k, v in session.items() if k not in ('token', 'player_id')}})
            return
        form = parse_qs(body.decode('utf-8'), keep_blank_values=True)
        if path == '/hub-demo/ge/v3/gameService':
            data = self.server.pp.handle(form)
            return self.respond(200, '&'.join(k + '=' + str(v) for k, v in data.items()).encode(), 'text/plain; charset=utf-8')
        if path in ('/hub-demo/saveSettings.do', '/hub-demo/ge/v3/saveSettings.do'):
            if any(len(v) != 1 for v in form.values()):
                raise ValueError()
            with self.server.service.connection(True) as db:
                player = self.server.service.sessions._player(db, form.get('mgckey', [''])[0])
                key = form.get('id', ['game'])[0]
                if 'settings' in form:
                    db.execute('INSERT OR REPLACE INTO pp_settings VALUES (?,?,?)', (player['id'], key, form['settings'][0]))
                row = db.execute('SELECT value FROM pp_settings WHERE player_id=? AND name=?', (player['id'], key)).fetchone()
            return self.respond(200, (row[0] if row else '').encode(), 'text/plain; charset=utf-8')
        raise ServiceError('NOT_FOUND', 'Unknown endpoint.', 404)


def build_server(port=8085, database=None, config=None):
    config = config or ROOT / 'services/gates-of-olympus/config/gates-of-olympus.json'
    service = GameService(database or ROOT / 'services/gates-of-olympus/data/games.sqlite3',
                          create_registry(['gates-of-olympus'], {'gates-of-olympus': config}))
    with service.connection(True) as db:
        db.execute('CREATE TABLE IF NOT EXISTS pp_settings (player_id TEXT NOT NULL REFERENCES players(id), name TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY(player_id,name))')
    initial = {k: v[0] for k, v in parse_qs((CLIENT / 'fixtures/init.txt').read_text(encoding='utf-8')).items()}
    http = ThreadingHTTPServer(('127.0.0.1', port), partial(Handler, directory=str(CLIENT)))
    http.daemon_threads = True
    http.service, http.pp = service, PPAdapter(service, initial)
    http.generated, http.service_id = True, 'gates-of-olympus'
    return http
