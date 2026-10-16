"""Local browser response recorder. Run with .venv/Scripts/python app.py."""
import asyncio
import base64
import copy
import json
import mimetypes
import os
import secrets
import sys
import threading
import time
import uuid
import webbrowser
import zipfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'captures'
TOKEN = secrets.token_urlsafe(32)
SESSIONS = {}
MANAGER_LOCK = threading.Lock()


async def launch_browser(pw, headless=False):
    edge = Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe'
    chrome = Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe'
    for channel, path in [('msedge', edge), ('chrome', chrome)]:
        if path.exists():
            return await pw.chromium.launch(channel=channel, headless=headless)
    return await pw.chromium.launch(headless=headless)


def now():
    return datetime.now(timezone.utc).isoformat()


class Capture:
    def __init__(self, url, headless=False):
        self.id = uuid.uuid4().hex
        self.url = url
        self.headless = headless
        self.folder = DATA / self.id
        (self.folder / 'bodies').mkdir(parents=True)
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.rows = []
        self.requests = {}
        self.tasks = set()
        self.state = 'starting'
        self.error = ''
        self.created = now()
        self.ws_count = 0
        self.accepting = True
        self.decoded = dict(ready=False, spins=0, scatter_wins=0, errors=0)

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(dict(id=self.id, url=self.url, created=self.created,
                state=self.state, error=self.error, rows=self.rows, ws_count=self.ws_count, decoded=self.decoded))

    def update(self, row, **values):
        with self.lock:
            row.update(values)

    def request(self, req):
        if req in self.requests:
            return self.requests[req]
        if not self.accepting:
            return None
        with self.lock:
            row = dict(id=len(self.rows) + 1, url=req.url, method=req.method,
                type=req.resource_type, started=now(), status=None, mime='', size=0,
                state='pending', body=None, error='', request_headers=[], response_headers=[])
            self.rows.append(row)
            self.requests[req] = row
        try:
            body = req.post_data_buffer
            if body is not None:
                name = f'bodies/{row["id"]:06d}.request.bin'
                (self.folder / name).write_bytes(body)
                self.update(row, request_body=name)
        except Exception as exc:
            self.update(row, request_body_error=str(exc))
        self.schedule(self.request_headers(req, row))
        return row

    async def request_headers(self, req, row):
        try:
            self.update(row, request_headers=await req.headers_array())
        except Exception as exc:
            self.update(row, request_headers_error=str(exc))

    def schedule(self, coro):
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def response(self, res):
        row = self.request(res.request)
        if row is None:
            return
        try:
            headers = await res.headers_array()
            mime = res.headers.get('content-type', '')
            self.update(row, status=res.status, mime=mime, response_headers=headers,
                from_service_worker=res.from_service_worker)
            raw = await res.body()
            ext = mimetypes.guess_extension(mime.split(';')[0].strip()) or '.bin'
            name = f'bodies/{row["id"]:06d}{ext}'
            (self.folder / name).write_bytes(raw)
            self.update(row, size=len(raw), body=name, state='complete')
        except Exception as exc:
            self.update(row, state='unavailable', error=str(exc))

    def failed(self, req):
        row = self.request(req)
        if row:
            self.update(row, state='failed', error=req.failure or 'Request failed')

    def websocket(self, ws):
        def record(direction, payload):
            binary = isinstance(payload, bytes)
            event = dict(time=now(), url=ws.url, direction=direction,
                encoding='base64' if binary else 'text',
                data=base64.b64encode(payload).decode() if binary else payload)
            with (self.folder / 'websockets.jsonl').open('a', encoding='utf-8') as f:
                f.write(json.dumps(event, ensure_ascii=False) + '\n')
            with self.lock:
                self.ws_count += 1
        ws.on('framesent', lambda data: record('sent', data))
        ws.on('framereceived', lambda data: record('received', data))

    def decoded_event(self, source, event):
        # Keep plaintext round data in the same private capture folder, never login tokens.
        path = urlsplit(source['frame'].url).path
        if not path.startswith('/sss-jf2/') or not isinstance(event, dict):
            return
        kind = event.get('kind')
        if kind not in ('ready', 'spin', 'spin-error'):
            return
        record = dict(time=now(), path=path, **event)
        with self.lock:
            if kind == 'ready':
                self.decoded['ready'] = True
            elif kind == 'spin':
                try:
                    sys.path.insert(0, str(ROOT.parent)) if str(ROOT.parent) not in sys.path else None
                    from server.adapters.jili.jokers_fortune_winx import unpack
                    response = event['response']
                    if response['ret'] != 0:
                        raise ValueError('Game response ret=' + str(response['ret']))
                    outer = unpack('SpinResponse', response['data'])
                    spin = unpack('SpinAck', outer['data'])
                    record['spin'] = spin
                    record['request_decoded'] = unpack('SpinReq', event['request'])
                    record['scatter_win'] = sum(r.get('ScatterWin', 0) for r in spin['RoundQueue'])
                    self.decoded['spins'] += 1
                    self.decoded['scatter_wins'] += int(record['scatter_win'] > 0)
                except Exception as exc:
                    record['decode_error'] = str(exc)
                    self.decoded['errors'] += 1
            else:
                self.decoded['errors'] += 1
            with (self.folder / 'decoded-rounds.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + '\n')

    async def run(self):
        browser = None
        context = None
        try:
            async with async_playwright() as pw:
                try:
                    browser = await launch_browser(pw, self.headless)
                    context = await browser.new_context(record_har_path=str(self.folder / 'network.har'),
                        record_har_content='embed', record_har_mode='full')
                    await context.expose_binding('__captureDecoded', self.decoded_event)
                    await context.add_init_script(path=str(ROOT / 'decoded-hook.js'))
                    context.on('request', self.request)
                    context.on('response', lambda response: self.schedule(self.response(response)))
                    context.on('requestfailed', self.failed)
                    context.on('page', lambda page: page.on('websocket', self.websocket))
                    page = await context.new_page()
                    with self.lock:
                        self.state = 'recording'
                    try:
                        await page.goto(self.url, wait_until='domcontentloaded', timeout=45000)
                    except Exception as exc:
                        with self.lock:
                            self.error = '页面导航提示：' + str(exc)
                    while not self.stop.is_set() and browser.is_connected() and context.pages:
                        await asyncio.sleep(0.2)
                finally:
                    with self.lock:
                        self.state = 'stopping'
                    self.accepting = False
                    if self.tasks:
                        await asyncio.wait(list(self.tasks), timeout=5)
                    if context:
                        try:
                            await context.close()
                        except Exception as exc:
                            with self.lock:
                                self.error += '\nHAR 保存提示：' + str(exc)
                    if self.tasks:
                        _, pending = await asyncio.wait(list(self.tasks), timeout=3)
                        for task in pending:
                            task.cancel()
                        await asyncio.gather(*pending, return_exceptions=True)
                    if browser:
                        await browser.close()
        except Exception as exc:
            with self.lock:
                self.error = str(exc)
                self.state = 'error'
        finally:
            with self.lock:
                for row in self.rows:
                    if row['state'] == 'pending':
                        row.update(state='unavailable', error='停止时请求未完成，未能取得完整响应。')
                if self.state != 'error':
                    self.state = 'completed'
                (self.folder / 'manifest.json').write_text(
                    json.dumps(self.snapshot(), ensure_ascii=False, indent=2), encoding='utf-8')

    def start(self):
        threading.Thread(target=lambda: asyncio.run(self.run()), daemon=True).start()


def snapshot(sid):
    if sid in SESSIONS:
        return SESSIONS[sid].snapshot()
    path = DATA / sid / 'manifest.json'
    if path.is_file():
        return json.loads(path.read_text(encoding='utf-8'))
    return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, status, data, mime='application/json; charset=utf-8', filename=None):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def allowed(self):
        return self.headers.get('Host', '') in ('127.0.0.1:8090', 'localhost:8090')

    def do_GET(self):
        if not self.allowed():
            return self.send(403, {'error': 'Invalid host'})
        path = urlsplit(self.path).path
        if path == '/':
            html = (ROOT / 'index.html').read_text(encoding='utf-8').replace('__TOKEN__', TOKEN)
            return self.send(200, html.encode(), 'text/html; charset=utf-8')
        if path == '/api/sessions':
            ids = set(SESSIONS)
            if DATA.exists():
                ids.update(p.name for p in DATA.iterdir() if (p / 'manifest.json').is_file())
            records = []
            for sid in ids:
                item = snapshot(sid)
                if item:
                    records.append({k: v for k, v in item.items() if k != 'rows'})
            return self.send(200, sorted(records, key=lambda x: x['created'], reverse=True))
        parts = path.strip('/').split('/')
        if len(parts) >= 3 and parts[:2] == ['api', 'sessions']:
            sid = parts[2]
            if len(sid) != 32 or any(c not in '0123456789abcdef' for c in sid):
                return self.send(404, {'error': '不存在的抓取记录'})
            item = snapshot(sid)
            if not item:
                return self.send(404, {'error': '不存在的抓取记录'})
            if len(parts) == 3:
                return self.send(200, item)
            if len(parts) == 4 and parts[3] == 'download':
                if item['state'] not in ('completed', 'error'):
                    return self.send(409, {'error': '请先停止抓取，等待文件保存完成'})
                folder = DATA / sid
                archive = folder / 'capture.zip'
                with MANAGER_LOCK:
                    if not archive.exists():
                        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
                            for file in folder.rglob('*'):
                                if file.is_file() and file != archive:
                                    z.write(file, file.relative_to(folder))
                # Stream the archive so large sessions do not require a second RAM copy.
                self.send_response(200)
                self.send_header('Content-Type', 'application/zip')
                self.send_header('Content-Length', str(archive.stat().st_size))
                self.send_header('Content-Disposition', f'attachment; filename="capture-{sid[:8]}.zip"')
                self.end_headers()
                with archive.open('rb') as f:
                    while chunk := f.read(1024 * 1024):
                        self.wfile.write(chunk)
                return
            if len(parts) == 5 and parts[3] == 'body' and parts[4].isdigit():
                row = next((r for r in item['rows'] if r['id'] == int(parts[4])), None)
                if not row or not row['body']:
                    return self.send(404, {'error': '该响应没有可用的响应体'})
                with (DATA / sid / row['body']).open('rb') as f:
                    raw = f.read(256 * 1024 + 1)
                is_text = any(t in row['mime'] for t in ('text/', 'json', 'javascript', 'xml', 'svg', 'form-urlencoded'))
                return self.send(200, dict(text=raw[:256*1024].decode('utf-8', errors='replace') if is_text else base64.b64encode(raw[:4096]).decode(),
                    encoding='text' if is_text else 'base64', truncated=len(raw) > 256*1024 if is_text else row['size'] > 4096))
        self.send(404, {'error': 'Not found'})

    def do_POST(self):
        if not self.allowed() or self.headers.get('X-Capture-Token') != TOKEN:
            return self.send(403, {'error': '请刷新本地页面后重试'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 16384:
                raise ValueError('请求长度无效')
            data = json.loads(self.rfile.read(size))
            path = urlsplit(self.path).path
            if path == '/api/start':
                url = data.get('url', '').strip()
                parsed = urlsplit(url)
                if parsed.scheme not in ('http', 'https') or not parsed.hostname:
                    raise ValueError('请输入完整的 http:// 或 https:// 网址')
                with MANAGER_LOCK:
                    if any(c.state in ('starting', 'recording', 'stopping') for c in SESSIONS.values()):
                        return self.send(409, {'error': '请先停止当前抓取'})
                    capture = Capture(url)
                    SESSIONS[capture.id] = capture
                    capture.start()
                return self.send(201, {'id': capture.id})
            if path == '/api/stop':
                capture = SESSIONS.get(data.get('id'))
                if not capture:
                    raise ValueError('没有正在运行的抓取')
                capture.stop.set()
                return self.send(200, {'ok': True})
            self.send(404, {'error': 'Not found'})
        except (ValueError, TypeError, AttributeError) as exc:
            self.send(400, {'error': str(exc)})


if __name__ == '__main__':
    server = ThreadingHTTPServer(('127.0.0.1', 8090), Handler)
    print('Response Capture: http://127.0.0.1:8090', flush=True)
    if '--open' in sys.argv:
        webbrowser.open('http://127.0.0.1:8090')
    server.serve_forever()
