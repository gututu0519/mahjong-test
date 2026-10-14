"""Mahjong client asset host plus compatibility adapter and platform API."""
import argparse
import sys
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs
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
    def serve_assets(self):
        GameRequestHandler.do_GET(self)

    def compatibility_post(self, path, body):
        service = self.server.service
        adapter = self.server.pg
        if path in ('/game-api/74/v4/Spin', '/game-api/mahjong-ways2/v4/Spin'):
            self._response(200, adapter.spin(body), 'application/octet-stream')
            return
        form = parse_qs(body.decode(), keep_blank_values=True)
        token = form.get('atk', [None])[0]
        if path == '/web-api/auth/session/v2/verifyOperatorPlayerSession':
            status, result = verify_operator_session(form)
            if status == 200:
                result['dt']['bl'] = service.wallet('local-demo-session')['balance_minor'] / 100
            self._json(status, result)
        elif path == '/game-api/74/v4/GameInfo/Get':
            if form.get('btt') != ['1'] or form.get('pf') != ['1']:
                raise ServiceError('SESSION_INVALID', 'Only the local demo is supported.')
            self._json(200, adapter.game_info(token))
        elif path == '/web-api/game-proxy/v2/GameWallet/Get':
            self._json(200, adapter.wallet(token))
        elif path == '/web-api/game-proxy/v2/GameName/Get':
            status, result = get_game_names(form)
            self._json(status, result)
        elif path == '/web-api/game-proxy/v2/GameRule/Get':
            status, result = get_game_rule(form)
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
