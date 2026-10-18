/* Local account integration; original bundles and all game entries stay intact. */
(() => {
  const params = new URL(location.href);
  const token = window.localTowerOps;
  params.searchParams.set('ops', token);
  history.replaceState(null, '', params);
  const key = `tower-seq:${token}`;
  const anchor = Math.max(window.localTowerSequence || 0, Number(sessionStorage.getItem(key) || 0));
  const originalSend = XMLHttpRequest.prototype.send;
  const originalOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url, ...args) {
    const target = new URL(url, location.href);
    if (target.origin === location.origin && target.pathname.startsWith('/configuration/')) {
      target.searchParams.set('ops', token);
      url = target.href;
    }
    return originalOpen.call(this, method, url, ...args);
  };
  XMLHttpRequest.prototype.send = function (body) {
    if (typeof body === 'string' && body.startsWith('d=')) {
      const form = new URLSearchParams(body);
      const packet = form.get('d');
      if (packet && /^\d+\r?\n/.test(packet)) {
        const sequence = Number(packet.match(/^\d+/)[0]) + anchor;
        const lines = packet.replace(/^\d+/, String(sequence)).split(/\r?\n/);
        lines[1] = token;
        form.set('d', lines.join('\r\n'));
        sessionStorage.setItem(key, String(Math.max(sequence, Number(sessionStorage.getItem(key) || 0))));
        body = form.toString();
      }
    }
    return originalSend.call(this, body);
  };
  let notified = false;
  const ready = () => {
    if (!notified && parent !== window) parent.postMessage({type:'demo:ready'}, 'http://127.0.0.1:8080');
    notified = true;
  };
  window.addEventListener('load', ready, {once:true});
})();
