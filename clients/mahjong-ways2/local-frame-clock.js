/* Keep the local demo responsive when an embedded browser throttles visible rAF. */
(function () {
    'use strict';
    if (new URL(location.href).searchParams.get('mock') !== '1') return;
    const request = window.requestAnimationFrame.bind(window);
    const cancel = window.cancelAnimationFrame.bind(window);
    const pending = new Map();
    window.requestAnimationFrame = function (callback) {
        let id, timer;
        function complete(timestamp, fallback) {
            if (!pending.delete(id)) return;
            clearTimeout(timer);
            if (fallback) {
                cancel(id);
                document.documentElement.dataset.localFrameFallback = 'active';
            }
            callback(timestamp);
        }
        id = request(timestamp => complete(timestamp, false));
        // Healthy browsers use native rAF. A visible, throttled WebView gets
        // a ~30 fps fallback; hidden tabs retain the browser's normal throttling.
        timer = setTimeout(() => {
            if (!document.hidden) complete(performance.now(), true);
        }, 34);
        pending.set(id, timer);
        return id;
    };
    window.cancelAnimationFrame = function (id) {
        if (pending.has(id)) {
            clearTimeout(pending.get(id));
            pending.delete(id);
        }
        cancel(id);
    };
})();
