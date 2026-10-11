"""Local static server with the scope header required by the original worker.

Run: python serve_local.py
Rollback: stop this process and run python -m http.server 8080
"""

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


class GameRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        if urlsplit(self.path).path == "/shared/service-worker/sw.js":
            self.send_header("Service-Worker-Allowed", "/")
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
