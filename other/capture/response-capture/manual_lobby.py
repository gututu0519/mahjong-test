"""在专用浏览器中手动登录大厅，让各游戏在同一登录环境的独立窗口内运行。"""
import asyncio
from dataclasses import dataclass, field
import secrets
import threading
import time

from playwright.async_api import Error as BrowserError, async_playwright

import lobby_flow
from lobby_flow import LobbyFlowError, ORIGIN, _site_path


@dataclass
class _Lobby:
    id: str = field(default_factory=lambda: secrets.token_hex(16))
    state: str = 'pending'
    message: str = '正在打开大厅登录窗口。'
    captures: set = field(default_factory=set)
    last_use: float = field(default_factory=time.monotonic)


async def _login(page):
    confirmed = asyncio.get_running_loop().create_future()

    def on_response(response):
        request = response.request
        if (confirmed.done() or not response.ok or request.method != 'POST'
                or request.frame != page.main_frame or _site_path(request.frame.url) is None):
            return
        path = _site_path(response.url)
        if path in ('/api/v1/auth/login', '/api/v1/auth/login/code', '/api/v1/auth/refresh'):
            confirmed.set_result(path)

    def on_close(*_):
        if not confirmed.done():
            confirmed.set_result(None)

    page.on('response', on_response)
    page.on('close', on_close)
    try:
        response = await page.goto(ORIGIN + '/login', wait_until='domcontentloaded', timeout=45000)
        if response is None or not response.ok or _site_path(page.url) is None:
            raise LobbyFlowError('大厅登录页暂时无法打开，请检查站点连接。')
        form = page.locator('form.login-form')
        tab = page.locator('button.login-tab')
        opener = page.get_by_role('button', name='Open Login / Register', exact=True)
        try:
            if not await form.is_visible() and not await tab.is_visible() and await opener.is_visible():
                await opener.click(timeout=1500)
            if not await form.is_visible() and await tab.is_visible():
                await tab.click(timeout=1500)
        except BrowserError:
            # 页面仍可由玩家操作，账号和密码只在这个原站页面填写。
            pass
        path = await confirmed
        if path is None:
            return False
        if path != '/api/v1/auth/refresh':
            await form.wait_for(state='hidden', timeout=45000)
        if _site_path(page.url) is None:
            raise LobbyFlowError('登录后未回到指定大厅，请重新连接。')
    except BrowserError:
        if page.is_closed():
            return False
        raise
    finally:
        page.remove_listener('response', on_response)
        page.remove_listener('close', on_close)
        confirmed.cancel()

    # 原站已确认登录。用户在显示成功提示期间关窗也可以继续使用此浏览器会话。
    try:
        await page.goto('about:blank')
        await page.set_content('<html lang="zh-CN"><meta charset="utf-8"><title>大厅已连接</title>'
                               '<h1>大厅已连接</h1><p>可以关闭此窗口，回到抓取列表选择游戏。</p></html>')
    except BrowserError:
        if not page.is_closed():
            raise
    return True


async def _target_id(context, page):
    channel = await context.new_cdp_session(page)
    try:
        return (await channel.send('Target.getTargetInfo'))['targetInfo']
    finally:
        await channel.detach()


async def _new_window(lobby):
    existing = set(lobby.context.pages)
    target = await lobby.cdp.send('Target.createTarget', {
        'url': 'about:blank', 'newWindow': True, 'background': True, 'browserContextId': lobby.context_id})
    # 现场也可能有用户打开的标签，只使用本次创建的 CDP target。
    try:
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            for page in lobby.context.pages:
                if page in existing or page.is_closed():
                    continue
                try:
                    info = await _target_id(lobby.context, page)
                except BrowserError:
                    if page.is_closed():
                        continue
                    raise
                if info['targetId'] == target['targetId']:
                    return page
                existing.add(page)
            await asyncio.sleep(.03)
        raise asyncio.TimeoutError()
    except BaseException:
        try:
            await lobby.cdp.send('Target.closeTarget', target)
        except BrowserError:
            pass
        raise


