/* Local protocol boundary. Original Cocos UI and animation code remain intact. */
(() => {
  'use strict';
  const params = new URLSearchParams(location.search);
  const token = params.get('ops');
  const NativeURL = window.URL;
  const nativeFetch = window.fetch.bind(window);
  // This client waits for the authenticated life-service connection before
  // starting game login. Keep the real WebSocket events and original callback.
  const NativeWebSocket = window.WebSocket;
  window.WebSocket = new Proxy(NativeWebSocket, {
    construct(target, args) {
      const url = new NativeURL(String(args[0]), location.href);
      if (url.pathname === '/lifeservice/ws2') {
        args[0] = `ws://${location.host}/lifeservice/ws2`;
      }
      return Reflect.construct(target, args);
    }
  });
  let queue = Promise.resolve();
  async function api(path, body) {
    const response = await nativeFetch(path, {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({token, ...body})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || result.error || 'Request failed');
    if (path === '/tada/command' && body.ack === 1) window.__localInfoReady = true;
    return result;
  }
  function command(ack, bytes) {
    const key = crypto.randomUUID();
    const body = {ack, payload:Array.from(bytes || []), key};
    // Retry the same logical request with the same idempotency key after a lost response.
    const run = () => api('/tada/command', body).catch(error => {
      if (error instanceof TypeError) return api('/tada/command', body);
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
          if ('W' in exports) exports.W = () => api('/tada/login', {});
          if ('c' in exports) exports.c = command;
          if ('b' in exports) exports.b = (path, data) => api('/tada/custom', {path, payload:Array.from(data || [])});
          return typeof key === 'object' ? publish(exports) : publish(key, exports[key]);
        };
        return factory(adapt, context);
      });
      return original.apply(this, args);
    };
  }
  window.installJokersFortuneWinXAdapter = () => install(window.System);
  function historyURL(input) {
    const value = String(input);
    // The UI also constructs URL objects for postMessage before setting iframe
    // src. Map at that boundary too, including its invalid IP-derived hostname.
    if (!/^https?:\/\/[^/]*history\.[^/]+(?:\/|$)/i.test(value)) return input;
    return location.origin + (/\/intro(?:[/?]|$)/.test(value) ? '/rules' : '/history') + '?ops=' + encodeURIComponent(token);
  }
  window.URL = new Proxy(NativeURL, {
    construct(target, args) {
      args[0] = historyURL(args[0]);
      return Reflect.construct(target, args);
    }
  });
  function localURL(input) {
    const url = new URL(String(input), location.href);
    // The client's connection probe reloads the launch path without its query.
    if (url.host === location.host && url.pathname === '/sss-jf2/' && !url.searchParams.has('ops')) {
      url.searchParams.set('ops', token);
    }
    if (!/^https?:$/.test(url.protocol) || url.origin === location.origin) return url.href;
    return location.origin + url.pathname + url.search;
  }
  window.fetch = (input, init) => nativeFetch(input instanceof Request ? new Request(localURL(input.url), input) : localURL(input), init);
  const open = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url, ...rest) { return open.call(this, method, localURL(url), ...rest); };
  for (const type of [HTMLScriptElement, HTMLImageElement, HTMLIFrameElement]) {
    const descriptor = Object.getOwnPropertyDescriptor(type.prototype, 'src');
    Object.defineProperty(type.prototype, 'src', {...descriptor, set(value) { descriptor.set.call(this, localURL(value)); }});
  }
  const popup = window.open;
  window.open = function(url, ...rest) { return popup.call(this, url ? localURL(url) : url, ...rest); };

  // Cocos writes @font-face rules into style.textContent, bypassing fetch/XHR.
  const textContent = Object.getOwnPropertyDescriptor(Node.prototype, 'textContent');
  Object.defineProperty(HTMLStyleElement.prototype, 'textContent', {
    configurable: true,
    get() { return textContent.get.call(this); },
    set(value) {
      const css = String(value).replace(/url\((['"]?)(.*?)\1\)/g, (_, quote, url) => `url("${localURL(url)}")`);
      textContent.set.call(this, css);
    }
  });

  const readyTimer = setInterval(() => {
    if (!window.__localInfoReady) return;
    const scene = window.cc?.director?.getScene();
    if (!scene) return;
    const visibleStart = node => (['Btn_Playing', 'Btn_Loading'].includes(node.name) && node.activeInHierarchy
      && Math.abs(node.worldScale.x) > 0.1 && Math.abs(node.worldScale.y) > 0.1
      && node.getComponent(window.cc.Button)?.interactable
      && node.getComponentsInChildren(window.cc.Label).some(label => /continue/i.test(label.string)))
      || node.children.some(visibleStart);
    const game = scene.getComponentsInChildren('GameView')[0];
    if (!visibleStart(scene) && !(game?.node.activeInHierarchy
      && game.IsLockRotation === false && scene.getComponentsInChildren(window.cc.Button).some(button => button.node.name === 'btn_spin' && button.node.activeInHierarchy && button.interactable))) return;
    clearInterval(readyTimer);
    if (window.parent !== window) window.parent.postMessage({type: 'demo:ready'}, 'http://127.0.0.1:8080');
  }, 100);
})();
