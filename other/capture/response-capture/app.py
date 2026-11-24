"""Local browser response recorder. Run with .venv/Scripts/python app.py."""
import asyncio
import base64
import copy
import json
import mimetypes
import os
import re
import secrets
import subprocess
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
from types import SimpleNamespace
from urllib.parse import urlsplit

from playwright.async_api import async_playwright
from feature_maintenance import start_supervisor, stop_supervisor
from quality_service import get_session_quality
from library_input import project_session, catalog_target
from game_covers import serve_cover
from archive_identity import archive_index, enrich_target, game_label, sync_legacy_groups, link_legacy_session
from capture_layout import session_folder, plain_directory, SESSION_ID
from capture_directories import annotate_directories, requested_directory, display_directory, open_directory
from original_games import OriginalGames, process_created
from lobby_flow import enter_lobby, has_lobby_session, open_game, LobbyFlowError, LobbyLoginExpired
from lobby_profiles import LobbyProfiles
from manual_lobby import ManualLobbies
from manual_har import safe_headers, safe_url, write_page_har

ROOT = Path(__file__).resolve().parent
LEGACY_ROOT = ROOT.parents[1] / 'legacy'
DATA = ROOT / 'captures'
ORIGINAL_GAMES = OriginalGames(ROOT.parents[2], DATA)
TOKEN = secrets.token_urlsafe(32)
SESSIONS = {}
MANAGER_LOCK = threading.Lock()
ZIP_LOCKS = [threading.Lock() for _ in range(32)]
ACTIVE_STATES = ('starting', 'recording', 'stopping')
LOBBY_URL = 'https://sdstest.ink/'
LOBBY_PROFILES = LobbyProfiles()
# 定向抓取保留游戏入口和游戏资源；大厅的登录、用户资料等接口不进入该批次。
GAME_TRAFFIC = re.compile(r'^https?://(?!sdstest\.ink(?::443)?/api/(?!v1/games/))', re.I)
PROCESS_STARTED = datetime.now(timezone.utc).isoformat()
try:
    PROCESS_CREATED = process_created(SimpleNamespace(pid=os.getpid(), _handle=-1)) if os.name == 'nt' else None
except OSError:
    PROCESS_CREATED = None


def browser_channel():
    edge = Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe'
    chrome = Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe'
    for channel, path in [('msedge', edge), ('chrome', chrome)]:
        if path.exists():
            return channel
    return None


async def launch_browser(pw, headless=False):
    return await pw.chromium.launch(channel=browser_channel(), headless=headless)


MANUAL_LOBBIES = ManualLobbies(launch_browser=launch_browser)


async def launch_game_context(pw, profile_path, headless=False):
    return await pw.chromium.launch_persistent_context(
        profile_path, channel=browser_channel(), headless=headless, service_workers='block',
        args=[] if headless else ['--start-minimized'])


async def game_window_state(context, page, state):
    # 只操作本批次专用浏览器中承载该页面的原生窗口。
    cdp = await context.new_cdp_session(page)
    try:
        window = await cdp.send('Browser.getWindowForTarget')
        await cdp.send('Browser.setWindowBounds', {'windowId': window['windowId'], 'bounds': {'windowState': state}})
    finally:
        await cdp.detach()


def now():
    return datetime.now(timezone.utc).isoformat()


