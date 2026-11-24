"""通过 SDS 公开玩家页面登录并打开一款已选游戏。"""
import asyncio
import re
from urllib.parse import quote, urlencode, urlsplit

from playwright.async_api import Error as BrowserError, TimeoutError as BrowserTimeout


ORIGIN = 'https://sdstest.ink'
LAUNCH_URL = re.compile(r'^https://sdstest\.ink(?::443)?/api/v1/games/[^/?#]+/launch(?:[?#].*)?$')
FORM_WAIT = 15000
ACTION_WAIT = 30000
SESSION_WAIT = 10000


class LobbyFlowError(ValueError):
    """只返回固定的阶段提示，避免浏览器异常包含输入值或启动网址。"""


class LobbyLoginExpired(LobbyFlowError):
    """原站已无法恢复这次手动登录。"""


def _site_path(url):
    p = urlsplit(url)
    return p.path if p.scheme == 'https' and p.netloc.lower() in ('sdstest.ink', 'sdstest.ink:443') else None


async def _visit(page, path, *, allow_login_redirect=False):
    response = await page.goto(ORIGIN + path, wait_until='domcontentloaded', timeout=45000)
    current = _site_path(page.url)
    if current != urlsplit(path).path and not (allow_login_redirect and current == '/login'):
        raise LobbyFlowError('大厅跳转到了其他地址，已停止自动操作。')
    if response is None or not response.ok:
        raise LobbyFlowError('大厅页面暂时无法打开，请检查站点连接后再试。')


async def has_lobby_session(page) -> bool:
    """打开大厅，让原站自行恢复登录。仅观察主页面发起的刷新请求及其状态。"""
    checked = asyncio.get_running_loop().create_future()

    requests = set()

    def on_request(request):
        if (request.method == 'POST' and _site_path(request.url) == '/api/v1/auth/refresh'
                and request.frame == page.main_frame and _site_path(request.frame.url) is not None):
            requests.add(request)

    def on_response(response):
        if not checked.done() and response.request in requests:
            checked.set_result(response.status)

    def on_failure(request):
        if not checked.done() and request in requests:
            checked.set_result(None)

    page.on('request', on_request)
    page.on('response', on_response)
    page.on('requestfailed', on_failure)
    try:
        await _visit(page, '/', allow_login_redirect=True)
        if _site_path(page.url) == '/login':
            return False
        try:
            status = await asyncio.wait_for(checked, SESSION_WAIT / 1000)
        except asyncio.TimeoutError:
            return False
        if status is not None and 200 <= status < 300:
            return True
        if status in (401, 403):
            return False
        raise LobbyFlowError('大厅暂时无法核验登录状态，请检查站点连接后再试。')
    except BrowserError:
        raise LobbyFlowError('无法连接大厅核验登录状态，请检查站点连接后再试。') from None
    finally:
        page.remove_listener('request', on_request)
        page.remove_listener('response', on_response)
        page.remove_listener('requestfailed', on_failure)
        checked.cancel()


async def enter_lobby(page, account, password):
    """只在同源公开密码表单提交一次。调用期间应暂停采集。"""
    if not isinstance(account, str) or not account.strip() or not isinstance(password, str) or not password:
        raise LobbyFlowError('请先填写预设登录账号和密码。')
    message = '未能打开大厅登录表单，请检查站点连接和登录入口。'
    try:
        await _visit(page, '/login')
        opener = page.get_by_role('button', name='Open Login / Register', exact=True)
        tab = page.locator('button.login-tab')
        form = page.locator('form.login-form')
        controls = page.locator('button.login-tab:visible, form.login-form:visible').first
        deadline = asyncio.get_running_loop().time() + FORM_WAIT / 1000
        while not await controls.is_visible():
            remaining = int((deadline - asyncio.get_running_loop().time()) * 1000)
            if remaining <= 0:
                raise LobbyFlowError(message)
            # 原站入口可能先于事件绑定出现。只重试打开尚未显示的弹窗，表单只提交一次。
            if await opener.is_visible() and not await page.get_by_role('dialog').count():
                await opener.click(timeout=remaining)
            try:
                await controls.wait_for(state='visible', timeout=min(remaining, 1000))
            except BrowserTimeout:
                continue
        if not await form.is_visible() and await tab.get_attribute('aria-selected') != 'true':
            await tab.click(timeout=FORM_WAIT)
        await form.wait_for(state='visible', timeout=FORM_WAIT)
        password_method = form.get_by_role('button', name='Log in with password', exact=True)
        if await password_method.is_visible():
            await password_method.click(timeout=FORM_WAIT)

        # 固定到同一文档的元素句柄。填表期间若发生导航，失效的句柄不会改填新页面。
        form_node = await form.element_handle(timeout=FORM_WAIT)
        if not await form_node.evaluate("""f => location.origin === 'https://sdstest.ink'
                && location.pathname === '/login' && new URL(f.action, location.href).origin === location.origin"""):
            raise LobbyFlowError('登录表单已经变更，已停止自动填写。')
        user_input = await form_node.wait_for_selector('input[autocomplete="username"]', state='visible', timeout=FORM_WAIT)
        secret_input = await form_node.wait_for_selector('input[autocomplete="current-password"]', state='visible', timeout=FORM_WAIT)
        submit = await form_node.query_selector('button[type="submit"]')
        if not user_input or not secret_input or not submit:
            raise LobbyFlowError('未找到原站的账号密码登录表单，请检查当前登录方式。')
        message = '登录未完成。请检查账号密码、表单提示或原站是否要求额外验证。'
        await user_input.fill(account.strip(), timeout=FORM_WAIT)
        await secret_input.fill(password, timeout=FORM_WAIT)
        async with page.expect_response(
            lambda r: r.request.method == 'POST' and _site_path(r.url) == '/api/v1/auth/login',
            timeout=ACTION_WAIT,
        ) as completed:
            try:
                await submit.click(timeout=FORM_WAIT)
            except BrowserTimeout:
                raise LobbyFlowError('原站登录按钮未就绪，请检查表单提示或稍后重试。') from None
        response = await completed.value
        if response.status == 429:
            raise LobbyFlowError('原站提示登录请求过于频繁，请稍后再试。')
        if not response.ok:
            raise LobbyFlowError('原站未接受本次登录，请检查预设账号密码或站点登录提示。')
        await form.wait_for(state='hidden', timeout=FORM_WAIT)
        if _site_path(page.url) is None:
            raise LobbyFlowError('登录后页面已离开指定大厅，未继续操作。')
    except BrowserError:
        raise LobbyFlowError(message) from None


