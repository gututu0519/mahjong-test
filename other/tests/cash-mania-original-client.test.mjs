import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { createContext, runInContext, Script } from 'node:vm';

const root = fileURLToPath(new URL('../../', import.meta.url));
const frontend = resolve(root, 'games/cash-mania/frontend');
const bootstrap = readFileSync(resolve(frontend, 'local-bootstrap.js'), 'utf8');
const imageMap = JSON.parse(readFileSync(resolve(frontend, 'fixtures/image-map.json'), 'utf8'));
const resourceIndex = JSON.parse(readFileSync(resolve(frontend, 'fixtures/resource-index.json'), 'utf8'));

// 实际执行入口适配脚本。只替换浏览器 I/O，不替换被测 URL 或会话处理逻辑。
function browser({ merchant, fetchEnabled = true, origin = 'http://127.0.0.1:18103', query = '?ops=original-client-test&mock=1' } = {}) {
  let current = new URL('/1682240/index.html' + query, origin);
  const navigations = [], replacements = [], fetched = [];
  const location = {
    get href() { return current.href; },
    set href(value) { navigations.push(String(value)); current = new URL(value, current); },
    get origin() { return current.origin; },
    get pathname() { return current.pathname; },
    get search() { return current.search; },
    get hostname() { return current.hostname; },
    replace(value) { navigations.push(String(value)); current = new URL(value, current); },
    assign(value) { navigations.push(String(value)); current = new URL(value, current); },
  };
  class Element {
    constructor() { this.attributes = {}; }
    setAttribute(name, value) { this.attributes[String(name)] = String(value); }
    getAttribute(name) { return this.attributes[String(name)] ?? null; }
  }
  function elementWithProperty(name) {
    const ctor = class extends Element {};
    Object.defineProperty(ctor.prototype, name, {
      configurable: true,
      enumerable: true,
      get() { return this.attributes[name] ?? ''; },
      set(value) { this.attributes[name] = String(value); },
    });
    return ctor;
  }
  class XMLHttpRequest {
    constructor() { this.headers = {}; this.listeners = {}; this.status = 200; }
    open(...args) { this.openArguments = args; }
    setRequestHeader(name, value) { this.headers[String(name).toLowerCase()] = String(value); }
    addEventListener(name, callback) { this.listeners[name] = callback; }
    send(body) { this.body = body; }
  }
  const context = createContext({
    URL, Request, Headers, Element, XMLHttpRequest,
    HTMLImageElement: elementWithProperty('src'),
    HTMLScriptElement: elementWithProperty('src'),
    HTMLLinkElement: elementWithProperty('href'),
    HTMLSourceElement: elementWithProperty('src'),
    location,
    history: {
      state: null,
      replaceState(_state, _title, url) { replacements.push(String(url)); current = new URL(url, current); },
    },
    ...(merchant ? { __GTT_MERCHANT__: merchant } : {}),
    ...(fetchEnabled ? { fetch(input, init) { fetched.push({ input, init }); return Promise.resolve({ ok: true, status: 200 }); } } : {}),
  });
  context.window = context;
  context.parent = context;
  runInContext(bootstrap, context, { timeout: 2000, filename: 'cash-mania/local-bootstrap.js' });
  return { context, location, navigations, replacements, fetched };
}

test('Cash Mania 原版入口：默认打开 index，执行适配后保持原页面且不重复安装', () => {
  const b = browser();
  assert.equal(b.location.pathname, '/1682240/index.html');
  assert.deepEqual(b.navigations, [], '适配不能导航到自制盘面或其他页面');
  assert.equal(b.replacements.length, 1);
  const launch = new URL(b.location.href);
  assert.equal(launch.searchParams.get('ops'), 'original-client-test');
  assert.equal(launch.searchParams.get('btt'), '2');
  const open = b.context.XMLHttpRequest.prototype.open;
  runInContext(bootstrap, b.context, { timeout: 2000 });
  assert.equal(b.context.XMLHttpRequest.prototype.open, open);
  assert.equal(b.replacements.length, 1);
  assert.deepEqual(b.navigations, []);
});

test('Cash Mania 原版入口：缺少或携带旧 or 的链接均向当前主机及端口加载共享模块', () => {
  const query = '?mock=1&l=en&btt=2&ot=local-demo&ops=local-demo-session&ao=06gvo%3Dl26dffi7i%3Dius';
  for (const [origin, tail, descriptor] of [
    ['http://127.0.0.1:18103', '', '00127=0=0=1:18103'],
    ['http://g20.localhost:8110', '&or=05x5%3Drrlf1%3Dhtr', '00g20=localhost:8110'],
  ]) {
    const b = browser({ origin, query: query + tail });
    const launch = new URL(b.location.href);
    assert.equal(launch.searchParams.get('or'), descriptor);
    assert.equal(launch.searchParams.get('ops'), 'local-demo-session');
    assert.deepEqual(b.navigations, []);
  }
});

