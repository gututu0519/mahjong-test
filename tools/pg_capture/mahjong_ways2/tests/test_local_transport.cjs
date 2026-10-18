// Exercise routing before the URL parser rejects the original numeric API host.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { clientRoot } = require('../layout.cjs');
const source = fs.readFileSync(require('node:path').join(clientRoot, 'local-auth-bootstrap.js'), 'utf8');
function context(mock = true) {
  const calls = [];
  class XHR { open(...args) { calls.push(args); } }
  const window = { fetch: (...args) => { calls.push(args); return Promise.resolve(); } };
  vm.runInNewContext(source, {
    URL, Request, URLSearchParams, XMLHttpRequest: XHR, window,
    location: { href: 'http://127.0.0.1:8080/?' + (mock ? 'mock=1' : ''), origin: 'http://127.0.0.1:8080' },
    history: { state: null, replaceState() {} }, setInterval() {}, console: { info() {} },
  });
  return { calls, XHR, window };
}
(async () => {
  const c = context();
  for (const input of [
    'https://api.0.0.1:8080/web-api/auth/session/v2/verifyOperatorPlayerSession',
    'https://api.example.com/game-api/74/v4/Spin?seq=1',
    '/web-api/game-proxy/v2/GameWallet/Get',
    'game-api/74/v4/Spin',
  ]) {
    new c.XHR().open('POST', input);
    const output = c.calls.at(-1)[1];
    assert.ok(output.startsWith('http://127.0.0.1:8080/'));
    assert.ok(/\/(web-api|game-api)\//.test(output));
  }
  const asset = 'https://static.example.com/shared/index.js';
  new c.XHR().open('GET', asset);
  assert.equal(c.calls.at(-1)[1], asset);
  await c.window.fetch('https://api.0.0.1:8080/game-api/74/v4/Spin');
  assert.equal(c.calls.at(-1)[0], 'http://127.0.0.1:8080/game-api/74/v4/Spin');
  const ordinary = context(false);
  new ordinary.XHR().open('POST', 'https://api.example.com/game-api/74/v4/Spin');
  assert.equal(ordinary.calls.at(-1)[1], 'https://api.example.com/game-api/74/v4/Spin');
  console.log('PG local transport: numeric host, API routing, query, assets, fetch and opt-in PASS');
})();
