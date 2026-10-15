"""Local captured PP frontend. Initialization only; no spins or wallet settlement."""
import argparse
import json
import logging
import secrets
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / 'clients/gates-of-olympus'
BASE = '/hub-demo/common/v3/games-html5/games/vs/vs20olympgate/'


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Game-Engine', 'generated' if getattr(self.server, 'generated', False) else 'frontend-preview')
        self.send_header('Content-Security-Policy', "default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'self' data: blob:; frame-ancestors http://127.0.0.1:8080 http://localhost:8080 http://127.0.0.1:8081 http://localhost:8081 'self'")
        super().end_headers()

    def respond(self, status, body, mime='application/json; charset=utf-8'):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def list_directory(self, path):
        self.send_error(404)
        return None

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/health':
            return self.respond(200, {'status': 'ok', 'service_id': 'gates-of-olympus-preview', 'mode': 'frontend-preview'})
        if path in ('/', '/index.html'):
            query = parse_qs(urlsplit(self.path).query)
            language = query.get('lang', ['zh'])[0]
            if language not in ('zh', 'en'):
                return self.respond(400, {'error': 'Invalid language'})
            token = query.get('ops', [''])[0]
            if not self.valid_session(token):
                token = self.new_session()
            origin = f'http://127.0.0.1:{self.server.server_port}'
            config = {'accountType': 'R', 'currency': 'USD', 'currencyOriginal': 'USD',
                      'datapath': origin + BASE, 'gameService': origin + '/hub-demo/ge/v3/gameService',
                      'lang': language, 'vendor': 'T', 'showRealCash': '1', 'clock': '0',
                      'mgckey': token, 'styleName': 'generic', 'extend_events': '1',
                      'jurisdiction': '99', 'langSelectorEnabled': '0', 'demoMode': '1',
                      'umpcEnabled': False, 'lcEnabled': False,
                      'SETTINGS': '/hub-demo/saveSettings.do', 'announcementsUpdateSeconds': 0,
                      'announcementsUpdateSecondsDefault': 0,
                      'localGenerated': getattr(self.server, 'generated', False)}
            html = (CLIENT / 'index.html').read_text(encoding='utf-8').replace('__LOCAL_CONFIG__', json.dumps(config))
            return self.respond(200, html.encode(), 'text/html; charset=utf-8')
        if path.startswith('/gs2c/announcements/'):
            return self.respond(200, b'<?xml version="1.0"?><announcements></announcements>', 'application/xml')
        if path == '/hub-demo/common/v3/games-html5/operator_logos/logo_info.js':
            # The hosted operator bundle also starts remote analytics and a lobby iframe.
            return self.respond(200, b'window.UHTLogotypeInfo = {};', 'application/javascript')
        target = Path(self.translate_path(self.path)).resolve()
        if not target.is_relative_to(CLIENT.resolve()):
            return self.send_error(404)
        relative = target.relative_to(CLIENT.resolve()).as_posix()
        if relative != 'local-preview.js' and not relative.startswith('hub-demo/common/'):
            return self.send_error(404)
        if path in (BASE + 'desktop/build.js', BASE + 'mobile/build.js'):
            # Audio initialization runs inside the bundle, before the appended adapter.
            # Both captures contain MP3 packages, not the browser-preferred OGG ones.
            data = target.read_bytes().replace(
                b'capabilities["ogg"]?SoundHelper.AudioFormat.ogg:SoundHelper.AudioFormat.mp3',
                b'SoundHelper.AudioFormat.mp3')
            data += b'\n' + (CLIENT / 'local-deserializer.js').read_bytes()
            return self.respond(200, data, 'application/javascript; charset=utf-8')
        return super().do_GET()

    def do_HEAD(self):
        # Do not expose fixture metadata through the inherited static handler.
        return self.send_error(405)

    def new_session(self):
        now = time.time()
        self.server.sessions = {k: v for k, v in self.server.sessions.items() if v['expires'] > now}
        token = secrets.token_urlsafe(32)
        self.server.sessions[token] = {'expires': now + 86400, 'settings': ''}
        return token

    def valid_session(self, token):
        return self.server.sessions.get(token, {}).get('expires', 0) > time.time()

    def do_POST(self):
        origin = self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'):
            return self.respond(403, {'error': 'Invalid origin'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 <= length <= 16384:
                raise ValueError()
            body = self.rfile.read(length)
            path = urlsplit(self.path).path
            if path == '/api/v1/games/gates-of-olympus/launch':
                payload = json.loads(body or b'{}')
                if not isinstance(payload, dict) or payload.get('language', 'en') not in ('zh', 'en'):
                    raise ValueError()
                token = self.new_session()
                return self.respond(201, {'game_id': 'gates-of-olympus', 'language': payload.get('language', 'zh'), 'mode': 'frontend-preview',
                                         'launch_url': '/?' + urlencode({'mock': 1, 'ops': token, 'lang': payload.get('language', 'zh'), 'symbol': 'vs20olympgate'}),
                                         'expires_at': int(self.server.sessions[token]['expires'])})
            form = parse_qs(body.decode('utf-8'), keep_blank_values=True)
            token = form.get('mgckey', [''])[0]
            if not self.valid_session(token):
                return self.respond(401, {'error': 'Invalid preview session'})
            if path == '/hub-demo/ge/v3/gameService':
                if form.get('symbol') != ['vs20olympgate']:
                    raise ValueError()
                if form.get('action') != ['doInit']:
                    return self.respond(501, {'error': 'PREVIEW_ONLY', 'message': 'Spins are not connected.'})
                values = dict(self.server.initial)
                values.update(balance='2,000.00', balance_cash='2,000.00', balance_bonus='0.00',
                              index=form.get('index', ['1'])[0], counter=form.get('counter', ['1'])[0],
                              stime=str(int(time.time() * 1000)))
                return self.respond(200, '&'.join(k + '=' + v for k, v in values.items()).encode(), 'text/plain; charset=utf-8')
            if path in ('/hub-demo/saveSettings.do', '/hub-demo/ge/v3/saveSettings.do'):
                settings = self.server.sessions[token]
                key = form.get('id', ['game'])[0]
                if 'settings' in form:
                    settings.setdefault('values', {})[key] = form['settings'][0]
                return self.respond(200, settings.get('values', {}).get(key, '').encode(), 'text/plain; charset=utf-8')
            return self.respond(404, {'error': 'Unknown endpoint'})
        except (ValueError, UnicodeError):
            return self.respond(400, {'error': 'Invalid request'})


def build_server(port=8085):
    initial = (CLIENT / 'fixtures/init.txt').read_text(encoding='utf-8')
    class PreviewServer(ThreadingHTTPServer):
        allow_reuse_address = False
    http = PreviewServer(('127.0.0.1', port), partial(Handler, directory=str(CLIENT)))
    http.daemon_threads = True
    http.sessions = {}
    http.initial = dict(part.split('=', 1) for part in initial.split('&') if '=' in part)
    return http


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8085)
    args = parser.parse_args()
    with build_server(args.port) as http:
        logging.warning('Olympus frontend preview: http://127.0.0.1:%s/', http.server_port)
        try:
            http.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
