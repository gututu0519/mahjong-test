/* Opt-in mock transport. The original login plugin still constructs and decodes requests. */
(function () {
    'use strict';
    const launch = new URL(location.href);
    if (launch.searchParams.get('mock') !== '1') return;
    launch.searchParams.set('btt', '1');
    launch.searchParams.set('ot', 'local-demo');
    launch.searchParams.set('ops', 'local-demo-session');
    // Do not carry a real game's session or signed launch settings into a mock session.
    for (const key of ['t', 'tk', 'ao', '__hv', '__sv']) launch.searchParams.delete(key);
    history.replaceState(history.state, '', launch);
    function localURL(input) {
        const url = new URL(input, location.href);
        if (/^\/(web-api|game-api)\//.test(url.pathname)) {
            return location.origin + url.pathname + url.search;
        }
        return input;
    }
    const open = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function (method, url, ...args) {
        return open.call(this, method, localURL(url), ...args);
    };
    const fetch = window.fetch;
    window.fetch = function (input, init) {
        const url = input instanceof Request ? input.url : String(input);
        const destination = localURL(url);
        return fetch.call(this, input instanceof Request && destination !== url
            ? new Request(destination, input) : destination === url ? input : destination, init);
    };
    // This client revision reads binary GameInfo; the supplied capture is JSON.
    // Feed that capture through its existing model/event pipeline in mock mode.
    function encodeThresholds(thresholds) {
        // Verified against this client's WinThresholds protobuf descriptor:
        // mw=1, bw=2, mgw=3, smgw=4; each is a little-endian fixed64 double.
        const bytes = new Uint8Array(36);
        const view = new DataView(bytes.buffer);
        ['mw', 'bw', 'mgw', 'smgw'].forEach((key, i) => {
            if (!Number.isFinite(thresholds[key])) throw new Error('Invalid threshold: ' + key);
            bytes[i * 9] = ((i + 1) << 3) | 1;
            view.setFloat64(i * 9 + 1, thresholds[key], true);
        });
        return bytes;
    }
    const install = setInterval(() => {
        const framework = window.System && System.get(location.origin + '/shared/b4d9192613/321ac46ae6.186bf.js');
        if (!framework || !framework.APIClient) return;
        clearInterval(install);
        framework.APIClient.prototype.getGameInfo = function (callback) {
            const controller = new AbortController();
            window.fetch('/game-api/74/v4/GameInfo/Get', {
                method: 'POST', signal: controller.signal,
                body: new URLSearchParams({ atk: 'local-demo-session', btt: '1', pf: '1' }),
            }).then(async response => {
                const data = await response.json();
                if (!response.ok || data.err) throw new Error(data.err?.msg || 'Local GameInfo failed');
                const common = { ...data.dt, wt: encodeThresholds(data.dt.wt) };
                let spin = data.dt.ls.si;
                if (data.localSpin) {
                    const raw = Uint8Array.from(atob(data.localSpin), c => c.charCodeAt(0));
                    spin = {
                        ...this.dataSource.transactionModel.deserializerTransactionInfo(raw),
                        ...this.dataSource.playerModel.deserializerWalletInfo(raw),
                    };
                }
                this.dataSource.overwriteGameInfo(common, spin);
                return this.dataSource.lastGameInfoRawData;
            }).then(data => { if (!controller.signal.aborted && callback) callback(undefined, data); }, error => {
                if (!controller.signal.aborted && callback) callback(error);
            });
            return () => controller.abort();
        };
    }, 5);
    const badge = document.createElement('div');
    badge.textContent = '本地样本回放 · 模拟余额';
    badge.setAttribute('role', 'note');
    badge.style.cssText = 'position:fixed;left:8px;top:8px;z-index:10000;padding:4px 8px;border-radius:6px;background:#0009;color:white;font:12px sans-serif;pointer-events:none';
    document.body.appendChild(badge);
    console.info('Local mock login enabled; the original client and rendering are unchanged.');
})();
