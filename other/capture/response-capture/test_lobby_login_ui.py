"""验证登录窗口状态与游戏行之间的交互，仅使用本地模拟接口。"""
from pathlib import Path
import unittest
from urllib.parse import urlsplit

from playwright.async_api import async_playwright, expect


class LobbyLoginUITest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        pw = await async_playwright().start()
        self.addAsyncCleanup(pw.stop)
        browser = await pw.chromium.launch(headless=True)
        self.addAsyncCleanup(browser.close)
        self.page = await browser.new_page()
        self.assertions = []
        self.sid = 'a' * 32
        self.login = 'deaf' * 8
        self.state = 'pending'
        self.capability = True
        self.service = 'response-capture'
        self.fail_open = False
        self.writes = []
        self.polled = 0
        self.url = 'http://127.0.0.1:18096/'
        self.page.on('pageerror', lambda error: self.assertions.append(str(error)))
        await self.page.route('**/*', self.route)

    async def asyncTearDown(self):
        self.assertEqual([], self.assertions)

    async def route(self, route):
        path = urlsplit(route.request.url).path
        method = route.request.method
        if path == '/':
            html = Path(__file__).with_name('index.html').read_text(encoding='utf-8')
            html = html.replace('__PARALLEL_CAPTURE_VERSION__', '1').replace('__TOKEN__', 'ui-test')
            return await route.fulfill(content_type='text/html;charset=utf-8', body=html)
        if method == 'POST':
            self.writes.append((path, route.request.post_data_json))
        if path == '/api/status':
            return await route.fulfill(json={'service':self.service,
                'capabilities':{'manual_lobby_login':self.capability}})
        if path == '/api/lobby-login' and self.fail_open:
            return await route.fulfill(status=503, json={'error':'模拟窗口无法打开'})
        if path in ('/api/lobby-login', '/api/lobby-login/'+self.login):
            self.polled += int(method == 'GET')
            return await route.fulfill(json={'id':self.login,'state':self.state})
        if path == '/api/lobby-login/'+self.login+'/close':
            return await route.fulfill(json={'id':self.login, 'state':'closed'})
        if path == '/api/start-game':
            return await route.fulfill(status=201,json={'id':'b'*32,'state':'completed'})
        if path == '/api/sessions':
            return await route.fulfill(json=[{'id':self.sid,'state':'completed','url':'https://sdstest.ink/'}])
        if path == '/api/sessions/'+self.sid+'/library-input':
            return await route.fulfill(json={'verified_files':True,'rows':[{'url':'https://sdstest.ink/api/v1/games/catalog',
                'id':1, 'method':'GET','status':200,'size':100}],'catalogs':{'1':[{'name':'Fixture Game',
                'nameZh':'演示游戏','id':'fixture-game','externalId':'10','metadata':{'brand':'PP'},'provider':{'code':'pp'}}]}})
        if path == '/api/original-games':
            return await route.fulfill(json={'games':[]})
        return await route.fulfill(status=404, body='')

    async def test_ready_capture_disconnect_and_return_to_preset(self):
        p = self.page
        await p.goto(self.url)
        row = p.get_by_role('button', name='抓取', exact=True)
        await row.wait_for()
        await p.fill('#preset-account','fixture')
        await p.fill('#preset-password','fixture-pass')
        await p.click('#lobby-login-open')
        await expect(p.locator('#lobby-login-close')).to_have_text('取消登录')
        await row.click()
        await expect(p.locator('#library-feedback')).to_contain_text('请等原站登录就绪')
        self.assertFalse(any(path == '/api/start-game' for path, _ in self.writes))
        self.state = 'ready'
        await expect(p.locator('#lobby-login-status')).to_contain_text('原站已登录')
        async with p.expect_request('**/api/start-game') as manual:
            await row.click()
        self.assertEqual({'game_id':'fixture-game', 'lobby_session':self.login}, (await manual.value).post_data_json)
        self.assertTrue(self.login not in await p.evaluate('JSON.stringify([sessionStorage,localStorage,location.href])'))
        await p.click('#lobby-login-close')
        await expect(p.locator('#lobby-login-status')).to_contain_text('已断开')
        self.assertIn(('/api/lobby-login/'+self.login+'/close',{}), self.writes)
        async with p.expect_request('**/api/start-game') as preset:
            await p.locator('.library-grab').first.click()
        self.assertEqual({'game_id':'fixture-game','password':'fixture-pass','account':'fixture'}, (await preset.value).post_data_json)

    async def test_cancel_error_and_refresh_forgets_local_reference(self):
        p = self.page
        await p.goto(self.url)
        self.fail_open=True
        await p.click('#lobby-login-open')
        await expect(p.locator('#lobby-login-status')).to_contain_text('模拟窗口无法打开')
        self.fail_open=False
        await p.click('#lobby-login-open')
        await p.get_by_role('button',name='取消登录').click()
        await expect(p.locator('#lobby-login-open')).to_be_visible()
        self.state='ready'
        await p.click('#lobby-login-open')
        await expect(p.locator('#lobby-login-close')).to_have_text('断开原站登录')
        await p.reload()
        await expect(p.locator('#lobby-login-open')).to_be_visible()
        await expect(p.locator('#lobby-login-close')).to_be_hidden()

    async def test_requires_capture_service_capability(self):
        for self.service, self.capability in [('control-console', True), ('response-capture',False)]:
            async with self.page.expect_response('**/api/status'):
                await self.page.goto(self.url)
            await expect(self.page.locator('#lobby-login-open')).to_be_hidden()
            await expect(self.page.locator('#preset-account')).to_be_enabled()
        self.assertEqual([], self.writes)

    async def test_server_ends_window_while_waiting_for_login(self):
        await self.page.goto(self.url)
        await self.page.click('#lobby-login-open')
        await expect(self.page.locator('#lobby-login-close')).to_have_text('取消登录')
        self.state = 'error'
        await expect(self.page.locator('#lobby-login-status')).to_contain_text('登录失败')
        await expect(self.page.locator('#lobby-login-open')).to_be_visible()
        await expect(self.page.locator('#preset-account')).to_be_enabled()


if __name__ == '__main__':
    unittest.main()
