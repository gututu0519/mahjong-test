"""End-to-end test against local fixtures; no third-party website needed."""
import asyncio
import base64
import hashlib
import io
import json
import struct
import tempfile
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import app
from playwright.async_api import async_playwright

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aN1sAAAAASUVORK5CYII=')


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == '/ws':
            key = self.headers['Sec-WebSocket-Key'] + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
            self.send_response(101)
            self.send_header('Upgrade', 'websocket')
            self.send_header('Connection', 'Upgrade')
            self.send_header('Sec-WebSocket-Accept', base64.b64encode(hashlib.sha1(key.encode()).digest()).decode())
            self.end_headers()
            self.wfile.write(b'\x81\x07ws-test')
            self.wfile.flush()
            self.close_connection = True
            return
        if self.path == '/redirect':
            self.send_response(302)
            self.send_header('Location', '/json')
            self.end_headers()
            return
        if self.path == '/failed':
            self.connection.shutdown(2)
            self.connection.close()
            return
        status = 200
        mime = 'text/html; charset=utf-8'
        if self.path == '/':
            body = b'''<!doctype html><img src="/image"><iframe src="/frame"></iframe><script>
fetch('/json');fetch('/redirect');fetch('/missing');fetch('/failed').catch(()=>{});
fetch('/echo',{method:'POST',body:'hello request'});
new WebSocket('ws://'+location.host+'/ws');
</script>'''
        elif self.path == '/json':
            body = '{"message":"你好","ok":true}'.encode()
            mime = 'application/json'
        elif self.path == '/image':
            body = PNG
            mime = 'image/png'
        elif self.path == '/frame':
            body = b'<p>iframe response</p>'
        else:
            body = b'not found'
            status = 404
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


async def test():
    fixture = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
    ui = ThreadingHTTPServer(('127.0.0.1', 8090), app.Handler)
    for server in [fixture, ui]:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    target = f'http://127.0.0.1:{fixture.server_port}'
    with tempfile.TemporaryDirectory(prefix='capture-test-') as temp:
        app.DATA = Path(temp)
        try:
            async with async_playwright() as pw:
                browser = await app.launch_browser(pw, headless=True)
                page = await browser.new_page(viewport={'width': 1440, 'height': 1000})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                await page.goto('http://127.0.0.1:8090')
                bad = await page.request.post('http://127.0.0.1:8090/api/start', data={'url':target})
                assert bad.status == 403, 'Missing CSRF token must be rejected'
                await page.get_by_label('目标网址', exact=True).fill(target)
                await page.get_by_role('button', name='开始抓取').click()
                for _ in range(120):
                    await asyncio.sleep(.25)
                    captures = list(app.SESSIONS.values())
                    if captures:
                        snap = captures[0].snapshot()
                        if snap['state'] == 'error':
                            raise AssertionError(snap['error'])
                        if len(snap['rows']) >= 9 and snap['ws_count'] and not any(r['state'] == 'pending' for r in snap['rows']):
                            break
                else:
                    raise AssertionError('Capture did not finish fixture requests: ' + str(snap))
                capture = captures[0]
                await page.get_by_role('button', name='停止并保存').click()
                await page.locator('#state').filter(has_text='已保存').wait_for(timeout=20000)
                snap = capture.snapshot()
                rows = snap['rows']
                get_row = lambda suffix: next(r for r in rows if r['url'].endswith(suffix))
                assert get_row('/json')['state'] == 'complete'
                assert get_row('/missing')['status'] == 404
                assert get_row('/redirect')['status'] == 302
                assert get_row('/failed')['state'] == 'failed'
                assert (capture.folder / get_row('/image')['body']).read_bytes() == PNG
                assert (capture.folder / get_row('/echo')['request_body']).read_bytes() == b'hello request'
                assert (capture.folder / get_row('/echo')['body']).read_bytes() == b'hello request'
                assert snap['ws_count'] >= 1
                await page.get_by_label('搜索请求').fill('/json')
                await page.locator('#rows tr').first.click()
                await page.locator('#preview').filter(has_text='你好').wait_for()
                await page.get_by_label('搜索请求').fill('')
                await page.screenshot(path=str(app.ROOT / 'preview.png'), full_page=True)
                archive = await page.request.get(f'http://127.0.0.1:8090/api/sessions/{capture.id}/download')
                assert archive.status == 200
                with zipfile.ZipFile(io.BytesIO(await archive.body())) as z:
                    assert 'manifest.json' in z.namelist()
                    assert 'network.har' in z.namelist()
                    assert 'websockets.jsonl' in z.namelist()
                    har = json.loads(z.read('network.har'))
                    assert len(har['log']['entries']) >= 8
                    assert z.read(get_row('/image')['body']) == PNG
                app.SESSIONS.clear()
                restored = await page.request.get(f'http://127.0.0.1:8090/api/sessions/{capture.id}')
                assert (await restored.json())['state'] == 'completed'
                await page.set_viewport_size({'width':390, 'height':844})
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile overflow'
                assert not errors, errors
                await browser.close()
                print('PASS: UI start/stop, JSON, binary, POST, iframe, redirect, 404, failure, WebSocket, preview, ZIP/HAR, history, CSRF, mobile layout')
        finally:
            for capture in app.SESSIONS.values():
                capture.stop.set()
            for server in [fixture, ui]:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    asyncio.run(test())
