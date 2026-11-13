/* 等待修复版缓存策略接管后启动，正常资源仍使用原有缓存。 */
(async function startLocalGame() {
    try {
        if ('serviceWorker' in navigator) {
            const registration = await navigator.serviceWorker.register(
                '/shared/service-worker/sw.js', { scope: '/', updateViaCache: 'none' }
            );
            await registration.update();
            const worker = registration.installing || registration.waiting || registration.active;
            if (worker && worker.state !== 'activated') {
                await new Promise((resolve, reject) => {
                    /** 等待新版本激活，阻止旧缓存模块抢先执行。 */
                    function checkState() {
                        if (worker.state === 'activated' || worker.state === 'redundant') {
                            worker.removeEventListener('statechange', checkState);
                            if (worker.state === 'activated') resolve();
                            else reject(new Error('本地缓存修复版本未能激活，请刷新页面。'));
                        }
                    }
                    worker.addEventListener('statechange', checkState);
                    checkState();
                });
            }
        }
        const original = document.getElementById('main-script');
        const script = document.createElement('script');
        script.id = original.id;
        script.dataset.rev = original.dataset.rev;
        script.textContent = original.textContent;
        original.replaceWith(script);
    } catch (error) {
        console.error('本地启动失败：', error);
        const message = document.createElement('pre');
        message.textContent = '本地启动失败：' + error.message;
        document.body.appendChild(message);
    }
})();
