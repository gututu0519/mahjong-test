const { projectRoot, clientRoot, diagnostics, formattedFixture } = require('../layout.cjs');
// Runs the real client against an isolated local wallet and blocks external traffic.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
let playwright;
try { playwright = require('playwright'); }
catch { playwright = require(path.join(process.env.TEMP, 'opencode/node_modules/playwright')); }

(async () => {
    const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'mahjong-spin-'));
    const port = 8082, base = `http://localhost:${port}`;
    const server = spawn('python', ['-u', '-m', 'tools.pg_capture.mahjong_ways2.serve_local', '--port', String(port), '--state-file', path.join(folder, 'wallet.json')],
        { cwd: projectRoot, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
    let logs = '';
    server.stderr.on('data', b => { logs += b; });
    let browser;
    try {
        await new Promise((resolve, reject) => {
            const timeout = setTimeout(() => reject(Error('Test server did not start: ' + logs)), 10000);
            server.stdout.once('data', () => { clearTimeout(timeout); resolve(); });
            server.once('exit', code => { clearTimeout(timeout); reject(Error('Test server exited: ' + code + ' ' + logs)); });
        });
        browser = await playwright.chromium.launch({ channel: 'msedge', headless: true });
        const context = await browser.newContext({ viewport: { width: 1280, height: 720 } });
        const remoteAPIs = [], errors = [], spinResponses = [];
        await context.route('**/*', route => {
            const url = new URL(route.request().url());
            if (url.hostname !== 'localhost' && !['blob:', 'data:'].includes(url.protocol)) {
                if (/^\/(web-api|game-api)\//.test(url.pathname)) remoteAPIs.push(url.pathname);
                return route.abort();
            }
            return route.continue();
        });
        const page = await context.newPage();
        page.on('pageerror', e => errors.push(e.message));
        page.on('response', r => { if (new URL(r.url()).pathname.endsWith('/Spin')) spinResponses.push(r.status()); });
        await page.addInitScript(() => {
            window.testSpins = [];
            const timer = setInterval(() => {
                const f = window.System?.get(location.origin + '/shared/b4d9192613/321ac46ae6.186bf.js');
                if (!f?.DataSource) return;
                clearInterval(timer);
                const init = f.DataSource.prototype.overwriteGameInfo;
                f.DataSource.prototype.overwriteGameInfo = function (...args) {
                    window.testSource = this;
                    return init.apply(this, args);
                };
                const update = f.DataSource.prototype.updateTransactionInfo;
                f.DataSource.prototype.updateTransactionInfo = function (...args) {
                    const result = update.apply(this, args);
                    testSpins.push({ ...this.lastTransactionRawData, balance: this.playerModel.balance });
                    return result;
                };
            }, 5);
        });
        async function enter() {
            await page.getByText('继续游戏', { exact: true }).click({ timeout: 10000 }).catch(() => {});
            await page.getByText('开始', { exact: true }).waitFor({ timeout: 45000 });
            await page.waitForTimeout(800);
            await page.mouse.click(640, 560);
            await page.waitForFunction(() => document.body.innerText.includes('麻将胡了2'));
            await page.waitForTimeout(2500);
        }
        await page.goto(base + '/?mock=1');
        await enter();
        await page.mouse.click(640, 645);
        await page.waitForFunction(() => testSpins.length === 1);
        const loss = await page.evaluate(() => testSpins[0]);
        assert.equal(loss.tb, 1); assert.equal(loss.tw, 0); assert.equal(loss.balance, 1999);
        await page.waitForTimeout(3500);
        await page.mouse.click(640, 645);
        await page.waitForFunction(() => testSpins.length === 4, null, { timeout: 60000 });
        const spins = await page.evaluate(() => testSpins);
        assert.deepEqual(spins.map(s => [s.st, s.nst]), [[1, 1], [1, 4], [4, 4], [4, 1]]);
        assert.deepEqual(spins.map(s => s.tb), [1, 1, 0, 0]);
        assert.deepEqual(spins.map(s => s.tw), [0, .6, .3, 0]);
        assert.equal(spins[3].aw, .9);
        assert.equal(spins[3].balance, 1998.9);
        await page.waitForTimeout(4000);
        fs.mkdirSync(path.join(diagnostics), { recursive: true });
        await page.screenshot({ path: path.join(clientRoot, 'diagnostics/spin-settled.png') });
        // A subsequent user click must start a new round, proving controls unlocked.
        await page.mouse.click(730, 645);
        await page.mouse.click(640, 645);
        await page.waitForFunction(() => testSpins.length === 5);
        const changed = await page.evaluate(() => testSpins[4]);
        assert.notEqual(changed.tb, 1, 'bet control should change the next stake');
        assert.equal(changed.tb, Math.round(changed.cs * changed.ml * 20 * 100) / 100);
        assert.equal(changed.balance, Math.round((1998.9 - changed.tb) * 100) / 100);
        await page.waitForTimeout(3500);
        await page.reload();
        await enter();
        const restored = await page.evaluate(() => ({ spin: testSource.lastTransactionRawData, balance: testSource.playerModel.balance }));
        assert.equal(restored.spin.sid, changed.sid);
        assert.equal(restored.balance, changed.balance);
        assert.deepEqual(spinResponses, [200, 200, 200, 200, 200]);
        assert.deepEqual(remoteAPIs, []);
        assert.deepEqual(errors, []);
        console.log('PASS real client: loss, two wins and cascade finish; next round, bet change, refresh; no remote game APIs');
        console.log(JSON.stringify({ spins: spins.map(s => ({ sid: s.sid, bet: s.tb, win: s.tw, balance: s.balance })), changedBet: changed.tb, restoredBalance: restored.balance }, null, 2));
    } finally {
        if (browser) await browser.close();
        server.kill();
        await new Promise(resolve => server.exitCode !== null ? resolve() : server.once('exit', resolve));
        for (const filename of ['wallet.json', 'wallet.tmp']) {
            const file = path.join(folder, filename);
            if (fs.existsSync(file)) fs.unlinkSync(file);
        }
        fs.rmdirSync(folder);
    }
})().catch(e => { console.error(e); process.exitCode = 1; });
