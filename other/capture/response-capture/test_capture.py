"""本机夹具端到端验证：底层网址抓取兼容接口与行内请求、保存、归档。"""
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
from types import SimpleNamespace
from unittest.mock import patch

import app
import control_server
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


def integrated_tool():
    manager = SimpleNamespace(snapshot=lambda: {'services': []}, original_games=app.ORIGINAL_GAMES)
    return control_server.create_server(('127.0.0.1', 0), manager=manager)


async def test():
    launch = app.launch_browser

    async def headless_browser(pw, headless=False):
        return await launch(pw, headless=True)

    fixture = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
    ui = integrated_tool()
    assert ui.integrated and ui.proxy is None
    origin = f'http://127.0.0.1:{ui.server_port}'
    for server in [fixture, ui]:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    target = f'http://127.0.0.1:{fixture.server_port}'
    with tempfile.TemporaryDirectory(prefix='capture-test-') as temp, \
         patch.object(app, 'DATA', Path(temp)), patch.object(app, 'SESSIONS', {}), \
         patch.object(app, 'launch_browser', headless_browser), \
         patch.object(app.ORIGINAL_GAMES, 'catalog', return_value={'games':[], 'errors':[]}):
        try:
            async with async_playwright() as pw:
                browser = await app.launch_browser(pw, headless=True)
                page = await browser.new_page(viewport={'width': 1440, 'height': 1000})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                await page.goto(origin)
                headers = {'X-Capture-Token': ui.token}
                status = await (await page.request.get(origin + '/api/status')).json()
                owner = await (await page.request.get(origin + '/api/services/control-status')).json()
                assert status['integrated'] and status['pid'] == owner['pid'] and status['port'] == owner['port']
                assert (await page.request.post(origin+'/api/shutdown', headers=headers, data={})).status == 409
                bad = await page.request.post(origin + '/api/start', data={'url':target})
                assert bad.status == 403, 'Missing CSRF token must be rejected'
                started = await page.request.post(origin + '/api/start',
                    headers=headers, data={'url':target})
                assert started.status == 201
                assert (await page.request.post(origin+'/api/services/stop', headers=headers, data={'id':'fixed.capture'})).status == 409
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
                row = page.locator('#library-rows > tr[data-game-key]').filter(has=page.locator('.game-records-toggle')).first
                await row.locator('.game-records-toggle').click()
                batch = row.locator('.capture-batch[data-session-id="' + capture.id + '"]')
                await batch.locator('.batch-view').click()
                async with page.expect_response(lambda r:r.url == origin+'/api/stop') as stopped:
                    await batch.locator('.batch-stop').click()
                assert (await stopped.value).request.post_data_json['id'] == capture.id
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
                tool = page.locator('.sc-card[data-service-id="fixed.capture"]')
                await tool.get_by_role('button', name='暂停新抓取：抓取工具').click()
                await tool.get_by_role('button', name='恢复新抓取：抓取工具').wait_for()
                assert (await page.request.post(origin+'/api/start', headers=headers, data={'url':target})).status == 409
                assert (await page.request.get(f'{origin}/api/sessions/{capture.id}/quality')).status == 200
                assert capture.id in (await (await page.request.get(origin+'/api/services/logs?id=fixed.capture')).json())['text']
                archive = await page.request.get(f'{origin}/api/sessions/{capture.id}/download')
                assert archive.status == 200
                with zipfile.ZipFile(io.BytesIO(await archive.body())) as z:
                    assert 'manifest.json' in z.namelist()
                    assert 'network.har' in z.namelist()
                    assert 'websockets.jsonl' in z.namelist()
                    har = json.loads(z.read('network.har'))
                    assert len(har['log']['entries']) >= 8
                    assert z.read(get_row('/image')['body']) == PNG
                app.SESSIONS.clear()
                restored = await page.request.get(f'{origin}/api/sessions/{capture.id}')
                assert (await restored.json())['state'] == 'completed'
                assert capture.id in [entry['id'] for entry in await (await page.request.get(origin+'/api/sessions')).json()]
                await tool.get_by_role('button', name='恢复新抓取：抓取工具').click()
                await tool.get_by_role('button', name='暂停新抓取：抓取工具').wait_for()
                assert (await (await page.request.get(origin+'/api/status')).json())['accepting_new']
                await page.set_viewport_size({'width':390, 'height':844})
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile overflow'
                assert not errors, errors
                await browser.close()
                print('PASS: 兼容 API 启动、行内停止与查看、JSON、二进制、POST、iframe、跳转、404、失败、WebSocket、ZIP/HAR、历史、CSRF、移动布局')
        finally:
            for capture in app.SESSIONS.values():
                capture.stop.set()
            for server in [fixture, ui]:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    asyncio.run(test())
