/* Route the original client to the isolated local generated-game service. */
(() => {
  'use strict';
  const launch = new URL(location.href);
  const token = launch.searchParams.get('ops') || 'local-demo-session';
  launch.searchParams.set('l', 'en');
  launch.searchParams.set('btt', '2');
  launch.searchParams.set('ot', 'local-demo');
  launch.searchParams.set('ops', token);
  // This older client requires the captured public API-host descriptor to initialize.
  // Actual API requests are always rewritten to this local preview service below.
  launch.searchParams.set('ao', '06gvo=l26dffi7i=ius');
  for (const key of ['t', 'tk', '__hv', '__sv', 'or']) launch.searchParams.delete(key);
  history.replaceState(history.state, '', launch);
  const notify = type => {
    if (parent === window) return;
    for (const origin of ['http://localhost:8080', 'http://127.0.0.1:8080']) {
      parent.postMessage({ type }, origin);
    }
  };
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
      this.setRequestHeader('X-Local-Game-Session', token);
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
    headers.set('X-Local-Game-Session', token);
    const destination = input instanceof Request ? new Request(localURL(source), input) : localURL(source);
    const response = await fetch.call(this, destination, { ...init, headers });
    if (url.pathname.endsWith('/GameInfo/Get')) notify(response.ok ? 'demo:ready' : 'demo:error');
    return response;
  };
})();
