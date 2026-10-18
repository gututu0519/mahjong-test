"""Original Wild Bandito client and independent durable wallet on port 8100."""
import copy
import hashlib
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from server.core.contracts import ServiceError
from server.core.service import GameService
from server.games.catalog import create_registry
from server.adapters.pg.wild_bandito import PGAdapter
from server.transport.http import PlatformRoutes

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / 'clients/wild-bandito'
from server.adapters.pg.client_modules import prepare_module


class Handler(PlatformRoutes, SimpleHTTPRequestHandler):
    def launch_game(self, game_id, language='zh'):
        self.server.service.registry.get(game_id)
        if language not in ('zh', 'en'):
            raise ServiceError('LANGUAGE_INVALID', 'Supported languages: zh, en.')
        session = self.server.service.create_session()
        query = urlencode(dict(mock=1, l='en', ops=session['token'], btt=2))
        return dict(game_id=game_id, language=language, client_language='en', launch_url='/?' + query,
                    mode='generated', expires_at=session['expires_at'], balance_minor=session['balance_minor'],
                    currency='DEMO', minor_unit=100)

    def compatibility_post(self, path, body):
        token = self.headers.get('X-Local-Game-Session')
        form = parse_qs(body.decode('utf-8'), keep_blank_values=True) if path.startswith('/web-api/') else {}
        token = token or form.get('atk', [None])[0]
        wallet = self.server.service.wallet(token)
        if path in ('/web-api/auth/session/v2/verifySession', '/web-api/auth/session/v2/verifyOperatorPlayerSession'):
            data = copy.deepcopy(self.server.auth)
            data.update(tk=token, pid=wallet['player_id'], pcd=wallet['player_id'], bl=wallet['balance_minor'] / 100)
            return self._json(200, dict(dt=data, err=None))
        if path == '/game-api/wild-bandito/v4/GameInfo/Get':
            return self._response(200, self.server.pg.game_info(body, token), 'application/octet-stream')
        if path == '/game-api/wild-bandito/v4/Spin':
            return self._response(200, self.server.pg.spin(body, token), 'application/octet-stream')
        if path == '/web-api/game-proxy/v2/GameWallet/Get':
            return self._json(200, self.server.pg.wallet(token))
        if path in ('/web-api/game-proxy/v2/BetSummary/Get', '/web-api/game-proxy/v2/BetHistory/Get'):
            return self._json(200, self.server.pg.history(token, form, summary='/BetSummary/' in path))
        if path == '/web-api/game-proxy/v2/GameName/Get':
            return self._json(200, {'dt': {'104': 'Wild Bandito'}, 'err': None})
        if path == '/web-api/game-proxy/v2/GameRule/Get':
            if form.get('gid', ['104'])[0] != '104':
                raise ServiceError('GAME_NOT_FOUND', 'Unknown game.', 404)
            return self._json(200, self.server.game_rule)
        if path == '/web-api/game-proxy/v2/Resources/GetByResourcesTypeIds':
            return self._json(200, {'dt': [], 'err': None})
        if path == '/web-api/game-proxy/ServerManager/RefreshWallet':
            return self._json(200, {'dt': None, 'err': None})
        raise ServiceError('NOT_IMPLEMENTED', 'Unknown endpoint.', 501)

    def serve_assets(self):
        return SimpleHTTPRequestHandler.do_GET(self)

    def list_directory(self, path):
        self.send_error(404)
        return None

    def send_head(self):
        url_path = urlsplit(self.path).path
        if url_path == '/':
            self.send_response(302)
            self.send_header('Location', '/104/index.html?' + urlsplit(self.path).query)
            self.end_headers()
            return None
        path = Path(self.translate_path(self.path)).resolve()
        if not path.is_relative_to(CLIENT.resolve()) or 'fixtures' in path.relative_to(CLIENT.resolve()).parts:
            self.send_error(404)
            return None
        if path.suffix.lower() in ('.py', '.pyc', '.md', '.bat', '.har', '.txt'):
            self.send_error(404)
            return None
        if url_path == '/local-bootstrap.js':
            return self._asset(path.read_bytes(), 'application/javascript; charset=utf-8')
        if url_path == '/104/index.html':
            data = path.read_bytes()
            original = b"xt=i,kt=''"
            if data.count(original) != 1:
                raise ValueError('Entry base changed')
            data = data.replace(original, b"xt=new URL('/shared/',location.href).href,kt=new URL('/104/',location.href).href", 1)
            scripts = ''.join(f'<script src="/{name}?v={hashlib.sha256((CLIENT / name).read_bytes()).hexdigest()[:12]}"></script>'
                              for name in ('local-bootstrap.js', 'local-frame-clock.js'))
            data = data.replace(b'<script id="main-script"', scripts.encode() + b'<script id="main-script"', 1)
            return self._asset(data, 'text/html; charset=utf-8')
        if path.name == 'index.js' and 'shared' in path.parts and path.is_file():
            data, _ = prepare_module(path.read_bytes())
            return self._asset(data, 'application/javascript; charset=utf-8')
        return super().send_head()

    def _asset(self, data, mime):
        from io import BytesIO
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        return BytesIO(data)


def build_server(port=8100, database=None, config=None):
    registry = create_registry(['wild-bandito'], {'wild-bandito': config or ROOT / 'services/wild-bandito/config/wild-bandito.json'})
    service = GameService(database or ROOT / 'services/wild-bandito/data/games.sqlite3', registry)
    service.ensure_local_demo()
    http = ThreadingHTTPServer(('127.0.0.1', port), partial(Handler, directory=str(CLIENT)))
    http.daemon_threads = True
    http.service, http.pg = service, PGAdapter(service)
    http.auth = json.loads((CLIENT / 'fixtures/auth-metadata.json').read_text(encoding='utf-8'))
    http.game_rule = json.loads((CLIENT / 'fixtures/game-rule.json').read_text(encoding='utf-8'))
    http.service_id = 'wild-bandito'
    return http
