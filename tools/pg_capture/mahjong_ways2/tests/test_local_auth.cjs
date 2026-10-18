const { projectRoot, clientRoot, diagnostics, formattedFixture } = require('../layout.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
let playwright;
try { playwright = require('playwright'); }
catch { playwright = require(path.join(process.env.TEMP, 'opencode/node_modules/playwright')); }
(async () => {
    const browser = await playwright.chromium.launch({ channel: 'msedge', headless: true });
    try {
        const context = await browser.newContext();
        const remoteGameRequests = [];
        await context.route('**/*', route => {
            const url = new URL(route.request().url());
            if (url.hostname !== 'localhost' && !['blob:', 'data:'].includes(url.protocol)) {
                if (/^\/(web-api|game-api)\//.test(url.pathname)) remoteGameRequests.push(url.pathname);
                return route.abort();
            }
            return route.continue();
        });
        const page = await context.newPage();
        await page.addInitScript(() => {
            const timer = setInterval(() => {
                const framework = window.System?.get(location.origin + '/shared/b4d9192613/321ac46ae6.186bf.js');
                if (!framework?.DataSource) return;
                clearInterval(timer);
                const update = framework.DataSource.prototype.overwriteGameInfo;
                framework.DataSource.prototype.overwriteGameInfo = function (...args) {
                    window.testDataSource = this;
                    return update.apply(this, args);
                };
            }, 5);
        });
        const calls = [];
        page.on('pageerror', error => console.error('Client exception:', error.message));
        page.on('response', response => {
            const url = new URL(response.url());
            if (/^\/(web-api|game-api)\//.test(url.pathname)) calls.push({ path: url.pathname, status: response.status() });
        });
        const authPromise = page.waitForResponse(r => r.url().endsWith('/verifyOperatorPlayerSession'), { timeout: 60000 });
        authPromise.catch(() => {});
        const namesPromise = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/GameName/Get'), { timeout: 60000 });
        namesPromise.catch(() => {});
        const infoPromise = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/GameInfo/Get'), { timeout: 60000 });
        infoPromise.catch(() => {});
        await page.goto('http://localhost:8080/?mock=1', { waitUntil: 'domcontentloaded' });
        await page.getByText('继续游戏', { exact: true }).click();
        const response = await authPromise;
        const payload = new URLSearchParams(response.request().postData());
        assert.equal(response.status(), 200);
        assert.equal(payload.get('os'), 'local-demo-session');
        assert.equal(payload.get('otk'), 'local-demo');
        assert.equal(payload.get('gi'), '74');
        const data = await response.json();
        assert.equal(data.err, null);
        assert.equal(data.dt.bl, 2000);
        const namesResponse = await namesPromise;
        assert.equal(namesResponse.status(), 200);
        const names = await namesResponse.json();
        assert.equal(names.err, null);
        assert.equal(names.dt['74'], 'Mahjong Ways 2');
        assert.deepEqual(names, JSON.parse(fs.readFileSync(path.join(clientRoot, 'fixtures/game-names.en.json'), 'utf8')));
        const namesForm = new URLSearchParams(namesResponse.request().postData());
        assert.equal(namesForm.get('atk'), 'local-demo-session');
        assert.equal(namesForm.get('gid'), '74');
        let infoResponse;
        try { infoResponse = await infoPromise; }
        catch (error) {
            console.error('API calls:', JSON.stringify(calls));
            console.error('Client state:', await page.locator('body').innerText({ timeout: 3000 }));
            throw error;
        }
        assert.equal(infoResponse.status(), 200);
        const info = JSON.parse(fs.readFileSync(path.join(clientRoot, 'fixtures/game-info.json'), 'utf8'));
        assert.deepEqual(await infoResponse.json(), info, 'GameInfo must preserve the supplied capture');
        const infoForm = new URLSearchParams(infoResponse.request().postData());
        assert.deepEqual(Object.fromEntries(infoForm), { atk: 'local-demo-session', btt: '1', pf: '1' });
        await page.waitForFunction(() => window.testDataSource?.lastGameInfoRawData?.dt?.ls?.si);
        const models = await page.evaluate(() => {
            const source = window.testDataSource;
            return { balance: source.playerModel.balance, currency: source.systemModel.currencyCode,
                sizes: source.systemModel.betSizeList, levels: source.systemModel.betLevelList,
                thresholds: source.systemModel.winThresholds.rawData,
                maxLines: source.systemModel.maxLineNumber,
                spin: source.lastGameInfoRawData.dt.ls.si };
        });
        assert.equal(models.balance, info.dt.bl);
        assert.equal(models.currency, info.dt.cc);
        assert.deepEqual(models.sizes, info.dt.cs);
        assert.deepEqual(models.levels, info.dt.ml);
        assert.deepEqual(models.thresholds, info.dt.wt, 'binary threshold adaptation must round-trip through the original model');
        assert.equal(models.maxLines, info.dt.mxl);
        assert.deepEqual(models.spin, info.dt.ls.si, 'all initial spin fields must survive the adapter');
        const result = await page.evaluate(() => {
            const framework = System.get(location.origin + '/shared/b4d9192613/321ac46ae6.186bf.js');
            return { text: document.body.innerText, session: framework.LaunchConfig.cs_Launch.operatorPlayerSession,
                canvas: !!document.getElementById('GameCanvas') };
        });
        assert.ok(result.canvas, 'original canvas must remain');
        assert.ok(!result.text.includes('C1002'), 'local login must pass the original authentication gate');
        assert.ok(calls.some(call => call.path.includes('/GameName/')), 'original client must advance beyond login');
        assert.deepEqual(remoteGameRequests, []);
        const rejected = await context.request.post('http://localhost:8080/web-api/auth/session/v2/verifyOperatorPlayerSession', {
            form: { os: 'wrong-session', otk: 'local-demo', gi: '74', btt: '1' },
        });
        assert.equal(rejected.status(), 400, 'mock endpoint must reject unknown sessions');
        const invalidNameSession = await context.request.post('http://localhost:8080/web-api/game-proxy/v2/GameName/Get', {
            form: { atk: 'wrong-session', gid: '74', lang: 'en' },
        });
        assert.equal(invalidNameSession.status(), 400);
        const invalidInfoSession = await context.request.post('http://localhost:8080/game-api/74/v4/GameInfo/Get', {
            form: { atk: 'wrong-session', btt: '1', pf: '1' },
        });
        assert.equal(invalidInfoSession.status(), 400);
        const unimplemented = await context.request.post('http://localhost:8080/game-api/74/v4/Uncaptured/Get');
        assert.equal(unimplemented.status(), 501, 'missing fixtures must fail explicitly');
        const normal = await context.request.get('http://localhost:8080/');
        assert.ok(!(await normal.text()).includes('/local-auth-bootstrap.js'), 'mock login must remain opt-in');
        fs.mkdirSync('diagnostics', { recursive: true });
        fs.writeFileSync('diagnostics/local-auth-result.json', JSON.stringify({ calls, models, ...result }, null, 2));
        await page.screenshot({ path: 'diagnostics/local-auth.png' });
        console.log('PASS original client accepts login, names and GameInfo; captured models verified; no remote game API requests');
        console.log(JSON.stringify({ calls, text: result.text }, null, 2));
    } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
