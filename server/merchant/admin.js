'use strict';
const $ = selector => document.querySelector(selector);
const roles = {admin: '管理员', operator: '运营', viewer: '只读'};
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
const field = (label, node) => el('label', {}, label, node);
const input = (name, value = '', attrs = {}) => el('input', {name, value, ...attrs});
function select(name, options, selected = '') {
  return el('select', {name}, options.map(([value, label]) => el('option', {value, selected: value === selected}, label)));
}
function notice(message, error = false) { $('#notice').textContent = message; $('#notice').className = error ? 'error' : ''; $('#notice').hidden = false; }
function showLogin() {
  session = null; generation++; closeModal(); $('#content').replaceChildren(); $('#app').hidden = true; $('#login').hidden = false;
  $('#login-form').elements.password.value = '';
}
function showApp(result) {
  session = result; $('#login').hidden = true; $('#app').hidden = false;
  $('#identity').textContent = result.user.username + ' · ' + roles[result.user.role];
  document.querySelectorAll('[data-permission]').forEach(node => { node.hidden = !can(node.dataset.permission); });
  if (view === 'users' && !can('users.manage')) view = 'overview';
  return loadView();
}
async function api(path, payload = {}) {
  const response = await fetch('/api/admin/' + path, {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json', 'X-GTT-CSRF': session?.csrf_token || ''}, body: JSON.stringify(payload)});
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
  modal(title, [el('p', {class: 'hint'}, '以下凭据仅在本次操作后展示。请妥善保存；关闭窗口后无法再次读取。'),
    ...Object.entries(values).map(([name, value]) => el('div', {}, el('p', {class: 'small muted'}, name), el('pre', {class: 'secret'}, value))),
    el('div', {class: 'modal-actions'}, button('已保存，关闭', closeModal, 'primary'))]);
}
function detail(title, value) { modal(title, el('pre', {class: 'details'}, JSON.stringify(value, null, 2))); }
function merchantOptions() { return [['', '全部商户'], ...merchants.map(m => [m.id, m.name + ' · ' + m.id])]; }
function txRows(rows) {
  return rows.map(row => [el('div', {}, el('div', {class: 'cell-title mono'}, row.id.slice(0, 20) + '…'), el('div', {class: 'subtext'}, time(row.created_at))),
    el('div', {}, el('div', {class: 'cell-title'}, row.merchant_id), el('div', {class: 'subtext'}, row.player_id)),
    row.game_id, el('span', {class: 'mono'}, '−' + amount(row.debit_minor) + ' / +' + amount(row.credit_minor)), status(row.status),
    el('div', {}, button('详情', () => run(async () => detail('交易详情', await api('transactions/detail', {operation_id: row.id, merchant_id: row.merchant_id})))),
      can('transactions.retry') && ['prepared', 'debited'].includes(row.status) ? button('恢复', () => recover(row)) : null)]);
}
function txTable(rows) { return table(['操作 / 时间', '商户 / 玩家', '游戏', '扣款 / 派彩', '状态', '操作'], txRows(rows)); }
async function overview() {
  const data = await api('overview');
  const stats = el('div', {class: 'stats'}, [
    ['合作商户', data.merchants, data.active_merchants + ' 个商户已启用', '▦'],
    ['网关游戏', data.games, '可分配给合作商户', '◇'],
    ['已完成交易', data.settled, '已确认钱包处理结果', '↗'],
    ['待处理交易', data.pending, data.rejected + ' 笔交易已拒绝', '⇄'],
  ].map(([label, number, foot, icon]) => el('div', {class: 'stat'}, el('div', {class: 'stat-icon'}, icon), el('div', {class: 'stat-label'}, label), el('div', {class: 'stat-number'}, amount(number)), el('div', {class: 'stat-foot'}, foot))));
  const guide = el('div', {class: 'panel-body'}, [
    ['01', '建立合作商户', '配置钱包服务地址、币种与接入密钥。'],
    ['02', '分配游戏授权', '启用所需游戏，通过签名接口创建玩家会话。'],
    ['03', '跟踪交易结果', '查看扣款与派彩状态，按原因恢复待处理交易。'],
  ].map(([n, title, description]) => el('div', {class: 'guide'}, el('span', {class: 'guide-number'}, n), el('div', {}, el('h3', {}, title), el('p', {}, description)))));
  return el('div', {}, stats, panel('最近交易', 'LATEST ACTIVITY · 最近 5 笔操作', txTable(data.recent), button('查看全部 →', () => navigate('transactions'))),
    el('div', {class: 'two-column'}, panel('商户接入流程', '从合作平台到游戏会话', guide), panel('运营工作台', '按角色提供操作入口', el('div', {class: 'panel-body'}, el('h3', {}, '每一次配置变更都有记录'), el('p', {class: 'muted'}, '商户授权即时生效。交易恢复沿用原操作 ID，避免重复扣款或派彩。'), button('查看操作审计 →', () => navigate('audit'), 'secondary')))));
}
function merchantEditor(merchant = null) {
  const editing = !!merchant, writable = can('merchants.write');
  const value = merchant || {id: '', name: '', wallet_url: '', currency: 'DEMO', games: [], enabled: true};
  const nodes = [el('div', {class: 'form-grid'}, field('商户号', input('id', value.id, {required: true, maxlength: 128, pattern: '[A-Za-z0-9_.:\\-]+', disabled: editing})), field('商户名称', input('name', value.name, {required: true, maxlength: 80})), field('钱包服务地址', input('wallet_url', value.wallet_url, {required: true, type: 'url', placeholder: 'https://wallet.example.com', maxlength: 512})), field('币种', input('currency', value.currency, {required: true, pattern: '[A-Z]{3,8}', disabled: editing}))),
    el('p', {class: 'hint'}, '钱包地址填写 origin，不带路径。金额精度为 100；创建后币种不可更改。'),
    el('label', {class: 'check-label'}, input('enabled', 'yes', {type: 'checkbox', checked: value.enabled}), '启用商户'),
    el('h3', {}, '游戏授权'), ...games.map(game => el('label', {class: 'check-label'}, input('games', game.id, {type: 'checkbox', checked: value.games.includes(game.id)}), game.title || game.id)),
    el('p', {class: 'hint'}, '停用或移除授权会阻止后续游戏请求；已受理的待处理交易仍可由运营人员恢复。')];
  if (!writable) { detail('商户配置', value); return; }
  formModal(editing ? '编辑商户' : '创建商户', nodes, '保存商户', async form => {
    const payload = {id: editing ? value.id : form.get('id'), name: form.get('name'), wallet_url: form.get('wallet_url'), currency: value.currency,
      enabled: form.get('enabled') === 'yes', games: form.getAll('games')};
    if (editing) payload.version = value.version; else payload.currency = form.get('currency');
    const result = await api('merchants/' + (editing ? 'update' : 'create'), payload);
    closeModal(); await loadView(); notice('商户配置已保存。');
    if (result.keys) reveal('商户已创建 · 保存接入密钥', {merchant_id: result.merchant.id, ...result.keys});
  });
}
function rotate(merchant) {
  formModal('轮换商户密钥', [el('p', {class: 'hint'}, '商户：' + merchant.name + '。API 与钱包签名密钥将同时更新，旧密钥立即失效。请同步更新合作平台配置。'), field('操作原因', input('reason', '', {required: true, minlength: 4, maxlength: 300}))], '轮换并显示新密钥', async form => {
    const result = await api('merchants/rotate', {id: merchant.id, version: merchant.version, reason: form.get('reason')});
    closeModal(); await loadView(); reveal('密钥已轮换 · 请保存', result.keys);
  });
}
async function merchantPage() {
  return panel('全部商户', merchants.length + ' 个合作平台', table(['商户', '状态', '钱包 / 币种', '授权游戏', '密钥版本', '操作'], merchants.map(m => [
    el('div', {}, el('div', {class: 'cell-title'}, m.name), el('div', {class: 'subtext mono'}, m.id)), badge(m.enabled ? '已启用' : '已停用', m.enabled ? 'good' : ''),
    el('div', {}, el('div', {class: 'cell-title'}, m.currency + ' · 精度 ' + m.minor_unit), el('div', {class: 'subtext'}, m.wallet_url)),
    m.games.length ? m.games.join(', ') : '未授权', el('div', {}, 'v' + m.key_version, el('div', {class: 'subtext mono'}, m.api_key_fingerprint)),
    el('div', {}, button(can('merchants.write') ? '编辑' : '查看', () => merchantEditor(m)), can('keys.rotate') ? button('轮换密钥', () => rotate(m)) : null),
  ])), can('merchants.write') ? button('+ 创建商户', () => merchantEditor(), 'primary') : null);
}
async function gamePage() {
  return el('div', {}, el('div', {class: 'game-grid'}, games.map(game => el('article', {class: 'game-card'}, el('div', {class: 'game-monogram'}, 'BW'), el('h2', {}, game.title || game.id), el('p', {class: 'muted mono'}, game.id), badge('商户网关已接入', 'good'),
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
  return panel('交易记录', '扣款与派彩金额均为整数最小单位', el('div', {}, filterForm([
    field('商户', select('merchant_id', merchantOptions(), transactionFilters.merchant_id)), field('玩家', input('player_id', transactionFilters.player_id || '')),
    field('状态', select('status', [['', '全部状态'], ...Object.entries(statusNames)], transactionFilters.status)), field('操作 ID', input('operation_id', transactionFilters.operation_id || '')),
  ], transactionFilters), txTable(rows), pager(rows, transactionFilters, loadView)));
}
function recover(row) {
  formModal('恢复待处理交易', [el('p', {class: 'hint'}, row.merchant_id + ' / ' + row.player_id), el('pre', {class: 'details'}, row.id + '\n扣款 ' + amount(row.debit_minor) + ' / 派彩 ' + amount(row.credit_minor)), el('p', {class: 'hint'}, '系统使用原交易 ID 重试钱包请求，不重新生成游戏结果。'), field('恢复原因', input('reason', '', {required: true, minlength: 4, maxlength: 300}))], '确认恢复', async form => {
    await api('transactions/retry', {merchant_id: row.merchant_id, operation_id: row.id, reason: form.get('reason')}); closeModal(); await loadView(); notice('交易已恢复完成。');
  });
}
async function auditPage() {
  const rows = (await api('audit', {...auditFilters, limit: 25})).audit;
  return panel('审计记录', '商户变更、密钥轮换、账户操作与交易恢复', el('div', {}, filterForm([
    field('操作人', input('actor', auditFilters.actor || '')), field('操作类型', input('action', auditFilters.action || '', {placeholder: '如 merchant.update'})), field('目标', input('target', auditFilters.target || '')),
  ], auditFilters), table(['时间', '操作人', '操作类型', '目标', '结果', '详情'], rows.map(row => [time(row.created_at), row.actor, el('span', {class: 'mono'}, row.action), el('span', {class: 'mono'}, row.target || '—'), badge(row.outcome, row.outcome === 'success' ? 'good' : 'bad'), button('查看', () => detail('审计详情 #' + row.seq, row))])), pager(rows, auditFilters, loadView)));
}
function userEditor(user = null) {
  const editing = !!user;
  formModal(editing ? '编辑账户权限' : '创建管理账户', [field('用户名', input('username', user?.username || '', {required: true, minlength: 3, maxlength: 40, pattern: '[A-Za-z0-9_.\\-]+', disabled: editing})),
    field('角色', select('role', Object.entries(roles), user?.role || 'viewer')), el('p', {class: 'hint'}, '管理员：维护商户、密钥和账户；运营：查询与恢复交易；只读：查看商户、交易和审计。'),
    editing ? el('label', {class: 'check-label'}, input('enabled', 'yes', {type: 'checkbox', checked: user.enabled}), '启用账户') : el('p', {class: 'hint'}, '创建后会生成一次性展示的初始密码。')], '保存账户', async form => {
    const result = await api('users/' + (editing ? 'update' : 'create'), {username: user?.username || form.get('username'), role: form.get('role'), enabled: editing ? form.get('enabled') === 'yes' : true});
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
  return panel('管理账户', '权限变更与停用会立即撤销已有会话', table(['用户名', '角色', '状态', '创建时间', '操作'], users.map(user => [user.username, badge(roles[user.role], 'purple'), badge(user.enabled ? '已启用' : '已停用', user.enabled ? 'good' : ''), time(user.created_at), el('div', {}, button('编辑权限', () => userEditor(user)), button('重置密码', () => resetPassword(user)))])), button('+ 创建账户', () => userEditor(), 'primary'));
}
async function run(action) { try { await action(); } catch (error) { if (session) notice(error.message, true); else $('#login-error').textContent = error.message; } }
function navigate(next) { view = next; $('#notice').hidden = true; loadView(); }
async function loadView() {
  if (!session) return;
  const current = ++generation;
  $('#page-title').textContent = $('#breadcrumb').textContent = pages[view][0]; $('#page-description').textContent = pages[view][1];
  document.querySelectorAll('[data-view]').forEach(node => node.classList.toggle('active', node.dataset.view === view));
  $('#refresh-button').disabled = true;
  try {
    const results = await Promise.all([api('merchants/list'), api('games')]);
    if (!session || generation !== current) return;
    merchants = results[0].merchants; games = results[1].games;
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
(async () => { try { const response = await fetch('/api/admin/me', {credentials: 'same-origin'}); if (!response.ok) { showLogin(); return; } await showApp((await response.json()).data); } catch { showLogin(); $('#login-error').textContent = '连接失败，请检查后台服务。'; } })();
