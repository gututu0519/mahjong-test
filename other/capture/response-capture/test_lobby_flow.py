"""使用完全拦截的原站页面验证大厅会话恢复和登录时序。"""
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from playwright.async_api import async_playwright

import lobby_flow


class LobbyFlowTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pw = await async_playwright().start()
        self.addAsyncCleanup(self.pw.stop)
        browser = await self.pw.chromium.launch()
        self.addAsyncCleanup(browser.close)
        self.page = await browser.new_page()
        self.routes = {}

        async def route(request):
            parts = urlsplit(request.request.url)
            if parts.netloc == 'sdstest.ink':
                body = self.routes.get((request.request.method, parts.path))
                if isinstance(body, int):
                    await request.fulfill(status=body, body='')
                    return
                if isinstance(body, str):
                    await request.fulfill(content_type='text/html', body=body)
                    return
            await request.abort()

        await self.page.route('**/*', route)

    async def test_site_refresh_status(self):
        self.routes['GET', '/'] = """<script>
            fetch('/api/v1/auth/refresh', {method: 'POST'}).catch(() => {});
            </script>"""
        for status, expected in [(204, True), (401, False), (403, False)]:
            with self.subTest(status=status):
                self.routes['POST', '/api/v1/auth/refresh'] = status
                self.assertIs(await lobby_flow.has_lobby_session(self.page), expected)
        for status in (503, None):
            with self.subTest(status=status):
                self.routes['POST', '/api/v1/auth/refresh'] = status
                with self.assertRaises(lobby_flow.LobbyFlowError):
                    await lobby_flow.has_lobby_session(self.page)
        self.routes['GET', '/'] = '<main>Lobby</main>'
        with patch.object(lobby_flow, 'SESSION_WAIT', 100):
            self.assertFalse(await lobby_flow.has_lobby_session(self.page))

    async def test_already_open_form_and_delayed_submit(self):
        self.routes['GET', '/login'] = """<form class="login-form">
            <input autocomplete="username"><input type="password" autocomplete="current-password">
            <button type="submit" disabled>Log in</button></form>
            <script>const form = document.querySelector('form');
            form.oninput = () => setTimeout(() => {form.querySelector('button').disabled = false}, 300);
            form.onsubmit = async e => {e.preventDefault();
              await fetch('/api/v1/auth/login', {method:'POST'}); form.remove(); };
            </script>"""
        self.routes['POST', '/api/v1/auth/login'] = 204
        await lobby_flow.enter_lobby(self.page, 'fixture', 'fixture-password')
        self.assertEqual(0, await self.page.locator('form').count())

    async def test_visible_opener_before_click_handler_is_ready(self):
        self.routes['GET', '/login'] = """<button id="open">Open Login / Register</button>
            <div role="dialog" hidden><form class="login-form">
            <input autocomplete="username"><input type="password" autocomplete="current-password">
            <button type="submit">Log in</button></form></div>
            <script>
            setTimeout(() => document.querySelector('#open').onclick = () => {
              document.querySelector('[role=dialog]').hidden = false;
            }, 2300);
            window.submits = 0;
            document.querySelector('form').onsubmit = async e => {e.preventDefault(); window.submits++;
              await fetch('/api/v1/auth/login', {method:'POST'}); e.target.remove(); };
            </script>"""
        self.routes['POST', '/api/v1/auth/login'] = 204
        await lobby_flow.enter_lobby(self.page, 'fixture', 'fixture-password')
        self.assertEqual(1, await self.page.evaluate('window.submits'))

    async def test_game_waits_until_lobby_initialized(self):
        self.routes['GET', '/games'] = """<header class="games-header"><i class="balance-skeleton">Wait</i></header>
            <article class="game-card" aria-label="Show actions for Test">Test
            <button hidden>Play</button></article>
            <script>const card = document.querySelector('article'), play = card.querySelector('button');
            card.onclick = () => {play.hidden = false;
              const skeleton = document.querySelector('.balance-skeleton');
              if (skeleton) setTimeout(() => skeleton.remove(), 300)};
            play.onclick = async () => {
              if (document.querySelector('.balance-skeleton')) return;
              await fetch('/api/v1/games/test/launch', {method:'POST'}); location.href = '/game'; };
            </script>"""
        self.routes['POST', '/api/v1/games/test/launch'] = 201
        self.routes['GET', '/game'] = '<iframe title="SDS Game" srcdoc="Game"></iframe>'
        with patch.object(lobby_flow, 'ACTION_WAIT', 3000):
            await lobby_flow.open_game(self.page, {'site':'test', 'name':'Test'})
        self.assertTrue(await self.page.frame_locator('iframe').get_by_text('Game').is_visible())
