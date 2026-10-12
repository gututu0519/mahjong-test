"""Local static server with the scope header required by the original worker.

Run: python serve_local.py
Rollback: stop this process and run python -m http.server 8080
"""

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit
from local_modules import prepare_module


class GameRequestHandler(SimpleHTTPRequestHandler):
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
        # 先等待修复版 SW 接管，再运行原入口，避免启动时读到旧的阻塞模块。
        content = content.replace(
            b'<script id="main-script"',
            b'<script type="application/x-local-game" id="main-script"',
            1,
        ).replace(
            b'</body>', b'<script src="/local-cache-bootstrap.js"></script></body>', 1
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
    args = parser.parse_args()
    handler = partial(GameRequestHandler, directory=str(Path(__file__).resolve().parent))
    with ThreadingHTTPServer((args.bind, args.port), handler) as server:
        print(f"Serving game at http://localhost:{args.port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
