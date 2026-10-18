"""Original Mahjong client entry, module repair and service-worker headers."""
import hashlib
from http.server import SimpleHTTPRequestHandler
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from server.adapters.pg.client_modules import prepare_module


class MahjongAssetHandler(SimpleHTTPRequestHandler):
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
        def local_script(name):
            revision = hashlib.sha256((Path(self.directory) / name).read_bytes()).hexdigest()[:12]
            return f'<script src="/{name}?v={revision}"></script>'.encode('ascii')

        mock_script = (local_script('local-frame-clock.js') + local_script('local-auth-bootstrap.js')
                       if parse_qs(urlsplit(self.path).query).get('mock') == ['1'] else b'')
        # 先等待修复版 SW 接管，再运行原入口，避免启动时读到旧的阻塞模块。
        content = content.replace(
            b'<script id="main-script"',
            b'<script type="application/x-local-game" id="main-script"',
            1,
        ).replace(
            b'</body>', mock_script + local_script('local-cache-bootstrap.js') + b'</body>', 1
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
