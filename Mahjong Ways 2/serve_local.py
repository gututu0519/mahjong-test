"""Local static server with the scope header required by the original worker.

Run: python serve_local.py
Synthetic operator login, using the original client: http://localhost:8080/?mock=1
Login, GameInfo, wallet and captured Spin replay are implemented.
Rollback: stop this process and run python -m http.server 8080
"""

import argparse
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from local_modules import prepare_module
from local_auth import (AUTH_PATH, GAME_NAME_PATH, GAME_INFO_PATH, GAME_RULE_PATH,
                        get_game_names, get_game_info, get_game_rule, verify_operator_session)
from local_auth import SESSION_TOKEN
from local_spin import LocalSpin, SpinError

SPIN_PATHS = ('/game-api/74/v4/Spin', '/game-api/mahjong-ways2/v4/Spin')
WALLET_PATH = '/web-api/game-proxy/v2/GameWallet/Get'


class GameRequestHandler(SimpleHTTPRequestHandler):
    def do_POST(self):
        path = urlsplit(self.path).path
        if not path.startswith(('/web-api/', '/game-api/')):
            self.send_error(404)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 <= length <= 16384:
                self.send_error(413)
                return
            body = self.rfile.read(length)
            if path in SPIN_PATHS:
                try:
                    content = self.server.spin.spin(body)
                except SpinError as error:
                    self.send_json(error.status, {'dt': None, 'err': {'cd': error.code, 'msg': str(error)}})
                    return
                except (ValueError, UnicodeError):
                    self.send_json(400, {'dt': None, 'err': {'cd': 'LOCAL_SPIN_INVALID', 'msg': 'Invalid Spin payload.'}})
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Length', str(len(content)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Local-Mock', 'captured-spin-replay')
                self.end_headers()
                self.wfile.write(content)
                return
            # The opt-in JSON adapter sends the captured form contract for GameInfo.
            form = (parse_qs(body.decode('utf-8'), keep_blank_values=True)
                    if path in (AUTH_PATH, GAME_NAME_PATH, GAME_INFO_PATH, GAME_RULE_PATH, WALLET_PATH) else {})
        except (ValueError, UnicodeError):
            self.send_error(400)
            return
        if path == AUTH_PATH:
            status, data = verify_operator_session(form)
            if status == 200:
                data['dt']['bl'] = self.server.spin.wallet()['dt']['cb']
        elif path == GAME_NAME_PATH:
            status, data = get_game_names(form)
        elif path == GAME_RULE_PATH:
            status, data = get_game_rule(form)
        elif path == GAME_INFO_PATH:
            status, data = get_game_info(form)
            if status == 200:
                data = self.server.spin.game_info(data)
        elif path == WALLET_PATH:
            if form.get('atk') != [SESSION_TOKEN]:
                status, data = 400, {'dt': None, 'err': {'cd': 'LOCAL_SESSION_INVALID', 'msg': 'Invalid local session.'}}
            else:
                status, data = 200, self.server.spin.wallet()
        else:
            # Missing captures must not silently become invented game responses.
            status, data = 501, {'dt': None, 'err': {'cd': 'LOCAL_MOCK_NOT_IMPLEMENTED',
                'msg': 'No local response fixture for ' + path}}
        self.send_json(status, data)

    def send_json(self, status, data):
        content = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Local-Mock', '1')
        self.end_headers()
        self.wfile.write(content)

    def send_head(self):
        """为本地入口补全模块加载基址，避免相对基址导致解析器阻塞。"""
        requested = Path(self.translate_path(self.path))
        shared = (Path(self.directory) / 'shared').resolve()
        if requested.name == 'index.js' and shared in requested.resolve().parents:
            try:
                content, revision = prepare_module(requested.read_bytes())
            except OSError:
                self.send_error(404, 'Module file not found')
                return None
            except ValueError as error:
                self.log_error('%s: %s', requested, error)
                self.send_error(422, 'Module initialization failed; see server log')
                return None
            self.send_response(200)
            self.send_header('Content-Type', 'application/javascript; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Local-Module-Fix', 'auto-1')
            self.send_header('X-Local-Module-Revision', revision)
            self.end_headers()
            return BytesIO(content)
        if urlsplit(self.path).path not in ("/", "/index.html"):
            return super().send_head()

        entry = Path(self.directory) / "index.html"
        try:
            content = entry.read_bytes()
        except OSError:
            self.send_error(404, "Entry file not found")
            return None

        original = b"xt=i,kt=''"
        replacement = (
            b"xt=new URL(i,location.href).href,"
            b"kt=new URL('.',location.href).href"
        )
        if content.count(original) != 1:
            self.send_error(500, "Entry path configuration changed; review local path fix")
            return None

        content = content.replace(original, replacement, 1)
        mock_script = (b'<script src="/local-auth-bootstrap.js"></script>'
                       if parse_qs(urlsplit(self.path).query).get('mock') == ['1'] else b'')
        # 先等待修复版 SW 接管，再运行原入口，避免启动时读到旧的阻塞模块。
        content = content.replace(
            b'<script id="main-script"',
            b'<script type="application/x-local-game" id="main-script"',
            1,
        ).replace(
            b'</body>', mock_script + b'<script src="/local-cache-bootstrap.js"></script></body>', 1
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        return BytesIO(content)

    def end_headers(self):
        """允许原有 Service Worker 使用根作用域。"""
        if urlsplit(self.path).path == "/shared/service-worker/sw.js":
            self.send_header("Service-Worker-Allowed", "/")
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--state-file", help="Separate local replay wallet state (useful for tests)")
    args = parser.parse_args()
    handler = partial(GameRequestHandler, directory=str(Path(__file__).resolve().parent))
    with ThreadingHTTPServer((args.bind, args.port), handler) as server:
        server.spin = LocalSpin(args.state_file)
        print(f"Serving game at http://localhost:{args.port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
