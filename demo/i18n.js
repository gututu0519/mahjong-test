/* Shared UI copy and persisted locale. Game language is supplied by the launch API. */
(() => {
  'use strict';
  const english = {
    '英文试玩已开放': 'English demo available',
    '游戏厂商': 'Game provider',
    '厂商筛选': 'Filter by provider',
    '全部厂商': 'All providers',
    '中英文试玩已开放': 'Chinese and English demos available',
    '连消 · 倍率球 · 免费旋转': 'Tumbles · Multipliers · Free spins',
    '三款游戏可试玩；宙斯支持横竖屏，使用本地生成规则和虚拟积分。': 'Three playable games. Olympus supports portrait and landscape, with local rules and virtual credits.',
    '七款游戏可试玩，选择喜欢的主题开始体验。': 'Six playable games. Choose your favourite theme and start playing.',

    '英文界面预览': 'English UI preview',
    '两款 PG 游戏可试玩；Gates of Olympus 提供英文界面预览，旋转暂未接入。': 'Two PG games are playable. Gates of Olympus offers an English UI preview; spins are not connected.',
    '美洲野牛试玩': 'Buffalo Win demo',
    '扩展转轴 · 百搭 · 免费旋转': 'Extra reels · Wilds · Free spins',
    '中文试玩已开放': 'Chinese demo available',
    '英文试玩测试中': 'English demo · Testing',
    '两款游戏均支持中英文入口，美洲野牛英文版测试中。其余主题为概念预告。': 'Both games have Chinese and English launch options. Buffalo Win English is in testing. Other themes are concepts.',
    '麻将胡了 2 支持中英文试玩，美洲野牛现开放中文试玩。其余主题为概念预告。': 'Mahjong Ways 2 supports Chinese and English. Buffalo Win is playable in Chinese. Other themes are concepts.',

    '界面预览': 'UI preview',
    '预览': 'Preview',
    '美洲野牛': 'Buffalo Win',
    '美洲野牛界面预览': 'Buffalo Win UI preview',
    '野牛主题': 'Buffalo theme',
    '原版游戏画面 · 中文预览': 'Original game UI · Chinese preview',
    '原版画面 · 旋转暂未接入': 'Original UI · Spins not connected',
    '英文资源待补齐': 'English assets coming soon',
    '界面预览 · 旋转暂未接入': 'UI preview · Spins not connected',
    '麻将胡了 2 可试玩；美洲野牛提供中文界面预览，旋转暂未接入。其余主题为概念预告。': 'Mahjong Ways 2 is playable. Buffalo Win has a Chinese UI preview; spins are not connected. Other themes are concepts.',

    'SPINLAB · Slot 游戏试玩': 'SPINLAB · Free Slot Demos',
    'SPINLAB 首页': 'SPINLAB home',
    '主导航': 'Main navigation',
    '界面语言': 'Interface language',
    '游戏大厅': 'Game lobby',
    '试玩指南': 'How to play',
    '只管玩，轻松转。': 'All play. No pressure.',
    '发现你的下一款': 'Discover your next',
    '心动 Slot 游戏。': 'favorite slot game.',
    '探索': 'Explore',
    'Slot 试玩大厅': 'Slot demo lobby',
    '✦ 免费试玩': '✦ Free play',
    '访客模式': 'Guest mode',
    '每一次旋转，': 'Every spin.',
    '都有新乐趣。': 'A little more fun.',
    '探索不同主题的 Slot 游戏。': 'Discover a world of slot themes.',
    '无需注册，点击试玩，即刻开启你的游戏时间。': 'No sign-up. Pick a game and press play.',
    '探索游戏': 'Explore games',
    '✓ 无需下载': '✓ No downloads',
    '✓ 虚拟积分': '✓ Demo credits',
    '✓ 免费体验': '✓ Free to play',
    '霓虹紫色老虎机，三个转轴显示 777，周围环绕金色游戏代币': 'A neon purple slot machine showing 777, surrounded by gold game tokens',
    '精选 Slot 体验': 'Curated slot games',
    '点击即玩，无需下载': 'Instant play, no downloads',
    '独立试玩，轻松探索': 'Your own demo session',
    '正在连接游戏服务…': 'Connecting to game service…',
    '游戏服务在线': 'Game service online',
    '服务暂时不可用': 'Service temporarily unavailable',
    '搜索游戏': 'Search games',
    '游戏筛选': 'Filter games',
    '全部游戏': 'All games',
    '可试玩': 'Playable',
    '即将上线': 'Coming soon',
    '连消 · 百搭 · 免费旋转': 'Cascades · Wilds · Free spins',
    '连消玩法': 'Cascading reels',
    '麻将胡了 2': 'Mahjong Ways 2',
    '免费体验': 'Free demo',
    '试玩': 'Play',
    '主题预告': 'Theme preview',
    '复古转轴的缤纷灵感': 'A colorful take on classic reels',
    '水果主题': 'Fruit theme',
    '经典水果': 'Fruit Classic',
    '更多主题，陆续接入': 'More themes on the way',
    '没有找到匹配的游戏': 'No matching games',
    '换个关键词，或查看全部游戏。': 'Try another keyword or browse all games.',
    '查看全部': 'View all games',
    '暂时无法连接游戏服务，请稍后重试。': 'Unable to connect to the game service. Please try again.',
    '重新连接 ↻': 'Reconnect ↻',
    '主题预告为展示概念，暂不提供试玩。当前可体验：麻将胡了 2。': 'Theme previews are concepts and are not playable yet. Available now: Mahjong Ways 2.',
    '你的试玩，只需三步。': 'Three steps. All the fun.',
    '从发现到体验，一切就在这里。': 'From discovery to play, all in one place.',
    '发现游戏': 'Find a game',
    '浏览大厅，选择喜欢的 Slot。': 'Browse the lobby and pick a slot.',
    '点击试玩': 'Press play',
    '自动开启独立试玩会话。': 'Your own demo session starts automatically.',
    '尽情体验': 'Enjoy the game',
    '使用虚拟积分，直接在站内玩。': 'Play right here with virtual credits.',
    '仅供游戏演示 · 积分无现金价值 · 不提供充值或提现': 'Demo only · Credits have no cash value · No deposits or withdrawals',
    '正在准备试玩…': 'Preparing your demo…',
    '重新载入游戏': 'Reload game',
    '重新载入': 'Reload',
    '全屏游戏': 'Fullscreen game',
    '全屏': 'Fullscreen',
    '返回大厅': 'Back to lobby',
    '麻将胡了 2 试玩': 'Mahjong Ways 2 demo',
    '正在开启游戏': 'Getting your game ready',
    '连接游戏服务，创建试玩会话…': 'Connecting and creating your demo session…',
    '重新尝试 ↻': 'Try again ↻',
    '虚拟积分试玩': 'Demo credits only',
    '关闭后本次试玩结束 · 再次进入开启新体验': 'Close to leave this session · Play again for a fresh start',
    '连接未完成': 'Connection incomplete',
    '正在加载游戏资源…': 'Loading game assets…',
    '游戏加载时间较长': 'The game is taking longer to load',
    '请检查服务是否正常。可以重新载入游戏，或返回大厅稍后再试。': 'Please check the game service. Reload the game or return to the lobby and try again.',
    '暂时无法开启试玩': 'Unable to start your demo',
    '游戏服务未响应。请重试，或返回大厅稍后再来。': 'The game service did not respond. Try again or return to the lobby.',
    '试玩已连接 · 独立虚拟积分': 'Demo connected · Your own virtual credits',
    '游戏连接已中断': 'Game connection interrupted',
    '试玩会话可能已过期，请返回大厅重新开启试玩。': 'Your session may have expired. Return to the lobby to start a new demo.',
    '当前浏览器暂不支持全屏': 'Fullscreen is unavailable in this browser',
    '游戏未上线': 'This game is not available',
    '无效的游戏链接': 'Invalid game link',
  };
  let language = 'zh';
  try { language = localStorage.getItem('spinlab-language') === 'en' ? 'en' : 'zh'; } catch { /* Storage may be disabled. */ }
  const requested = new URL(location.href).searchParams.get('lang');
  if (requested === 'zh' || requested === 'en') language = requested;

  // Bind the authored Chinese text once, retaining markup and decorative icons.
  const bindings = [];
  const walker = document.createTreeWalker(document.documentElement, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    if (node.parentElement?.closest('script, style, [data-language]')) continue;
    const source = node.textContent.trim();
    if (Object.hasOwn(english, source)) {
      bindings.push({ node, source, leading: node.textContent.match(/^\s*/)[0], trailing: node.textContent.match(/\s*$/)[0] });
    }
  }
  const attributes = [];
  document.querySelectorAll('[title], [aria-label], [placeholder]').forEach(element => {
    for (const attribute of ['title', 'aria-label', 'placeholder']) {
      const source = element.getAttribute(attribute);
      if (Object.hasOwn(english, source)) attributes.push({ element, attribute, source });
    }
  });
  function t(source) { return language === 'en' ? (english[source] ?? source) : source; }
  function setText(id, source) {
    const element = document.getElementById(id);
    element.dataset.i18nText = source;
    element.textContent = t(source);
  }
  function applyLanguage(next) {
    language = next;
    document.documentElement.lang = next === 'en' ? 'en' : 'zh-CN';
    for (const binding of bindings) {
      binding.node.textContent = binding.leading + t(binding.source) + binding.trailing;
    }
    for (const binding of attributes) binding.element.setAttribute(binding.attribute, t(binding.source));
    document.querySelectorAll('[data-i18n-text]').forEach(element => {
      element.textContent = t(element.dataset.i18nText);
    });
    document.querySelectorAll('[data-language]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.language === next));
    });
    try { localStorage.setItem('spinlab-language', next); } catch { /* Keep switching functional without storage. */ }
    const url = new URL(location.href);
    url.searchParams.set('lang', next);
    history.replaceState(history.state, '', url);
    window.dispatchEvent(new Event('spinlab:languagechange'));
  }
  window.SpinLabI18n = { get language() { return language; }, t, setText };
  document.querySelectorAll('[data-language]').forEach(button => {
    button.addEventListener('click', () => applyLanguage(button.dataset.language));
  });
  applyLanguage(language);
})();
