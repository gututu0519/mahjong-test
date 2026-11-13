/* Local frontend preview: asset rendering and menus, without wagering or settlement. */
(() => {
  'use strict';
  const launch = new URL(location.href);
  const token = launch.searchParams.get('ops') || 'local-preview-session';
  const english = launch.searchParams.get('l') === 'en';
  launch.searchParams.set('btt', '2');
  launch.searchParams.set('ot', 'local-demo');
  launch.searchParams.set('ops', token);
  // This older client requires the captured public API-host descriptor to initialize.
  // Actual API requests are always rewritten to this local preview service below.
  launch.searchParams.set('ao', '02crk=keizbb3gn=eqo');
  for (const key of ['t', 'tk', '__hv', '__sv', 'or']) launch.searchParams.delete(key);
  history.replaceState(history.state, '', launch);
  const notify = type => {
    if (parent === window) return;
    for (const origin of ['http://localhost:8080', 'http://127.0.0.1:8080']) {
      parent.postMessage({ type }, origin);
    }
  };
  let messageTimer;
  function previewMessage() {
    let message = document.getElementById('preview-message');
    if (!message) {
      message = document.createElement('div');
      message.id = 'preview-message';
      message.setAttribute('role', 'status');
      message.style.cssText = 'position:fixed;bottom:18%;left:50%;transform:translateX(-50%);z-index:100001;padding:14px 20px;border-radius:8px;background:#16111def;color:white;font:14px/1.6 sans-serif;text-align:center;max-width:85vw;pointer-events:none';
      document.body.appendChild(message);
    }
    message.textContent = english ? 'Frontend preview only. Spin gameplay will be connected next.' : '当前为界面预览，旋转玩法将在后续接入。';
    message.hidden = false;
    clearTimeout(messageTimer);
    messageTimer = setTimeout(() => { message.hidden = true; }, 4000);
  }
  function localURL(input) {
    const url = new URL(input, location.href);
    return /^\/(web-api|game-api)\//.test(url.pathname) ? location.origin + url.pathname + url.search : input;
  }
  const open = XMLHttpRequest.prototype.open;
  const send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, input, ...args) {
    const url = new URL(input, location.href);
    this.localAPI = /^\/(web-api|game-api)\//.test(url.pathname);
    this.localPath = url.pathname;
    return open.call(this, method, localURL(input), ...args);
  };
  XMLHttpRequest.prototype.send = function (body) {
    if (this.localAPI) {
      this.setRequestHeader('X-Local-Preview-Session', token);
      if (this.localPath.endsWith('/Spin')) previewMessage();
      if (this.localPath.endsWith('/GameInfo/Get')) this.addEventListener('load', () => {
        notify(this.status === 200 ? 'demo:ready' : 'demo:error');
      }, { once: true });
    }
    return send.call(this, body);
  };
  const fetch = window.fetch;
  window.fetch = async function (input, init) {
    const source = input instanceof Request ? input.url : String(input);
    const url = new URL(source, location.href);
    if (!/^\/(web-api|game-api)\//.test(url.pathname)) return fetch.call(this, input, init);
    const headers = new Headers(init?.headers || (input instanceof Request ? input.headers : undefined));
    headers.set('X-Local-Preview-Session', token);
    if (url.pathname.endsWith('/Spin')) previewMessage();
    const destination = input instanceof Request ? new Request(localURL(source), input) : localURL(source);
    const response = await fetch.call(this, destination, { ...init, headers });
    if (url.pathname.endsWith('/GameInfo/Get')) notify(response.ok ? 'demo:ready' : 'demo:error');
    return response;
  };
})();
