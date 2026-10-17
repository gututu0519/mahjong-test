(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const { setText } = window.SpinLabI18n;
  const dialog = $('player'), overlay = $('player-overlay');
  let frame = $('game-frame');
  const launchButtons = [...document.querySelectorAll('[data-launch]')];
  let launchURL = null, requestController = null, readyTimer = null, requestVersion = 0;
  let opener = null, activeGame = 'mahjong-ways2', catalog = [];
  let activeFilter = 'all', activeProvider = 'all';
  const cards = [...document.querySelectorAll('.game-card')];

  function updateCatalogCounts() {
    document.querySelectorAll('[data-filter]').forEach(button => {
      const badge = button.querySelector('span');
      if (badge) badge.textContent = cards.filter(card => card.dataset.status === button.dataset.filter).length;
    });
    document.querySelectorAll('[data-provider-filter]').forEach(button => {
      const badge = button.querySelector('span');
      if (badge) badge.textContent = cards.filter(card => card.dataset.provider === button.dataset.providerFilter).length;
    });
  }

  function filterGames() {
    const query = $('game-search').value.trim().toLocaleLowerCase();
    let playable = 0, preview = 0, upcoming = 0;
    cards.forEach(card => {
      const visible = (activeFilter === 'all' || card.dataset.status === activeFilter)
        && (activeProvider === 'all' || card.dataset.provider === activeProvider)
        && card.dataset.name.toLocaleLowerCase().includes(query);
      card.hidden = !visible;
      if (visible) {
        if (card.dataset.status === 'playable') playable++;
        else if (card.dataset.status === 'preview') preview++;
        else upcoming++;
      }
    });
    $('result-count').textContent = window.SpinLabI18n.language === 'en'
      ? `${playable} playable · ${preview} UI preview` + (upcoming ? ` · ${upcoming} coming soon` : '')
      : `${playable} 款可试玩 · ${preview} 款界面预览` + (upcoming ? ` · ${upcoming} 个主题预告` : '');
    $('empty-results').hidden = playable + preview + upcoming > 0;
    document.querySelectorAll('[data-provider-filter]').forEach(button => {
      const selected = button.dataset.providerFilter === activeProvider;
      button.classList.toggle('selected', selected);
      button.setAttribute('aria-pressed', String(selected));
    });
    document.querySelectorAll('[data-filter]').forEach(button => {
      const selected = button.dataset.filter === activeFilter;
      button.classList.toggle('selected', selected);
      button.setAttribute('aria-pressed', String(selected));
    });
  }
  document.querySelectorAll('[data-provider-filter]').forEach(button => {
    button.addEventListener('click', () => { activeProvider = button.dataset.providerFilter; filterGames(); });
  });
  document.querySelectorAll('[data-filter]').forEach(button => {
    button.addEventListener('click', () => { activeFilter = button.dataset.filter; filterGames(); });
  });
  $('game-search').addEventListener('input', filterGames);
  $('reset-search').addEventListener('click', () => {
    activeFilter = 'all';
    activeProvider = 'all';
    $('game-search').value = '';
    filterGames();
    $('game-search').focus();
  });

  async function api(path, options = {}) {
    const response = await fetch(path, { cache: 'no-store', ...options });
    const data = await response.json();
    if (!response.ok || data.err) throw new Error(data.err?.msg || '服务暂时不可用');
    return data;
  }

  async function loadCatalog() {
    setText('service-status', '正在连接游戏服务…');
    $('service-status').classList.remove('online');
    $('catalog-error').hidden = true;
    launchButtons.forEach(button => button.disabled = true);
    $('retry-catalog').disabled = true;
    try {
      const data = await api('/api/v1/demo/games', { signal: AbortSignal.timeout(10000) });
      if (!data.games.some(game => game.id === 'mahjong-ways2')) throw new Error('游戏未上线');
      setText('service-status', '游戏服务在线');
      $('service-status').classList.add('online');
      catalog = data.games;
      updateAvailability();
    } catch {
      setText('service-status', '服务暂时不可用');
      $('catalog-error').hidden = false;
    } finally { $('retry-catalog').disabled = false; }
  }

  function updateAvailability() {
    launchButtons.forEach(button => {
      const available = catalog.find(game => game.id === button.dataset.launch)?.languages.includes(window.SpinLabI18n.language);
      button.disabled = !available;
    });
    setText('buffalo-note', window.SpinLabI18n.language === 'en' ? '英文试玩测试中' : '中文试玩已开放');
  }

  function updatePlayerCopy() {
    const buffalo = activeGame === 'buffalo-win';
    const olympus = activeGame === 'gates-of-olympus';
    const bass = activeGame === 'big-bass-bonanza';
    const sweet = activeGame === 'sweet-bonanza-pop';
    const ace = activeGame === 'super-ace';
    const moneyPot = activeGame === 'money-pot-deluxe';
    const wicked = activeGame === 'wicked-grin';
    const roma = activeGame === 'roma-x-10000';
    const vaults = activeGame === '3-billion-vaults';
    const joker = activeGame === 'jokers-fortune-winx';
    const gems = activeGame === 'fortune-gems2';
    setText('player-title', wicked ? 'Wicked Grin' : roma ? 'Roma X 10000' : moneyPot ? 'Money Pot DELUXE' : vaults ? '3 Billion Vaults' : joker ? "Joker’s Fortune WinX" : gems ? 'Fortune Gems 2' : ace ? 'Super Ace' : bass ? 'Big Bass Bonanza' : sweet ? 'Sweet Bonanza POP' : olympus ? 'Gates of Olympus' : buffalo ? '美洲野牛' : '麻将胡了 2');
    frame.title = wicked ? 'Wicked Grin' : roma ? 'Roma X 10000' : moneyPot ? 'Money Pot DELUXE' : vaults ? '3 Billion Vaults' : joker ? "Joker’s Fortune WinX" : gems ? 'Fortune Gems 2' : ace ? 'Super Ace' : bass ? 'Big Bass Bonanza' : sweet ? 'Sweet Bonanza POP' : olympus ? 'Gates of Olympus demo' : window.SpinLabI18n.t(buffalo ? '美洲野牛试玩' : '麻将胡了 2 试玩');
    setText('player-mode', '虚拟积分试玩');
  }

  function showError(title, detail) {
    clearTimeout(readyTimer);
    overlay.hidden = false;
    setText('overlay-title', title);
    setText('overlay-detail', detail);
    $('retry-game').hidden = false;
    setText('player-status', '连接未完成');
  }

  function loadFrame() {
    clearTimeout(readyTimer);
    resetFrame();
    overlay.hidden = true; // Let the game's own loading screen remain visible.
    frame.hidden = false;
    setText('player-status', '正在加载游戏资源…');
    frame.src = launchURL.href;
    readyTimer = setTimeout(() => showError('游戏加载时间较长', '请检查服务是否正常。可以重新载入游戏，或返回大厅稍后再试。'), 90000);
  }

  function resetFrame() {
    // Destroy the previous browsing context: the original client prevents navigation on unload.
    const next = frame.cloneNode(false);
    next.removeAttribute('src');
    next.hidden = true;
    frame.replaceWith(next);
    frame = next;
    updatePlayerCopy();
  }

  async function launch(gameId = activeGame) {
    activeGame = gameId;
    updatePlayerCopy();
    const version = ++requestVersion;
    requestController?.abort();
    requestController = new AbortController();
    clearTimeout(readyTimer);
    launchURL = null;
    resetFrame();
    overlay.hidden = false;
    setText('overlay-title', '正在开启游戏');
    setText('overlay-detail', '连接游戏服务，创建试玩会话…');
    $('retry-game').hidden = true;
    $('reload-game').disabled = true;
    setText('player-status', '正在准备试玩…');
    if (!dialog.open) { opener = document.activeElement; dialog.showModal(); }
    const timeout = setTimeout(() => requestController?.abort(), 15000);
    try {
      const data = await api(`/api/v1/games/${encodeURIComponent(activeGame)}/launch`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ language: window.SpinLabI18n.language }), signal: requestController.signal,
      });
      if (version !== requestVersion || !dialog.open) return;
      const url = new URL(data.launch_url, location.origin);
      const expectedOrigin = activeGame === 'wicked-grin' ? 'http://127.0.0.1:8095' : activeGame === 'roma-x-10000' ? 'http://127.0.0.1:8094' : activeGame === 'money-pot-deluxe' ? 'http://127.0.0.1:8093' : activeGame === '3-billion-vaults' ? 'http://127.0.0.1:8092' : activeGame === 'jokers-fortune-winx' ? 'http://127.0.0.1:8091' : activeGame === 'fortune-gems2' ? 'http://127.0.0.1:8089' : activeGame === 'super-ace' ? 'http://127.0.0.1:8088' : activeGame === 'big-bass-bonanza' ? 'http://127.0.0.1:8087' : activeGame === 'sweet-bonanza-pop' ? 'http://127.0.0.1:8086' : activeGame === 'gates-of-olympus' ? 'http://127.0.0.1:8085' : activeGame === 'buffalo-win' ? 'http://127.0.0.1:8083' : location.origin;
      if (url.origin !== expectedOrigin || url.pathname !== '/' || url.searchParams.get('mock') !== '1' || !url.searchParams.get('ops')) throw new Error('无效的游戏链接');
      launchURL = url;
      $('reload-game').disabled = false;
      loadFrame();
    } catch {
      if (version === requestVersion && dialog.open) showError('暂时无法开启试玩', '游戏服务未响应。请重试，或返回大厅稍后再来。');
    } finally { clearTimeout(timeout); }
  }

  window.addEventListener('message', event => {
    if (!dialog.open || !launchURL || event.origin !== launchURL.origin || event.source !== frame.contentWindow) return;
    if (event.data?.type === 'demo:ready') {
      clearTimeout(readyTimer);
      overlay.hidden = true;
      setText('player-status', '试玩已连接 · 独立虚拟积分');
    } else if (event.data?.type === 'demo:error') {
      showError('游戏连接已中断', '试玩会话可能已过期，请返回大厅重新开启试玩。');
    }
  });

  dialog.addEventListener('close', () => {
    ++requestVersion;
    requestController?.abort();
    clearTimeout(readyTimer);
    resetFrame();
    launchURL = null;
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    opener?.focus();
  });
  $('close-player').addEventListener('click', () => dialog.close());
  $('reload-game').addEventListener('click', () => { if (launchURL) loadFrame(); });
  $('retry-game').addEventListener('click', () => { if (launchURL) loadFrame(); else launch(); });
  $('retry-catalog').addEventListener('click', loadCatalog);
  $('fullscreen').hidden = !document.fullscreenEnabled;
  $('fullscreen').addEventListener('click', async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await $('player-shell').requestFullscreen();
    } catch { setText('player-status', '当前浏览器暂不支持全屏'); }
  });
  launchButtons.forEach(button => button.addEventListener('click', () => launch(button.dataset.launch)));
  window.addEventListener('spinlab:languagechange', () => { filterGames(); updateAvailability(); updatePlayerCopy(); });
  updateCatalogCounts();
  filterGames();
  loadCatalog();
})();