class ManualLobbies:
    def __init__(self, launch_browser=None, *, headless=False, pending_timeout=600, idle_timeout=1800):
        self._launch = launch_browser
        self._headless = headless
        self._pending_timeout = pending_timeout
        self._idle_timeout = idle_timeout
        self._lock = threading.Condition()
        self._lobbies = {}
        self._loop = self._thread = None
        self._stopping = False

    def _lookup(self, ref):
        if not isinstance(ref, str) or ref not in self._lobbies:
            raise LobbyFlowError('登录窗口无效，请在抓取列表重新连接大厅。')
        return self._lobbies[ref]

    @staticmethod
    def _status(lobby):
        return {'id': lobby.id, 'state': lobby.state, 'message': lobby.message}

    def start(self):
        with self._lock:
            if self._stopping:
                raise LobbyFlowError('大厅登录窗口正在关闭，请稍后重试。')
            # 每次连接属于发起连接的列表页；新页面只会获得自己的登录窗口。
            if sum(not lobby.worker.done() for lobby in self._lobbies.values()) >= 4:
                raise LobbyFlowError('已打开四个大厅登录窗口，请先断开闲置的连接。')
            if len(self._lobbies) >= 16:
                oldest = next(ref for ref, old in self._lobbies.items() if old.worker.done())
                del self._lobbies[oldest]
            if self._loop is None:
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(target=self._loop.run_forever, daemon=True, name='manual-lobby')
                self._thread.start()
            lobby = _Lobby()
            self._lobbies[lobby.id] = lobby
            lobby.worker = asyncio.run_coroutine_threadsafe(self._serve(lobby), self._loop)
            return self._status(lobby)

    def status(self, ref):
        with self._lock:
            return self._status(self._lookup(ref))

    def close(self, ref):
        with self._lock:
            lobby = self._lookup(ref)
            if lobby.captures:
                raise LobbyFlowError('请先停止并保存使用此登录窗口的游戏抓取。')
            lobby.state, lobby.message = 'closed', '已断开大厅登录。'
            return self._status(lobby)

    def capture(self, ref, capture):
        with self._lock:
            lobby = self._lookup(ref)
            if self._stopping or lobby.state != 'ready':
                raise LobbyFlowError('请先在大厅窗口完成登录，再抓取游戏。')
            if capture in lobby.captures:
                raise LobbyFlowError('这个抓取已在当前大厅窗口启动。')
            lobby.captures.add(capture)
            return asyncio.run_coroutine_threadsafe(self._run_capture(lobby, capture), self._loop)

    async def _run_capture(self, lobby, capture):
        page = None
        try:
            while not capture.stop.is_set():
                try:
                    await asyncio.wait_for(lobby.window_lock.acquire(), timeout=.2)
                    break
                except asyncio.TimeoutError:
                    continue
            else:
                raise LobbyFlowError('已取消打开游戏窗口。')
            try:
                with self._lock:
                    if lobby.state != 'ready':
                        raise LobbyFlowError('大厅登录已断开，请重新连接。')
                page = await _new_window(lobby)
            finally:
                lobby.window_lock.release()
            await capture.run_manual(lobby.context, page, lobby.launch_lock)
        except lobby_flow.LobbyLoginExpired:
            with self._lock:
                lobby.state, lobby.message = 'closed', '原站登录已过期，请重新连接大厅。'
            raise
        except (BrowserError, asyncio.TimeoutError):
            raise LobbyFlowError('游戏窗口未能打开或已关闭，请检查大厅连接。') from None
        finally:
            try:
                if page is not None and not page.is_closed():
                    await page.close()
            except BrowserError:
                pass
            finally:
                with self._lock:
                    lobby.captures.discard(capture)
                    lobby.last_use = time.monotonic()
                    self._lock.notify_all()

    async def _serve(self, lobby):
        with self._lock:
            if lobby.state != 'pending':
                return
        login = browser = None
        try:
            async with async_playwright() as pw:
                try:
                    browser = (await self._launch(pw, headless=self._headless) if self._launch
                               else await pw.chromium.launch(headless=self._headless))
                    lobby.context = await browser.new_context(service_workers='block')
                    context_closed = asyncio.Event()
                    lobby.context.on('close', lambda *_: context_closed.set())
                    page = await lobby.context.new_page()
                    lobby.context_id = (await _target_id(lobby.context, page))['browserContextId']
                    lobby.cdp = await browser.new_browser_cdp_session()
                    lobby.launch_lock, lobby.window_lock = asyncio.Lock(), asyncio.Lock()
                    login = asyncio.create_task(_login(page))
                    with self._lock:
                        if lobby.state == 'pending':
                            lobby.message = '请在弹出的大厅窗口中正常登录。'
                    while True:
                        with self._lock:
                            state = lobby.state
                            elapsed = time.monotonic() - lobby.last_use
                            if state in ('pending', 'ready') and (not browser.is_connected() or context_closed.is_set()):
                                lobby.state, lobby.message = 'closed', '大厅浏览器连接已结束，请重新登录。'
                            elif state == 'pending' and login.done():
                                if login.result():
                                    lobby.state, lobby.message = 'ready', '大厅已登录，可以关闭原站窗口，继续抓取游戏。'
                                    lobby.last_use = time.monotonic()
                                else:
                                    lobby.state, lobby.message = 'closed', '登录尚未完成，原站窗口已关闭。'
                            elif state == 'pending' and elapsed >= self._pending_timeout:
                                lobby.state, lobby.message = 'closed', '等待登录超时，请重新连接大厅。'
                            elif state == 'ready' and not lobby.captures and elapsed >= self._idle_timeout:
                                lobby.state, lobby.message = 'closed', '大厅登录连接已闲置到期。'
                            if lobby.state in ('closed', 'error') and not lobby.captures:
                                break
                        await asyncio.sleep(.15)
                finally:
                    if login is not None:
                        login.cancel()
                        await asyncio.gather(login, return_exceptions=True)
                    if browser is not None:
                        await browser.close()
        except Exception as exc:
            with self._lock:
                if lobby.state != 'closed':
                    lobby.state = 'error'
                    lobby.message = str(exc) if isinstance(exc, LobbyFlowError) else '大厅登录窗口未能就绪，请检查浏览器或站点连接。'

    def shutdown(self):
        with self._lock:
            if self._loop is None or self._stopping:
                return
            if any(not getattr(capture, 'archived', False) for lobby in self._lobbies.values() for capture in lobby.captures):
                raise LobbyFlowError('还有游戏正在抓取，请先保存。')
            self._stopping = True
            # 清单已保存后关闭游戏页仍需短暂时间。只等待已归档对象释放其窗口。
            if not self._lock.wait_for(lambda: all(not lobby.captures for lobby in self._lobbies.values()), timeout=4):
                self._stopping = False
                raise LobbyFlowError('已保存的游戏窗口仍在关闭，请稍后重试。')
            for lobby in self._lobbies.values():
                lobby.state, lobby.message = 'closed', '已关闭大厅登录窗口。'
            loop, thread = self._loop, self._thread
            workers = [lobby.worker for lobby in self._lobbies.values()]
        for worker in workers:
            worker.result(timeout=55)
        loop.call_soon_threadsafe(loop.stop)
        thread.join()
        loop.close()
        with self._lock:
            self._loop = self._thread = None
            self._lobbies.clear()
            self._stopping = False
