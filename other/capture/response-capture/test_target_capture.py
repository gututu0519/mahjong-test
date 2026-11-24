"""用本机采集界面和完全拦截的大厅页面验收行内抓取。"""
import asyncio
import io
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading
import unittest
from http.cookies import SimpleCookie
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
import zipfile

from playwright.async_api import async_playwright

import app
from test_capture import integrated_tool


GAME_ID = '00112233-4455-4677-8899-aabbccddeeff'
GAME_NAME = '7 Monkeys'
EXTERNAL_ID = '90020277'
SECOND_ID = '22334455-6677-4899-aabb-ccddeeff0011'
SECOND_NAME = '7 Piggies'
SAMPLE_SITE = 'https://sdstest.ink'
ASSET_SITE = 'https://game-fixture.invalid'

HOME = """<!doctype html><title>Lobby</title>
<script>fetch('/api/v1/auth/refresh', {method:'POST'});</script>"""

LOGIN = """<!doctype html><title>Login</title>
<button onclick="document.getElementById('dialog').hidden=false">Open Login / Register</button>
<div id="dialog" role="dialog" class="registration-dialog" hidden>
 <button class="login-tab" onclick="document.getElementById('form').hidden=false">Log In</button>
 <form id="form" class="auth-form login-form" hidden>
 <input placeholder="Username" autocomplete="username" name="username">
 <input placeholder="Password" autocomplete="current-password" name="password" type="password">
 <button type="submit" class="submit-button login-submit-button">Log In</button></form>
</div>
<script>
form.onsubmit=async function(evt){
 evt.preventDefault();
 const response=await fetch('/api/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},
 body:JSON.stringify({username:form.username.value,password:form.password.value})});
 if(response.ok){dialog.hidden=true;form.remove();}else{document.body.append('Login failed');}
};</script>"""

GAMES = """<!doctype html><title>Games</title>
<input type="search" aria-label="Search games" placeholder="Games/Providers/Theme">
<article class="game-card" aria-label="Show actions for 7 Monkeys Classic"><button>Play</button></article>
<article class="game-card" aria-label="Show actions for 7 Monkeys" aria-expanded="false">
 <img alt="7 Monkeys"><button type="button" class="play-button" hidden>Play</button></article>
<script>
const card=document.querySelectorAll('article')[1], play=card.querySelector('button');
card.onclick=()=>{card.setAttribute('aria-expanded','true');play.hidden=false;};
play.onclick=async()=>{const res=await fetch('/api/v1/games/GAME_ID/launch',{method:'POST'});
if(res.ok)location.href='/game';};
</script>""".replace('GAME_ID', GAME_ID)


async def eventually(predicate, seconds=20):
    for _ in range(seconds * 10):
        if predicate():
            return
        await asyncio.sleep(.1)
    raise AssertionError('等待本地测试事件超时')


class TargetCaptureTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.data = Path(temp.name)
        self.profile_pool = app.LobbyProfiles()
        self.addCleanup(self.profile_pool.close)
        for attr, value in [('DATA', self.data), ('SESSIONS', {}), ('LOBBY_PROFILES', self.profile_pool)]:
            scoped = patch.object(app, attr, value)
            scoped.start()
            self.addCleanup(scoped.stop)
        originals = patch.object(app.ORIGINAL_GAMES, 'catalog', return_value={'games':[], 'errors':[]})
        originals.start()
        self.addCleanup(originals.stop)
        sid = 'a' * 32
        sample = self.data / sid / 'bodies'
        sample.mkdir(parents=True)
        cat = json.dumps({'items': [
            dict(id=GAME_ID, externalId=EXTERNAL_ID, name=GAME_NAME, nameZh='7只猴子',
                 metadata={'brand':'pp'}, provider={'code':'fp'}),
            dict(id=SECOND_ID, externalId='90020267', name=SECOND_NAME, nameZh='7只小猪',
                 metadata={'brand':'pp'}, provider={'code':'fp'})]}).encode()
        (sample/'1.json').write_bytes(cat)
        row = dict(id=1, state='complete', method='GET', status=200, mime='application/json',
                   type='fetch', body='bodies/1.json', url=SAMPLE_SITE+'/api/v1/games/catalog', size=len(cat))
        manifest = dict(id=sid, state='completed', created='2026-11-24T00:00:00Z',
                        url=SAMPLE_SITE+'/', ws_count=0, error='', rows=[row])
        (sample.parent/'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')

        self.ui = integrated_tool()
        self.origin = f'http://127.0.0.1:{self.ui.server_port}'
        self.server_thread = threading.Thread(target=self.ui.serve_forever, daemon=True)
        self.server_thread.start()
        self.pw = await async_playwright().start()
        self.addAsyncCleanup(self.pw.stop)
        original_launch = app.launch_browser
        self.browser = await original_launch(self.pw, headless=True)
        self.addAsyncCleanup(self.browser.close)
        self.page = await self.browser.new_page()
        self.page_errors = []
        self.page.on('pageerror', lambda error: self.page_errors.append(str(error))
                     if self.page.url.startswith(self.origin + '/') else None)
        self.account = 'fixture-user-' + secrets.token_hex(5)
        self.password = 'Fixture-' + secrets.token_hex(16)
        self.login_ok = True
        self.card_site = GAME_ID
        self.visits = []
        self.submissions = []
        self.valid_sessions = set()
        self.profile_paths = []
        self.refresh_results = []
        self.window_states = []

        async def isolated_recorder(pw, headless=False):
            browser = await original_launch(pw, headless=True)
            original_context = browser.new_context

            async def local_context(**kwargs):
                kwargs.setdefault('service_workers', 'block')
                context = await original_context(**kwargs)
                await context.route('**/*', self.route)
                return context
            browser.new_context = local_context
            return browser

        hook = patch.object(app, 'launch_browser', isolated_recorder)
        hook.start()
        self.addCleanup(hook.stop)
        launch_context = app.launch_game_context

        async def isolated_game_context(pw, profile_path, headless=False):
            self.profile_paths.append(Path(profile_path))
            context = await launch_context(pw, profile_path, headless=True)
            await context.route('**/*', self.route)
            return context

        profile_hook = patch.object(app, 'launch_game_context', isolated_game_context)
        profile_hook.start()
        self.addCleanup(profile_hook.stop)
        change_window = app.game_window_state

        async def observe_window(context, page, state):
            await change_window(context, page, state)
            self.window_states.append((state, page.url))

        window_hook = patch.object(app, 'game_window_state', observe_window)
        window_hook.start()
        self.addCleanup(window_hook.stop)

    async def asyncTearDown(self):
        try:
            for capture in tuple(app.SESSIONS.values()):
                capture.stop.set()
            await eventually(lambda: all((c.folder/'manifest.json').is_file() for c in app.SESSIONS.values()))
        finally:
            await asyncio.to_thread(self.ui.shutdown)
            self.ui.server_close()
            self.server_thread.join(timeout=2)
        self.assertEqual([], self.page_errors)

    async def route(self, route):
        url = urlsplit(route.request.url)
        self.visits.append((url.hostname, route.request.method, url.path))
        if url.hostname == 'game-fixture.invalid':
            return await route.fulfill(content_type='text/html', body='<title>7 Monkeys game</title>')
        if url.scheme != 'https' or url.hostname != 'sdstest.ink':
            return await route.abort()
        if url.path == '/':
            return await route.fulfill(content_type='text/html', body=HOME)
        if url.path == '/login':
            return await route.fulfill(content_type='text/html', body=LOGIN)
        if url.path == '/api/v1/auth/login':
            body = route.request.post_data_json
            matched = body == {'username':self.account, 'password':self.password}
            self.submissions.append(matched)
            if not matched or not self.login_ok:
                return await route.fulfill(status=401, json={'ok':False})
            fixture_session = secrets.token_hex(16)
            self.valid_sessions.add(fixture_session)
            return await route.fulfill(json={'ok':True}, headers={'Set-Cookie':
                f'fixture_session={fixture_session}; Max-Age=3600; Path=/; Secure; HttpOnly; SameSite=Lax'})
        if url.path == '/api/v1/auth/refresh' or url.path.endswith('/launch'):
            cookies = SimpleCookie((await route.request.all_headers()).get('cookie', ''))
            fixture = cookies.get('fixture_session')
            signed_in = fixture is not None and fixture.value in self.valid_sessions
            if url.path == '/api/v1/auth/refresh':
                self.refresh_results.append(signed_in)
                return await route.fulfill(status=200 if signed_in else 401, json={'ok':signed_in})
            if not signed_in:
                return await route.fulfill(status=401, json={'ok':False})
        if url.path == '/games':
            second = parse_qs(url.query).get('search') in ([SECOND_NAME], ['7只小猪'])
            cards = GAMES.replace(GAME_NAME, SECOND_NAME).replace(GAME_ID, SECOND_ID) if second else GAMES.replace(GAME_ID, self.card_site)
            return await route.fulfill(content_type='text/html', body=cards)
        if url.path in ('/api/v1/games/' + site + '/launch' for site in (GAME_ID, SECOND_ID)):
            return await route.fulfill(status=201, json={'ok':True})
        if url.path == '/game':
            return await route.fulfill(content_type='text/html',
                                       body=f'<iframe title="SDS Game" src="{ASSET_SITE}/play"></iframe>')
        return await route.fulfill(status=404, body='')

    async def post(self, path, data, csrf=True):
        headers = {'X-Capture-Token':self.ui.token} if csrf else {}
        return await self.page.request.post(self.origin + path, headers=headers, data=data)

    async def stop_and_check_archive(self, capture, via_ui=False):
        if via_ui:
            row = self.game_row(capture.target.get('zh') or capture.target['name'])
            async with self.page.expect_response(lambda r: r.url == self.origin + '/api/stop') as reply:
                await row.locator('.game-stop').click()
            self.assertEqual(capture.id, (await reply.value).request.post_data_json['id'])
        else:
            await self.post('/api/stop', {'id':capture.id})
        await eventually(lambda: (capture.folder/'manifest.json').is_file())
        archive = await self.page.request.get(f'{self.origin}/api/sessions/{capture.id}/download')
        self.assertEqual(200, archive.status)
        with zipfile.ZipFile(io.BytesIO(await archive.body())) as saved:
            for name in saved.namelist():
                data = saved.read(name)
                self.assertFalse(self.account.encode() in data or self.password.encode() in data,
                                 f'预设登录输入出现在抓取归档 {name}')
            manifest = json.loads(saved.read('manifest.json'))
            rows = manifest['rows']
            self.assertTrue(all('/api/v1/auth/' not in r['url'] for r in rows))
            if capture.state == 'completed' and rows:
                self.assertIn('network.har', saved.namelist())
            if 'network.har' in saved.namelist():
                entries = json.loads(saved.read('network.har'))['log']['entries']
                self.assertTrue(all('/api/v1/auth/' not in e['request']['url'] for e in entries))
                if capture.state == 'completed' and rows:
                    self.assertTrue(any(e['request']['url'].startswith(ASSET_SITE) for e in entries))
            return rows

    def game_row(self, title):
        return self.page.locator('#library-rows > tr[data-game-key]').filter(has_text=title)

    async def expand_records(self, row):
        if not await row.locator('.game-history').is_visible():
            await row.locator('.game-records-toggle').click()
        await row.locator('.game-history').wait_for(state='visible')

    async def capture_from_list(self, game_id, title):
        await self.page.fill('#preset-account', self.account)
        await self.page.fill('#preset-password', self.password)
        row = self.game_row(title)
        async with self.page.expect_response(lambda r: r.url == self.origin + '/api/start-game') as pending:
            await row.locator('.library-grab').click()
        response = await pending.value
        self.assertEqual(201, response.status)
        capture = app.SESSIONS[(await response.json())['id']]
        await eventually(lambda: capture.state == 'error' or (capture.state == 'recording' and any(
            r['url'] == ASSET_SITE + '/play' and r['state'] == 'complete' for r in capture.snapshot()['rows'])))
        self.assertNotEqual('error', capture.state, capture.error)
        self.assertEqual(game_id, capture.target['site'])
        await self.stop_and_check_archive(capture)

    async def test_next_game_reuses_login_and_expired_session_signs_in_once(self):
        await self.page.goto(self.origin)
        await self.capture_from_list(GAME_ID, '7只猴子')
        first_logins = self.visits.count(('sdstest.ink', 'GET', '/login'))
        self.assertEqual(1, first_logins)
        self.assertEqual([True], self.submissions)
        self.assertEqual([('minimized', 'about:blank'), ('normal', SAMPLE_SITE + '/game')], self.window_states)
        await self.capture_from_list(SECOND_ID, '7只小猪')
        self.assertEqual(1, self.visits.count(('sdstest.ink', 'GET', '/login')))
        self.assertEqual([True], self.submissions)
        self.assertIn(True, self.refresh_results)
        self.assertEqual(self.profile_paths[0], self.profile_paths[1])
        self.assertEqual(self.window_states[:2], self.window_states[2:])

        # 站点撤销刚才的模拟会话，复用同一浏览器资料也必须重新认证。
        self.valid_sessions.clear()
        await self.capture_from_list(GAME_ID, '7只猴子')
        self.assertFalse(self.refresh_results[-1])
        self.assertEqual([True, True], self.submissions)
        self.assertEqual(2, self.visits.count(('sdstest.ink', 'GET', '/login')))

    async def test_changed_credentials_cannot_use_previous_profile(self):
        await self.page.goto(self.origin)
        await self.capture_from_list(GAME_ID, '7只猴子')
        self.password = 'Changed-' + secrets.token_hex(12)
        await self.capture_from_list(SECOND_ID, '7只小猪')
        self.account = 'another-user-' + secrets.token_hex(6)
        await self.capture_from_list(GAME_ID, '7只猴子')
        self.assertEqual([True, True, True], self.submissions)
        self.assertEqual(3, len(set(self.profile_paths)))

    async def test_one_manual_login_two_games_and_independent_archives(self):
        login_window_closed = threading.Event()

        async def test_browser(pw, headless):
            browser = await app.launch_browser(pw, headless=True)
            make_context = browser.new_context

            async def with_player(**kwargs):
                context = await make_context(**kwargs)

                async def player_login(page):
                    form = page.locator('form.login-form')
                    await form.locator('[autocomplete=username]').fill(self.account)
                    await form.locator('[autocomplete=current-password]').fill(self.password)
                    await form.get_by_role('button', name='Log In').click()
                    await page.get_by_role('heading', name='大厅已连接').wait_for()
                    await page.close()
                    login_window_closed.set()

                context.once('page', player_login)
                return context

            browser.new_context = with_player
            return browser

        manager = app.ManualLobbies(launch_browser=test_browser, headless=True)
        try:
            with patch.object(app, 'MANUAL_LOBBIES', manager):
                await self.page.goto(self.origin)
                async with self.page.expect_response(lambda r: r.url == self.origin + '/api/lobby-login') as opened:
                    await self.page.get_by_role('button', name='点击登录获取session', exact=True).click()
                ref = (await (await opened.value).json())['id']
                await eventually(login_window_closed.is_set)
                await eventually(lambda: manager.status(ref)['state'] == 'ready')
                await self.page.locator('#lobby-login-status').get_by_text('大厅已登录', exact=False).wait_for(timeout=10000)
                self.assertEqual('', await self.page.locator('#preset-account').input_value())
                self.assertEqual('', await self.page.locator('#preset-password').input_value())
                captures = []
                for site, title in ((GAME_ID, '7只猴子'), (SECOND_ID, '7只小猪')):
                    async with self.page.expect_response(lambda r: r.url == self.origin + '/api/start-game') as started:
                        await self.game_row(title).get_by_role('button', name='抓取', exact=True).click()
                    response = await started.value
                    self.assertEqual(response.request.post_data_json, {'game_id': site, 'lobby_session': ref})
                    self.assertEqual(201, response.status)
                    captures.append(app.SESSIONS[(await response.json())['id']])
                await eventually(lambda: all(c.state == 'recording' and any(
                    r.get('url') == ASSET_SITE+'/play' and r.get('state') == 'complete'
                    for r in c.snapshot()['rows']) for c in captures))
                self.assertEqual([True], self.submissions)
                self.assertEqual(409, (await self.post('/api/lobby-login/' + ref + '/close', {})).status)
                for i, capture in enumerate(captures):
                    rows = await self.stop_and_check_archive(capture, via_ui=True)
                    launches = [r for r in rows if r['url'].endswith('/launch')]
                    self.assertEqual([SAMPLE_SITE + '/api/v1/games/' + capture.target['site'] + '/launch'],
                                     [r['url'] for r in launches])
                    self.assertFalse(any(h['name'].lower() in ('cookie','authorization','set-cookie')
                                         for r in rows for h in r['request_headers'] + r['response_headers']))
                    self.assertNotIn(ref.encode(), (capture.folder / 'network.har').read_bytes())
                    if i == 0:
                        self.assertEqual('recording', captures[1].state)
                self.assertEqual(200, (await self.post('/api/lobby-login/' + ref + '/close', {})).status)
        finally:
            for capture in app.SESSIONS.values():
                capture.stop.set()
            await eventually(lambda: all(c.archived for c in app.SESSIONS.values()))
            await asyncio.to_thread(manager.shutdown)

    async def test_row_start_selects_internal_id_and_skips_login_in_archive(self):
        await self.page.goto(self.origin)
        self.assertEqual(0, await self.page.locator('#form, #url, #start, #history, #stop, #download, .intro').count())
        self.assertEqual('all', await self.page.locator('#library-filter').input_value())
        self.assertFalse(await self.page.locator('#capture-detail').is_visible())
        self.assertTrue(await self.page.locator('#login-settings').evaluate('el => el.open'))
        await self.page.locator('#login-settings > summary').click()
        row = self.game_row('7只猴子')
        start = row.locator('.library-grab')
        await start.wait_for(timeout=15000)
        await start.click()
        self.assertEqual({}, app.SESSIONS)
        self.assertTrue(await self.page.locator('#login-settings').evaluate('el => el.open'))
        self.assertTrue(await self.page.locator('#preset-account').evaluate('el => el === document.activeElement'))
        await self.page.fill('#preset-account', self.account)
        await self.page.fill('#preset-password', self.password)
        async with self.page.expect_response(lambda r:r.url == self.origin+'/api/start-game') as response:
            await start.click()
        result = await response.value
        self.assertEqual(201, result.status)
        self.assertEqual(GAME_ID, result.request.post_data_json['game_id'])
        capture = app.SESSIONS[(await result.json())['id']]
        duplicate = await self.post('/api/start-game', {'game_id':GAME_ID, 'account':self.account,'password':self.password})
        self.assertEqual(409, duplicate.status)
        self.assertTrue(await start.is_disabled())
        await eventually(lambda: capture.state == 'error' or any(
            r.get('state') == 'complete' and r['url'] == ASSET_SITE+'/play' for r in capture.snapshot()['rows']))
        self.assertNotEqual('error', capture.state, capture.error)
        self.assertEqual([True], self.submissions)
        self.assertEqual(1, self.visits.count(('sdstest.ink', 'POST', '/api/v1/games/'+GAME_ID+'/launch')))
        rows = await self.stop_and_check_archive(capture)
        self.assertTrue(any(r['url'] == ASSET_SITE+'/play' for r in rows))
        self.assertEqual('completed', capture.state)
        storage = await self.page.evaluate('JSON.stringify([localStorage,sessionStorage])')
        self.assertFalse(self.account in storage or self.password in storage)
        await self.page.reload()
        self.assertEqual('', await self.page.locator('#preset-password').input_value())

    async def test_rejected_credentials_unknown_target_and_ordinary_capture(self):
        data = {'game_id':GAME_ID,'account':self.account,'password':self.password}
        self.assertEqual(403, (await self.post('/api/start-game', data, csrf=False)).status)
        self.assertEqual(400, (await self.post('/api/start-game', {**data,'password':''})).status)
        invalid = await self.post('/api/start-game', {**data, 'game_id':EXTERNAL_ID})
        self.assertGreaterEqual(invalid.status, 400)
        self.assertEqual({}, app.SESSIONS)
        self.login_ok = False
        res = await self.post('/api/start-game', data)
        self.assertEqual(201, res.status)
        capture = app.SESSIONS[(await res.json())['id']]
        await eventually(lambda:(capture.folder/'manifest.json').is_file())
        self.assertEqual('error',capture.state)
        self.assertEqual([True], self.submissions)
        self.assertFalse(any(v[2].endswith('/launch') for v in self.visits))
        self.assertEqual([],await self.stop_and_check_archive(capture))
        ordinary = await self.post('/api/start', {'url':ASSET_SITE+'/ordinary'})
        self.assertEqual(201, ordinary.status)
        rec = app.SESSIONS[(await ordinary.json())['id']]
        await eventually(lambda:any(r.get('state')=='complete' for r in rec.snapshot()['rows']))
        self.assertTrue(any(r['url']==ASSET_SITE+'/ordinary' for r in await self.stop_and_check_archive(rec)))

    async def test_changed_card_id_cannot_launch_other_game(self):
        self.card_site = 'a-different-game'
        await self.page.context.route('**/*', self.route)
        with self.assertRaises(app.LobbyFlowError):
            await app.open_game(self.page, {'site':GAME_ID, 'name':GAME_NAME,'zh':'7只猴子'})
        self.assertFalse(any(v[2].endswith('/launch') for v in self.visits))

    async def test_two_game_windows_save_independently(self):
        await self.page.goto(self.origin)
        self.assertTrue(await self.page.locator('#login-settings').evaluate('el => el.open'))
        await self.page.fill('#preset-account', self.account)
        await self.page.fill('#preset-password', self.password)
        captures = []
        for title in ('7只猴子', '7只小猪'):
            row = self.game_row(title)
            async with self.page.expect_response(lambda r: r.url == self.origin + '/api/start-game') as pending:
                await row.get_by_role('button', name='抓取', exact=True).click()
            response = await pending.value
            self.assertEqual(201, response.status)
            captures.append(app.SESSIONS[(await response.json())['id']])
        await eventually(lambda: all(c.state == 'recording' and any(
            r['url'] == ASSET_SITE+'/play' and r['state'] == 'complete' for r in c.snapshot()['rows']
        ) for c in captures))
        self.assertEqual([True, True], self.submissions)
        self.assertEqual(2, len(set(self.profile_paths)))
        labels = ['PP-90020277-7只猴子', 'PP-90020267-7只小猪']
        self.assertNotEqual(captures[0].id, captures[1].id)
        for c, label in zip(captures, labels):
            self.assertEqual(self.data / label / c.id, c.folder)
            row = self.game_row(c.target['zh'])
            await self.expand_records(row)
            batch = row.locator('.capture-batch[data-session-id="' + c.id + '"]')
            await batch.wait_for(state='visible')
            self.assertEqual(1, await row.locator('.capture-batch').count())
            self.assertTrue(await batch.locator('.batch-stop').is_visible())
        duplicate = await self.post('/api/start-game', {'game_id': GAME_ID, 'account': self.account, 'password': self.password})
        self.assertEqual(409, duplicate.status)
        result = {'环境': '本地 Chromium，测试大厅和游戏响应均由本机提供', '两款游戏同时录制': True,
                  '重复启动同一游戏的响应码': duplicate.status, '批次': []}
        for capture in captures:
            rows = await self.stop_and_check_archive(capture, via_ui=True)
            launches = [r['url'] for r in rows if r['url'].endswith('/launch')]
            self.assertEqual([SAMPLE_SITE+'/api/v1/games/'+capture.target['site']+'/launch'], launches)
            self.assertEqual('completed', capture.state)
            row = self.game_row(capture.target['zh'])
            download = row.locator('.game-download')
            await download.wait_for(state='visible')
            self.assertTrue((await download.get_attribute('href')).endswith('/' + capture.id + '/download'))
            result['批次'].append({'游戏': capture.display_name, '批次目录': capture.folder.relative_to(self.data).as_posix(),
                                 'ZIP内启动请求数': len(launches), 'ZIP内请求总数': len(rows), '最终状态': capture.state})
            if capture is captures[0]:
                result['保存第一个时第二个的状态'] = captures[1].state
                self.assertEqual('recording', captures[1].state)
                self.assertFalse(captures[1].stop.is_set())
        # 记录查看器留在被查看游戏行下方，切换时只显示对应批次的请求。
        for capture in captures:
            row = self.game_row(capture.target['zh'])
            await self.expand_records(row)
            await row.locator('.capture-batch[data-session-id="' + capture.id + '"] .batch-view').click()
            await self.page.wait_for_function('(id) => data && data.id === id', arg=capture.id)
            detail_row = self.page.locator('#capture-detail').locator('xpath=ancestor::tr[1]')
            self.assertIn('library-detail-row', await detail_row.get_attribute('class'))
            self.assertTrue(await detail_row.evaluate('(el, title) => el.previousElementSibling.textContent.includes(title)', capture.target['zh']))
            await self.page.fill('#filter', '/launch')
            self.assertIn(capture.target['site'], await self.page.locator('#rows').inner_text())
        await self.page.set_viewport_size({'width':390, 'height':844})
        self.assertTrue(await self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        if directory := os.environ.get('CAPTURE_ACCEPTANCE_DIR'):
            path = Path(directory)
            path.mkdir(parents=True, exist_ok=True)
            (path/'并行抓取验收.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    unittest.main()
