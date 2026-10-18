"""Isolated Buffalo Win frontend preview. No spin engine or settlement is provided."""
import argparse
import copy
import json
import logging
import secrets
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / 'clients/buffalo-win'
from server.adapters.pg.client_modules import prepare_module
from server.core.contracts import ServiceError
from server.transport.http import PlatformRoutes


class Handler(PlatformRoutes, SimpleHTTPRequestHandler):
    bootstrap_script = 'local-preview.js'
    def _get(self):
        path = urlsplit(self.path).path
        if path == '/health':
            return self._json(200, {'status': 'ok', 'service_id': 'buffalo-win-preview', 'mode': 'frontend-preview'})
        SimpleHTTPRequestHandler.do_GET(self)

    def _post(self):
        self._guard_origin()
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 <= length <= 16384:
            raise ServiceError('BODY_TOO_LARGE', 'Request body exceeds 16 KiB.', 413)
        body = self.rfile.read(length)
        path = urlsplit(self.path).path
        if path == '/api/v1/games/buffalo-win/launch':
            if self.headers.get_content_type() != 'application/json':
                raise ServiceError('CONTENT_TYPE', 'Use application/json.', 415)
            payload = json.loads(body or b'{}')
            if not isinstance(payload, dict):
                raise ServiceError('BAD_REQUEST', 'Expected an object.')
            language = payload.get('language', 'zh')
            if language != 'zh':
                raise ServiceError('LANGUAGE_UNAVAILABLE', 'English assets are not captured yet. Chinese preview is available.')
            now = int(time.time())
            # Preview sessions hold no wallet or account data and expire after 24 hours.
            for token, expiry in list(self.server.sessions.items()):
                if expiry <= now:
                    self.server.sessions.pop(token, None)
            if len(self.server.sessions) >= 1000:
                raise ServiceError('SESSION_LIMIT', 'Restart the local preview to clear sessions.', 429)
            token = secrets.token_urlsafe(32)
            self.server.sessions[token] = now + 86400
            query = urlencode({'mock': 1, 'l': language, 'ops': token, 'btt': 2})
            return self._json(201, {'game_id': 'buffalo-win', 'language': language,
                                   'launch_url': '/?' + query, 'mode': 'frontend-preview',
                                   'expires_at': now + 86400})
        form = parse_qs(body.decode('utf-8'), keep_blank_values=True)
        token = self.headers.get('X-Local-Preview-Session') or form.get('atk', [''])[0]
        if self.server.sessions.get(token, 0) <= time.time():
            raise ServiceError('SESSION_INVALID', 'Invalid preview session.', 401)
        if path in ('/web-api/auth/session/v2/verifySession',
                    '/web-api/auth/session/v2/verifyOperatorPlayerSession'):
            data = copy.deepcopy(self.server.auth)
            data.update(tk=token, pid='local-preview', pcd='local-preview', nkn='Preview',
                        ioph='local-preview', oj={'jid': 1}, bl=2000)
            return self._json(200, {'dt': data, 'err': None})
        if path == '/game-api/buffalo-win/v2/GameInfo/Get':
            return self._json(200, self.server.info)
        if path == '/web-api/game-proxy/v2/GameName/Get':
            name = 'Buffalo Win' if form.get('lang', ['zh'])[0] == 'en' else '美洲野牛'
            return self._json(200, {'dt': {'108': name}, 'err': None})
        if path == '/web-api/game-proxy/v2/Resources/GetByResourcesTypeIds':
            return self._json(200, {'dt': [], 'err': None})
        if path == '/web-api/game-proxy/ServerManager/RefreshWallet':
            return self._json(200, {'dt': None, 'err': None})
        if path == '/web-api/game-proxy/v2/GameWallet/Get':
            return self._json(200, {'dt': {'cc': 'PGC', 'tb': 2000, 'pb': 0, 'cb': 2000,
                'tbb': 0, 'tfgb': 0, 'rfgc': 0, 'inbe': False, 'infge': False, 'iebe': False,
                'iefge': False, 'ch': {'k': '0_C', 'cid': 0, 'cb': 2000}, 'p': None,
                'ocr': None, 'bwc': 0, 'fgwc': 0}, 'err': None})
        if path.endswith('/Spin'):
            raise ServiceError('PREVIEW_ONLY', 'Frontend preview only. The spin engine is not connected.', 501)
        raise ServiceError('NOT_IMPLEMENTED', 'This endpoint is not available in the frontend preview.', 501)

    def list_directory(self, path):
        self.send_error(404)
        return None

    def send_head(self):
        path = Path(self.translate_path(self.path)).resolve()
        if not path.is_relative_to(CLIENT.resolve()):
            self.send_error(404)
            return None
        relative = path.relative_to(CLIENT.resolve())
        if ('fixtures' in relative.parts or path.suffix.lower() in ('.py', '.pyc', '.bat', '.md', '.har', '.txt')):
            self.send_error(404)
            return None
        if urlsplit(self.path).path in ('/', '/index.html'):
            content = (CLIENT / 'index.html').read_bytes()
            original = b"xt=i,kt=''"
            if content.count(original) != 1:
                raise ValueError('Entry base configuration changed')
            content = content.replace(original, b"xt=new URL(i,location.href).href,kt=new URL('.',location.href).href", 1)
            bootstrap = f'<script src="/{self.bootstrap_script}"></script><script src="/local-frame-clock.js"></script>'.encode()
            content = content.replace(b'<script id="main-script"', bootstrap + b'<script id="main-script"', 1)
            return self._asset(content, 'text/html; charset=utf-8')
        if path.name == 'index.js' and 'shared' in relative.parts and path.is_file():
            content, _ = prepare_module(path.read_bytes())
            return self._asset(content, 'application/javascript; charset=utf-8')
        return super().send_head()

    def _asset(self, content, mime):
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        return BytesIO(content)


def build_server(port=8083):
    http = ThreadingHTTPServer(('127.0.0.1', port), partial(Handler, directory=str(CLIENT)))
    http.daemon_threads = True
    http.engine_mode = 'frontend-preview'
    http.sessions = {'local-preview-session': 253402300799}
    http.auth = json.loads((CLIENT / 'fixtures/auth-metadata.json').read_text(encoding='utf-8'))
    http.info = json.loads((CLIENT / 'fixtures/game-info.json').read_text(encoding='utf-8'))
    return http


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8083)
    args = parser.parse_args()
    logs = ROOT / 'services/buffalo-win/logs'
    logs.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, handlers=[logging.FileHandler(logs / 'service.log', encoding='utf-8')])
    with build_server(args.port) as http:
        print(f'Buffalo Win frontend preview: http://127.0.0.1:{http.server_port}/?mock=1&l=zh', flush=True)
        try:
            http.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
