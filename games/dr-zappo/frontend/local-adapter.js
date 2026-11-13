/* Integration only: original game, math display and UI bundles remain intact. */
(() => {
  'use strict';
  const launch = new URL(location.href);
  let ready = false;
  const timer = setInterval(() => {
    const channels = window.hacksawCasino?.PubSub;
    if (!channels || ready) return;
    ready = true;
    clearInterval(timer);
    const game = channels.getChannel('casino');
    let notified = false;
    const notifyReady = () => {
      if (!notified && parent !== window) parent.postMessage({ type: 'demo:ready' }, 'http://127.0.0.1:8080');
      notified = true;
    };
    game.subscribe('gameLoaded', notifyReady);
    game.subscribe('gameStarted', notifyReady);
  }, 50);
  // Preserve the request sequence across reloads of the same isolated account.
  const token = launch.searchParams.get('token');
  const key = token ? `dr-zappo-seq:${token}` : null;
  if (token) launch.searchParams.set('sessionuuid', token);
  if (key && sessionStorage.getItem(key)) {
    launch.searchParams.set('seq', String(Math.max(Number(launch.searchParams.get('seq') || 0), Number(sessionStorage.getItem(key)))));
  }
  history.replaceState(null, '', launch);
  const send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function (body) {
    if (key && typeof body === 'string') {
      try {
        const data = JSON.parse(body);
        if (Number.isInteger(data.seq)) sessionStorage.setItem(key, String(Math.max(data.seq, Number(sessionStorage.getItem(key) || 0))));
      } catch {}
    }
    return send.call(this, body);
  };
})();
