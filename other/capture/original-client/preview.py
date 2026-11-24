"""为本次导出的静态客户端提供回环地址。"""
import argparse
from datetime import datetime, timezone
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import shutil
import sys
from urllib.parse import quote, unquote, urlsplit
import webbrowser


class Assets(BaseHTTPRequestHandler):
    def __init__(self, *args, root, entry, redirects, **kwargs):
        self.root, self.entry, self.redirects = root, entry, redirects
        super().__init__(*args, **kwargs)

    def log_message(self, *_):
        pass

    def do_HEAD(self):
        self.respond(False)

    def do_GET(self):
        self.respond(True)

    def respond(self, send_body):
        if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
            self.send_error(400)
            return
        try:
            path = unquote(urlsplit(self.path).path, errors="strict")
            if not path.startswith("/") or "//" in path or "\\" in path or ":" in path:
                raise ValueError
            mapped = self.redirects.get(path)
            name = mapped.lstrip("/") if mapped else self.entry if path == "/" else path[1:]
            if any(p in (".", "..", "") for p in name.split("/")):
                raise ValueError
            actual = self.root.joinpath(name)
            if actual.resolve(strict=True) != actual or not actual.is_file() or not actual.is_relative_to(self.root):
                raise ValueError
            f = actual.open("rb")
        except (OSError, ValueError, RuntimeError):
            self.send_error(404)
            return
        with f:
            if mapped or (path == "/" and "/" in self.entry):
                self.send_response(302)
                self.send_header("Location", "/" + quote(name, safe="/"))
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(os.fstat(f.fileno()).st_size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy",
                "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; "
                "base-uri 'self'; form-action 'none'; worker-src 'none'; frame-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            if send_body:
                try:
                    shutil.copyfileobj(f, self.wfile)
                except (BrokenPipeError, ConnectionResetError):
                    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    home = Path(__file__).resolve().parent
    report = json.loads((home / "转换结果.json").read_bytes())
    if report["status"] != "static_candidate":
        raise SystemExit("此目录缺少匹配的静态客户端。")
    root = (home / "client").resolve(strict=True)
    entry = report["entry_path"]
    handler = partial(Assets, root=root, entry=entry, redirects=report.get("redirects", {}))
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        url = f"http://127.0.0.1:{server.server_port}/" + quote(entry, safe="/")
        owner = dict(pid=os.getpid(), started=datetime.now(timezone.utc).isoformat(), port=server.server_port,
                     launcher=str(Path(__file__).resolve()), cwd=str(Path.cwd()), command=sys.argv,
                     chat=os.environ.get("CODEX_THREAD_ID"), url=url)
        (home / f"预览进程-{os.getpid()}.json").write_text(json.dumps(owner, ensure_ascii=False, indent=2), encoding="utf8")
        print(url, flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
