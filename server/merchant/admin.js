'use strict';
const $ = selector => document.querySelector(selector);
const roles = {admin: '平台管理员', operator: '平台运营', viewer: '平台只读', merchant_admin: '商户管理员', merchant_operator: '商户运营', merchant_viewer: '商户只读'};
const tenant = () => !!session?.user.merchant_id;
const portal = location.pathname.startsWith('/merchant');
const apiRoot = portal ? '/api/merchant/' : '/api/admin/';
const statusNames = {settled: '已完成', prepared: '待确认扣款', debited: '待确认派彩', rejected: '已拒绝'};
const pages = {
  overview: ['运营概览', '关注商户接入、交易处理与日常运营。'],
  merchants: ['商户管理', '维护合作平台、钱包连接和游戏授权。'],
  games: ['游戏目录', '查看已接入商户网关的游戏与规则版本。'],
  transactions: ['交易中心', '查询游戏交易，恢复已受理但尚未完成的操作。'],
  audit: ['操作审计', '追踪账户、商户配置及交易恢复的操作记录。'],
  users: ['账户与权限', '为团队分配管理员、运营或只读权限。'],
};
let session = null, view = 'overview', generation = 0;
let transactionFilters = {}, auditFilters = {}, merchants = [], games = [];
const can = permission => session?.permissions.includes(permission);
const el = (tag, attrs = {}, ...children) => {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (value !== undefined && value !== null && value !== false) node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children.flat()) if (child !== null && child !== undefined) node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  return node;
};
const button = (label, action, className = 'quiet') => el('button', {type: 'button', class: className, onclick: action}, label);
const badge = (label, kind = '') => el('span', {class: 'badge ' + kind}, label);
const status = value => badge(statusNames[value] || value, value === 'settled' ? 'good' : value === 'rejected' ? 'bad' : 'pending');
const time = timestamp => new Date(timestamp * 1000).toLocaleString('zh-CN', {hour12: false});
const amount = number => number.toLocaleString('zh-CN');
function money(minor, row) {
  if (!row.currency || row.minor_unit !== 100) return amount(minor) + ' 最小单位（币种未确认）';
  // Integer arithmetic preserves every cent, including near the balance limit.
  const units = BigInt(minor);
  return (units / 100n).toLocaleString('en-US') + '.' + (units % 100n).toString().padStart(2, '0') + ' ' + row.currency;
}
const field = (label, node) => el('label', {}, label, node);
const input = (name, value = '', attrs = {}) => el('input', {name, value, ...attrs});
function select(name, options, selected = '') {
  return el('select', {name}, options.map(([value, label]) => el('option', {value, selected: value === selected}, label)));
}
function notice(message, error = false) { $('#notice').textContent = message; $('#notice').className = error ? 'error' : ''; $('#notice').hidden = false; }
function showLogin() {
  session = null; generation++; closeModal(); $('#content').replaceChildren(); $('#app').hidden = true; $('#login').hidden = false;
  transactionFilters = {}; auditFilters = {}; merchants = []; games = [];
  $('#login-form').elements.password.value = '';
}
function showApp(result) {
  session = result; $('#login').hidden = true; $('#app').hidden = false;
  $('#identity').textContent = result.user.username + ' · ' + roles[result.user.role];
  $('#profile-avatar').textContent = result.user.username.slice(0, 1).toUpperCase();
  $('#merchant-nav-label').textContent = tenant() ? '我的商户' : '商户管理';
  $('#workspace-kind').textContent = tenant() ? '商户专属空间' : '运营管理空间';
  document.querySelectorAll('[data-permission]').forEach(node => { node.hidden = !can(node.dataset.permission); });
  if (view === 'users' && !can('users.manage')) view = 'overview';
  return loadView();
}
async function api(path, payload = {}) {
  const response = await fetch(apiRoot + path, {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json', 'X-GTT-CSRF': session?.csrf_token || ''}, body: JSON.stringify(payload)});
  const result = await response.json();
  if (!response.ok) {
    if (response.status === 401 && path !== 'login') showLogin();
    throw new Error(result.error?.message || '请求失败，请稍后重试。');
  }
  return result.data;
}
function table(headers, rows) {
  return el('div', {class: 'table-scroll'}, el('table', {}, el('thead', {}, el('tr', {}, headers.map(text => el('th', {}, text)))),
    el('tbody', {}, rows.length ? rows.map(cells => el('tr', {}, cells.map(cell => el('td', {}, cell)))) : el('tr', {}, el('td', {colspan: headers.length, class: 'empty'}, '暂无匹配记录')))));
}
function panel(title, subtitle, content, action = null) {
  return el('section', {class: 'panel'}, el('div', {class: 'panel-heading'}, el('div', {}, el('h3', {}, title), el('p', {}, subtitle)), action), content);
}
function closeModal() { if ($('#modal').open) $('#modal').close(); $('#modal-body').replaceChildren(); }
function modal(title, content) {
  closeModal(); $('#modal-body').replaceChildren(el('div', {class: 'modal-header'}, el('h2', {}, title), button('✕', closeModal)), el('div', {class: 'modal-content'}, content));
  $('#modal').showModal();
}
$('#modal').addEventListener('close', () => { if (!$('#modal').open) $('#modal-body').replaceChildren(); });
function formModal(title, nodes, submitLabel, action) {
  const error = el('p', {class: 'error', role: 'alert'});
  const submit = el('button', {type: 'submit', class: 'primary'}, submitLabel);
  const form = el('form', {}, nodes, error, el('div', {class: 'modal-actions'}, button('取消', closeModal, 'secondary'), submit));
  form.addEventListener('submit', async event => {
    event.preventDefault(); submit.disabled = true; error.textContent = '';
    try { await action(new FormData(form)); } catch (failure) { if (form.isConnected) error.textContent = failure.message; else notice(failure.message, true); }
    finally { submit.disabled = false; }
  });
  modal(title, form);
}
function reveal(title, values) {
  modal(title, [el('p', {class: 'hint'}, values.merchant_secret ? '商户密钥由 GTT 自动生成，可在商户详情随时查看或复制。' : '以下凭据仅在本次操作后展示。请妥善保存；关闭窗口后无法再次读取。'),
    ...Object.entries(values).map(([name, value]) => el('div', {}, el('p', {class: 'small muted'}, name), el('pre', {class: 'secret'}, value))),
    el('div', {class: 'modal-actions'}, button('已保存，关闭', closeModal, 'primary'))]);
}
function detail(title, value) { modal(title, el('pre', {class: 'details'}, JSON.stringify(value, null, 2))); }
function transactionDetail(row) {
  modal('交易详情', [el('p', {class: 'cell-title'}, '扣款 ' + money(row.debit_minor, row) + ' / 派彩 ' + money(row.credit_minor, row)),
    el('pre', {class: 'details'}, JSON.stringify(row, null, 2))]);
}
function merchantOptions() { return [['', '全部商户'], ...merchants.map(m => [m.id, m.name + ' · ' + m.id])]; }
function txRows(rows) {
  return rows.map(row => [el('div', {}, el('div', {class: 'cell-title mono'}, row.id.slice(0, 20) + '…'), el('div', {class: 'subtext'}, time(row.created_at))),
    el('div', {}, el('div', {class: 'cell-title'}, row.merchant_id), el('div', {class: 'subtext'}, row.player_id)),
    row.game_id, el('span', {class: 'mono'}, '−' + money(row.debit_minor, row)), el('span', {class: 'mono'}, '+' + money(row.credit_minor, row)), status(row.status),
    el('div', {}, button('详情', () => run(async () => transactionDetail(await api('transactions/detail', {operation_id: row.id, merchant_id: row.merchant_id})))),
      can('transactions.retry') && ['prepared', 'debited'].includes(row.status) ? button('恢复', () => recover(row)) : null)]);
}
function txTable(rows) { return table(['操作 / 时间', '商户 / 玩家', '游戏', '扣款', '派彩', '状态', '操作'], txRows(rows)); }
async function overview() {
  const data = await api('overview');
  const own = merchants[0];
  const welcome = el('section', {class: 'welcome-strip'}, el('div', {}, el('p', {class: 'eyebrow'}, tenant() ? 'YOUR PARTNERSHIP, AT A GLANCE' : 'A CLEAR VIEW OF YOUR OPERATIONS'),
    el('h2', {}, tenant() ? (own?.name || '商户') + '，欢迎回来。' : '每一份合作，都有新的可能。'),
    el('p', {}, tenant() ? '从接入配置到每一笔交易，你的业务尽在这里。' : '在一个工作空间，连接合作伙伴、游戏与交易。')),
    button(tenant() ? '管理我的商户 ↗' : '管理合作商户 ↗', () => navigate('merchants'), 'welcome-action'));
  const stats = el('div', {class: 'stats'}, [
    [tenant() ? '已结算玩家' : '合作商户', tenant() ? data.players : data.merchants, tenant() ? '按商户与玩家身份去重' : data.active_merchants + ' 个商户已启用', '▦'],
    ['已接入游戏', data.games, tenant() ? '本商户已获授权' : '商户钱包链路已接通', '◇'],
    ['已完成交易', data.settled, '已确认钱包处理结果', '↗'],
    ['待处理交易', data.pending, data.rejected + ' 笔交易已拒绝', '⇄'],
  ].map(([label, number, foot, icon]) => el('div', {class: 'stat'}, el('div', {class: 'stat-icon'}, icon), el('div', {class: 'stat-label'}, label), el('div', {class: 'stat-number'}, amount(number)), el('div', {class: 'stat-foot'}, foot))));
  const totals = el('div', {class: 'settlement-list'}, data.totals.length ? data.totals.map(row => el('div', {class: 'settlement-currency'},
    badge(row.currency), el('div', {class: 'settlement-row'}, el('span', {}, '累计投注'), el('strong', {}, money(row.debit_minor, row))),
    el('div', {class: 'settlement-row'}, el('span', {}, '累计派彩'), el('strong', {}, money(row.credit_minor, row))))) : el('div', {class: 'empty'}, '完成首笔交易后，将在这里展示结算金额。'));
  const chart = settlementChart(data.daily);
  return el('div', {}, welcome, stats, el('div', {class: 'two-column'}, panel('交易脉搏', '最近 7 天 · UTC · 已完成游戏操作', chart, badge('7 DAYS')), panel('资金概览', '累计已结算金额 · 按币种独立统计', totals)),
    panel('最近交易', 'LATEST ACTIVITY / 最近 5 笔游戏操作', txTable(data.recent), button('查看全部 →', () => navigate('transactions'))));
}
function settlementChart(days) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 640 170'); svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', days.map(d => d.date + ': ' + d.settled + ' 笔').join('，'));
  const maximum = Math.max(1, ...days.map(d => d.settled));
  function shape(tag, attrs) { const node = document.createElementNS(svg.namespaceURI, tag); for (const [k,v] of Object.entries(attrs)) node.setAttribute(k,v); svg.append(node); return node; }
  function draw(width) {
    svg.replaceChildren(); svg.setAttribute('viewBox', '0 0 ' + width + ' 170');
    const step = (width - 24) / 7, barWidth = Math.min(32, step * .42);
    for (let i = 0; i < 4; i++) { const y = 15 + i * 43; shape('line', {x1: 10, x2: width - 10, y1: y, y2: y, class: 'chart-grid'}); }
    days.forEach((d, i) => { const x = 12 + step * (i + .5) - barWidth / 2, height = d.settled / maximum * 113;
    const bar = shape('rect', {x, y: 144 - Math.max(2, height), width: barWidth, height: Math.max(2, height), rx: 3, class: 'chart-bar'});
    const title = document.createElementNS(svg.namespaceURI,'title'); title.textContent = d.date + ' · ' + d.settled + ' 笔'; bar.append(title);
    const label = shape('text', {x: x + barWidth / 2, y: 165, 'text-anchor': 'middle', class: 'chart-label'}); label.textContent = d.date.slice(5);
    const count = shape('text', {x: x + barWidth / 2, y: Math.max(12, 137 - height), 'text-anchor': 'middle', class: 'chart-value'}); count.textContent = d.settled;
    });
  }
  draw(640);
  const observer = new ResizeObserver(() => { if (!svg.isConnected) { observer.disconnect(); return; } draw(Math.max(220, svg.clientWidth)); });
  observer.observe(svg);
  return el('div', {class: 'chart-body'}, svg);
}
function merchantEditor(merchant = null) {
  const editing = !!merchant, writable = can('merchants.write') || can('profile.write');
  const value = merchant || {id: '', name: '', wallet_url: '', currency: 'USD', games: [], enabled: true};
  const currency = select('currency', editing && value.currency !== 'USD' ? [[value.currency, value.currency]] : [['USD', '美元（USD）']], value.currency);
  const prebet = value.pre_payout || {};
  currency.required = true;
  currency.disabled = editing;
  const nodes = [el('div', {class: 'form-grid'}, field('商户号', input('id', value.id, {disabled: true, placeholder: '保存后自动生成'})), field('商户名称', input('name', value.name, {required: true, maxlength: 80})), field('钱包服务地址', input('wallet_url', value.wallet_url, {required: true, type: 'url', placeholder: 'https://wallet.example.com', maxlength: 512})), field('币种', currency)),
    el('p', {class: 'hint'}, 'merchant_secret 由 GTT 自动生成。统一签名使用同一把密钥处理游戏接入、钱包和预派彩请求。创建后即可查看、复制和使用。'),
    el('p', {class: 'hint'}, '钱包地址填写 origin，不带路径。金额精度为 100；创建后币种不可更改。'),
    tenant() ? el('p', {class: 'hint'}, '商户启用状态与游戏授权由 GTT 平台维护。') : el('label', {class: 'check-label'}, input('enabled', 'yes', {type: 'checkbox', checked: value.enabled}), '启用商户'),
    el('h3', {}, '游戏授权'), ...games.map(game => el('label', {class: 'check-label'}, input('games', game.id, {type: 'checkbox', checked: value.games.includes(game.id), disabled: tenant()}), game.title || game.id)),
    el('h3', {}, '平台预派彩'),
    el('label', {class: 'check-label'}, input('prebet_enabled', 'yes', {type: 'checkbox', checked: prebet.enabled}), '开奖前向平台获取整局派彩倍数区间'),
    field('preBetDecision 接口地址', input('prebet_url', prebet.url || '', {type: 'url', autocomplete: 'off', maxlength: 1024, placeholder: '填写合作平台的预下注决策接口地址'})),
    el('p', {class: 'hint'}, '统一签名复用 merchant_secret，预派彩无需另配凭据；是否启用由商户决定。'),
    el('p', {class: 'hint'}, '倍数以整局实际扣款为基数，包含续列和免费旋转。启动请求需提供 external_username。'),
    el('p', {class: 'hint'}, '停用或移除授权会阻止后续游戏请求；已受理的待处理交易仍可由运营人员恢复。')];
  if (!writable) { detail('商户配置', value); return; }
  formModal(editing ? '编辑商户' : '创建商户', nodes, '保存商户', async form => {
    const payload = {name: form.get('name'), wallet_url: form.get('wallet_url'), currency: editing ? value.currency : form.get('currency'),
      enabled: form.get('enabled') === 'yes', games: form.getAll('games')};
    if (editing) Object.assign(payload, {id: value.id, version: value.version});
    payload.pre_payout = {enabled: form.get('prebet_enabled') === 'yes', url: form.get('prebet_url').trim()};
    if (tenant()) { delete payload.enabled; delete payload.games; delete payload.currency; }
    const result = await api('merchants/' + (tenant() ? 'profile' : editing ? 'update' : 'create'), payload);
    closeModal(); await loadView(); notice(editing ? '商户配置已保存。' : '商户已创建，商户号：' + result.merchant.id);
    if (result.keys) showMerchantSecret(result.merchant.id, result.keys.merchant_secret);
  });
}
function showMerchantSecret(merchantId, secret) {
  const secretInput = input('merchant_secret', secret, {type: 'password', readonly: true, autocomplete: 'off'});
  const message = el('p', {class: 'hint', role: 'status'}, '密钥由 GTT 自动生成，可随时在后台查看或复制。');
  const toggle = button('显示密钥', () => { const show = secretInput.type === 'password'; secretInput.type = show ? 'text' : 'password'; toggle.textContent = show ? '隐藏密钥' : '显示密钥'; }, 'secondary');
  const copy = button('复制密钥', async () => {
    try { await navigator.clipboard.writeText(secret); message.textContent = '密钥已复制。'; }
    catch { secretInput.type = 'text'; toggle.textContent = '隐藏密钥'; secretInput.select(); message.textContent = '已选中密钥，可按 Ctrl+C 复制。'; }
  }, 'primary');
  modal('商户密钥', [field('商户号', input('merchant_id', merchantId, {readonly: true})), field('merchant_secret', secretInput), message,
    el('div', {class: 'modal-actions'}, toggle, copy, button('关闭', closeModal, 'secondary'))]);
}
function merchantSecret(merchant) {
  run(async () => { const result = await api('merchants/signing/view', {id: merchant.id}); showMerchantSecret(merchant.id, result.keys.merchant_secret); });
}
function rotate(merchant) {
  formModal('重置商户密钥', [el('p', {class: 'hint'}, 'GTT 将生成一把新密钥，原密钥立即失效。重置后请同步更新商户服务端配置。'),
    field('操作原因', input('reason', '', {required: true, minlength: 4, maxlength: 300}))], '重置密钥', async form => {
    const result = await api('merchants/signing/rotate', {id: merchant.id, version: merchant.version, reason: form.get('reason')});
    closeModal(); await loadView(); showMerchantSecret(merchant.id, result.keys.merchant_secret);
  });
}
async function merchantPage() {
  if (tenant()) return merchantProfile();
  return panel('全部商户', merchants.length + ' 个合作平台', table(['商户', '状态', '钱包 / 币种', '授权游戏', '密钥版本', '操作'], merchants.map(m => [
    el('div', {}, el('div', {class: 'cell-title'}, m.name), el('div', {class: 'subtext mono'}, m.id)), badge(m.enabled ? '已启用' : '已停用', m.enabled ? 'good' : ''),
    el('div', {}, el('div', {class: 'cell-title'}, m.currency + ' · 精度 ' + m.minor_unit), el('div', {class: 'subtext'}, m.wallet_url)),
    m.games.length ? m.games.join(', ') : '未授权', el('div', {}, 'v' + m.merchant_key_version, el('div', {class: 'subtext mono'}, m.merchant_key_fingerprint)),
    el('div', {}, button(can('merchants.write') ? '编辑' : '查看', () => merchantEditor(m)), can('users.manage') ? button('开通后台', () => userEditor(null, m)) : null, can('keys.rotate') ? [button('查看密钥', () => merchantSecret(m)), button('重置密钥', () => rotate(m))] : null),
  ])), can('merchants.write') ? button('+ 创建商户', () => merchantEditor(), 'primary') : null);
}
function merchantProfile() {
  const m = merchants[0];
  const property = (label, value) => el('div', {class: 'property'}, el('span', {}, label), el('strong', {}, value));
  return el('div', {}, el('section', {class: 'merchant-banner'}, el('span', {class: 'merchant-avatar'}, m.name.slice(0,1)), el('div', {}, el('p', {class: 'eyebrow'}, 'MERCHANT PROFILE'), el('h2', {}, m.name), el('span', {class: 'mono'}, m.id)), badge(m.enabled ? '合作已启用' : '合作已停用', m.enabled ? 'good' : 'bad')),
    el('div', {class: 'two-column'}, panel('接入配置', '管理你的平台连接', el('div', {class: 'panel-body'}, property('钱包地址', m.wallet_url), property('结算币种', m.currency), property('已授权游戏', m.games.join(', ') || '暂无授权'), property('平台预派彩', m.pre_payout.enabled ? '已启用' : '未启用'), property('决策接口', m.pre_payout.url || '未配置')), can('profile.write') ? button('编辑接入配置 ↗', () => merchantEditor(m), 'secondary') : null),
    panel('统一接入密钥', 'GTT 自动签发 · 游戏、钱包、预派彩共用', el('div', {class: 'panel-body'}, property('签名模式', 'HMAC-SHA256'), property('密钥版本', 'v' + m.merchant_key_version), property('密钥指纹', m.merchant_key_fingerprint),
      el('p', {class: 'hint'}, '只需保存商户号和一把 merchant_secret。每次请求使用新的时间戳、随机数和签名，密钥不放入请求体或游戏链接。'),
      can('keys.rotate') ? [button('查看 / 复制密钥', () => merchantSecret(m), 'secondary'), button('重置密钥', () => rotate(m), 'secondary')] : null))),
    panel('接入路径', '从玩家登录到钱包结算', el('div', {class: 'integration-flow'}, ...[['01', '签名启动', '由你的服务端调用 /gtt/v1/games/launch'], ['02', '打开游戏', '使用 GTT 域名拼接返回的 launch_url'], ['03', '钱包结算', '处理 GTT 的扣款和派奖签名回调']].map(([n,title,desc]) => el('div', {class: 'guide'}, el('span', {class: 'guide-number'}, n), el('div', {}, el('h3', {}, title), el('p', {}, desc)))))));
}
async function gamePage() {
  return el('div', {}, !games.length ? panel('暂无已授权游戏', '联系 GTT 平台开通游戏授权', el('p', {class: 'panel-body muted'}, '游戏开通后将在这里显示，已有商户资料及交易记录可继续查看。')) : null, el('div', {class: 'game-grid'}, games.map(game => el('article', {class: 'game-card'}, el('div', {class: 'game-monogram'}, 'BW'), el('h2', {}, game.title || game.id), el('p', {class: 'muted mono'}, game.id), badge('商户网关已接入', 'good'),
    ...Object.entries({'规则版本': game.ruleset_id || game.version || '—', '已授权商户': merchants.filter(m => m.games.includes(game.id)).length, '目标 RTP': '尚未标定'}).map(([key, value]) => el('div', {class: 'game-info'}, el('span', {class: 'muted'}, key), el('span', {}, value))),
    el('p', {class: 'hint'}, '游戏授权在商户配置中维护。目标 RTP 需完成数学模型标定后开放设置。')))),
    el('p', {class: 'hint'}, '此处列出已接入商户钱包链路的游戏。其他游戏的原有大厅入口继续保留。'));
}
function pager(rows, filters, reload) {
  return el('div', {class: 'pagination'}, el('span', {}, '当前 ' + rows.length + ' 条 · 每页 25 条'), el('div', {},
    filters.before_seq ? button('返回最新', () => { delete filters.before_seq; reload(); }) : null,
    rows.length === 25 ? button('下一页 →', () => { filters.before_seq = rows.at(-1).seq; reload(); }, 'secondary') : null));
}
function filterForm(fields, filters) {
  const form = el('form', {class: 'filters'}, fields, el('button', {type: 'submit', class: 'primary'}, '查询'), button('清空', () => { for (const key of Object.keys(filters)) delete filters[key]; loadView(); }));
  form.addEventListener('submit', event => { event.preventDefault(); for (const key of Object.keys(filters)) delete filters[key]; for (const [key, value] of new FormData(form)) if (value.trim()) filters[key] = value.trim(); loadView(); });
  return form;
}
async function transactionPage() {
  const rows = (await api('transactions/list', {...transactionFilters, limit: 25})).transactions;
  return panel('交易记录', '扣款与派彩按商户币种显示，1:1 对应平台钱包', el('div', {}, filterForm([
    field('商户', select('merchant_id', merchantOptions(), transactionFilters.merchant_id)), field('玩家', input('player_id', transactionFilters.player_id || '')),
    field('状态', select('status', [['', '全部状态'], ...Object.entries(statusNames)], transactionFilters.status)), field('操作 ID', input('operation_id', transactionFilters.operation_id || '')),
  ], transactionFilters), txTable(rows), pager(rows, transactionFilters, loadView)),
    button('预下注决策', () => run(async () => detail('最近预下注决策', await api('prebet/list', {merchant_id: transactionFilters.merchant_id || '', limit: 25}))), 'secondary'));
}
function recover(row) {
  formModal('恢复待处理交易', [el('p', {class: 'hint'}, row.merchant_id + ' / ' + row.player_id), el('pre', {class: 'details'}, row.id + '\n扣款 ' + money(row.debit_minor, row) + ' / 派彩 ' + money(row.credit_minor, row)), el('p', {class: 'hint'}, '系统使用原交易 ID 重试钱包请求，不重新生成游戏结果。'), field('恢复原因', input('reason', '', {required: true, minlength: 4, maxlength: 300}))], '确认恢复', async form => {
    await api('transactions/retry', {merchant_id: row.merchant_id, operation_id: row.id, reason: form.get('reason')}); closeModal(); await loadView(); notice('交易已恢复完成。');
  });
}
async function auditPage() {
  const rows = (await api('audit', {...auditFilters, limit: 25})).audit;
  return panel('审计记录', '商户变更、密钥轮换、账户操作与交易恢复', el('div', {}, filterForm([
    field('操作人', input('actor', auditFilters.actor || '')), field('操作类型', input('action', auditFilters.action || '', {placeholder: '如 merchant.update'})), field('目标', input('target', auditFilters.target || '')),
  ], auditFilters), table(['时间', '操作人', '操作类型', '目标', '结果', '详情'], rows.map(row => [time(row.created_at), row.actor, el('span', {class: 'mono'}, row.action), el('span', {class: 'mono'}, row.target || '—'), badge(row.outcome, row.outcome === 'success' ? 'good' : 'bad'), button('查看', () => detail('审计详情 #' + row.seq, row))])), pager(rows, auditFilters, loadView)));
}
function userEditor(user = null, merchant = null) {
  const editing = !!user;
  const roleOptions = Object.entries(roles).filter(([role]) => !tenant() || role.startsWith('merchant_'));
  formModal(editing ? '编辑账户权限' : '创建管理账户', [field('用户名', input('username', user?.username || '', {required: true, minlength: 3, maxlength: 40, pattern: '[A-Za-z0-9_.\\-]+', disabled: editing})),
    field('角色', select('role', roleOptions, user?.role || (merchant ? 'merchant_admin' : tenant() ? 'merchant_viewer' : 'viewer'))),
    !tenant() ? field('绑定商户', select('merchant_id', [['', '平台账号（不绑定商户）'], ...merchants.map(m => [m.id, m.name + ' · ' + m.id])], user?.merchant_id || merchant?.id || '')) : null,
    el('p', {class: 'hint'}, tenant() ? '商户管理员管理本商户接入与团队；运营可查询和恢复交易；只读仅可查看。' : '商户角色须选择绑定商户；平台角色不绑定商户。商户账号仅能访问本商户的数据。'),
    editing ? el('label', {class: 'check-label'}, input('enabled', 'yes', {type: 'checkbox', checked: user.enabled}), '启用账户') : el('p', {class: 'hint'}, '创建后会生成一次性展示的初始密码。')], '保存账户', async form => {
    const result = await api('users/' + (editing ? 'update' : 'create'), {username: user?.username || form.get('username'), role: form.get('role'), merchant_id: tenant() ? session.user.merchant_id : form.get('merchant_id') || null, enabled: editing ? form.get('enabled') === 'yes' : true});
    closeModal();
    if (editing && user.username === session?.user.username) { showLogin(); return; }
    await loadView(); notice('账户已保存。'); if (result.temporary_password) reveal('账户已创建', {username: result.user.username, temporary_password: result.temporary_password});
  });
}
function resetPassword(user) {
  formModal('重置账户密码', [el('p', {class: 'hint'}, '重置 ' + user.username + ' 的密码，并立即撤销该账户的全部已登录会话。')], '重置密码', async () => {
    const result = await api('users/reset', {username: user.username}); closeModal();
    if (user.username === session.user.username) showLogin();
    reveal('新密码 · 请保存', {username: user.username, temporary_password: result.temporary_password});
  });
}
async function userPage() {
  const users = (await api('users/list')).users;
  return panel(tenant() ? '商户团队' : '管理账户', '权限变更与停用会立即撤销已有会话', table(['用户名', '角色', '所属商户', '状态', '创建时间', '操作'], users.map(user => [user.username, badge(roles[user.role], 'purple'), user.merchant_id || 'GTT 平台', badge(user.enabled ? '已启用' : '已停用', user.enabled ? 'good' : ''), time(user.created_at), el('div', {}, button('编辑权限', () => userEditor(user)), button('重置密码', () => resetPassword(user)))])), button('+ 创建账户', () => userEditor(), 'primary'));
}
async function run(action) { try { await action(); } catch (error) { if (session) notice(error.message, true); else $('#login-error').textContent = error.message; } }
function navigate(next) { view = next; $('#notice').hidden = true; loadView(); }
async function loadView() {
  if (!session) return;
  const current = ++generation;
  $('#page-title').textContent = $('#breadcrumb').textContent = pages[view][0]; $('#page-description').textContent = pages[view][1];
  if (tenant() && view === 'merchants') { $('#page-title').textContent = $('#breadcrumb').textContent = '我的商户'; $('#page-description').textContent = '管理商户资料、平台连接与接入凭据。'; }
  $('#page-eyebrow').textContent = (tenant() ? 'PARTNER' : 'PLATFORM') + ' / ' + view.toUpperCase();
  $('#workspace-date').textContent = new Date().toLocaleDateString('zh-CN', {year:'numeric',month:'long',day:'numeric'});
  document.querySelectorAll('[data-view]').forEach(node => { const active = node.dataset.view === view; node.classList.toggle('active', active); node.setAttribute('aria-label', tenant() && node.dataset.view === 'merchants' ? '我的商户' : pages[node.dataset.view][0]); if (active) node.setAttribute('aria-current', 'page'); else node.removeAttribute('aria-current'); });
  $('#refresh-button').disabled = true;
  try {
    const results = await Promise.all([api('merchants/list'), api('games')]);
    if (!session || generation !== current) return;
    merchants = results[0].merchants; games = results[1].games;
    $('#workspace-name').textContent = tenant() ? merchants[0]?.name || '我的商户' : 'GTT 平台';
    $('#workspace-avatar').textContent = tenant() ? (merchants[0]?.name || 'M').slice(0,1) : 'G';
    const result = await ({overview, merchants: merchantPage, games: gamePage, transactions: transactionPage, audit: auditPage, users: userPage})[view]();
    if (generation === current && session) $('#content').replaceChildren(result);
  } catch (error) { if (session && generation === current) notice(error.message, true); }
  finally { if (generation === current || !session) $('#refresh-button').disabled = false; }
}
$('#navigation').addEventListener('click', event => { const target = event.target.closest('[data-view]'); if (target) navigate(target.dataset.view); });
$('#refresh-button').addEventListener('click', () => { $('#notice').hidden = true; loadView(); });
$('#login-form').addEventListener('submit', async event => {
  event.preventDefault(); const form = event.target, submit = form.querySelector('button'); submit.disabled = true; $('#login-error').textContent = '';
  try { const result = await api('login', {username: form.elements.username.value, password: form.elements.password.value}); form.elements.password.value = ''; await showApp(result); }
  catch (error) { $('#login-error').textContent = error.message; }
  finally { submit.disabled = false; }
});
$('#logout-button').addEventListener('click', () => run(async () => { await api('logout'); showLogin(); }));
$('#password-button').addEventListener('click', () => formModal('修改登录密码', [field('当前密码', input('current_password', '', {type: 'password', required: true, autocomplete: 'current-password', maxlength: 128})), field('新密码', input('new_password', '', {type: 'password', required: true, minlength: 12, maxlength: 128, autocomplete: 'new-password'})), field('再次输入新密码', input('confirm_password', '', {type: 'password', required: true, minlength: 12, maxlength: 128, autocomplete: 'new-password'}))], '更新密码并重新登录', async form => {
  if (form.get('new_password') !== form.get('confirm_password')) throw new Error('两次输入的新密码不一致。');
  await api('password', {current_password: form.get('current_password'), new_password: form.get('new_password')}); showLogin();
}));
if (portal) { document.title = 'GTT · 商户工作台'; $('#login-title').textContent = '登录商户工作台'; $('#login-description').textContent = '使用你的商户账号，进入专属运营空间。'; $('#portal-switch').textContent = '平台控制台 ↗'; $('#portal-switch').href = '/'; }
(async () => { try { const response = await fetch(apiRoot + 'me', {credentials: 'same-origin'}); if (!response.ok) { showLogin(); return; } await showApp((await response.json()).data); } catch { showLogin(); $('#login-error').textContent = '连接失败，请检查后台服务。'; } })();
