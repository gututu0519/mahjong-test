"""Exercise the running Super Ace service in a fresh demo browser session.

Run with response-capture/.venv/Scripts/python.exe tools/jili_capture/check_local.py.
Uses the real captured client without browser response overrides.
"""
import argparse
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'clients/super-ace/diagnostics'
MODULE = "System.get('chunks:///index-2059667d.js')"


async def main(url):
    OUT.mkdir(parents=True, exist_ok=True)
    errors, failures = [], []
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='msedge', headless=True)
        context = await browser.new_context(viewport={'width': 1100, 'height': 800})
        page = await context.new_page()
        page.set_default_timeout(15000)
        page.on('pageerror', lambda error: errors.append(error.stack or str(error)))
        page.on('response', lambda response: failures.append([response.status, response.url.split('?')[0]])
                if response.status >= 400 else None)

        async def wait_idle():
            await page.wait_for_function(f"{MODULE}?.j?.m_currState === 1005 && {MODULE}.h.IsGameIdle", timeout=90000)

        async def snapshot():
            return await page.evaluate("""async () => {
                const m = System.get('chunks:///index-2059667d.js');
                const token = new URLSearchParams(location.search).get('ops');
                const headers = {Authorization: 'Bearer ' + token};
                const wallet = await (await fetch('/api/v1/wallet', {headers})).json();
                const history = await (await fetch('/api/v1/history', {headers})).json();
                return {balance: wallet.balance_minor, ui: Math.round(m.h.GetChips() * 10000),
                    auto: m.h.IsAutoSpin, rounds: history.spins.map(x => ({sid: x.sid, wallet: x.wallet})),
                    predicatesRemoved: !Object.hasOwn(Function.prototype, 'V97') && !Object.hasOwn(Function.prototype, 'r3L3')};
            }""")

        try:
            await page.goto(url, wait_until='domcontentloaded')
            await page.wait_for_function(f"{MODULE}?.x?.IsGetInfo && {MODULE}.x.m_iGameCommon")
            await page.wait_for_function("typeof progressNow !== 'undefined' && progressNow >= 100", timeout=30000)
            await page.screenshot(path=str(OUT / 'startup.png'))
            await page.mouse.click(550, 640)  # Original Continue button.
            await page.wait_for_timeout(1000)
            await page.mouse.click(550, 470)  # Original Play button.
            await wait_idle()
            initial = await snapshot()
            assert initial['balance'] == initial['ui'] == 20000000, initial
            assert initial['predicatesRemoved'], 'Temporary prototype setters were not removed'
            print('Startup and session: OK', flush=True)

            await page.mouse.click(550, 710)
            await page.wait_for_function(f"{MODULE}.e.IsSpined")
            await page.wait_for_timeout(1500)
            await wait_idle()
            spun = await snapshot()
            assert len(spun['rounds']) == 1 and spun['balance'] == spun['ui'], spun
            assert spun['rounds'][0]['wallet']['debit_minor'] == 5000, spun
            await page.screenshot(path=str(OUT / 'spin.png'))

            await page.mouse.click(635, 708)
            await page.wait_for_function(f"{MODULE}.h.IsAutoSpin")
            await page.wait_for_timeout(5000)
            await page.mouse.click(635, 708)
            await page.wait_for_function(f"!{MODULE}.h.IsAutoSpin")
            await wait_idle()
            autoplay = await snapshot()
            assert len(autoplay['rounds']) >= 2 and autoplay['balance'] == autoplay['ui'], autoplay
            print('Spin, autoplay and wallet: OK', flush=True)

            for name, y, text in [('rules', 600, 'Golden Card'), ('history', 553, 'Balance')]:
                await page.mouse.click(360, 705)
                await page.wait_for_timeout(400)
                await page.mouse.click(360, y)
                frame = page.frame_locator('iframe')
                await frame.get_by_text(text, exact=False).first.wait_for()
                await page.screenshot(path=str(OUT / (name + '.png')))
                await frame.get_by_role('button', name='Back to game').click()
                await page.locator('iframe').wait_for(state='hidden')
            print('Rules and history: OK', flush=True)

            before_reload = await snapshot()
            await page.reload(wait_until='domcontentloaded')
            await page.wait_for_function(f"{MODULE}?.x?.IsGetInfo && {MODULE}.x.m_iGameCommon")
            await page.wait_for_function("typeof progressNow !== 'undefined' && progressNow >= 100", timeout=30000)
            await page.mouse.click(550, 640)
            await page.wait_for_timeout(1000)
            await page.mouse.click(550, 470)
            await wait_idle()
            restored = await snapshot()
            assert restored['balance'] == before_reload['balance'] == restored['ui'], restored
            assert restored['rounds'] == before_reload['rounds'], 'Reload charged another round'
            await page.set_viewport_size({'width': 390, 'height': 844})
            await page.wait_for_timeout(1000)
            await page.screenshot(path=str(OUT / 'mobile.png'))
            assert not errors, errors
            unexpected = [x for x in failures if not x[1].endswith(('/favicon0.ico', '/rankingservice/user/GetMailList'))]
            assert not unexpected, unexpected
            print(json.dumps({'ok': True, 'rounds': len(restored['rounds']), 'balance_minor': restored['balance'],
                              'checks': ['startup', 'spin', 'autoplay', 'rules', 'history', 'reload', 'mobile'],
                              'platform_requests': failures}, ensure_ascii=False), flush=True)
        finally:
            await page.screenshot(path=str(OUT / 'check-final.png'))
            (OUT / 'browser-check.json').write_text(json.dumps({'errors': errors, 'failures': failures}, indent=2), encoding='utf-8')
            await browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8088/')
    asyncio.run(main(parser.parse_args().url))
