// Run with the local server listening on http://localhost:8080/.
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const vm = require('node:vm');
const crypto = require('node:crypto');
let playwright;
try { playwright = require('playwright'); }
catch { playwright = require(path.join(process.env.TEMP, 'opencode/node_modules/playwright')); }

(async () => {
    const browser = await playwright.chromium.launch({ channel: 'msedge', headless: true });
    try {
        const context = await browser.newContext();
        const repaired = fs.readdirSync(path.join(__dirname, 'shared'))
            .filter(name => fs.existsSync(path.join(__dirname, 'shared', name, 'index.js')))
            .map(name => '/shared/' + name + '/index.js');
        async function enter(page, reload = false) {
            const responses = repaired.map(url => page.waitForResponse(
                response => response.request().method() === 'GET' &&
                    new URL(response.url()).pathname === url, { timeout: 15000 }
            ));
            // Attach handlers immediately so a failed navigation cannot leave unhandled rejections.
            const downloaded = Promise.all(responses);
            downloaded.catch(() => {});
            if (reload) await page.reload({ waitUntil: 'domcontentloaded' });
            else await page.goto('http://localhost:8080/', { waitUntil: 'domcontentloaded' });
            // After accepting once, other tabs share that browser preference and skip the prompt.
            const needsContinue = await Promise.race([
                page.getByText('继续游戏', { exact: true }).waitFor({ timeout: 15000 })
                    .then(() => true, () => false),
                downloaded.then(() => false),
            ]);
            if (needsContinue) await page.getByText('继续游戏', { exact: true }).click();
            for (const response of await downloaded) {
                assert.equal(response.status(), 200);
                assert.equal(await response.headerValue('X-Local-Module-Fix'), 'auto-1');
            }
            // A DOM operation after module execution must complete even if assets are missing.
            await page.waitForTimeout(1000);
            const text = await page.locator('body').innerText({ timeout: 3000 });
            assert.ok(!text.includes('G1011'), '游戏入口的插件版本校验失败');
            for (const url of repaired) {
                const delivered = await page.evaluate(async url => {
                    const response = await fetch(url);
                    return {body: await response.text(), revision: response.headers.get('X-Local-Module-Revision')};
                }, url);
                assert.equal(crypto.createHash('sha256').update(delivered.body).digest('hex'),
                    delivered.revision, '浏览器必须加载服务器修复后的模块：' + url);
                assert.notEqual(delivered.body, 'while (true) {}');
            }
        }
        const first = await context.newPage();
        await enter(first);
        const mainScript = '/shared/0dd866175d/d22297d156.9858d.js';
        await first.evaluate(async url => {
            const cache = await caches.open('General2');
            await cache.put(url, new Response('throw new Error("stale main script")'));
        }, mainScript);
        const actualMain = await first.evaluate(async url => (await fetch(url)).text(), mainScript);
        assert.equal(actualMain, fs.readFileSync(path.join(__dirname, mainScript.slice(1)), 'utf8'));
        console.log('PASS 同名主脚本替换后绕过旧缓存');
        // Simulate the bad modules retained by an older tab / worker version.
        await first.evaluate(async urls => {
            const cache = await caches.open('Entry2');
            for (const url of urls) {
                await cache.put(url, new Response('while (true) {}', {
                    headers: { 'Content-Type': 'application/javascript',
                        'X-Local-Module-Fix': '1', Date: new Date().toUTCString() },
                }));
            }
        }, repaired);
        const second = await context.newPage();
        await enter(second);
        assert.equal(context.pages().length, 2);
        await first.locator('body').innerText({ timeout: 3000 });
        console.log('PASS 同一浏览器两个标签页均响应，第二个标签页拒绝旧模块缓存');
        await enter(second, true);
        console.log('PASS 保留两个标签页时刷新仍响应');
        // Add an unknown module name AFTER worker activation, then overwrite it in place.
        const folder = fs.mkdtempSync(path.join(__dirname, 'shared', '.local-module-test-'));
        const filename = path.join(folder, 'index.js');
        const url = '/shared/' + path.basename(folder) + '/index.js';
        const original = fs.readFileSync(path.join(__dirname, 'tests/fixtures/formatted-index.js'));
        try {
            fs.writeFileSync(filename, original);
            await first.evaluate(async url => {
                const cache = await caches.open('Entry2');
                await cache.put(url, new Response('while(true){}'));
            }, url);
            async function load(page) {
                return page.evaluate(async url => {
                    const response = await fetch(url);
                    return { status: response.status, body: await response.text(),
                        revision: response.headers.get('X-Local-Module-Revision') };
                }, url);
            }
            const initial = await load(first);
            assert.equal(initial.status, 200);
            let registered = false;
            vm.runInNewContext(initial.body, { System: { register() { registered = true; } } }, { timeout: 1000 });
            assert.ok(registered);
            assert.deepEqual(fs.readFileSync(filename), original);
            fs.appendFileSync(filename, '\n// updated while both tabs remain open');
            const updated = await load(second);
            assert.equal(updated.status, 200);
            assert.notEqual(updated.revision, initial.revision);
            assert.ok(updated.body.endsWith('// updated while both tabs remain open'));
            fs.writeFileSync(filename, 'while (true) {}');
            assert.equal((await load(second)).status, 422);
            console.log('PASS 运行中新增模块自动修复，替换立即生效，未知死循环被拒绝');
        } finally {
            fs.unlinkSync(filename);
            fs.rmdirSync(folder);
        }
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