class Capture:
    def __init__(self, url, headless=False, *, target=None, manual_login=False):
        self.id = uuid.uuid4().hex
        self.url = url
        self.headless = headless
        self.target = target
        self.manual_login = manual_login
        self.display_name = game_label(target) if target else ''
        self.game_stage = '正在准备游戏窗口' if target else ''
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
            row = dict(id=len(self.rows) + 1, url=safe_url(req.url) if self.manual_login else req.url, method=req.method,
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
            headers = await req.headers_array()
            self.update(row, request_headers=safe_headers(headers) if self.manual_login else headers)
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
            self.update(row, status=res.status, mime=mime, response_headers=safe_headers(headers) if self.manual_login else headers,
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
            if not self.accepting:
                return
            binary = isinstance(payload, bytes)
            event = dict(time=now(), url=safe_url(ws.url) if self.manual_login else ws.url, direction=direction,
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

    async def prepare_lobby(self, page, returning, credentials):
        if returning:
            self.game_stage = '正在确认大厅登录状态'
            if await has_lobby_session(page):
                return
        self.game_stage = '正在使用预设账号登录大厅'
        await enter_lobby(page, *credentials)

    def record_error(self, exc):
        with self.lock:
            if self.target:
                self.error = str(exc) if isinstance(exc, LobbyFlowError) else self.game_stage + '未完成，请检查网络或重新开始。'
                self.game_stage = '定向抓取未完成'
            else:
                self.error = str(exc)
            self.state = 'error'

    def save_manifest(self):
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

    async def run_manual(self, context, page, launch_lock):
        async def open_selected_game():
            async with launch_lock:
                self.game_stage = '正在确认原站登录状态'
                if not await has_lobby_session(page):
                    raise LobbyLoginExpired('原站登录已过期，请回到抓取页，选择“点击登录获取session”重新登录。')
                self.game_stage = '已确认登录，正在打开所选游戏'
                # 独立监听页面及其游戏框架，登录窗口和其他游戏的请求不归到本批。
                await page.route('**/*', lambda route: route.fallback())
                await page.expose_binding('__captureDecoded', self.decoded_event)
                await page.add_init_script(path=str(ROOT / 'decoded-hook.js'))
                page.on('request', self.request)
                page.on('response', lambda response: self.schedule(self.response(response)))
                page.on('requestfailed', self.failed)
                page.on('websocket', self.websocket)
                await open_game(page, self.target)

        try:
            if not self.headless:
                await game_window_state(context, page, 'minimized')
            self.game_stage = '等待使用已登录的原站窗口'
            if not await self.wait_for_action(open_selected_game(), page):
                return
            if not self.headless:
                await game_window_state(context, page, 'normal')
                await page.bring_to_front()
            self.game_stage = '已进入所选游戏，正在抓取'
            self.state = 'recording'
            while not self.stop.is_set() and not page.is_closed():
                await asyncio.sleep(0.2)
        except Exception as exc:
            self.record_error(exc)
            if isinstance(exc, LobbyLoginExpired):
                raise
        finally:
            self.accepting = False
            if self.state != 'error':
                self.state = 'stopping'
            try:
                if self.tasks:
                    await asyncio.wait(list(self.tasks), timeout=5)
                if not page.is_closed():
                    await page.close()
                if self.tasks:
                    _, pending = await asyncio.wait(list(self.tasks), timeout=3)
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                await asyncio.to_thread(write_page_har, self.folder, self.rows, self.created)
            except Exception:
                self.record_error(LobbyFlowError('游戏窗口已结束，本批的 HAR 保存未完成。'))
            finally:
                self.save_manifest()

    def manual_done(self, future):
        # 建窗阶段就失败时，run_manual 尚未开始，也应当结束批次并留下诊断。
        if not self.archived:
            try:
                future.result()
            except Exception as exc:
                self.record_error(exc)
            self.save_manifest()

    async def run(self, credentials=None):
        browser = None
        context = None
        profile = None
        game_ready = closed_cleanly = False
        try:
            async with async_playwright() as pw:
                try:
                    har = str(self.folder / 'network.har')
                    if self.target:
                        profile = LOBBY_PROFILES.acquire(*credentials)
                        context = await launch_game_context(pw, profile.path, self.headless)
                        # 新标签不继承前一款游戏按标签保存的会话。
                        initial_pages = context.pages
                        page = await context.new_page()
                        for initial in initial_pages:
                            await initial.close()
                        if not self.headless:
                            await game_window_state(context, page, 'minimized')
                        try:
                            if not await self.wait_for_action(self.prepare_lobby(page, profile.returning, credentials), page):
                                return
                        finally:
                            credentials = None
                        self.game_stage = '登录成功，正在打开所选游戏'
                        # 在同一浏览器窗口中，登录完成后才开始 HAR 记录。
                        await context.route_from_har(har, url=GAME_TRAFFIC, update=True, update_content='embed', update_mode='full')
                    else:
                        browser = await launch_browser(pw, self.headless)
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
                        if not self.headless:
                            await game_window_state(context, page, 'normal')
                            await page.bring_to_front()
                        game_ready = True
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
                    while not self.stop.is_set() and context.pages and (browser is None or browser.is_connected()):
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
                            closed_cleanly = True
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
            self.record_error(exc)
        finally:
            if profile is not None:
                LOBBY_PROFILES.release(profile, reusable=game_ready and closed_cleanly)
            self.save_manifest()

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


def unfinished_count():
    """在 MANAGER_LOCK 内统计尚未完成保存的批次，供启动和关闭操作使用。"""
    return sum(c.state in ACTIVE_STATES or not c.archived for c in SESSIONS.values())


def session_records(previous=None):
    """列表与目录操作使用同一份游戏身份及实际目录核验结果。"""
    with MANAGER_LOCK:
        local = list(SESSIONS.values())
    records = {c.id: c.snapshot(include_rows=False) for c in local}
    folders = {c.id: c.folder for c in local}
    if previous:
        external = previous.active()
        records.update(external)
        folders.update({sid: folder for sid in external if (folder := session_folder(DATA, sid))})
    saved = archive_index(DATA)
    sync_legacy_groups(DATA, saved)
    records.update({sid: entry['summary'] for sid, entry in saved.items()})
    folders.update({sid: entry['folder'] for sid, entry in saved.items()})
    return annotate_directories(DATA, records, folders), folders


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

    def allowed_post(self):
        if not self.allowed() or self.headers.get('X-Capture-Token') != TOKEN:
            return False
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + self.headers.get('Host', ''):
            return False
        return (self.client_address[0] in ('127.0.0.1', '::1') and
                self.headers.get('Sec-Fetch-Site', 'none') in ('none', 'same-origin'))

    def do_GET(self):
        if not self.allowed():
            return self.send(403, {'error': 'Invalid host'})
        path = urlsplit(self.path).path
        if path.startswith('/game-covers/'):
            return serve_cover(self, path)
        if path == '/':
            html = (ROOT / 'index.html').read_text(encoding='utf-8').replace('__TOKEN__', TOKEN)
            html = html.replace('__LOCAL_GAME_COVERS__', '1')
            html = html.replace('__GAME_CAPTURE_VERSION__', '1')
            html = html.replace('__PARALLEL_CAPTURE_VERSION__', '1')
            return self.send(200, html.encode(), 'text/html; charset=utf-8')
        if path in ('/service-console.js', '/service-console.css'):
            asset = ROOT / path[1:]
            if not asset.is_file():
                return self.send(404, {'error': '没有该控制台资源'})
            mime = 'text/javascript; charset=utf-8' if path.endswith('.js') else 'text/css; charset=utf-8'
            return self.send(200, asset.read_bytes(), mime)
        login_status = re.fullmatch(r'/api/lobby-login/([0-9a-f]{32,64})', path)
        if login_status:
            try:
                return self.send(200, MANUAL_LOBBIES.status(login_status[1]))
            except LobbyFlowError as exc:
                return self.send(404, {'error': str(exc)})
        if path == '/api/status':
            with MANAGER_LOCK:
                active = unfinished_count()
                stopping = bool(getattr(self.server, 'stopping', False))
                paused = getattr(self.server, 'capture_paused', False)
            integrated = getattr(self.server, 'integrated', False)
            return self.send(200, {'service': 'response-capture', 'version': 1, 'pid': os.getpid(),
                                  'parent_pid': os.getppid(), 'created': PROCESS_CREATED, 'started': PROCESS_STARTED,
                                  'chat': os.environ.get('CODEX_THREAD_ID'), 'cwd': str(ROOT),
                                  'entry': str(ROOT / ('control_server.py' if integrated else 'app.py')),
                                  'integrated': integrated, 'accepting_new': not (paused or stopping),
                                  'port': self.server.server_port, 'state': 'stopping' if stopping else 'running',
                                  'active_sessions': active, 'capabilities': {
                                      'shutdown': not integrated, 'direct_game_window': True, 'manual_lobby_login': True,
                                      'close_login_window_after_sign_in': True}})
        if path == '/api/feature-maintenance':
            status = ROOT.parents[2] / 'other/diagnostics/feature-maintenance/status.json'
            try:
                return self.send(200, json.loads(status.read_text(encoding='utf-8')))
            except (OSError, ValueError):
                return self.send(200, {'status': 'pending', 'reason': '维护表监督器尚未生成状态'})
        if path == '/api/sessions':
            records, _ = session_records(getattr(self.server, 'previous_recorder', None))
            return self.send(200, sorted(records.values(), key=lambda x: x.get('created') or '', reverse=True))
        if path == '/api/original-games':
            try:
                return self.send(200, ORIGINAL_GAMES.catalog())
            except (OSError, ValueError, subprocess.SubprocessError):
                return self.send(503, {'error': '暂时无法读取本仓库的原版游戏产物。'})
        if path.startswith('/api/original-games/previews/'):
            try:
                return self.send(200, ORIGINAL_GAMES.job(path.rsplit('/', 1)[-1]))
            except ValueError as error:
                return self.send(404, {'error': str(error)})
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
        if not self.allowed_post():
            return self.send(403, {'error': '请刷新本地页面后重试'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 16384:
                raise ValueError('请求长度无效')
            data = json.loads(self.rfile.read(size))
        except (ValueError, TypeError) as exc:
            return self.send(400, {'error': str(exc)})
        return self.capture_post(urlsplit(self.path).path, data)

    def capture_post(self, path, data):
        try:
            if not isinstance(data, dict):
                raise ValueError('抓取操作需要 JSON 对象。')
            if path == '/api/lobby-login':
                if data != {}:
                    raise ValueError('打开原站登录不需要输入参数。')
                with MANAGER_LOCK:
                    if getattr(self.server, 'capture_paused', False):
                        return self.send(409, {'error': '已暂停新抓取，请先在抓取工具中恢复接收。'})
                    if getattr(self.server, 'stopping', False):
                        return self.send(409, {'error': '抓取服务正在关闭。'})
                    login = MANUAL_LOBBIES.start()
                return self.send(201, login)
            close_login = re.fullmatch(r'/api/lobby-login/([0-9a-f]{32,64})/close', path)
            if close_login:
                if data != {}:
                    raise ValueError('断开原站登录不需要输入参数。')
                try:
                    return self.send(200, MANUAL_LOBBIES.close(close_login[1]))
                except LobbyFlowError as exc:
                    return self.send(409, {'error': str(exc)})
            if path == '/api/shutdown':
                if data != {}:
                    raise ValueError('关闭抓取服务不接受额外参数。')
                if getattr(self.server, 'integrated', False):
                    return self.send(409, {'error': '抓取和服务管理共用此进程。可在抓取工具中暂停接收新抓取。'})
                with MANAGER_LOCK:
                    if unfinished_count():
                        return self.send(409, {'error': '仍有活动抓取，请先在游戏行停止并保存，再关闭抓取服务。'})
                    already = bool(getattr(self.server, 'stopping', False))
                    self.server.stopping = True
                self.send(200, {'ok': True, 'state': 'stopping', 'message': '正在正常关闭抓取服务。'})
                if not already:
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if path in ('/api/original-games/open-directory', '/api/original-games/preview'):
                if not isinstance(data, dict) or set(data) != {'id'}:
                    raise ValueError('请指定一个原版产物 ID，不能提交路径或启动命令。')
                try:
                    result = ORIGINAL_GAMES.open_folder(data['id']) if path.endswith('/open-directory') else ORIGINAL_GAMES.preview(data['id'])
                    return self.send(200, result)
                except (OSError, subprocess.SubprocessError):
                    return self.send(503, {'error': '原版产物操作失败，请检查本机资源管理器和启动环境。'})
            if path == '/api/open-directory':
                records, folders = session_records(getattr(self.server, 'previous_recorder', None))
                folder = requested_directory(DATA, records, folders, data)
                try:
                    open_directory(folder)
                except OSError:
                    return self.send(503, {'error': '无法打开资源管理器，请根据游戏行中的路径手动打开目录。'})
                return self.send(200, {'ok': True, 'directory': display_directory(DATA, folder)})
            if path in ('/api/start', '/api/start-game'):
                target = credentials = manual_ref = None
                if path == '/api/start-game':
                    if isinstance(data, dict) and set(data) == {'game_id', 'lobby_session'}:
                        manual_ref = data['lobby_session']
                        if not isinstance(manual_ref, str) or not re.fullmatch('[0-9a-f]{32,64}', manual_ref):
                            raise ValueError('本机登录窗口标识无效，请重新打开原站登录。')
                        if MANUAL_LOBBIES.status(manual_ref)['state'] != 'ready':
                            return self.send(409, {'error': '请先完成原站登录。'})
                    elif isinstance(data, dict) and set(data) == {'game_id', 'account', 'password'}:
                        account, password = data.get('account'), data.get('password')
                        if (not isinstance(account, str) or not 0 < len(account.strip()) <= 256 or
                                not isinstance(password, str) or not 0 < len(password) <= 1024):
                            raise ValueError('请输入有效的预设账号和密码。')
                        credentials = (account.strip(), password)
                    else:
                        raise ValueError('请选择已登录的原站窗口，或填写预设账号和密码。')
                    target = resolve_target(data['game_id'])
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
                    if getattr(self.server, 'capture_paused', False):
                        return self.send(409, {'error': '已暂停新抓取，请先在抓取工具中恢复接收。'})
                    if getattr(self.server, 'stopping', False):
                        return self.send(409, {'error': '抓取服务正在关闭，请等待重新启动后再抓取。'})
                    if any(c.state in ACTIVE_STATES and same_recording({'target_game': c.target, 'url': c.url}, target, url)
                           for c in SESSIONS.values()):
                        return self.send(409, {'error': '该游戏或网址已有抓取窗口，可继续选择其他游戏。'})
                    capture = Capture(url, target=target, manual_login=True) if manual_ref else (
                        Capture(url, target=target) if target else Capture(url))
                    SESSIONS[capture.id] = capture
                    if manual_ref:
                        try:
                            task = MANUAL_LOBBIES.capture(manual_ref, capture)
                        except LobbyFlowError as exc:
                            capture.record_error(exc)
                            capture.save_manifest()
                            return self.send(409, {'error': str(exc)})
                        task.add_done_callback(capture.manual_done)
                    elif target:
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
        try:
            MANUAL_LOBBIES.shutdown()
        finally:
            stop_supervisor(supervisor)
            server.server_close()
