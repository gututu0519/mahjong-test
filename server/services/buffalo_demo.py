"""Buffalo Win client, generated engine and private durable wallet on port 8083."""
import copy
import json
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlencode

from server.core.contracts import ServiceError
from server.core.service import GameService
from server.games.catalog import create_registry
from server.adapters.pg.buffalo_win import PGAdapter
from server.services.buffalo_preview import Handler as AssetHandler, ROOT, CLIENT
from server.transport.http import PlatformRoutes


class Handler(AssetHandler):
    bootstrap_script = 'local-auth-bootstrap.js'
    _get = PlatformRoutes._get
    _post = PlatformRoutes._post

    def serve_assets(self):
        SimpleHTTPRequestHandler.do_GET(self)

    def launch_game(self, game_id, language='zh'):
        self.server.service.registry.get(game_id)
        if language not in ('zh', 'en'):
            raise ServiceError('LANGUAGE_INVALID', 'Supported languages: zh, en.')
        session = self.server.service.create_session()
        query = urlencode({'mock': 1, 'l': language, 'ops': session['token'], 'btt': 2})
        return {'game_id': game_id, 'language': language, 'launch_url': '/?' + query,
                'mode': 'generated', 'expires_at': session['expires_at'],
                'balance_minor': session['balance_minor'], 'currency': 'DEMO', 'minor_unit': 100}

    def compatibility_post(self, path, body):
        form = parse_qs(body.decode('utf-8'), keep_blank_values=True)
        token = self.headers.get('X-Local-Game-Session') or form.get('atk', [None])[0]
        wallet = self.server.service.wallet(token)
        if path in ('/web-api/auth/session/v2/verifySession', '/web-api/auth/session/v2/verifyOperatorPlayerSession'):
            data = copy.deepcopy(self.server.auth)
            data.update(tk=token, pid=wallet['player_id'], pcd=wallet['player_id'], nkn='Local demo',
                        ioph='local-demo', oj={'jid': 1}, bl=wallet['balance_minor'] / 100)
            return self._json(200, {'dt': data, 'err': None})
        if path == '/game-api/buffalo-win/v2/GameInfo/Get':
            return self._json(200, self.server.pg.game_info(token))
        if path == '/game-api/buffalo-win/v2/Spin':
            return self._json(200, self.server.pg.spin(body, token))
        if path == '/web-api/game-proxy/v2/GameWallet/Get':
            return self._json(200, self.server.pg.wallet(token))
        if path == '/web-api/game-proxy/v2/GameName/Get':
            name = 'Buffalo Win' if form.get('lang', ['zh'])[0] == 'en' else '美洲野牛'
            return self._json(200, {'dt': {'108': name}, 'err': None})
        if path == '/web-api/game-proxy/v2/GameRule/Get':
            if form.get('gid', ['108'])[0] != '108':
                raise ServiceError('GAME_NOT_FOUND', 'Unknown game.', 404)
            return self._json(200, self.server.game_rule)
        if path == '/web-api/game-proxy/v2/Resources/GetByResourcesTypeIds':
            return self._json(200, {'dt': [], 'err': None})
        if path == '/web-api/game-proxy/ServerManager/RefreshWallet':
            return self._json(200, {'dt': None, 'err': None})
        raise ServiceError('NOT_IMPLEMENTED', 'This local endpoint is not implemented.', 501)


def build_server(port=8083, database=None, config=None):
    config = config or ROOT / 'services/buffalo-win/config/buffalo-win.json'
    registry = create_registry(['buffalo-win'], {'buffalo-win': config})
    service = GameService(database or ROOT / 'services/buffalo-win/data/games.sqlite3', registry)
    service.ensure_local_demo()
    http = ThreadingHTTPServer(('127.0.0.1', port), partial(Handler, directory=str(CLIENT)))
    http.daemon_threads = True
    http.service, http.pg = service, PGAdapter(service)
    http.auth = json.loads((CLIENT / 'fixtures/auth-metadata.json').read_text(encoding='utf-8'))
    http.game_rule = json.loads((CLIENT / 'fixtures/game-rule.json').read_text(encoding='utf-8'))
    http.service_id = 'buffalo-win'
    return http


if __name__ == '__main__':
    import sys
    from server.run import main
    main(['--service-dir', str(ROOT / 'services/buffalo-win'), *sys.argv[1:]])