test('Cash Mania 原版入口：商户会话保留原页面，XHR 业务请求走本地并注入会话', () => {
  const b = browser({ merchant: { token: 'merchant-original-client-test', operator: 'test-operator' } });
  assert.equal(b.location.pathname, '/1682240/index.html');
  assert.deepEqual(b.navigations, []);
  const launch = new URL(b.location.href);
  assert.equal(launch.searchParams.get('btt'), '1');
  assert.equal(launch.searchParams.get('ops'), 'merchant-original-client-test');
  assert.equal(launch.searchParams.has('mock'), false);
  for (const path of ['/game-api/cash-mania/v4/Spin', '/game-api/cash-mania/v4/GameInfo/Get', '/web-api/game-proxy/v2/GameWallet/Get']) {
    const xhr = new b.context.XMLHttpRequest();
    const payload = new Uint8Array([1, 7, 23]);
    xhr.open('POST', 'https://api.mmga1.com' + path + '?test=1', true);
    xhr.send(payload);
    assert.equal(xhr.openArguments[1], b.location.origin + path + '?test=1');
    assert.equal(xhr.headers['x-local-game-session'], 'merchant-original-client-test');
    assert.equal(xhr.body, payload, '二进制业务请求体不得被修改');
  }
  const unrelated = new b.context.XMLHttpRequest();
  unrelated.open('GET', 'https://example.invalid/resource.json', true);
  unrelated.send(null);
  assert.equal(unrelated.openArguments[1], 'https://example.invalid/resource.json');
  assert.equal(unrelated.headers['x-local-game-session'], undefined);
});

test('Cash Mania 原版入口：fetch 字符串和 Request 保留方法与头部，并注入本地会话', async () => {
  const b = browser();
  await b.context.fetch('https://api.mmga1.com/game-api/cash-mania/v4/Spin', {
    method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: new Uint8Array([2, 3]),
  });
  assert.equal(b.fetched[0].input, b.location.origin + '/game-api/cash-mania/v4/Spin');
  assert.equal(b.fetched[0].init.method, 'POST');
  assert.equal(b.fetched[0].init.headers.get('x-local-game-session'), 'original-client-test');
  assert.equal(b.fetched[0].init.headers.get('content-type'), 'application/octet-stream');
  const request = new Request('https://api.mmga1.com/game-api/cash-mania/v4/GameInfo/Get', { headers: { 'X-Test': 'kept' } });
  await b.context.fetch(request);
  assert.equal(b.fetched[1].input.url, b.location.origin + '/game-api/cash-mania/v4/GameInfo/Get');
  assert.equal(b.fetched[1].init.headers.get('x-test'), 'kept');
  assert.equal(b.fetched[1].init.headers.get('x-local-game-session'), 'original-client-test');
});

test('Cash Mania 原版入口：没有 fetch 时 XHR 降级仍可访问同一本地协议', () => {
  const b = browser({ fetchEnabled: false });
  assert.equal(b.context.fetch, undefined);
  const xhr = new b.context.XMLHttpRequest();
  xhr.open('POST', '/game-api/cash-mania/v4/Spin', true);
  xhr.send('request');
  assert.equal(xhr.openArguments[1], b.location.origin + '/game-api/cash-mania/v4/Spin');
  assert.equal(xhr.headers['x-local-game-session'], 'original-client-test');
  assert.deepEqual(b.navigations, []);
});

test('Cash Mania 原版素材：全部旧图片地址映射到存在的 Adam7 PNG，保留查询参数与片段', () => {
  const b = browser();
  assert.ok(Object.keys(imageMap).length > 0);
  assert.deepEqual(JSON.parse(JSON.stringify(b.context.__CASH_MANIA_IMAGE_MAP__)), imageMap);
  for (const [original, mapped] of Object.entries(imageMap)) {
    const bytes = readFileSync(resolve(frontend, '.' + mapped));
    assert.deepEqual(bytes.subarray(0, 8), Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), mapped);
    assert.equal(bytes.toString('ascii', 12, 16), 'IHDR');
    assert.equal(bytes[28], 1, mapped + ' 必须使用 Adam7 编码');
    const image = new b.context.HTMLImageElement();
    image.src = 'https://s5.mmga1.com' + original + '?v=1#sprite';
    assert.equal(image.src, b.location.origin + mapped + '?v=1#sprite');
    const other = new b.context.HTMLImageElement();
    other.setAttribute('src', original);
    assert.equal(other.getAttribute('src'), b.location.origin + mapped);
  }
  const image = new b.context.HTMLImageElement();
  image.src = 'data:image/png;base64,dGVzdA==';
  assert.equal(image.src, 'data:image/png;base64,dGVzdA==');
  const script = new b.context.HTMLScriptElement();
  script.src = 'https://s5.mmga1.com/1682240/assets/main/index.8cd01.js';
  assert.equal(script.src, b.location.origin + '/1682240/assets/main/index.8cd01.js');
});