async def _filter_brand(page, brand):
    trigger = page.locator('button[aria-controls="brand-filter-panel"]')
    if not await trigger.is_visible():
        return False
    await trigger.click(timeout=FORM_WAIT)
    panel = page.locator('#brand-filter-panel')
    await panel.wait_for(state='visible', timeout=FORM_WAIT)
    choice = panel.get_by_role('button', name=brand.upper(), exact=True)
    if await choice.count() != 1:
        return False
    if await choice.get_attribute('aria-pressed') != 'true':
        await choice.click(timeout=FORM_WAIT)
    await panel.get_by_role('button', name='Confirm', exact=True).click(timeout=FORM_WAIT)
    await panel.wait_for(state='hidden', timeout=FORM_WAIT)
    return True


async def _find_card(page, target):
    names = list(dict.fromkeys(n for n in (target.get('name'), target.get('zh')) if n))
    if not names:
        raise LobbyFlowError('这条目录记录缺少可搜索的游戏名称。')
    for query in names:
        await _visit(page, '/games?' + urlencode({'search': query}))
        # 加载骨架或加载中的状态文案不表示无结果。
        try:
            await page.wait_for_function("""names => {
                const cards = Array.from(document.querySelectorAll('article.game-card[aria-label]'));
                if (cards.some(c => names.includes(c.getAttribute('aria-label')))) return true;
                const state = document.querySelector('.catalog-state');
                return !!state && /no games match your search|no games are available|games are temporarily unavailable/i.test(state.textContent);
            }""", arg=['Show actions for ' + n for n in names], timeout=ACTION_WAIT)
        except BrowserTimeout:
            if query == names[-1]:
                raise LobbyFlowError('等待大厅搜索结果超时，未能确认目标游戏。') from None
            continue
        for name in names:
            cards = page.get_by_role('article', name='Show actions for ' + name, exact=True)
            count = await cards.count()
            if count == 1:
                return cards
            if count > 1:
                by_id = [card for card in await cards.all() if await card.get_attribute('data-game-id') == target['site']]
                if len(by_id) == 1:
                    return by_id[0]
                if target.get('brand'):
                    try:
                        filtered = await _filter_brand(page, target['brand'])
                    except BrowserTimeout:
                        filtered = False
                    if filtered and await cards.count() == 1:
                        return cards
                break
    raise LobbyFlowError('大厅搜索未能唯一确定所选游戏。请核对目录名称，避免进入同名游戏。')


async def open_game(page, target):
    """通过卡片的 Play 操作进入游戏；只有所选站内 ID 的启动才允许送达。"""
    site = target.get('site', '')
    if not isinstance(site, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', site):
        raise LobbyFlowError('所选游戏缺少有效的站内游戏 ID，请重新核对历史。')
    expected = '/api/v1/games/' + quote(site, safe='') + '/launch'
    settled = asyncio.get_running_loop().create_future()

    async def guard(route):
        if route.request.method != 'POST' or _site_path(route.request.url) != expected:
            if not settled.done():
                settled.set_result('wrong')
            await route.abort()
        else:
            await route.fallback()

    def on_response(response):
        if not settled.done() and response.request.method == 'POST' and _site_path(response.url) == expected:
            settled.set_result('accepted' if response.ok else 'rejected')

    message = '大厅中未能打开所选游戏的卡片，请检查搜索结果或页面提示。'
    try:
        card = await _find_card(page, target)
        await page.route(LAUNCH_URL, guard)
        page.on('response', on_response)
        try:
            await card.click(timeout=FORM_WAIT)
            message = '大厅尚未完成玩家状态加载，请检查站点连接后再试。'
            await page.locator('.games-header .balance-skeleton').wait_for(state='hidden', timeout=ACTION_WAIT)
            message = '未收到所选游戏的启动确认，请检查大厅提示及登录状态。'
            await card.get_by_role('button', name='Play', exact=True).click(timeout=FORM_WAIT)
            outcome = await asyncio.wait_for(settled, ACTION_WAIT / 1000)
            if outcome == 'wrong':
                raise LobbyFlowError('大厅卡片的站内 ID 与清单不同，已阻止启动其他游戏。')
            if outcome != 'accepted':
                raise LobbyFlowError('大厅未接受所选游戏的启动请求，请检查站点提示。')
            message = '大厅接受了启动请求，但尚未显示游戏页面。'
            await page.wait_for_url(lambda url: _site_path(url) == '/game', timeout=ACTION_WAIT)
            await page.locator('iframe[title="SDS Game"]').wait_for(state='visible', timeout=ACTION_WAIT)
        finally:
            page.remove_listener('response', on_response)
            if not page.is_closed():
                await page.unroute(LAUNCH_URL, guard)
    except (BrowserError, asyncio.TimeoutError):
        raise LobbyFlowError(message) from None
