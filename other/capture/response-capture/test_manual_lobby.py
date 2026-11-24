"""用完全拦截的大厅页面验证手动登录、独立窗口和会话生命周期。"""
import asyncio
import threading
import time
import unittest
from urllib.parse import urlsplit

from lobby_flow import LobbyFlowError, LobbyLoginExpired, ORIGIN
from manual_lobby import ManualLobbies, _target_id


def wait_until(check):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(.03)
    raise AssertionError('等待本地浏览器事件超时')


class _Capture:
    def __init__(self, expired=False):
        self.stop = threading.Event()
        self.entered = threading.Event()
        self.expired = expired

    async def run_manual(self, context, page, launch_lock):
        async with launch_lock:
            if self.expired:
                raise LobbyLoginExpired('测试会话过期')
            response = await page.goto(ORIGIN + '/manual-game')
            self.authenticated = response.status == 200
            self.separate_storage = await page.evaluate("""() => {
                const fresh = sessionStorage.getItem('fixture-game') === null && window.opener === null;
                sessionStorage.setItem('fixture-game', 'started');
                return fresh;
            }""")
            self.context = context
            info = await _target_id(context, page)
            cdp = await context.browser.new_browser_cdp_session()
            try:
                self.window = (await cdp.send('Browser.getWindowForTarget', {'targetId': info['targetId']}))['windowId']
            finally:
                await cdp.detach()
        self.entered.set()
        while not self.stop.is_set():
            await asyncio.sleep(.03)


