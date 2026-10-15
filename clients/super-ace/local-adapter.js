/* Local protocol boundary. Original Cocos UI and animation code remain intact. */
(() => {
  'use strict';
  const params = new URLSearchParams(location.search);
  const token = params.get('ops');
  const nativeFetch = window.fetch.bind(window);
  let queue = Promise.resolve();
  async function api(path, body) {
    const response = await nativeFetch(path, {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({token, ...body})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || result.error || 'Request failed');
    return result;
  }
  function command(ack, bytes) {
    const key = crypto.randomUUID();
    const body = {ack, payload:Array.from(bytes || []), key};
    // Retry the same logical request with the same idempotency key after a lost response.
    const run = () => api('/jili/command', body).catch(error => {
      if (error instanceof TypeError) return api('/jili/command', body);
      throw error;
    });
    const next = queue.then(run, run);
    queue = next.catch(() => {});
    return next;
  }
  let system;
  function install(value) {
    system = value;
    if (!system?.register || system.__localAdapter) return;
    system.__localAdapter = true;
    const original = system.register;
    system.register = function (...args) {
      const name = args[0], factory = args.pop();
      if (typeof name !== 'string' || !name.includes('WASM-')) return original.apply(this, [...args, factory]);
      // SystemJS checks factory.length before supplying the context argument.
      args.push(function (publish, context) {
        const adapt = (key, value) => {
          const exports = typeof key === 'object' ? {...key} : {[key]:value};
          if ('W' in exports) exports.W = () => api('/jili/login', {});
          if ('c' in exports) exports.c = command;
          if ('b' in exports) exports.b = (path, data) => api('/jili/custom', {path, payload:Array.from(data || [])});
          return typeof key === 'object' ? publish(exports) : publish(key, exports[key]);
        };
        return factory(adapt, context);
      });
      return original.apply(this, args);
    };
  }
  window.installSuperAceAdapter = () => install(window.System);
  function localURL(input) {
    const url = new URL(String(input), location.href);
    if (!/^https?:$/.test(url.protocol) || url.origin === location.origin) return url.href;
    if (/history/.test(url.hostname)) return location.origin + (/intro/.test(url.pathname) ? '/rules' : '/history') + '?ops=' + encodeURIComponent(token);
    return location.origin + url.pathname + url.search;
  }
  window.fetch = (input, init) => nativeFetch(typeof input === 'string' || input instanceof URL ? localURL(input) : input, init);
  const open = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url, ...rest) { return open.call(this, method, localURL(url), ...rest); };
  for (const type of [HTMLScriptElement, HTMLImageElement, HTMLIFrameElement]) {
    const descriptor = Object.getOwnPropertyDescriptor(type.prototype, 'src');
    Object.defineProperty(type.prototype, 'src', {...descriptor, set(value) { descriptor.set.call(this, localURL(value)); }});
  }
  const popup = window.open;
  window.open = function(url, ...rest) { return popup.call(this, localURL(url), ...rest); };

})();