test('Cash Mania 原版资源入口：保留抓取主脚本与资源清单，不引入自制盘面入口', () => {
  const allowed = new Set(resourceIndex.resources.map(item => item.path));
  ['local-bootstrap.js', 'local-frame-clock.js', 'fixtures/resource-index.json', 'fixtures/image-map.json', 'fixtures/image-conversion-report.json'].forEach(path => allowed.add(path));
  const files = readdirSync(frontend, { recursive: true, withFileTypes: true }).filter(entry => entry.isFile());
  for (const file of files) {
    const path = resolve(file.parentPath, file.name).slice(frontend.length + 1).replace(/\\/g, '/');
    assert.ok(allowed.has(path), path + ' 不在抓取资源或必要适配清单中');
  }
  const html = readFileSync(resolve(frontend, resourceIndex.entry), 'utf8');
  assert.equal(resourceIndex.game, 'cash-mania');
  assert.equal(resourceIndex.entry, '1682240/index.html');
  assert.doesNotMatch(html + bootstrap, /\b(?:play|capture-stage)\.(?:html|js|css)\b/);
  const scripts = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)];
  const main = scripts.filter(match => /\bid=["']main-script["']/.test(match[1]));
  assert.equal(main.length, 1);
  assert.doesNotThrow(() => new Script(main[0][2], { filename: 'cash-mania-original-main' }));
  const originalModules = [
    '1682240/assets/main/index.8cd01.js', '1682240/assets/main/config.baf4f.json',
    '1682240/assets/resources/index.b994a.js', '1682240/assets/resources/config.d8d53.json',
  ];
  for (const path of originalModules) {
    const record = resourceIndex.resources.find(item => item.path === path);
    assert.ok(record, path + ' 必须有抓取来源记录');
    assert.ok(Number.isSafeInteger(record.request) && record.request > 0);
    assert.ok(['s5.mmga1.com', 'static5.mmga1.com'].includes(new URL(record.source).hostname));
    const bytes = readFileSync(resolve(frontend, path));
    assert.equal(createHash('sha256').update(bytes).digest('hex'), record.sha256, path + ' 应符合已记录的导入资源摘要');
    if (path.endsWith('.js')) assert.doesNotMatch(bytes.toString('utf8'), /\b(?:play|capture-stage)\.(?:html|js|css)\b/);
  }
});

test('Cash Mania 原版菜单：赔付表、规则及单局历史详情的依赖均有抓取正文', () => {
  const read = path => {
    const item = resourceIndex.resources.find(item => item.path === path);
    const bytes = readFileSync(resolve(frontend, path));
    assert.ok(item?.source_size > 0 && bytes.length > 0, path + ' 需要完整的抓取正文');
    assert.equal(createHash('sha256').update(bytes).digest('hex'), item.sha256);
    if (path.endsWith('.png')) {
      assert.deepEqual(bytes.subarray(0, 8), Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]));
      assert.equal(bytes[28], 1);
    } else assert.equal(item.sha256, item.source_sha256);
    return bytes;
  };
  assert.ok(JSON.parse(read('1682240/ed9449d6ad.166f1.json')).data.some(row => row.segment_id === 'symbol_payout'));
  assert.ok(JSON.parse(read('1682240/2a92004b4e.28b0b.json')).rules.length > 0);
  assert.ok(JSON.parse(read('1682240/60677c52da.42475.json')).CashManiaRule);
  read('shared/4528468aab/bd94233190.9c045.png');
  read('1682240/a97442bc64.084ff.png');
  read('1682240/b66b2f5498.0b6a5.png');
  read('1682240/history/index.json');
  read('1682240/b3e98640be.bd729.js');
  read('1682240/d781f2b636.53679.json');
  for (const image of ['f2e7d71fc6.e2d23', '8dfb2c52ba.bfd59', '766be34028.7c9b4', 'ad342b85a5.7b6ca']) {
    read('1682240/' + image + '.png');
  }
});