class ManualLobbyTest(unittest.TestCase):
    def setUp(self):
        self.pages = []
        self.captures = []
        self.login_submissions = 0
        self.login_path = '/api/v1/auth/login'
        self.manager = ManualLobbies(self.launch, headless=True)
        self.addCleanup(self.cleanup)

    async def launch(self, pw, *, headless):
        browser = await pw.chromium.launch(headless=headless)
        new_context = browser.new_context

        async def intercept(**options):
            context = await new_context(**options)
            context.on('page', lambda page: self.pages.append(page))

            async def route(r):
                url = urlsplit(r.request.url)
                if url.netloc != 'sdstest.ink':
                    return await r.abort()
                if url.path == '/login':
                    return await r.fulfill(content_type='text/html', body="""<form class="login-form">
                      <button>Fixture sign in</button></form><script>
                      document.querySelector('form').onsubmit = async e => {e.preventDefault();
                          await fetch('/api/v1/auth/login', {method:'POST'}); e.target.remove()};
                      </script>""".replace('/api/v1/auth/login', self.login_path))
                if url.path == self.login_path:
                    self.login_submissions += 1
                    return await r.fulfill(status=204, headers={'Set-Cookie': 'fixture=allowed; Path=/; Secure; HttpOnly'})
                if url.path == '/manual-game':
                    authorized = await r.request.header_value('cookie') == 'fixture=allowed'
                    return await r.fulfill(status=200 if authorized else 401, body='game')
                await r.abort()

            await context.route('**/*', route)
            return context

        browser.new_context = intercept
        return browser

    def sign_in(self):
        ref = self.manager.start()['id']
        page = wait_until(lambda: next((p for p in reversed(self.pages) if p.url == ORIGIN + '/login'), None))

        async def click():
            await page.get_by_role('button', name='Fixture sign in').click()

        asyncio.run_coroutine_threadsafe(click(), self.manager._loop).result(timeout=5)
        wait_until(lambda: self.manager.status(ref)['state'] == 'ready')
        self.assertEqual(page.url, 'about:blank')
        return ref

    def start_capture(self, ref, expired=False):
        capture = _Capture(expired)
        future = self.manager.capture(ref, capture)
        self.captures.append((capture, future))
        return capture, future

    def cleanup(self):
        for capture, future in self.captures:
            capture.stop.set()
        for _, future in self.captures:
            try:
                future.result(timeout=8)
            except LobbyFlowError:
                pass
        self.manager.shutdown()

    def test_distinct_games_and_login_handles(self):
        ref = self.sign_in()
        other = self.manager.start()
        self.assertNotEqual(ref, other['id'])
        self.assertEqual('pending', other['state'])
        with self.assertRaises(LobbyFlowError):
            self.manager.capture(other['id'], _Capture())
        self.assertEqual('closed', self.manager.close(other['id'])['state'])
        first, first_done = self.start_capture(ref)
        second, second_done = self.start_capture(ref)
        self.assertTrue(first.entered.wait(8))
        self.assertTrue(second.entered.wait(8))
        self.assertTrue(first.authenticated and second.authenticated)
        self.assertTrue(first.separate_storage and second.separate_storage)
        self.assertIs(first.context, second.context)
        self.assertNotEqual(first.window, second.window)
        with self.assertRaises(LobbyFlowError):
            self.manager.close(ref)
        with self.assertRaises(LobbyFlowError):
            self.manager.shutdown()
        first.stop.set()
        first_done.result(timeout=8)
        self.assertFalse(second_done.done())
        second.stop.set()
        second_done.result(timeout=8)
        self.assertEqual('closed', self.manager.close(ref)['state'])
        with self.assertRaises(LobbyFlowError):
            self.manager.status('unknown')

    def test_expired_ref_keeps_running_game(self):
        self.login_path = '/api/v1/auth/login/code'
        ref = self.sign_in()
        live, ongoing = self.start_capture(ref)
        self.assertTrue(live.entered.wait(8))
        _, failed = self.start_capture(ref, expired=True)
        with self.assertRaises(LobbyLoginExpired):
            failed.result(timeout=8)
        self.assertEqual('closed', self.manager.status(ref)['state'])
        self.assertFalse(ongoing.done())
        with self.assertRaises(LobbyFlowError):
            self.manager.capture(ref, _Capture())
        live.stop.set()
        ongoing.result(timeout=8)

    def test_close_login_window_after_sign_in_and_reopen_games(self):
        ref = self.sign_in()
        login_page, = self.pages
        asyncio.run_coroutine_threadsafe(login_page.close(), self.manager._loop).result(timeout=5)
        self.assertEqual([], login_page.context.pages)

        first, first_done = self.start_capture(ref)
        second, second_done = self.start_capture(ref)
        for capture in (first, second):
            self.assertTrue(capture.entered.wait(8))
            self.assertTrue(capture.authenticated)
            self.assertTrue(capture.separate_storage)
        self.assertNotEqual(first.window, second.window)
        self.assertEqual('ready', self.manager.status(ref)['state'])
        first.stop.set()
        first_done.result(timeout=8)
        self.assertFalse(second_done.done())
        second.stop.set()
        second_done.result(timeout=8)
        self.assertEqual([], login_page.context.pages)

        later, later_done = self.start_capture(ref)
        self.assertTrue(later.entered.wait(8))
        self.assertTrue(later.authenticated)
        self.assertEqual(1, self.login_submissions)
        later.stop.set()
        later_done.result(timeout=8)

    def test_close_login_window_before_sign_in_cancels_connection(self):
        ref = self.manager.start()['id']
        page = wait_until(lambda: next((p for p in self.pages if p.url == ORIGIN + '/login'), None))
        asyncio.run_coroutine_threadsafe(page.close(), self.manager._loop).result(timeout=5)
        wait_until(lambda: self.manager.status(ref)['state'] == 'closed')
        self.assertEqual(0, self.login_submissions)
        with self.assertRaises(LobbyFlowError):
            self.manager.capture(ref, _Capture())

    def test_pending_and_idle_windows_expire(self):
        self.manager._pending_timeout = .15
        ref = self.manager.start()['id']
        wait_until(lambda: self.manager.status(ref)['state'] == 'closed')
        self.manager._pending_timeout = 30
        self.manager._idle_timeout = .2
        ref = self.sign_in()
        wait_until(lambda: self.manager.status(ref)['state'] == 'closed')

    def test_shutdown_waits_for_archived_capture_to_release_window(self):
        live, done = self.start_capture(self.sign_in())
        self.assertTrue(live.entered.wait(8))
        live.archived = True
        timer = threading.Timer(.15, live.stop.set)
        timer.start()
        try:
            self.manager.shutdown()
            self.assertTrue(done.done())
        finally:
            timer.join()
