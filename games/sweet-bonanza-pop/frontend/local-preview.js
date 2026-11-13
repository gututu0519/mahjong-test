/* Local client bootstrap and viewport selection. No remote sessions. */
(() => {
  'use strict';
  // Choose from the actual iframe viewport, including desktop side panels.
  const isPortrait = () => false; // Captured desktop build scales to the viewport until mobile assets arrive.
  const portrait = isPortrait();
  UHT_DEVICE_TYPE.MOBILE = portrait;
  UHT_DEVICE_TYPE.DESKTOP = !portrait;
  document.documentElement.id = portrait ? 'Mobile' : 'Desktop';
  document.documentElement.dataset.previewLayout = portrait ? 'portrait' : 'landscape';
  let sessionToken, resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      if (isPortrait() === portrait || !sessionToken) return;
      const url = new URL(location.href);
      url.searchParams.set('ops', sessionToken);
      // The two original bundles cannot coexist in one JS context.
      window.onbeforeunload = null;
      location.replace(url.href);
    }, 300);
  });
  const originalInit = Html5GameManager.init;
  Html5GameManager.init = function (options) {
    const config = JSON.parse(options.gameConfig);
    config.lang = 'en';
    config.demoMode = '0';
    options.gameConfig = JSON.stringify(config);
    sessionToken = config.mgckey;
    window.__LOCAL_GENERATED__ = config.localGenerated === true;
    const currentURL = new URL(location.href);
    currentURL.searchParams.set('ops', sessionToken);
    history.replaceState(null, '', currentURL.href);
    originalInit(options);
    const adapter = window.sendToAdapter;
    window.sendToAdapter = function (message) {
      try {
        const event = JSON.parse(message);
        if (event.common === 'EVT_GAME_LOAD_COMPLITED') {
          document.documentElement.dataset.previewReady = 'true';
          for (const origin of ['http://127.0.0.1:8080', 'http://localhost:8080', 'http://127.0.0.1:8081', 'http://localhost:8081']) {
            parent.postMessage({ type: 'demo:ready', mode: window.__LOCAL_GENERATED__ ? 'generated' : 'frontend-preview' }, origin);
          }
        }
      } catch (_) { /* Original adapter handles malformed messages. */ }
      return adapter(message);
    };
  };
})();
