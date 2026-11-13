"""Browser-only regression: clearing never sends a mutation to the capture server."""
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright
from app import launch_browser


async def main():
    session_id = 'a' * 32
    rows = [dict(id=i, url=f'https://example.test/{i}', method='GET', type='fetch',
                 status=200, size=10, body=f'bodies/{i}.json', mime='application/json',
                 state='complete', request_headers=[], response_headers=[]) for i in (1, 2)]
    session = dict(id=session_id, url='https://example.test', created='2026-10-13T12:00:00Z',
                   state='recording', error='', ws_count=0, rows=rows)
    mutations, errors = [], []
    html = Path(__file__).with_name('index.html').read_text(encoding='utf8').replace('__TOKEN__', 'test')
    async with async_playwright() as pw:
        browser = await launch_browser(pw, headless=True)
        try:
            page = await browser.new_page(viewport={'width': 1280, 'height': 900})
            page.on('pageerror', lambda error: errors.append(str(error)))

            async def route(request):
                url = request.request.url
                if request.request.method != 'GET':
                    mutations.append(url)
                    return await request.abort()
                if url.endswith('/api/sessions'):
                    body = [{k: v for k, v in session.items() if k != 'rows'}]
                elif url.endswith('/api/sessions/' + session_id):
                    body = session
                elif '/body/' in url:
                    await asyncio.sleep(0.3)  # A stale preview must not reappear after clear.
                    body = dict(text='old response', encoding='text', truncated=False)
                elif url == 'http://127.0.0.1:8090/':
                    return await request.fulfill(content_type='text/html', body=html)
                else:
                    return await request.abort()
                await request.fulfill(content_type='application/json', body=json.dumps(body))

            await page.route('**/*', route)
            await page.goto('http://127.0.0.1:8090/')
            await page.wait_for_function("document.querySelector('#count').textContent === '2'")
            await page.locator('#rows tr').first.click()
            await page.locator('#filter').fill('does-not-match')
            await page.locator('#clear-records').click()
            assert await page.locator('#count').inner_text() == '0'
            assert await page.locator('#rows tr').count() == 0
            await page.wait_for_timeout(500)
            assert await page.locator('#preview').inner_text() == '尚未选择请求'
            assert len(rows) == 2
            rows.append({**rows[0], 'id': 3, 'url': 'https://example.test/3'})
            await page.locator('#filter').fill('')
            await page.wait_for_function("document.querySelector('#count').textContent === '1'")
            assert await page.locator('#rows tr').count() == 1
            await page.reload()
            await page.wait_for_function("document.querySelector('#count').textContent === '1'")
            await page.locator('#show-all').click()
            assert await page.locator('#count').inner_text() == '3'
            assert await page.locator('#rows tr').count() == 3
            assert await page.locator('#saved').inner_text() == '3'
            await page.set_viewport_size({'width': 390, 'height': 844})
            assert await page.locator('#clear-records').is_visible()
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors, errors
            assert not mutations, mutations
            print('PASS: clear, filtered rows, stale preview, live new requests, reload, restore, mobile; no server mutations')
        finally:
            await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
