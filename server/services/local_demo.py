"""Mahjong client asset host plus compatibility adapter and platform API."""
import argparse
import json
import sys
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen
from urllib.error import URLError
from server.core.contracts import ServiceError
from server.core.service import GameService
from server.games.catalog import create_registry
from server.adapters.pg.mahjong_ways2 import PGAdapter
from server.transport.http import PlatformRoutes

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / 'Mahjong Ways 2'
# Only this deployment imports the legacy client's asset repair/help functions.
sys.path.insert(0, str(CLIENT))
from serve_local import GameRequestHandler
from local_auth import verify_operator_session, get_game_names, get_game_rule


class Handler(PlatformRoutes, GameRequestHandler):
    def _get(self):
        if urlsplit(self.path).path == '/api/v1/demo/games':
            return self._json(200, {'games': [
                {'id': 'mahjong-ways2', 'mode': 'playable', 'languages': ['zh', 'en']},
                {'id': 'buffalo-win', 'mode': 'playable', 'languages': ['zh', 'en']},
            ]})
        return super()._get()

    def serve_assets(self):
        path = urlsplit(self.path).path
        demo_files = {'/demo': ('index.html', 'text/html; charset=utf-8'),
                      '/demo/': ('index.html', 'text/html; charset=utf-8'),
                      '/demo/style.css': ('style.css', 'text/css; charset=utf-8'),
                      '/demo/i18n.js': ('i18n.js', 'application/javascript; charset=utf-8'),
                      '/demo/app.js': ('app.js', 'application/javascript; charset=utf-8'),
                      '/demo/buffalo-cover.jpg': ('buffalo-cover.jpg', 'image/jpeg')}
        if path in demo_files:
            name, content_type = demo_files[path]
            self._response(200, (ROOT / 'demo' / name).read_bytes(), content_type)
            return
        GameRequestHandler.do_GET(self)

    def launch_game(self, game_id, language='zh'):
        if game_id == 'buffalo-win':
            if language not in ('zh', 'en'):
                raise ServiceError('LANGUAGE_INVALID', 'Supported languages: zh, en.')
            origin = 'http://127.0.0.1:8083'
            request = Request(origin + '/api/v1/games/buffalo-win/launch',
                              data=json.dumps({'language': language}).encode(),
                              headers={'Content-Type': 'application/json'}, method='POST')
            try:
                with urlopen(request, timeout=5) as response:
                    result = json.load(response)
                link = urlsplit(result['launch_url'])
                query = parse_qs(link.query)
                if link.scheme or link.netloc or link.path != '/' or query.get('mock') != ['1'] or not query.get('ops'):
                    raise ValueError('Invalid game link')
                result['launch_url'] = origin + result['launch_url']
                return result
            except (URLError, OSError, ValueError, KeyError):
                raise ServiceError('GAME_UNAVAILABLE', 'Buffalo Win service is unavailable.', 503)
        self.server.service.registry.get(game_id)
        if game_id != 'mahjong-ways2':
            raise ServiceError('NOT_FOUND', 'This game has no web client.', 404)
        if language not in ('zh', 'en'):
            raise ServiceError('LANGUAGE_INVALID', 'Supported languages: zh, en.')
        session = self.server.service.create_session()
        query = urlencode({'mock': '1', 'btt': '1', 'ot': 'local-demo', 'ops': session['token'], 'l': language})
        return {'game_id': game_id, 'launch_url': '/?' + query, 'language': language,
                'expires_at': session['expires_at'], 'balance_minor': session['balance_minor'],
                'currency': session['currency'], 'minor_unit': session['minor_unit']}

    def compatibility_post(self, path, body):
        service = self.server.service
        adapter = self.server.pg
        if path in ('/game-api/74/v4/Spin', '/game-api/mahjong-ways2/v4/Spin'):
            self._response(200, adapter.spin(body), 'application/octet-stream')
            return
        form = parse_qs(body.decode(), keep_blank_values=True)
        token = form.get('atk', [None])[0]
        if path == '/web-api/auth/session/v2/verifyOperatorPlayerSession':
            token = form.get('os', [None])[0]
            wallet = service.wallet(token)
            status, result = verify_operator_session({**form, 'os': ['local-demo-session']})
            if status == 200:
                result['dt'].update(tk=token, bl=wallet['balance_minor'] / 100,
                                    pid=wallet['player_id'], pcd=wallet['player_id'])
            self._json(status, result)
        elif path == '/game-api/74/v4/GameInfo/Get':
            if form.get('btt') != ['1'] or form.get('pf') != ['1']:
                raise ServiceError('SESSION_INVALID', 'Only the local demo is supported.')
            self._json(200, adapter.game_info(token))
        elif path == '/web-api/game-proxy/v2/GameWallet/Get':
            self._json(200, adapter.wallet(token))
        elif path == '/web-api/game-proxy/v2/GameName/Get':
            service.wallet(token)
            status, result = get_game_names({**form, 'atk': ['local-demo-session']})
            self._json(status, result)
        elif path == '/web-api/game-proxy/v2/GameRule/Get':
            service.wallet(token)
            status, result = get_game_rule({**form, 'atk': ['local-demo-session']})
            self._json(status, result)
        else:
            raise ServiceError('NOT_IMPLEMENTED', 'This compatibility endpoint is not implemented.', 501)

    def list_directory(self, path):
        self.send_error(404)
        return None

    def send_head(self):
        # Assets only: Python sources, captures and diagnostics are not web assets.
        path = Path(self.translate_path(self.path)).resolve()
        if not path.is_relative_to(CLIENT.resolve()):
            self.send_error(404)
            return None
        relative = path.relative_to(CLIENT.resolve())
        if ('diagnostics' in relative.parts or 'fixtures' in relative.parts
                or path.suffix.lower() in ('.py', '.pyc', '.cjs', '.bat', '.har', '.txt')):
            self.send_error(404)
            return None
        return super().send_head()


def build_server(port=8080, database=None, config=None):
    config = config or ROOT / 'services/mahjong-ways2/config/mahjong-ways2.json'
    registry = create_registry(['mahjong-ways2'], configs={'mahjong-ways2': config} if config else None)
    service = GameService(database or ROOT / 'services/mahjong-ways2/data/games.sqlite3', registry)
    service.ensure_local_demo()
    http = ThreadingHTTPServer(('127.0.0.1', port), partial(Handler, directory=str(CLIENT)))
    http.daemon_threads = True
    http.service = service
    http.pg = PGAdapter(service)
    return http


def main():
    parser = argparse.ArgumentParser(description='Local multi-game service with generated outcomes')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--database', type=Path)
    parser.add_argument('--config', type=Path, help='Mahjong probability configuration')
    args = parser.parse_args()
    with build_server(args.port, args.database, args.config) as http:
        print(f'Generated game server: http://localhost:{http.server_port}/?mock=1', flush=True)
        print(f'Platform API: http://localhost:{http.server_port}/api/v1/games', flush=True)
        try:
            http.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
