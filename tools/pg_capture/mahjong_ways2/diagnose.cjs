const { projectRoot, clientRoot, diagnostics, formattedFixture } = require('./layout.cjs');
// Diagnostic only: preserves original files and observes the unmodified client.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
let playwright;
try { playwright = require('playwright'); }
catch { playwright = require(path.join(process.env.TEMP, 'opencode/node_modules/playwright')); }
const { chromium } = playwright;
const root = clientRoot;
const out = diagnostics;
fs.mkdirSync(out, { recursive: true });
const files = ['index.html', 'shared/984721902a/index.json', 'shared/984721902a/996b5422dd.27a51.js'];
const inventory = files.map(file => {
  const data = fs.readFileSync(path.join(root, file));
  const backup = path.join(out, 'backup', file);
  fs.mkdirSync(path.dirname(backup), { recursive: true });
  if (!fs.existsSync(backup)) fs.writeFileSync(backup, data);
  return { file, bytes: data.length, sha256: crypto.createHash('sha256').update(data).digest('hex') };
});
fs.writeFileSync(path.join(out, 'inventory.json'), JSON.stringify(inventory, null, 2));
(async () => {
  const debug = process.argv.includes('--debug');
  const trace = process.argv.includes('--trace');
  const labelArg = process.argv.find(a => a.startsWith('--label='));
  const label = labelArg ? labelArg.slice(8) : trace ? 'trace' : debug ? 'debug' : 'baseline';
  if (!/^[a-zA-Z0-9_-]+$/.test(label)) throw Error('Invalid label');
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({ viewport: { width: 960, height: 900 }, recordHar: { path: path.join(out, label + '.har') } });
  const page = await context.newPage();
  const events = [];
  page.on('console', msg => events.push({ type: 'console', level: msg.type(), text: msg.text(), location: msg.location() }));
  page.on('pageerror', e => events.push({ type: 'pageerror', message: e.message, stack: e.stack }));
  page.on('response', r => events.push({ type: 'response', status: r.status(), url: r.url() }));
  page.on('requestfailed', r => events.push({ type: 'requestfailed', url: r.url(), error: r.failure() }));
  if (debug) {
    const cdp = await context.newCDPSession(page);
    await cdp.send('Debugger.enable');
    await cdp.send('Debugger.setPauseOnExceptions', { state: 'all' });
    if (trace) await cdp.send('Debugger.setBreakpointByUrl', { urlRegex: '^blob:http://localhost:8080/', lineNumber: 88, condition: 'V7[0][0] && V7[0][0].name === "l5o"' });
    let count = 0;
    cdp.on('Debugger.paused', async ev => {
      try {
        const record = { type: 'paused', reason: ev.reason, data: ev.data, frames: ev.callFrames.map(f => ({ functionName: f.functionName, url: f.url, location: f.location })) };
        const frame = ev.callFrames.find(f => f.functionName === 'l5o');
        if (trace && ev.reason !== 'exception') {
          record.indexInput = await cdp.send('Debugger.evaluateOnCallFrame', { callFrameId: ev.callFrames[0].callFrameId, expression: 'JSON.stringify({names:D6,mask:b0[3],seed:b0[7],args:[V7[0][1],V7[0][2],V7[0][3],V7[0][4]],sourceMethod:b0[2].name,stringMethod:b0[6].name})', returnByValue: true });
        }
        if (frame && ev.reason === 'exception') {
          record.locals = await cdp.send('Debugger.evaluateOnCallFrame', { callFrameId: frame.callFrameId, expression: 'JSON.stringify({E5P,e7O,keys:Object.keys(W3D),values:W3D,source:l5o.toString()})', returnByValue: true });
          const loaded = await cdp.send('Debugger.getScriptSource', { scriptId: frame.location.scriptId });
          const disk = fs.readFileSync(path.join(root, files[2]), 'utf8');
          record.loadedSourceMatchesDisk = loaded.scriptSource === disk;
          record.loadedSourceSha256 = crypto.createHash('sha256').update(loaded.scriptSource).digest('hex');
        }
        events.push(record);
        if (++count > 30) await cdp.send('Debugger.setPauseOnExceptions', { state: 'none' });
      } finally { await cdp.send('Debugger.resume').catch(() => {}); }
    });
  }
  try {
    await page.goto('http://localhost:8080', { waitUntil: 'domcontentloaded', timeout: 30000 });
    if (process.argv.includes('--continue')) {
      const proceed = page.getByText('继续游戏', { exact: true });
      if (await proceed.isVisible().catch(() => false)) await proceed.click();
      else await proceed.waitFor({ timeout: 10000 }).then(() => proceed.click()).catch(() => {});
    }
    await page.waitForTimeout(15000);
    events.push({ type: 'serviceworkers', registrations: await page.evaluate(async () => {
      if (!('serviceWorker' in navigator)) return [];
      return (await navigator.serviceWorker.getRegistrations()).map(r => ({ scope: r.scope,
        active: r.active && { url: r.active.scriptURL, state: r.active.state },
        waiting: r.waiting && r.waiting.state, installing: r.installing && r.installing.state }));
    }) });
    await page.screenshot({ path: path.join(out, label + '.png'), fullPage: true });
    fs.writeFileSync(path.join(out, label + '-dom.html'), await page.content());
    events.push({ type: 'summary', title: await page.title(), text: await page.locator('body').innerText() });
  } catch (e) { events.push({ type: 'harnesserror', message: e.stack }); }
  fs.writeFileSync(path.join(out, label + '.json'), JSON.stringify(events, null, 2));
  await context.close();
  await browser.close();
  console.log(JSON.stringify(events.filter(e => e.type !== 'response'), null, 2));
})();
