"""跨批次游戏清单的身份归属、历史恢复和录制中更新回归。"""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlsplit

from playwright.async_api import async_playwright

from app import launch_browser
from library_input import project_session


class GameLibraryTest(unittest.IsolatedAsyncioTestCase):
    async def test_cover_preview_leaves_names_and_rows_in_place(self):
        from io import BytesIO
        from PIL import Image
        from game_covers import encode_cover

        png = BytesIO()
        Image.new('RGB', (24, 32), 'navy').save(png, format='PNG')
        payload = encode_cover(png.getvalue())
        p = self.page
        await p.route('**/game-covers/**', lambda route: route.fulfill(content_type='image/png', body=payload))
        await p.goto('http://127.0.0.1:8090/')
        await p.select_option('#library-filter', 'all')
        await p.fill('#library-search', 'old-cover')
        thumb = p.locator('#library-rows .game-cover-thumb')
        await thumb.scroll_into_view_if_needed()
        await thumb.locator('img').evaluate('img=>img.decode()')
        row = p.locator('#library-rows tr[data-game-key]')
        before = await row.bounding_box()
        await thumb.hover()
        enlarged = p.locator('.game-cover-preview')
        await enlarged.wait_for()
        self.assertGreater((await enlarged.bounding_box())['width'], (await thumb.bounding_box())['width'])
        self.assertEqual(before, await row.bounding_box())
        await p.mouse.move(2, 2)
        await enlarged.wait_for(state='detached')
        await thumb.focus()
        await enlarged.wait_for()
        await p.keyboard.press('Tab')
        await enlarged.wait_for(state='detached')
        self.assertIn('仅见封面', await row.inner_text())

    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.sessions = {}
        self.compact = True
        self.catalog_reads = 0
        self.writes = []
        self.directory_requests = []
        self.library_gate = None
        self.body_delays = {}
        self.original_games = []
        self.original_requests = []
        self.original_failures = {}
        self.preview_replies = {}
        self.preview_states = {}
        self.site, self.live = '1' * 32, '2' * 32
        for sid, state in [(self.site, 'completed'), (self.live, 'recording')]:
            (self.root / sid / 'bodies').mkdir(parents=True)
            self.sessions[sid] = dict(id=sid, state=state, url='https://sdstest.ink', rows=[],
                                      created='2026-11-23T00:00:00Z', ws_count=0, error='')
        items = []
        for site, ext, brand, name, zh in [
            ('cash', '1682240', 'pg', 'Cash Mania', '现金风暴'), ('same', '25', 'pp', 'Cash Mania', '同名游戏'),
            ('bear', '603', 'igt', 'Great Bear', '大熊'), ('cover', '80', 'pg', 'Cover Only', '仅见封面'),
        ]:
            items.append(dict(id=site, externalId=ext, name=name, nameZh=zh, provider={'code': 'fp'},
                              metadata={'brand': brand, 'legacyGameId': 'old-' + site}))
        self.row(self.site, 'https://sdstest.ink/api/v1/games/catalog?page=1', json.dumps({'items': items}))
        self.row(self.live, 'https://sdstest.ink/api/v1/games/catalog?page=1', json.dumps({'items': items[:1]}))
        self.row(self.site, 'https://cdn.777sslot.com/common/game_icon_shu/Cover.png', 'cover', 'image/png')
        self.row(self.live, 'http://g20.localhost:8110/80/index.html', 'local', 'text/html')
        self.row(self.site, 'https://sdstest.ink/api/v1/games/bear/launch', '{}', method='POST', status=201)
        self.row(self.site, 'https://static.funapptoday.com/igt/v0/ABC/local/hosts/r/studios/dev/games/GreatBear/splash.html',
                 'bear', 'text/html')
        self.row(self.site, 'https://api.mmga1.com/game-api/mystery/v4/Spin', 'abc', 'application/octet-stream', 'POST')
        self.row(self.live, 'https://api.mmga1.com/game-api/cash-mania/v4/Spin', 'bad', method='POST', status=500)
        self.row(self.live, 'https://sdstest.ink/api/v1/games/cash/launch', '{}', method='POST', status=201)
        self.pw = await async_playwright().start()
        self.addAsyncCleanup(self.pw.stop)
        self.browser = await launch_browser(self.pw, True)
        self.addAsyncCleanup(self.browser.close)
        self.page = await self.browser.new_page()
        await self.page.route('**/*', self.route)
        await self.page.context.route('http://127.0.0.1:8090/fixture-preview', self.route)

    def row(self, sid, url, content, mime='application/json', method='GET', status=200):
        rows = self.sessions[sid]['rows']
        rid = len(rows) + 1
        body = f'bodies/{rid:06d}.bin'
        raw = content.encode()
        (self.root / sid / body).write_bytes(raw)
        rows.append(dict(id=rid, url=url, body=body, state='complete', method=method, status=status, size=len(raw),
                         mime=mime, started=f'2026-11-23T01:00:{rid:02}Z', type='fetch', request_headers=[], response_headers=[]))
        return body

    async def route(self, route):
        url = urlsplit(route.request.url)
        # 游戏清单用例隔离独立的服务控制台，仍拦截任何意外的写请求。
        if (route.request.method == 'GET' and url.netloc == '127.0.0.1:18096'
                and url.path in ('/service-console.js', '/service-console.css')):
            return await route.fulfill(status=204, body='')
        body_finished = None
        if url.netloc == '127.0.0.1:8090' and url.path == '/fixture-preview' and route.request.method == 'GET':
            return await route.fulfill(content_type='text/html; charset=utf-8', body='<title>预览夹具</title>')
        if url.netloc == '127.0.0.1:8090' and url.path == '/api/original-games' and route.request.method == 'GET':
            return await route.fulfill(json={'games':self.original_games, 'errors':[]})
        if (url.netloc == '127.0.0.1:8090' and url.path.startswith('/api/original-games/previews/')
                and route.request.method == 'GET'):
            run_id = url.path.rsplit('/', 1)[-1]
            state = self.preview_states[run_id]
            return await route.fulfill(json=state)
        if (url.netloc == '127.0.0.1:8090' and url.path in
                ('/api/original-games/open-directory', '/api/original-games/preview') and route.request.method == 'POST'):
            payload = route.request.post_data_json
            self.original_requests.append({'path':url.path, 'body':payload})
            failure = self.original_failures.get(payload['id'])
            if failure:
                return await route.fulfill(status=503, json={'error':failure})
            if url.path.endswith('/preview'):
                fallback = {'ok':True, 'state':'ready', 'message':'原版试玩已打开'}
                product = next(item for item in self.original_games if item['id'] == payload['id'])
                if product['preview_mode'] in ('static', 'adapter'):
                    fallback.update(mode=product['preview_mode'], url='http://127.0.0.1:8090/fixture-preview', port=8090)
                response = self.preview_replies.get(payload['id'], fallback)
            else:
                response = {'ok':True, 'directory':str(self.root / payload['id'])}
            return await route.fulfill(json=response)
        if route.request.method == 'POST' and url.netloc == '127.0.0.1:8090' and url.path == '/api/open-directory':
            self.directory_requests.append(route.request.post_data_json)
            return await route.fulfill(content_type='application/json', body=json.dumps({'ok':True, 'directory':str(self.root)}))
        if route.request.method != 'GET' or url.netloc != '127.0.0.1:8090':
            self.writes.append(route.request.method + ' ' + url.netloc)
            return await route.abort()
        if url.path == '/':
            html = Path(__file__).with_name('index.html').read_bytes().replace(b'__LOCAL_GAME_COVERS__', b'1')
            return await route.fulfill(content_type='text/html', body=html)
        if url.path.startswith('/game-covers/'):
            return await route.fulfill(status=404, body=b'')
        parts = url.path.strip('/').split('/')
        if parts == ['api', 'sessions']:
            value = [{k: v for k, v in s.items() if k != 'rows'} for s in self.sessions.values()]
        else:
            sid = parts[2]
            session = self.sessions[sid]
            if len(parts) == 3:
                value = session
            elif parts[3] == 'quality':
                value = dict(version=1, session_id=sid, generated_at=session['created'], summary={}, games=[])
            elif parts[3] == 'library-input' and self.compact:
                if self.library_gate and sid == self.site:
                    await self.library_gate.wait()
                self.catalog_reads += 1
                value = project_session(session, self.root / sid)
            elif parts[3] == 'body':
                delayed = self.body_delays.get((sid, int(parts[4])))
                if delayed:
                    started, release, body_finished = delayed
                    started.set()
                    await release.wait()
                row = session['rows'][int(parts[4]) - 1]
                path = self.root / sid / row['body']
                if not path.exists():
                    return await route.fulfill(status=404, body='{}')
                self.catalog_reads += int('/catalog' in row['url'])
                value = dict(text=path.read_text(encoding='utf8'), encoding='text', truncated=False)
            else:
                return await route.fulfill(status=404, body='{}')
        await route.fulfill(content_type='application/json', body=json.dumps(value))
        if body_finished:
            body_finished.set()

    async def exercise(self):
        p = self.page
        await p.goto('http://127.0.0.1:8090/')
        summary = p.locator('#library-summary')
        await p.wait_for_function("document.getElementById('library-summary').textContent.includes('已核对 2 个批次')")
        self.assertIn('未抓 3 · 待补抓 1 · 待识别 1', await summary.inner_text())
        await p.select_option('#library-filter', 'unseen')
        await p.fill('#library-search', 'old-cover')
        self.assertIn('仅见封面', await p.locator('#library-rows').inner_text())
        await p.fill('#library-search', '大熊')
        await p.click('#library-find-all')
        self.assertIn('待补抓', await p.locator('#library-rows').inner_text())
        await p.select_option('#library-filter', 'unknown')
        await p.fill('#library-search', '')
        self.assertIn('mystery', await p.locator('#library-rows').inner_text())
        self.row(self.live, 'https://api.mmga1.com/game-api/cash-mania/v4/Spin?secret=private',
                 'round', 'application/octet-stream', 'POST')
        await p.wait_for_function("document.getElementById('library-summary').textContent.includes('未抓 2 · 待补抓 2')", timeout=20000)
        await p.select_option('#library-filter', 'partial')
        await p.fill('#library-search', '1682240')
        await p.locator('#library-rows details > summary').first.click()
        self.assertIn('旋转接口响应', await p.locator('#library-rows').inner_text())
        self.assertNotIn('private', await p.locator('#library-rows').inner_text())
        row = p.locator('#library-rows > tr[data-game-key]').filter(has_text='现金风暴')
        await row.locator('.game-records-toggle').click()
        await row.locator('.capture-batch[data-session-id="' + self.live + '"] .batch-view').click()
        await p.click('#clear-records')
        self.assertIn('现金风暴', await p.locator('#library-rows').inner_text())
        self.sessions[self.live]['state'] = 'completed'
        await p.click('#library-recheck')
        await p.wait_for_function("document.getElementById('library-summary').textContent.startsWith('已核对')")
        reads = self.catalog_reads
        await p.reload()
        await p.wait_for_function("document.getElementById('library-summary').textContent.includes('未抓 2 · 待补抓 2')")
        self.assertEqual(reads, self.catalog_reads)
        self.assertEqual([], self.writes)
        # 新窗口没有任何浏览器缓存，仍能从已保存批次重建。
        await p.evaluate('localStorage.clear()')
        await p.reload()
        await p.wait_for_function("document.getElementById('library-summary').textContent.includes('未抓 2 · 待补抓 2')")
        self.assertGreater(self.catalog_reads, reads)

    async def test_compact_input(self):
        await self.exercise()

    async def test_existing_recording_process(self):
        self.compact = False
        await self.exercise()

    async def test_pg_api_needs_independent_identity(self):
        self.row(self.site, 'https://api.mmga1.com/game-api/cover-only/v4/Spin', 'spin', 'application/octet-stream', 'POST')
        await self.page.goto('http://127.0.0.1:8090/')
        await self.page.wait_for_function("document.getElementById('library-summary').textContent.startsWith('已核对')")
        await self.page.select_option('#library-filter','unknown')
        await self.page.fill('#library-search','cover-only')
        self.assertEqual(1,await self.page.locator('#library-rows > tr[data-game-key]').count())
        self.row(self.site, 'https://s5.mmga1.com/80/history/index.json', '{}')
        await self.page.click('#library-recheck')
        await self.page.wait_for_function("document.getElementById('library-summary').textContent.startsWith('已核对')")
        await self.page.select_option('#library-filter','partial')
        await self.page.fill('#library-search','old-cover')
        content = await self.page.locator('#library-rows').inner_text()
        self.assertIn('旋转接口响应',content)
        self.assertIn('游戏专属资源',content)

    async def test_unreadable_archive_and_ambiguous_identity(self):
        sid = self.site
        path = self.root / sid / self.sessions[sid]['rows'][0]['body']
        catalog = json.loads(path.read_bytes())
        game = dict(catalog['items'][0], id='other', provider={'code': 'other'})
        self.row(sid, 'https://sdstest.ink/api/v1/games/catalog?page=2', json.dumps({'items':[game]}))
        self.row(sid, 'https://s5.mmga1.com/1682240/index.html', 'body', 'text/html')
        missing = self.row(sid, 'https://s5.mmga1.com/80/index.html', 'lost', 'text/html')
        (self.root / sid / missing).unlink()
        await self.page.goto('http://127.0.0.1:8090/')
        await self.page.wait_for_function("document.getElementById('library-summary').textContent.includes('部分结果')")
        await self.page.select_option('#library-filter','unknown')
        await self.page.fill('#library-search','1682240')
        self.assertEqual(3, await self.page.locator('#library-rows > tr[data-game-key]').count())
        await self.page.select_option('#library-filter','partial')
        self.assertEqual(0, await self.page.locator('#library-rows > tr[data-game-key]').count())

    async def test_all_batches_and_shared_history_remain_in_game_rows(self):
        p = self.page
        third = '3' * 32
        cash = dict(site='cash', brand='PG', externalId='1682240', name='Cash Mania', zh='现金风暴')
        bear = dict(site='bear', brand='IGT', externalId='603', name='Great Bear', zh='大熊')
        self.sessions[third] = dict(id=third, state='completed', url='https://sdstest.ink', rows=[],
            created='2026-11-24T00:00:00Z', ws_count=0, error='', target_game=cash, identity_games=[cash])
        (self.root / third / 'bodies').mkdir(parents=True)
        self.row(self.site, 'https://s5.mmga1.com/1682240/index.html', '<title>cash</title>', 'text/html')
        self.row(self.live, 'https://s5.mmga1.com/1682240/index.html', '<title>cash</title>', 'text/html')
        self.row(third, 'https://s5.mmga1.com/1682240/index.html', '<title>cash</title>', 'text/html')
        for sid, games in [(self.site, [cash, bear]), (self.live, [cash]), (third, [cash])]:
            self.sessions[sid]['identity_games'] = games
            self.sessions[sid]['directory'] = str(self.root / sid)
            self.sessions[sid]['game_directories'] = [dict(game_id=g['site'], name=g['zh'],
                                                         path=str(self.root / g['zh'])) for g in games]
        await p.goto('http://127.0.0.1:8090/')
        await p.wait_for_function("document.getElementById('library-summary').textContent.includes('已核对 3 个批次')")
        await p.select_option('#library-filter', 'has-records')
        await p.fill('#library-search', 'old-cash')
        row = p.locator('#library-rows > tr[data-game-key]').filter(has_text='现金风暴')
        await row.locator('.game-records-toggle').click()
        self.assertEqual(3, await row.locator('.capture-batch').count())
        self.assertEqual({self.site, self.live, third}, set(await row.locator('.capture-batch').evaluate_all(
            'nodes => nodes.map(node => node.dataset.sessionId)')))
        await row.locator('.capture-batch[data-session-id="' + third + '"] .batch-folder').click()
        self.assertEqual([{'session_id':third}], self.directory_requests)
        await row.locator('.game-folder').click()
        self.assertEqual([{'session_id':third}, {'game_id':'cash'}], self.directory_requests)
        self.assertEqual([], self.writes)
        # 轮询及同款游戏新数据不收起已经打开的记录。
        self.row(self.live, 'https://api.mmga1.com/game-api/cash-mania/v4/Spin', 'round', 'application/octet-stream', 'POST')
        await p.wait_for_function("document.querySelector('#library-rows').textContent.includes('旋转接口响应')", timeout=20000)
        self.assertTrue(await row.locator('.game-history').is_visible())
        self.assertEqual(3, await row.locator('.capture-batch').count())
        await p.fill('#library-search', '大熊')
        bear_row = p.locator('#library-rows > tr[data-game-key]').filter(has_text='大熊')
        await bear_row.locator('.game-records-toggle').click()
        self.assertEqual([self.site], await bear_row.locator('.capture-batch').evaluate_all(
            'nodes => nodes.map(node => node.dataset.sessionId)'))

    async def test_cold_deep_link_survives_late_catalog_identity(self):
        p = self.page
        self.sessions[self.live]['target_game'] = dict(site='cash', brand='PG', externalId='1682240',
                                                      name='Cash Mania', zh='现金风暴')
        self.library_gate = asyncio.Event()
        try:
            await p.goto('http://127.0.0.1:8090/#capture-session=' + self.live)
            await p.locator('#capture-detail').wait_for(state='visible')
            await p.wait_for_function('(id) => data && data.id === id', arg=self.live)
            row = p.locator('#library-rows > tr[data-game-key]').filter(has_text='现金风暴')
            initial_key = await row.get_attribute('data-game-key')
            self.assertEqual('identity/cash', initial_key)
            await row.locator('.game-records-toggle').click()
            self.assertTrue(await row.locator('.game-history').is_visible())
            self.library_gate.set()
            await p.wait_for_function("document.getElementById('library-summary').textContent.includes('已核对 2 个批次')")
            self.assertNotEqual(initial_key, await row.get_attribute('data-game-key'))
            self.assertTrue(await p.locator('#capture-detail').is_visible())
            self.assertTrue(await row.locator('.game-history').is_visible())
            self.assertEqual(self.live, await p.evaluate('data.id'))
            self.assertTrue(await p.locator('#capture-detail').evaluate(
                "node => node.closest('tr').previousElementSibling.textContent.includes('现金风暴')"))
        finally:
            self.library_gate.set()

    async def test_late_response_cannot_replace_other_game_preview(self):
        p = self.page
        self.row(self.live, 'https://fixture.invalid/late-response', '旧游戏响应不可出现在新游戏', 'text/plain')
        rid = self.sessions[self.live]['rows'][-1]['id']
        started, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()
        self.body_delays[(self.live, rid)] = (started, release, finished)
        try:
            await p.goto('http://127.0.0.1:8090/')
            await p.wait_for_function("document.getElementById('library-summary').textContent.includes('已核对 2 个批次')")
            await p.fill('#library-search', 'old-cash')
            row = p.locator('#library-rows > tr[data-game-key]').filter(has_text='现金风暴')
            await row.locator('.game-records-toggle').click()
            await row.locator('.capture-batch[data-session-id="' + self.live + '"] .batch-view').click()
            await p.fill('#filter', '/late-response')
            await p.locator('#rows tr').first.click()
            await asyncio.wait_for(started.wait(), timeout=5)
            await p.fill('#library-search', '大熊')
            other = p.locator('#library-rows > tr[data-game-key]').filter(has_text='大熊')
            await other.locator('.game-records-toggle').click()
            await other.locator('.capture-batch[data-session-id="' + self.site + '"] .batch-view').click()
            await p.wait_for_function('(id) => data && data.id === id', arg=self.site)
            release.set()
            await asyncio.wait_for(finished.wait(), timeout=5)
            await p.wait_for_timeout(100)
            self.assertEqual('尚未选择请求', await p.locator('#preview').inner_text())
            self.assertEqual(self.site, await p.evaluate('data.id'))
            self.assertTrue(await p.locator('#capture-detail').evaluate(
                "node => node.closest('tr').previousElementSibling.textContent.includes('大熊')"))
        finally:
            release.set()

    async def test_original_products_open_only_the_matching_game(self):
        p = self.page
        self.original_games = [
            dict(id='cash-latest', game_ids=['cash'], brand='PG', external_id='1682240', title='现金风暴',
                 directory=str(self.root / 'cash-latest'), status='captured_candidate', can_preview=True,
                 preview_mode='offline', reason='原版已生成，玩法待验收'),
            dict(id='cash-previous', game_ids=['cash'], brand='PG', external_id='1682240', title='现金风暴',
                 directory=str(self.root / 'cash-previous'), status='captured_candidate', can_preview=True,
                 preview_mode='offline', reason='原版已生成，玩法待验收'),
            dict(id='bear-original', game_ids=['bear'], brand='IGT', external_id='603', title='大熊',
                 directory=str(self.root / 'bear-original'), status='adapter_ready', can_preview=True,
                 preview_mode='adapter', reason='已匹配同版客户端，特殊玩法仍待验收'),
        ]
        await p.goto('http://127.0.0.1:8090/')
        await p.wait_for_function("document.getElementById('library-summary').textContent.includes('已核对 2 个批次')")
        cash = p.locator('#library-rows > tr[data-game-key]').filter(has_text='现金风暴')
        bear = p.locator('#library-rows > tr[data-game-key]').filter(has_text='大熊')
        same_name = p.locator('#library-rows > tr[data-game-key]').filter(has_text='同名游戏')
        uncaptured = p.locator('#library-rows > tr[data-game-key]').filter(has_text='仅见封面')
        await cash.locator('.original-preview:visible').wait_for()
        await bear.locator('.original-preview:visible').wait_for()
        self.assertEqual(0, await same_name.locator('.original-preview, .original-folder').count())
        self.assertEqual(0, await uncaptured.locator('.original-preview, .original-folder').count())
        self.assertEqual('cash-latest', await cash.locator('.original-preview:visible').get_attribute('data-original-id'))
        self.assertEqual('bear-original', await bear.locator('.original-preview:visible').get_attribute('data-original-id'))
        self.assertIn('待验收', await cash.locator('.original-products').inner_text())
        self.assertNotIn('已完成复刻', await cash.locator('.original-products').inner_text())
        await cash.locator('.original-folder:visible').click()
        await bear.locator('.original-folder:visible').click()
        self.assertEqual([
            {'path':'/api/original-games/open-directory', 'body':{'id':'cash-latest'}},
            {'path':'/api/original-games/open-directory', 'body':{'id':'bear-original'}},
        ], self.original_requests)
        self.original_failures['cash-latest'] = '现金风暴隔离预览启动失败'
        await cash.locator('.original-preview:visible').click()
        await cash.get_by_text('现金风暴隔离预览启动失败', exact=True).wait_for()
        self.assertNotIn('现金风暴隔离预览启动失败', await bear.inner_text())
        await bear.locator('.original-preview:visible').click()
        self.assertEqual({'path':'/api/original-games/preview', 'body':{'id':'bear-original'}}, self.original_requests[-1])
        self.assertIn('现金风暴隔离预览启动失败', await cash.inner_text())
        await cash.locator('.original-history > summary').click()
        previous = cash.locator('.original-history .original-folder[data-original-id="cash-previous"]')
        await previous.click()
        self.assertEqual({'path':'/api/original-games/open-directory', 'body':{'id':'cash-previous'}}, self.original_requests[-1])
        self.assertEqual([], self.writes)

    async def test_original_preview_waits_for_ready_and_reports_failure(self):
        p = self.page
        self.original_games = [dict(id='cash-pending', game_ids=['cash'], brand='PG', external_id='1682240',
            title='现金风暴', directory=str(self.root / 'cash-pending'), status='captured_candidate',
            can_preview=True, preview_mode='offline', reason='原版已生成，玩法待验收')]
        self.preview_replies['cash-pending'] = {'ok':True, 'state':'starting', 'run_id':'fixture-run', 'message':'正在启动原版试玩'}
        self.preview_states['fixture-run'] = {'ok':True, 'state':'starting', 'run_id':'fixture-run', 'message':'正在启动原版试玩'}
        await p.goto('http://127.0.0.1:8090/')
        await p.wait_for_function("document.getElementById('library-summary').textContent.includes('已核对 2 个批次')")
        cash = p.locator('#library-rows > tr[data-game-key]').filter(has_text='现金风暴')
        button = cash.locator('.original-preview:visible')
        await button.click()
        self.assertTrue(await button.is_disabled())
        self.assertNotIn('试玩已打开', await cash.inner_text())
        self.preview_states['fixture-run'] = {'ok':False, 'state':'error', 'run_id':'fixture-run', 'message':'隔离浏览器未能就绪'}
        await cash.get_by_text('隔离浏览器未能就绪', exact=True).wait_for(timeout=15000)
        self.assertTrue(await button.is_enabled())
        self.assertEqual([{'path':'/api/original-games/preview', 'body':{'id':'cash-pending'}}], self.original_requests)
        self.preview_states['fixture-run'] = {'ok':True, 'state':'ready', 'run_id':'fixture-run', 'message':'原版试玩已打开'}
        await button.click()
        await cash.get_by_text('原版试玩已打开', exact=True).wait_for(timeout=15000)
        self.assertTrue(await button.is_enabled())
        self.assertEqual(2, len(self.original_requests))

    async def test_unready_original_keeps_folder_and_explains_preview(self):
        p = self.page
        self.original_games = [dict(id='cash-incomplete', game_ids=['cash'], brand='PG', external_id='1682240',
            title='现金风暴', directory=str(self.root / 'cash-incomplete'), status='needs_adapter',
            can_preview=False, preview_mode=None, reason='该版本还缺少本地启动适配器')]
        await p.goto('http://127.0.0.1:8090/')
        await p.wait_for_function("document.getElementById('library-summary').textContent.includes('已核对 2 个批次')")
        cash = p.locator('#library-rows > tr[data-game-key]').filter(has_text='现金风暴')
        await cash.locator('.original-preview').wait_for()
        self.assertTrue(await cash.locator('.original-preview').is_disabled())
        self.assertTrue(await cash.locator('.original-folder').is_enabled())
        self.assertIn('该版本还缺少本地启动适配器', await cash.locator('.original-products').inner_text())
        await cash.locator('.original-folder').click()
        self.assertEqual([{'path':'/api/original-games/open-directory', 'body':{'id':'cash-incomplete'}}], self.original_requests)

    async def test_original_history_stays_open_during_async_actions(self):
        p = self.page
        self.original_games = [dict(id=identifier, game_ids=['cash'], brand='PG', external_id='1682240',
            title='现金风暴', directory=str(self.root / identifier), status='captured_candidate',
            can_preview=True, preview_mode='offline', reason='原版客户端已导出，玩法待验收')
            for identifier in ('history-latest', 'history-previous')]
        self.preview_replies['history-previous'] = {
            'ok':True, 'state':'starting', 'run_id':'history-run', 'message':'旧产物正在启动'}
        self.preview_states['history-run'] = {
            'ok':True, 'state':'starting', 'run_id':'history-run', 'message':'旧产物正在启动'}
        await p.goto('http://127.0.0.1:8090/')
        await p.wait_for_function("document.getElementById('library-summary').textContent.includes('已核对 2 个批次')")
        cash = p.locator('#library-rows > tr[data-game-key]').filter(has_text='现金风暴')
        history = cash.locator('.original-history')
        await history.locator('summary').click()
        self.assertTrue(await history.evaluate('node => node.open'))
        previous = history.locator('.original-product[data-original-id="history-previous"]')
        await previous.locator('.original-preview').click()
        self.assertTrue(await history.evaluate('node => node.open'), '启动中的行重绘不能收起其他生成记录')
        self.assertTrue(await previous.locator('.original-preview').is_visible())
        self.preview_states['history-run'] = {
            'ok':True, 'state':'ready', 'run_id':'history-run', 'message':'旧产物试玩已打开'}
        await p.wait_for_function("document.querySelector('.original-product[data-original-id=\"history-previous\"] .game-feedback').textContent === '旧产物试玩已打开'")
        self.assertTrue(await history.evaluate('node => node.open'), '异步启动结果重绘不能收起其他生成记录')
        self.assertTrue(await previous.locator('.original-preview').is_visible())
        await previous.locator('.original-folder').click()
        await p.wait_for_function("document.querySelector('.original-product[data-original-id=\"history-previous\"] .game-feedback').textContent === '已请求打开原版游戏文件夹'")
        self.assertTrue(await history.evaluate('node => node.open'), '打开旧产物目录后的行重绘不能收起其他生成记录')
        self.assertTrue(await previous.locator('.original-folder').is_visible())
        self.assertEqual([
            {'path':'/api/original-games/preview', 'body':{'id':'history-previous'}},
            {'path':'/api/original-games/open-directory', 'body':{'id':'history-previous'}},
        ], self.original_requests)

    async def test_adapter_popup_waits_for_verified_url_and_shows_failure(self):
        p = self.page
        self.original_games = [dict(id='bear-popup', game_ids=['bear'], brand='IGT', external_id='603',
            title='大熊', directory=str(self.root / 'bear-popup'), status='adapter_ready',
            can_preview=True, preview_mode='adapter', reason='同版客户端已适配')]
        self.preview_replies['bear-popup'] = {'ok':True, 'state':'starting', 'run_id':'popup-run', 'mode':'adapter'}
        self.preview_states['popup-run'] = {'ok':True, 'state':'starting', 'run_id':'popup-run', 'mode':'adapter'}
        destination = 'http://127.0.0.1:49218/preview-fixture'
        navigations = []

        async def preview_fixture(route):
            navigations.append(route.request.url)
            await route.fulfill(content_type='text/html; charset=utf-8', body='<meta charset="utf-8"><title>原版试玩夹具</title><p>已到达本次试玩入口</p>')

        await p.context.route(destination, preview_fixture)
        await p.goto('http://127.0.0.1:8090/')
        await p.wait_for_function("document.getElementById('library-summary').textContent.includes('已核对 2 个批次')")
        bear = p.locator('#library-rows > tr[data-game-key]').filter(has_text='大熊')
        async with p.expect_popup() as opened:
            await bear.locator('.original-preview').click()
        popup = await opened.value
        self.assertEqual('about:blank', popup.url)
        self.assertIn('正在', await popup.locator('body').inner_text())
        self.assertEqual([], navigations)
        self.preview_states['popup-run'] = {'ok':True, 'state':'ready', 'run_id':'popup-run',
                                           'mode':'adapter', 'url':destination, 'port':49218}
        await popup.wait_for_url(destination)
        self.assertEqual('原版试玩夹具', await popup.title())
        self.assertEqual([destination], navigations)
        # 下一次失败只在本次等待窗口说明错误，不导航到前次或其他地址。
        self.preview_replies['bear-popup'] = {'ok':True, 'state':'starting', 'run_id':'popup-failed', 'mode':'adapter'}
        self.preview_states['popup-failed'] = {'ok':False, 'state':'error', 'run_id':'popup-failed',
                                               'message':'预览夹具启动失败', 'mode':'adapter'}
        async with p.expect_popup() as failed_open:
            await bear.locator('.original-preview').click()
        failed = await failed_open.value
        await failed.get_by_text('预览夹具启动失败').wait_for(timeout=15000)
        self.assertEqual('about:blank', failed.url)
        self.assertEqual([destination], navigations)
        await bear.get_by_text('预览夹具启动失败', exact=True).wait_for()


if __name__ == '__main__':
    unittest.main()
