"""跨批次游戏清单的身份归属、历史恢复和录制中更新回归。"""
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlsplit

from playwright.async_api import async_playwright

from app import launch_browser
from library_input import project_session


class GameLibraryTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.sessions = {}
        self.compact = True
        self.catalog_reads = 0
        self.writes = []
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
        if route.request.method != 'GET' or url.netloc != '127.0.0.1:8090':
            self.writes.append(route.request.method + ' ' + url.netloc)
            return await route.abort()
        if url.path == '/':
            return await route.fulfill(content_type='text/html', body=Path(__file__).with_name('index.html').read_bytes())
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
                self.catalog_reads += 1
                value = project_session(session, self.root / sid)
            elif parts[3] == 'body':
                row = session['rows'][int(parts[4]) - 1]
                path = self.root / sid / row['body']
                if not path.exists():
                    return await route.fulfill(status=404, body='{}')
                self.catalog_reads += int('/catalog' in row['url'])
                value = dict(text=path.read_text(encoding='utf8'), encoding='text', truncated=False)
            else:
                return await route.fulfill(status=404, body='{}')
        await route.fulfill(content_type='application/json', body=json.dumps(value))

    async def exercise(self):
        p = self.page
        await p.goto('http://127.0.0.1:8090/')
        summary = p.locator('#library-summary')
        await p.wait_for_function("document.getElementById('library-summary').textContent.includes('已核对 2 个批次')")
        self.assertIn('未抓 3 · 待补抓 1 · 待识别 1', await summary.inner_text())
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
        await p.locator('#library-rows summary').click()
        self.assertIn('旋转接口响应', await p.locator('#library-rows').inner_text())
        self.assertNotIn('private', await p.locator('#library-rows').inner_text())
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
        self.assertEqual(1,await self.page.locator('#library-rows tr').count())
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
        self.assertEqual(3, await self.page.locator('#library-rows tr').count())
        await self.page.select_option('#library-filter','partial')
        self.assertEqual(0, await self.page.locator('#library-rows tr').count())


if __name__ == '__main__':
    unittest.main()
