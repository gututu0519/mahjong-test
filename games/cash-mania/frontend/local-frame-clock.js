/* 本地可见 WebView 被限帧时使用定时回退；正常浏览器仍使用原生帧回调。 */
(function () {
  'use strict';
  if (!window.__GTT_MERCHANT__ && new URL(location.href).searchParams.get('mock') !== '1') return;
  if (!window.requestAnimationFrame || !window.cancelAnimationFrame) return;
  var request = window.requestAnimationFrame.bind(window);
  var cancel = window.cancelAnimationFrame.bind(window);
  var pending = {};
  function now() { return window.performance && performance.now ? performance.now() : Date.now(); }
  window.requestAnimationFrame = function (callback) {
    var id, timer;
    function complete(timestamp, fallback) {
      if (!Object.prototype.hasOwnProperty.call(pending, id)) return;
      delete pending[id];
      clearTimeout(timer);
      if (fallback) cancel(id);
      callback(timestamp);
    }
    id = request(function (timestamp) { complete(timestamp, false); });
    timer = setTimeout(function () {
      if (!document.hidden) complete(now(), true);
    }, 34);
    pending[id] = timer;
    return id;
  };
  window.cancelAnimationFrame = function (id) {
    if (Object.prototype.hasOwnProperty.call(pending, id)) {
      clearTimeout(pending[id]);
      delete pending[id];
    }
    cancel(id);
  };
})();
