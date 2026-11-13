const { projectRoot, clientRoot, diagnostics, formattedFixture } = require('../layout.cjs');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require(path.join(process.env.TEMP, 'opencode/node_modules/playwright'));

// Tests the captured original help panels without placing any bets.
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 720 } });
    await context.route('**/*', route =>
      new URL(route.request().url()).hostname === 'localhost' ? route.continue() : route.abort());
    const page = await context.newPage();
    const helpFailures = [];
    let checkingHelp = false, spins = 0, gameRuleLoaded = false;
    page.on('request', request => { if (new URL(request.url()).pathname.endsWith('/Spin')) spins++; });
    page.on('response', response => {
      if (response.url().includes('/GameRule/Get') && response.status() === 200) gameRuleLoaded = true;
      if (checkingHelp && response.status() >= 400) helpFailures.push([response.status(), response.url()]);
    });
    await page.goto('http://localhost:8080/?mock=1', { waitUntil: 'domcontentloaded', timeout: 20000 });
    await page.getByText('继续游戏', { exact: true }).click({ timeout: 10000 }).catch(() => {});
    await page.getByText('开始', { exact: true }).waitFor({ timeout: 45000 });
    await page.waitForTimeout(800);
    await page.mouse.click(640, 560);
    await page.waitForTimeout(6000);
    for (let i = 0; i < 4; i++) {
      await page.mouse.click(460, 574);
      await page.waitForTimeout(1000);
      if (await page.getByText('赔付表', { exact: true }).count()) break;
    }
    checkingHelp = true;
    await page.locator('#user-profile-paytable-button').click();
    const payout = page.locator('#user-profile-paytable-internal-page');
    await payout.getByText('符号赔付值', { exact: true }).waitFor();
    await page.waitForTimeout(2000);
    const payoutText = await payout.innerText();
    for (const text of ['金色麻将符号', '免费旋转模式', '2,000路', '10 x 6 = 60']) assert(payoutText.includes(text), text);
    await page.screenshot({ path: 'diagnostics/original-paytable.png' });
    await payout.getByText('所有赢奖以现金显示。', { exact: true }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: 'diagnostics/original-paytable-bottom.png' });
    await page.locator('#user-profile-rules-button').click();
    const rules = page.locator('#user-profile-rules-internal-page');
    await rules.waitFor({ state: 'visible' });
    await page.waitForTimeout(2000);
    const rulesText = await rules.innerText();
    fs.writeFileSync('diagnostics/original-rules.txt', rulesText);
    console.log('RULES', rulesText);
    assert(rulesText.length > 500, 'Original rules should contain the full instructions');
    await page.screenshot({ path: 'diagnostics/original-rules.png' });
    await page.locator('#user-profile-paytable-button').click();
    await payout.getByText('符号赔付值', { exact: true }).waitFor();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(1000);
    await payout.getByText('符号赔付值', { exact: true }).scrollIntoViewIfNeeded();
    const bounds = await payout.boundingBox();
    assert(bounds.x >= -1 && bounds.x + bounds.width <= 391, 'Mobile panel overflows');
    await page.screenshot({ path: 'diagnostics/original-help-mobile.png' });
    assert.equal(await page.locator('#local-game-help').count(), 0, 'Replacement help must be removed');
    assert(gameRuleLoaded, 'Captured GameRule response was not loaded');
    assert.deepEqual(helpFailures, [], 'Original help requests failed');
    assert.equal(spins, 0, 'Help navigation must not submit a Spin');
    console.log('PASS: original payout, scroll, rules, switch, mobile layout, GameRule API, no help failures, no Spin');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
