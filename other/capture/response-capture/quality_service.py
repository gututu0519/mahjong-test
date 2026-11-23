"""抓取完整度的只读接口；兼容正在录制、尚未加载新接口的抓取进程。"""
import copy
import json
import re
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'captures'
SID = re.compile(r'^[0-9a-f]{32}$')
ALLOWED_ORIGINS = {'http://127.0.0.1:8090', 'http://localhost:8090'}
MAX_DETAIL_BYTES = 64 * 1024 * 1024


def analyze(detail, folder):
    from capture_quality import analyze_capture
    return analyze_capture(detail, folder)


class QualityCache:
    """仅短时缓存脱敏结果；重新计算失败时不返回旧的完成信号。"""
    def __init__(self, analyzer=None, ttl=2):
        self.analyzer = analyzer or analyze
        self.ttl = ttl
        self.entries = {}
        self.lock = threading.Lock()

    def get(self, detail, folder):
        sid = detail.get('id', '')
        if not SID.fullmatch(sid):
            raise ValueError('会话标识无效')
        with self.lock:
            cached = self.entries.get(sid)
            if cached and time.monotonic() - cached[0] < self.ttl:
                return copy.deepcopy(cached[1])
            result = self.analyzer(detail, folder)
            result['generated_at'] = datetime.now(timezone.utc).isoformat()
            result['capture_state'] = detail.get('state', 'unknown')
            result['session_id'] = sid
            if len(self.entries) >= 32:
                self.entries.pop(next(iter(self.entries)))
            self.entries[sid] = (time.monotonic(), copy.deepcopy(result))
            return result


CACHE = QualityCache()


def get_session_quality(detail, folder):
    return CACHE.get(detail, folder)


def fetch_live_detail(sid):
    if not SID.fullmatch(sid):
        raise ValueError('会话标识无效')
    # 目标固定为本机抓取工具；请求参数不能指定远端网址或读取任意文件。
    with urlopen('http://127.0.0.1:8090/api/sessions/' + sid, timeout=15) as response:
        raw = response.read(MAX_DETAIL_BYTES + 1)
    if len(raw) > MAX_DETAIL_BYTES:
        raise ValueError('会话数据超过检查上限')
    detail = json.loads(raw)
    if detail.get('id') != sid:
        raise ValueError('会话身份不匹配')
    return detail


class QualityHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def allowed(self):
        port = self.server.server_port
        host = self.headers.get('Host', '')
        origin = self.headers.get('Origin')
        return host in (f'127.0.0.1:{port}', f'localhost:{port}') and (origin is None or origin in ALLOWED_ORIGINS)

    def send_json(self, status, value):
        raw = json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        origin = self.headers.get('Origin')
        if origin in ALLOWED_ORIGINS:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if not self.allowed():
            return self.send_json(403, {'error': '不允许的本机来源'})
        parsed = urlsplit(self.path)
        if parsed.query or parsed.fragment:
            return self.send_json(400, {'error': '完整度接口不接受查询参数'})
        if parsed.path == '/health':
            return self.send_json(200, {'version': 1, 'service': 'capture-quality', 'read_only': True})
        match = re.fullmatch(r'/api/sessions/([0-9a-f]{32})/quality', parsed.path)
        if not match:
            return self.send_json(404, {'error': '没有该检查接口'})
        sid = match.group(1)
        try:
            detail = self.server.detail_source(sid)
            result = self.server.quality_cache.get(detail, self.server.capture_root / sid)
            result['transport'] = 'capture-compatibility'
            return self.send_json(200, result)
        except HTTPError as error:
            status = 404 if error.code == 404 else 503
            return self.send_json(status, {'error': '抓取会话不可读取，暂时无法判断完整度', 'status': 'unknown'})
        except (OSError, URLError, ValueError, TypeError, KeyError):
            return self.send_json(503, {'error': '采集检查暂不可用，请保留当前抓取记录', 'status': 'unknown'})


def create_server(address=('127.0.0.1', 8091), *, detail_source=None, capture_root=None, quality_cache=None):
    server = ThreadingHTTPServer(address, QualityHandler)
    server.detail_source = detail_source or fetch_live_detail
    server.capture_root = Path(capture_root or DATA)
    server.quality_cache = quality_cache or CACHE
    return server


if __name__ == '__main__':
    server = create_server()
    print('Capture Quality: http://127.0.0.1:8091 （只读检查现有录制）', flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
