/* Local UI preview only. No remote sessions or spin results. */
(() => {
  'use strict';
  const originalInit = Html5GameManager.init;
  Html5GameManager.init = function (options) {
    originalInit(options);
    const adapter = window.sendToAdapter;
    window.sendToAdapter = function (message) {
      try {
        const event = JSON.parse(message);
        if (event.common === 'EVT_GAME_LOAD_COMPLITED') {
          document.documentElement.dataset.previewReady = 'true';
          for (const origin of ['http://127.0.0.1:8080', 'http://localhost:8080']) {
            parent.postMessage({ type: 'demo:ready', mode: 'frontend-preview' }, origin);
          }
        }
      } catch (_) { /* Original adapter handles malformed messages. */ }
      return adapter(message);
    };
  };
  document.addEventListener('DOMContentLoaded', () => {
    const note = document.createElement('div');
    note.id = 'local-preview-note';
    note.style.cssText = 'position:fixed;top:8px;left:50%;transform:translateX(-50%);z-index:2147483647;background:#201730ed;color:#f5db9b;border:1px solid #a68a55;border-radius:7px;padding:7px 14px;font:12px/1.4 Arial,sans-serif;max-width:calc(100vw - 40px);text-align:center;pointer-events:none';
    note.textContent = '界面预览 · 英文资源 · 旋转暂未接入 / UI preview · Spins unavailable';
    document.body.appendChild(note);
  });
})();
