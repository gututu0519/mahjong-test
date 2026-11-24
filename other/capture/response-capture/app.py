"""Local browser response recorder. Run with .venv/Scripts/python app.py."""
import asyncio
import base64
import copy
import json
import mimetypes
import os
import re
import secrets
import sys
import threading
import time
import uuid
import webbrowser
import zipfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.client import HTTPConnection, HTTPException
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import async_playwright
from feature_maintenance import start_supervisor, stop_supervisor
from quality_service import get_session_quality
from library_input import project_session, catalog_target
from archive_identity import archive_index, enrich_target, game_label, sync_legacy_groups, link_legacy_session
from capture_layout import session_folder, plain_directory, SESSION_ID
from lobby_flow import enter_lobby, open_game, LobbyFlowError

ROOT = Path(__file__).resolve().parent
LEGACY_ROOT = ROOT.parents[1] / 'legacy'
DATA = ROOT / 'captures'
TOKEN = secrets.token_urlsafe(32)
SESSIONS = {}
MANAGER_LOCK = threading.Lock()
ZIP_LOCKS = [threading.Lock() for _ in range(32)]
ACTIVE_STATES = ('starting', 'recording', 'stopping')
LOBBY_URL = 'https://sdstest.ink/'
# 定向抓取保留游戏入口和游戏资源；大厅的登录、用户资料等接口不进入该批次。
GAME_TRAFFIC = re.compile(r'^https?://(?!sdstest\.ink(?::443)?/api/(?!v1/games/))', re.I)


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
    def __init__(self, url, headless=False, *, target=None):
        self.id = uuid.uuid4().hex
        self.url = url
        self.headless = headless
        self.target = target
        self.display_name = game_label(target) if target else ''
        self.game_stage = '等待打开登录窗口' if target else ''
        base = DATA / self.display_name if self.display_name else DATA
        base.mkdir(parents=True, exist_ok=True)
        if not plain_directory(base):
            raise ValueError('目标游戏的保存位置不是实际文件夹。')
        self.folder = base / self.id
        self.folder.mkdir()
        (self.folder / 'bodies').mkdir()
        self.archived = False
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

    def snapshot(self, include_rows=True):
        with self.lock:
            if include_rows and self.archived:
                return json.loads((self.folder / 'manifest.json').read_bytes())
            item = dict(id=self.id, url=self.url, created=self.created, state=self.state,
                        error=self.error, ws_count=self.ws_count, decoded=self.decoded)
            if include_rows:
                item['rows'] = self.rows
            if self.display_name:
                item['display_name'] = self.display_name
            if self.target:
                item.update(game_stage=self.game_stage, target_game=self.target)
            return copy.deepcopy(item)

    def update(self, row, **values):
        with self.lock:
            row.update(values)

    def request(self, req):
        if self.target and not GAME_TRAFFIC.match(req.url):
            return None
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
        # 新模式中，开始监听前发出的请求可能在登录之后才返回。
        row = self.requests.get(res.request) if self.target else self.request(res.request)
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
        row = self.requests.get(req) if self.target else self.request(req)
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
        if not path.startswith(('/sss-jf2/', '/sss-tbv/', '/mpt2/', '/rx10000/')) or not isinstance(event, dict):
            return
        kind = event.get('kind')
        if kind not in ('ready', 'spin', 'spin-error'):
            return
        record = dict(time=now(), path=path, **event)
        with self.lock:
            if kind == 'ready':
                self.decoded['ready'] = True
                self.decoded['game'] = ('Roma X 10000' if path.startswith('/rx10000/')
                                        else 'Money Pot DELUXE' if path.startswith('/mpt2/')
                                        else '3 Billion Vaults' if path.startswith('/sss-tbv/') else 'Joker')
            elif kind == 'spin':
                try:
                    if str(LEGACY_ROOT) not in sys.path:
                        sys.path.insert(0, str(LEGACY_ROOT))
                    if path.startswith('/rx10000/'):
                        from py.adapters.jili.roma_x_10000 import unpack
                    elif path.startswith('/mpt2/'):
                        from py.adapters.jili.money_pot_deluxe import unpack
                    elif path.startswith('/sss-tbv/'):
                        from py.adapters.jili.three_billion_vaults import unpack
                    else:
                        from py.adapters.jili.jokers_fortune_winx import unpack
                    response = event['response']
                    if response['ret'] != 0:
                        raise ValueError('Game response ret=' + str(response['ret']))
                    outer = unpack('SpinResponse', response['data'])
                    spin = unpack('SpinAck', outer['data'])
                    record['spin'] = spin
                    record['request_decoded'] = unpack('SpinReq', event['request'])
                    record['scatter_win'] = sum(r.get('ScatterWin', 0) for r in spin['RoundQueue'])
                    if path.startswith('/sss-tbv/'):
                        self.decoded['feature_spins'] = self.decoded.get('feature_spins', 0) + int(any(r.get('FreeTotalRound', 0) > 0 for r in spin['RoundQueue']))
                        self.decoded['jackpot_wins'] = self.decoded.get('jackpot_wins', 0) + int(any(r.get('JPPlate', {}).get('Win', 0) > 0 for r in spin['RoundQueue']))
                    if path.startswith('/mpt2/'):
                        self.decoded['feature_spins'] = self.decoded.get('feature_spins', 0) + int(any(r.get('GetReSpin', False) for r in spin['RoundQueue']))
                    if path.startswith('/rx10000/'):
                        self.decoded['feature_spins'] = self.decoded.get('feature_spins', 0) + int(
                            any(r.get('FreeTotalRound', 0) > 0 for r in spin['RoundQueue']) or bool(spin.get('BonusInfo')) or bool(spin.get('BonusWheelMult')))
                    self.decoded['spins'] += 1
                    self.decoded['scatter_wins'] += int(record['scatter_win'] > 0)
                except Exception as exc:
                    record['decode_error'] = str(exc)
                    self.decoded['errors'] += 1
            else:
                self.decoded['errors'] += 1
            with (self.folder / 'decoded-rounds.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + '\n')

    async def wait_for_action(self, action, page):
        """登录或导航过程中，同样允许通过工具的停止按钮取消。"""
        task = asyncio.create_task(action)
        try:
            while not task.done():
                if self.stop.is_set():
                    return False
                if page.is_closed():
                    raise LobbyFlowError('抓取窗口已关闭，请重新点击该游戏的“抓取”。')
                await asyncio.wait((task,), timeout=0.2)
            await task
            return not self.stop.is_set()
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def run(self, credentials=None):
        browser = None
        context = None
        try:
            async with async_playwright() as pw:
                try:
                    browser = await launch_browser(pw, self.headless)
                    har = str(self.folder / 'network.har')
                    if self.target:
                        context = await browser.new_context(service_workers='block')
                        page = await context.new_page()
                        self.game_stage = '正在登录大厅'
                        try:
                            if not await self.wait_for_action(enter_lobby(page, *credentials), page):
                                return
                        finally:
                            credentials = None
                        self.game_stage = '登录成功，正在打开所选游戏'
                        # 在同一浏览器窗口中，登录完成后才开始 HAR 记录。
                        await context.route_from_har(har, url=GAME_TRAFFIC, update=True, update_content='embed', update_mode='full')
                    else:
                        context = await browser.new_context(record_har_path=har, record_har_content='embed', record_har_mode='full')
                    await context.expose_binding('__captureDecoded', self.decoded_event)
                    await context.add_init_script(path=str(ROOT / 'decoded-hook.js'))
                    context.on('request', self.request)
                    context.on('response', lambda response: self.schedule(self.response(response)))
                    context.on('requestfailed', self.failed)
                    context.on('page', lambda page: page.on('websocket', self.websocket))
                    if self.target:
                        page.on('websocket', self.websocket)
                        if not await self.wait_for_action(open_game(page, self.target), page):
                            return
                        self.game_stage = '已进入所选游戏，正在抓取'
                        self.state = 'recording'
                    else:
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
                if self.target:
                    self.error = str(exc) if isinstance(exc, LobbyFlowError) else self.game_stage + '未完成，请检查网络或重新开始。'
                    self.game_stage = '定向抓取未完成'
                else:
                    self.error = str(exc)
                self.state = 'error'
        finally:
            with self.lock:
                for row in self.rows:
                    if row['state'] == 'pending':
                        row.update(state='unavailable', error='停止时请求未完成，未能取得完整响应。')
                if self.state != 'error':
                    self.state = 'completed'
                    if self.target:
                        self.game_stage = '抓取已结束'
                pending = self.folder / 'manifest.pending'
                pending.write_text(json.dumps(self.snapshot(), ensure_ascii=False, indent=2), encoding='utf-8')
                pending.replace(self.folder / 'manifest.json')
                self.archived = True
                self.requests.clear()
                self.rows.clear()

    def start(self, credentials=None):
        threading.Thread(target=asyncio.run, args=(self.run(credentials),), daemon=True).start()


def snapshot(sid):
    if sid in SESSIONS:
        return SESSIONS[sid].snapshot()
    folder = session_folder(DATA, sid)
    if folder and (path := folder / 'manifest.json').is_file():
        item = json.loads(path.read_bytes())
        if item.get('state') == 'complete':
            item['state'] = 'completed'
        return item
    return None


def resolve_target(game_id):
    if not isinstance(game_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', game_id):
        raise ValueError('无效的站内游戏 ID，请重新选择游戏。')
    historic = enrich_target(DATA, {'site': game_id})
    if historic and (historic.get('name') or historic.get('zh')) and historic.get('externalId'):
        return historic
    with MANAGER_LOCK:
        sessions = list(SESSIONS.values())
    for capture in reversed(sessions):
        if capture.archived:
            continue
        with capture.lock:
            rows = list(capture.rows)
        match = catalog_target(rows, capture.folder, game_id)
        if match:
            return match
    if historic and (historic.get('name') or historic.get('zh')):
        return historic
    raise ValueError('已保存的大厅目录中找不到这个站内 ID，请重新核对历史。')


class PreviousRecorder:
    """升级期间只读取旧实例的活动摘要，已完成的批次从共用目录读取。"""
    def __init__(self, port):
        self.port = port
        self.lock = threading.Lock()
        self.checked = None
        self.confirmed = None
        self.cache = {}

    def unfinished(self):
        return {sid: entry for sid, entry in self.cache.items()
                if (folder := session_folder(DATA, sid)) and not (folder / 'manifest.json').is_file()}

    def active(self):
        with self.lock:
            if self.checked is not None and time.monotonic() - self.checked < 20:
                return self.unfinished()
            connection = HTTPConnection('127.0.0.1', self.port, timeout=4)
            try:
                connection.request('GET', '/api/sessions')
                response = connection.getresponse()
                if response.status != 200:
                    raise ValueError('读取旧实例失败')
                data = json.loads(response.read(4 * 1024 * 1024))
                if not isinstance(data, list):
                    raise ValueError('旧实例不是抓取工具')
            except (ValueError, OSError, HTTPException):
                # 旧进程短暂繁忙时，保留已经确认属于该窗口的记录。
                self.checked = time.monotonic()
                if self.confirmed is None or self.checked - self.confirmed >= 60:
                    self.cache.clear()
                return self.unfinished()
            finally:
                connection.close()
            found = {}
            for raw in data:
                if not isinstance(raw, dict) or raw.get('state') not in ACTIVE_STATES:
                    continue
                sid = raw.get('id')
                if not isinstance(sid, str) or not SESSION_ID.fullmatch(sid) or not session_folder(DATA, sid):
                    continue
                target = raw.get('target_game')
                target = enrich_target(DATA, target) if isinstance(target, dict) else {}
                label = game_label(target) if target else ''
                found[sid] = {**{k: raw.get(k) for k in ('id','created','state','game_stage')},
                              'target_game': target, 'url': LOBBY_URL if target else '',
                              'display_name': label or '待识别游戏', 'source_port': self.port, 'external_session': True}
                if label:
                    link_legacy_session(DATA, sid, [label])
            self.checked = time.monotonic()
            self.confirmed = self.checked
            self.cache = found
            return self.unfinished()


def same_recording(record, target, url):
    other = record.get('target_game')
    if target:
        return bool(other and other.get('site') == target['site'])
    return not other and record.get('url') == url


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
        port = self.server.server_address[1]
        return self.headers.get('Host', '') in (f'127.0.0.1:{port}', f'localhost:{port}')

    def do_GET(self):
        if not self.allowed():
            return self.send(403, {'error': 'Invalid host'})
        path = urlsplit(self.path).path
        if path == '/':
            html = (ROOT / 'index.html').read_text(encoding='utf-8').replace('__TOKEN__', TOKEN)
            html = html.replace('__GAME_CAPTURE_VERSION__', '1')
            html = html.replace('__PARALLEL_CAPTURE_VERSION__', '1')
            return self.send(200, html.encode(), 'text/html; charset=utf-8')
        if path == '/api/feature-maintenance':
            status = ROOT.parents[2] / 'other/diagnostics/feature-maintenance/status.json'
            try:
                return self.send(200, json.loads(status.read_text(encoding='utf-8')))
            except (OSError, ValueError):
                return self.send(200, {'status': 'pending', 'reason': '维护表监督器尚未生成状态'})
        if path == '/api/sessions':
            with MANAGER_LOCK:
                local = list(SESSIONS.values())
            records = {c.id: c.snapshot(include_rows=False) for c in local}
            previous = getattr(self.server, 'previous_recorder', None)
            if previous:
                records.update(previous.active())
            saved = archive_index(DATA)
            sync_legacy_groups(DATA, saved)
            records.update({sid: entry['summary'] for sid, entry in saved.items()})
            return self.send(200, sorted(records.values(), key=lambda x: x.get('created') or '', reverse=True))
        parts = path.strip('/').split('/')
        if len(parts) >= 3 and parts[:2] == ['api', 'sessions']:
            sid = parts[2]
            if len(sid) != 32 or any(c not in '0123456789abcdef' for c in sid):
                return self.send(404, {'error': '不存在的抓取记录'})
            folder = session_folder(DATA, sid)
            if not folder:
                return self.send(404, {'error': '该批次的抓取目录不存在或有冲突'})
            item = snapshot(sid)
            if not item:
                return self.send(404, {'error': '不存在的抓取记录'})
            if len(parts) == 3:
                if not item.get('display_name') and folder and (folder / 'manifest.json').is_file():
                    summary = archive_index(DATA).get(sid, {}).get('summary', {})
                    for key in ('display_name','target_game','identity_games'):
                        if key in summary:
                            item[key] = summary[key]
                return self.send(200, item)
            if len(parts) == 4 and parts[3] == 'library-input':
                try:
                    return self.send(200, project_session(item, folder))
                except (OSError, ValueError, TypeError, KeyError):
                    return self.send(503, {'error': '批次目录尚未核对成功，请稍后重试'})
            if len(parts) == 4 and parts[3] == 'quality':
                try:
                    return self.send(200, get_session_quality(item, folder))
                except (OSError, ValueError, TypeError, KeyError):
                    return self.send(503, {'error': '采集检查暂不可用，请保留当前抓取记录', 'status': 'unknown'})
            if len(parts) == 4 and parts[3] == 'download':
                if item['state'] not in ('completed', 'error'):
                    return self.send(409, {'error': '请先停止抓取，等待文件保存完成'})
                archive = folder / 'capture.zip'
                with ZIP_LOCKS[int(sid[:2], 16) % len(ZIP_LOCKS)]:
                    if not archive.exists():
                        temporary = folder / ('archive-' + uuid.uuid4().hex + '.part')
                        try:
                            with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as z:
                                for file in folder.rglob('*'):
                                    if file.is_file() and file != archive and file.suffix != '.part':
                                        z.write(file, file.relative_to(folder))
                            temporary.replace(archive)
                        finally:
                            temporary.unlink(missing_ok=True)
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
                with (folder / row['body']).open('rb') as f:
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
            if path in ('/api/start', '/api/start-game'):
                target = credentials = None
                if path == '/api/start-game':
                    if not isinstance(data, dict) or set(data) != {'game_id', 'account', 'password'}:
                        raise ValueError('定向抓取需要站内游戏 ID、预设账号和密码。')
                    account, password = data.get('account'), data.get('password')
                    if (not isinstance(account, str) or not 0 < len(account.strip()) <= 256 or
                            not isinstance(password, str) or not 0 < len(password) <= 1024):
                        raise ValueError('请输入有效的预设账号和密码。')
                    target = resolve_target(data['game_id'])
                    credentials = (account.strip(), password)
                    url = LOBBY_URL
                else:
                    url = data.get('url', '').strip()
                    parsed = urlsplit(url)
                    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
                        raise ValueError('请输入完整的 http:// 或 https:// 网址')
                previous = getattr(self.server, 'previous_recorder', None)
                if previous and any(same_recording(r, target, url) for r in previous.active().values()):
                    return self.send(409, {'error': '该目标已在原窗口抓取，可继续选择其他游戏。'})
                with MANAGER_LOCK:
                    if any(c.state in ACTIVE_STATES and same_recording({'target_game': c.target, 'url': c.url}, target, url)
                           for c in SESSIONS.values()):
                        return self.send(409, {'error': '该游戏或网址已有抓取窗口，可继续选择其他游戏。'})
                    capture = Capture(url, target=target) if target else Capture(url)
                    SESSIONS[capture.id] = capture
                    if target:
                        capture.start(credentials=credentials)
                    else:
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
    import argparse
    parser = argparse.ArgumentParser(description='本地响应抓取工具')
    parser.add_argument('--port', type=int, default=8090)
    parser.add_argument('--previous-port', type=int, help='仅查看指定本机旧实例中正在录制的批次')
    parser.add_argument('--open', action='store_true')
    options = parser.parse_args()
    if options.previous_port is not None and (not 1 <= options.previous_port <= 65535 or options.port == options.previous_port):
        parser.error('旧实例端口必须有效且与本实例不同')
    server = ThreadingHTTPServer(('127.0.0.1', options.port), Handler)
    server.previous_recorder = PreviousRecorder(options.previous_port) if options.previous_port else None
    address = f'http://127.0.0.1:{server.server_address[1]}'
    print('Response Capture: ' + address, flush=True)
    if options.open:
        webbrowser.open(address)
    supervisor = start_supervisor() if options.port == 8090 else None
    try:
        server.serve_forever()
    finally:
        stop_supervisor(supervisor)
