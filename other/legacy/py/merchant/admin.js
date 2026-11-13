'use strict';
const $ = selector => document.querySelector(selector);
const roles = {admin: '平台管理员', operator: '平台运营', viewer: '平台只读', merchant_admin: '商户管理员', merchant_operator: '商户运营', merchant_viewer: '商户只读'};
const tenant = () => !!session?.user.merchant_id;
let portal = location.pathname.startsWith('/merchant');
let apiRoot = portal ? '/api/merchant/' : '/api/admin/';
const statusNames = {settled: '已完成', prepared: '待确认扣款', debited: '待确认派彩', rejected: '已拒绝'};
const pages = {
  overview: ['运营概览', '关注商户接入、交易处理与日常运营。'],
  merchants: ['商户管理', '维护合作平台、钱包连接和游戏授权。'],
  integration: ['接入中心', '从身份凭证到结算规范，一站完成 GTT 服务端接入。'],
  games: ['游戏目录', '查看已接入商户网关的游戏与规则版本。'],
  rtp: ['RTP 设置', '一个商户，一个默认 RTP。修改后从下一付费整局生效。'],
  transactions: ['交易中心', '查询游戏交易，恢复已受理但尚未完成的操作。'],
  audit: ['操作审计', '追踪账户、商户配置及交易恢复的操作记录。'],
  users: ['账户与权限', '为团队分配管理员、运营或只读权限。'],
};
const initialView = location.hash.slice(1);
let session = null, view = Object.keys(pages).includes(initialView) ? initialView : 'overview', generation = 0;
let transactionFilters = {}, auditFilters = {}, merchants = [], games = [];
let rtpTab = 'merchants', rtpFilters = {};
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
let selectSequence = 0;
function enhanceSelects(root) {
  root.querySelectorAll('select:not([data-enhanced])').forEach(native => {
    native.dataset.enhanced = 'true'; native.classList.add('select-native'); native.tabIndex = -1; native.setAttribute('aria-hidden','true');
    const label=Array.from(native.closest('label')?.childNodes || []).filter(n=>n.nodeType===Node.TEXT_NODE).map(n=>n.textContent).join('').trim() || native.name;
    const id='select-menu-'+(++selectSequence), wrapper=el('span',{class:'select-control'});
    native.before(wrapper); wrapper.append(native);
    const text=el('span',{class:'select-value'}), trigger=el('button',{type:'button',class:'select-trigger',role:'combobox','aria-label':label,'aria-haspopup':'listbox','aria-controls':id,'aria-expanded':'false',disabled:native.disabled},text,el('span',{class:'select-chevron','aria-hidden':'true'},'⌄'));
    const list=el('div',{id,role:'listbox','aria-label':label,class:'select-options'}), search=input('', '', {type:'search',placeholder:'搜索选项…',autocomplete:'off','aria-label':'搜索'+label,class:'select-search'});
    const menu=el('div',{class:'select-menu',popover:'auto'},native.options.length>6?search:null,list);
    wrapper.append(trigger,menu);
    let active=-1, visible=[];
    const sync=()=>{text.textContent=native.selectedOptions[0]?.textContent || '请选择';trigger.disabled=native.disabled;list.querySelectorAll('[role=option]').forEach(node=>node.setAttribute('aria-selected',node.dataset.value===native.value?'true':'false'));};
    const highlight=index=>{active=Math.max(0,Math.min(visible.length-1,index));visible.forEach((node,i)=>node.classList.toggle('is-active',i===active));if(visible[active]){trigger.setAttribute('aria-activedescendant',visible[active].id);visible[active].scrollIntoView({block:'nearest'});}else trigger.removeAttribute('aria-activedescendant');};
    const choose=node=>{if(!node)return;native.value=node.dataset.value;native.dispatchEvent(new Event('change',{bubbles:true}));menu.hidePopover();trigger.focus();};
    const render=()=>{const needle=search.value.trim().toLocaleLowerCase();visible=[];list.replaceChildren();Array.from(native.options).forEach((option,i)=>{
      if(!option.textContent.toLocaleLowerCase().includes(needle))return;
      const node=el('button',{type:'button',id:id+'-'+i,role:'option',class:'select-option','aria-selected':option.selected?'true':'false','data-value':option.value,disabled:option.disabled,tabindex:-1,onclick:event=>{event.preventDefault();choose(node);}},el('span',{},option.textContent),el('span',{class:'select-check','aria-hidden':'true'},'✓'));
      list.append(node);if(!option.disabled)visible.push(node);
    });if(!visible.length)list.append(el('p',{class:'select-empty'},'没有匹配选项'));highlight(Math.max(0,visible.findIndex(node=>node.dataset.value===native.value)));};
    menu.position=()=>{const rect=trigger.getBoundingClientRect(),roomBelow=innerHeight-rect.bottom-12,above=roomBelow<180&&rect.top>roomBelow,height=Math.min(330,Math.max(100,(above?rect.top:roomBelow)-16)),width=Math.min(Math.max(rect.width,200),innerWidth-24);Object.assign(menu.style,{width:width+'px',maxHeight:height+'px',left:Math.max(12,Math.min(rect.left,innerWidth-width-12))+'px',top:above?'auto':rect.bottom+7+'px',bottom:above?innerHeight-rect.top+7+'px':'auto'});list.style.maxHeight=Math.max(70,height-(native.options.length>6?62:16))+'px';};
    const open=()=>{if(trigger.disabled)return;search.value='';render();menu.showPopover();menu.position();trigger.setAttribute('aria-expanded','true');if(native.options.length>6)search.focus();};
    trigger.addEventListener('click',()=>{if(menu.matches(':popover-open'))menu.hidePopover();else open();});
    menu.addEventListener('toggle',event=>{trigger.setAttribute('aria-expanded',event.newState==='open'?'true':'false');if(event.newState==='closed')trigger.removeAttribute('aria-activedescendant');});
    const keydown=event=>{
      if(event.key==='Tab'&&menu.matches(':popover-open')){menu.hidePopover();trigger.focus();return;}
      if(event.key==='Escape'&&menu.matches(':popover-open')){event.preventDefault();event.stopPropagation();menu.hidePopover();trigger.focus();return;}
      if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)&&!(event.target===search&&['Home','End'].includes(event.key))){event.preventDefault();if(!menu.matches(':popover-open')){open();return;}highlight(event.key==='Home'?0:event.key==='End'?visible.length-1:active+(event.key==='ArrowDown'?1:-1));}
      else if((event.key==='Enter'||event.key===' '&&event.target!==search)&&menu.matches(':popover-open')){event.preventDefault();choose(visible[active]);}
    };
    trigger.addEventListener('keydown',keydown);menu.addEventListener('keydown',keydown);search.addEventListener('input',render);native.addEventListener('change',sync);sync();
  });
}
const positionSelectMenus=()=>document.querySelectorAll('.select-menu:popover-open').forEach(menu=>menu.position());
window.addEventListener('resize',positionSelectMenus);document.addEventListener('scroll',positionSelectMenus,true);
function notice(message, error = false) { $('#notice').textContent = message; $('#notice').className = error ? 'error' : ''; $('#notice').hidden = false; }
function showLogin() {
  session = null; generation++; closeModal(); $('#content').replaceChildren(); $('#app').hidden = true; $('#login').hidden = false;
  transactionFilters = {}; auditFilters = {}; merchants = []; games = [];
  rtpFilters = {}; rtpTab = 'merchants';
  $('#login-form').elements.password.value = '';
}
function showApp(result) {
  session = result; $('#login').hidden = true; $('#app').hidden = false;
  $('#identity').textContent = result.user.login_name + ' · ' + roles[result.user.role];
  $('#profile-avatar').textContent = result.user.login_name.slice(0, 1).toUpperCase();
  $('#merchant-nav-label').textContent = tenant() ? '我的商户' : '商户管理';
  $('#workspace-kind').textContent = tenant() ? '商户专属空间' : '运营管理空间';
  document.querySelectorAll('[data-permission]').forEach(node => { node.hidden = !can(node.dataset.permission); });
  document.querySelectorAll('[data-tenant]').forEach(node => { node.hidden = !tenant(); });
  if (view === 'integration' && !tenant()) view = 'overview';
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
  enhanceSelects($('#modal-body'));
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
    el('div', {class: 'welcome-actions'}, tenant() ? button('接入中心 ↗', () => navigate('integration'), 'welcome-action') : null,
      button(tenant() ? '管理我的商户 ↗' : '管理合作商户 ↗', () => navigate('merchants'), 'welcome-action')));
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
  const nodes = [el('div', {class: 'form-grid'}, field('商户号（接口对接）', input('id', value.id, {disabled: true, placeholder: '自动分配，如 GTT000001'})), field('商户名称（主账号登录）', input('name', value.name, {required: true, maxlength: 80})), field('钱包服务地址', input('wallet_url', value.wallet_url, {required: true, type: 'url', placeholder: 'https://wallet.example.com', maxlength: 512})), field('币种', currency)),
    el('p', {class: 'hint'}, '商户名称须唯一，用于主账号登录；改名后使用新名称和原密码。商户号由 GTT 按顺序分配，仅用于接口对接。创建商户时自动开通主账号。'),
    el('p', {class: 'hint'}, 'merchant_secret 由 GTT 自动生成。统一签名使用同一把密钥处理游戏接入、钱包和预派彩请求。创建后即可查看、复制和使用。'),
    el('p', {class: 'hint'}, '钱包地址填写 origin，不带路径。金额精度为 100；创建后币种不可更改。'),
    tenant() ? el('p', {class: 'hint'}, '商户启用状态与游戏授权由 GTT 平台维护。') : el('label', {class: 'check-label'}, input('enabled', 'yes', {type: 'checkbox', checked: value.enabled}), '启用商户'),
    el('h3', {}, '游戏授权'), ...games.map(game => el('label', {class: 'check-label'}, input('games', game.id, {type: 'checkbox', checked: value.games.includes(game.id), disabled: tenant()}), (game.title || 'Game') + ' · ID ' + game.id)),
    el('h3', {}, '平台预派彩'),
    el('label', {class: 'check-label'}, input('prebet_enabled', 'yes', {type: 'checkbox', checked: prebet.enabled}), '开奖前向平台获取整局派彩倍数区间'),
    field('preBetDecision 接口地址', input('prebet_url', prebet.url || '', {type: 'url', autocomplete: 'off', maxlength: 1024, placeholder: '填写合作平台的预下注决策接口地址'})),
    el('p', {class: 'hint'}, '统一签名复用 merchant_secret，预派彩无需另配凭据；是否启用由商户决定。'),
    el('p', {class: 'hint'}, '倍数以整局实际扣款为基数，包含续列和免费旋转。启动请求需提供 external_username。'),
    el('p', {class: 'hint'}, '停用或移除授权会阻止后续游戏请求；已受理的待处理交易仍可由运营人员恢复。')];
  if (!writable) { detail('商户配置', value); return; }
  formModal(editing ? '编辑商户' : '创建商户', nodes, '保存商户', async form => {
    const payload = {name: form.get('name'), wallet_url: form.get('wallet_url'), currency: editing ? value.currency : form.get('currency'),
      enabled: form.get('enabled') === 'yes', games: form.getAll('games').map(Number)};
    if (editing) Object.assign(payload, {id: value.id, version: value.version});
    payload.pre_payout = {enabled: form.get('prebet_enabled') === 'yes', url: form.get('prebet_url').trim()};
    if (tenant()) { delete payload.enabled; delete payload.games; delete payload.currency; }
    const result = await api('merchants/' + (tenant() ? 'profile' : editing ? 'update' : 'create'), payload);
    closeModal(); await loadView(); notice(editing ? '商户配置已保存。' : '商户已创建，商户号：' + result.merchant.id);
    if (result.keys) showMerchantSecret(result.merchant.id, result.keys.merchant_secret, result.login);
  });
}
function merchantSecretControls(secret) {
  const secretInput = input('merchant_secret', secret, {type: 'password', readonly: true, autocomplete: 'off', class: 'merchant-secret-value'});
  const fullSecret = el('textarea', {name: 'merchant_secret_full', readonly: true, hidden: true, rows: 3, spellcheck: false, class: 'merchant-secret-value', 'aria-label': '完整 merchant_secret'}, secret);
  const message = el('p', {class: 'hint', role: 'status'}, '这是服务端接入使用的完整密钥，可随时显示或复制。');
  const toggle = button('显示完整密钥', () => { const show = fullSecret.hidden; secretInput.hidden = show; fullSecret.hidden = !show; toggle.textContent = show ? '隐藏密钥' : '显示完整密钥'; }, 'secondary');
  const copy = button('复制密钥', async () => {
    try { await navigator.clipboard.writeText(secret); message.textContent = '密钥已复制。'; }
    catch { secretInput.hidden = true; fullSecret.hidden = false; toggle.textContent = '隐藏密钥'; fullSecret.select(); message.textContent = '已选中完整密钥，可按 Ctrl+C 复制。'; }
  }, 'primary');
  return el('div', {class: 'merchant-secret-control'}, field('merchant_secret · ' + secret.length + ' 个字符', el('div', {}, secretInput, fullSecret)),
    el('div', {class: 'secret-actions'}, toggle, copy), message);
}
function showMerchantSecret(merchantId, secret, login = null) {
  modal('商户密钥', [login ? el('div', {}, field('商户登录名称', input('login_name', login.name, {readonly: true})), field('初始登录密码（请保存）', input('temporary_password', login.temporary_password, {readonly: true})), el('p', {class: 'hint'}, '使用商户名称登录商户工作台。初始密码仅展示本次，可在账户管理中重置。')) : null,
    field('商户号（接口对接）', input('merchant_id', merchantId, {readonly: true})), merchantSecretControls(secret),
    el('div', {class: 'modal-actions'}, button('关闭', closeModal, 'secondary'))]);
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
    m.games.length ? m.games.join(', ') : '未授权', el('div', {}, 'v' + m.merchant_key_version, el('div', {class: 'subtext mono'}, '指纹：' + m.merchant_key_fingerprint)),
    el('div', {}, button(can('merchants.write') ? '编辑' : '查看', () => merchantEditor(m)), can('users.manage') ? button('添加成员', () => userEditor(null, m)) : null, can('keys.rotate') ? [button('查看密钥', () => merchantSecret(m)), button('重置密钥', () => rotate(m))] : null),
  ])), can('merchants.write') ? button('+ 创建商户', () => merchantEditor(), 'primary') : null);
}
async function secretPanel(merchant) {
  const result = can('keys.rotate') ? await api('merchants/signing/view', {id: merchant.id}) : null;
  const current = result?.merchant || merchant;
  return panel('商户接入密钥', '商户号 + 完整 merchant_secret · 用于游戏、钱包和预派彩签名',
    el('div', {class: 'panel-body'}, field('商户名称 · 主账号登录', input('merchant_login_name', merchant.name, {readonly: true})), field('商户号 · 接口对接', input('merchant_id', merchant.id, {readonly: true})),
      result ? merchantSecretControls(result.keys.merchant_secret) : el('p', {class: 'hint'}, '当前账号没有查看密钥权限，请使用商户管理员账号。'),
      el('p', {class: 'hint'}, '签名算法 HMAC-SHA256 · 密钥版本 v' + current.merchant_key_version)),
    can('keys.rotate') ? button('重置密钥', () => rotate(current), 'secondary') : null);
}
async function integrationPage() {
  if (!tenant()) return merchantPage();
  const [docs, credentials] = await Promise.all([api('integration/docs'), secretPanel(merchants[0])]);
  const endpoints = Object.fromEntries(docs.endpoints.map(endpoint => [endpoint.id, endpoint]));
  const schemaRows = (schema, prefix = '', depth = 0) => {
    if (schema.$ref) schema = docs.schemas[schema.$ref.split('/').at(-1)];
    return Object.entries(schema.properties || {}).flatMap(([name, prop]) => {
      const type = prop.type || (prop.$ref ? prop.$ref.split('/').at(-1) : 'object');
      const description = [prop.description, prop.enum ? '允许值：' + prop.enum.join(' / ') : '', prop.default !== undefined ? '默认：' + prop.default : '', prop.minimum !== undefined ? '最小：' + prop.minimum : '', prop.maximum !== undefined ? '最大：' + prop.maximum : '', prop.maxLength ? '最长：' + prop.maxLength : ''].filter(Boolean).join('；');
      const rows = [[el('code', {}, prefix + name), Array.isArray(type) ? type.join(' / ') : type, (schema.required || []).includes(name) ? '必填' : '可选', description || '—']];
      let nested = prop.items || prop;
      if (nested.anyOf) nested = nested.anyOf.find(option => option.type !== 'null') || {};
      if (depth < 5 && (nested.$ref || nested.properties)) rows.push(...schemaRows(nested, prefix + name + (prop.items ? '[].' : '.'), depth + 1));
      return rows;
    });
  };
  const codeBlock = (value, language, title) => {
    const pre = el('pre', {tabindex: '0'}, el('code', {}, value));
    const copy = button('复制代码', async () => {
      try { await navigator.clipboard.writeText(value); copy.textContent = '已复制'; }
      catch { const range = document.createRange(); range.selectNodeContents(pre); window.getSelection().removeAllRanges(); window.getSelection().addRange(range); copy.textContent = '已选中，请复制'; }
    }, 'doc-copy');
    return el('div', {class: 'doc-code'}, el('div', {class: 'doc-code-heading'}, el('span', {}, title || language.toUpperCase()), copy), pre);
  };
  const renderEndpoint = endpoint => el('article', {class: 'doc-endpoint', id: 'api-' + endpoint.id},
    el('div', {class: 'doc-endpoint-meta'}, badge(endpoint.direction), el('span', {class: 'mono'}, 'HTTP ' + endpoint.status)),
    el('h3', {}, endpoint.title), el('div', {class: 'doc-path'}, el('span', {}, endpoint.method), el('code', {}, endpoint.path)),
    el('p', {}, endpoint.description), el('h4', {}, '请求字段'),
    schemaRows(endpoint.request_schema).length ? table(['字段', '类型', '要求', '说明'], schemaRows(endpoint.request_schema)) : el('p', {}, '请求体为空 JSON 对象 {}。'),
    codeBlock(JSON.stringify(endpoint.request_example, null, 2), 'json', '请求示例'),
    el('h4', {}, '响应字段'), table(['字段', '类型', '要求', '说明'], schemaRows(endpoint.response_schema)),
    codeBlock(JSON.stringify(endpoint.response_example, null, 2), 'json', '成功响应 · HTTP ' + endpoint.status),
    endpoint.notes.length ? el('ul', {class: 'doc-notes'}, endpoint.notes.map(note => el('li', {}, note))) : null);
  const renderBlock = block => {
    if (block.type === 'paragraph') return el('p', {}, block.text);
    if (block.type === 'list') return el('ol', {}, block.items.map(item => el('li', {}, item)));
    if (block.type === 'table') return table(block.headers, block.rows);
    if (block.type === 'code') return codeBlock(block.code, block.language, block.title);
    return renderEndpoint(endpoints[block.endpoint_id]);
  };
  const chapters = docs.sections.map(section => el('section', {class: 'doc-chapter', id: 'guide-' + section.id, tabindex: '-1'},
    el('div', {class: 'doc-chapter-heading'}, el('h2', {}, section.title), el('p', {}, section.summary)), section.blocks.map(renderBlock)));
  const toc = el('aside', {class: 'doc-toc', 'aria-label': '接入文档目录'}, el('p', {class: 'eyebrow'}, 'IN THIS GUIDE'),
    docs.sections.map((section, index) => button(section.title, () => { chapters[index].scrollIntoView({block: 'start'}); chapters[index].focus({preventScroll: true}); }, 'doc-toc-link')),
    el('p', {class: 'hint'}, '接口 v1 · ' + docs.endpoints.length + ' 项接口\n更新于 ' + docs.updated));
  return el('div', {class: 'integration-page'},
    el('div', {class: 'integration-top'}, el('section', {class: 'integration-hero'},
      el('p', {class: 'eyebrow'}, 'GTT / DEVELOPER RESOURCES'), el('h2', {}, '一次接入，', el('br'), '连接完整游戏体验。'),
      el('p', {}, '使用一把 merchant_secret 完成游戏调用、钱包回调与预派彩验签。按同一份规范开发、联调与验收。'),
      el('div', {class: 'doc-context'}, badge(docs.environment), el('span', {}, '规范 v' + docs.version)),
      el('label', {class: 'doc-origin'}, 'GTT API ORIGIN', el('code', {}, docs.gateway_origin)),
      el('label', {class: 'doc-origin doc-play-origin'}, 'GAME PLAY ORIGIN', el('code', {}, docs.play_origin)),
      el('div', {class: 'doc-downloads'}, el('a', {class: 'primary', href: apiRoot + 'integration/guide.md', download: 'GTT-Integration-v1.md'}, '下载接入指南 ↓'),
        el('a', {class: 'secondary', href: apiRoot + 'integration/openapi.json', download: 'GTT-OpenAPI-v1.json'}, 'OpenAPI 3.1 ↓'))), credentials),
    el('div', {class: 'doc-layout'}, toc, el('div', {class: 'doc-content'}, chapters)));
}
async function merchantProfile() {
  const m = merchants[0];
  const property = (label, value) => el('div', {class: 'property'}, el('span', {}, label), el('strong', {}, value));
  return el('div', {}, el('section', {class: 'merchant-banner'}, el('span', {class: 'merchant-avatar'}, m.name.slice(0,1)), el('div', {}, el('p', {class: 'eyebrow'}, 'MERCHANT PROFILE'), el('h2', {}, m.name), el('span', {class: 'mono'}, m.id)), badge(m.enabled ? '合作已启用' : '合作已停用', m.enabled ? 'good' : 'bad')),
    el('div', {class: 'two-column'}, panel('接入配置', '管理你的平台连接', el('div', {class: 'panel-body'}, property('钱包地址', m.wallet_url), property('结算币种', m.currency), property('已授权游戏', m.games.join(', ') || '暂无授权'), property('平台预派彩', m.pre_payout.enabled ? '已启用' : '未启用'), property('决策接口', m.pre_payout.url || '未配置')), can('profile.write') ? button('编辑接入配置 ↗', () => merchantEditor(m), 'secondary') : null),
    await secretPanel(m)),
    panel('接入路径', '从玩家登录到钱包结算', el('div', {class: 'integration-flow'}, ...[['01', '签名启动', '由你的服务端调用 /gtt/v1/games/launch'], ['02', '打开游戏', '直接打开返回的完整 launch_url；本机相对地址拼接本机 GTT 域名'], ['03', '钱包结算', '处理 GTT 的扣款和派奖签名回调']].map(([n,title,desc]) => el('div', {class: 'guide'}, el('span', {class: 'guide-number'}, n), el('div', {}, el('h3', {}, title), el('p', {}, desc)))))));
}
async function gamePage() {
  return el('div', {}, !games.length ? panel('暂无已授权游戏', '联系 GTT 平台开通游戏授权', el('p', {class: 'panel-body muted'}, '游戏开通后将在这里显示，已有商户资料及交易记录可继续查看。')) : null, el('div', {class: 'game-grid'}, games.map(game => el('article', {class: 'game-card'}, el('div', {class: 'game-monogram'}, 'BW'), el('h2', {}, game.title || game.id), el('p', {class: 'muted mono'}, '游戏 ID · ' + game.id), badge('商户网关已接入', 'good'),
    ...Object.entries({'规则版本': game.ruleset_id || game.version || '—', '已授权商户': merchants.filter(m => m.games.includes(game.id)).length, '目标 RTP': game.target_rtp == null ? '尚未设置 / 预派彩模式' : game.target_rtp.toFixed(2) + '%'}).map(([key, value]) => el('div', {class: 'game-info'}, el('span', {class: 'muted'}, key), el('span', {}, value))),
    button('进入 RTP 中心 ↗', () => navigate('rtp'), 'secondary')))),
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
  formModal(editing ? '编辑账户权限' : '创建管理账户', [field(user?.primary ? '商户名称（主账号登录）' : '账号', input('username', user?.login_name || '', {required: true, minlength: 3, maxlength: user?.primary ? 80 : 40, pattern: '[A-Za-z0-9_.\\-]+', disabled: editing})),
    field('角色', select('role', roleOptions, user?.role || (merchant ? 'merchant_admin' : tenant() ? 'merchant_viewer' : 'viewer'))),
    !tenant() ? field('绑定商户', select('merchant_id', [['', '平台账号（不绑定商户）'], ...merchants.map(m => [m.id, m.name + ' · ' + m.id])], user?.merchant_id || merchant?.id || '')) : null,
    el('p', {class: 'hint'}, tenant() ? '商户管理员管理本商户接入与团队；运营可查询和恢复交易；只读仅可查看。' : '商户角色须选择绑定商户；平台角色不绑定商户。商户账号仅能访问本商户的数据。'),
    editing ? el('label', {class: 'check-label'}, input('enabled', 'yes', {type: 'checkbox', checked: user.enabled}), '启用账户') : el('p', {class: 'hint'}, '创建后会生成一次性展示的初始密码。')], '保存账户', async form => {
    const result = await api('users/' + (editing ? 'update' : 'create'), {username: user?.username || form.get('username'), role: form.get('role'), merchant_id: tenant() ? session.user.merchant_id : form.get('merchant_id') || null, enabled: editing ? form.get('enabled') === 'yes' : true});
    closeModal();
    if (editing && user.username === session?.user.username) { showLogin(); return; }
    await loadView(); notice('账户已保存。'); if (result.temporary_password) reveal('账户已创建', {login_name: result.user.login_name, temporary_password: result.temporary_password});
  });
}
function resetPassword(user) {
  formModal('重置账户密码', [el('p', {class: 'hint'}, '重置 ' + user.login_name + ' 的密码，并立即撤销该账户的全部已登录会话。')], '重置密码', async () => {
    const result = await api('users/reset', {username: user.username}); closeModal();
    if (user.username === session.user.username) showLogin();
    reveal('新密码 · 请保存', {login_name: user.login_name, temporary_password: result.temporary_password});
  });
}
async function userPage() {
  const users = (await api('users/list')).users;
  return panel(tenant() ? '商户团队' : '管理账户', '商户主账号使用商户名称登录，团队成员使用独立账号；权限变更会立即撤销已有会话', table(['登录名称', '角色', '所属商户', '状态', '创建时间', '操作'], users.map(user => [el('div', {}, user.login_name, user.primary ? el('div', {class: 'subtext'}, '商户主账号') : null), badge(roles[user.role], 'purple'), user.merchant_id || 'GTT 平台', badge(user.enabled ? '已启用' : '已停用', user.enabled ? 'good' : ''), time(user.created_at), el('div', {}, button('编辑权限', () => userEditor(user)), button('重置密码', () => resetPassword(user)))])), button('+ 创建账户', () => userEditor(), 'primary'));
}
const rtpPercent = value => value == null ? '—' : Number(value).toFixed(2) + '%';
const rtpSource = value => ({platform:'平台默认',merchant:'商户默认',player:'玩家单独配置',legacy:'未标定旧模型'})[value] || value;
function rtpAvailableModels(data) {
  const targets=new Map();
  data.models.filter(model=>model.published).forEach(model=>{if(!targets.has(model.target_bp)||model.created_at>=targets.get(model.target_bp).created_at)targets.set(model.target_bp,model);});
  return Array.from(targets.values()).sort((a,b)=>a.target_bp-b.target_bp);
}
function rtpMerchantEditor(data, merchant) {
  const own=data.policies.find(p=>p.scope==='merchant'&&p.merchant_id===merchant.merchant_id);
  const available=rtpAvailableModels(data), options=available.map(m=>[m.id,(m.target_bp/100).toFixed(2)+'%']);
  const selected=available.find(m=>m.target_bp===merchant.default.target_bp)?.id || options[0]?.[0] || '';
  formModal('修改商户 RTP',[
    el('p',{class:'rtp-editor-merchant'},merchant.name,el('span',{class:'subtext mono'},merchant.merchant_id)),
    field('商户 RTP',select('model_id',options,selected)),
    el('p',{class:'hint'},'未单独设置 RTP 的玩家统一使用此值。保存后从新付费整局生效。'),
    merchant.mode==='prebet'?el('p',{class:'rtp-mode-notice'},'保存将启用 GTT RTP，并关闭当前预派彩。进行中的整局不受影响。'):null,
    el('details',{class:'rtp-editor-more'},el('summary',{},'其他选项'),button('使用平台默认',()=>run(async()=>{await api('rtp/policy',{scope:'merchant',merchant_id:merchant.merchant_id,model_id:null,revision:own?.revision || 0,reason:'商户选择使用平台默认 RTP'});closeModal();await loadView();notice('已使用平台默认 RTP。');})))
  ],'保存 RTP',async form=>{
    await api('rtp/policy',{scope:'merchant',merchant_id:merchant.merchant_id,model_id:form.get('model_id'),revision:own?.revision || 0,activate_rtp:true,mode_revision:merchant.revision,reason:'后台修改商户 RTP'});
    closeModal();await loadView();notice('商户 RTP 已保存，新付费整局生效。');
  });
}
function rtpPolicyEditor(data, scope, mid = '', pid = '') {
  const row = data.policies.find(p => p.scope === scope && p.merchant_id === mid && p.player_id === pid);
  const available=rtpAvailableModels(data), target=data.models.find(m=>m.id===row?.model_id)?.target_bp;
  const options = [['', scope === 'platform' ? '恢复未配置状态' : scope === 'player' ? '使用商户默认' : '使用平台默认'], ...available.map(m => [m.id, (m.target_bp / 100).toFixed(2) + '%'])];
  formModal('设置' + ({platform:'平台',merchant:'商户',player:'玩家'})[scope] + '目标 RTP', [
    el('p', {class:'hint'}, '游戏 1 · Buffalo Win。发布后从新付费整局生效；免费、续列与交易恢复沿用原模型。'),
    scope !== 'platform' ? field('商户', mid?input('merchant_id', mid, {readonly:true}):select('merchant_id',merchants.map(m=>[m.id,m.name+' · '+m.id]))):null,
    scope === 'player' ? field('玩家 ID', input('player_id', pid, {required:true,maxlength:128})) : null,
    field('目标模型', select('model_id', options, available.find(m=>m.target_bp===target)?.id || '')),
    el('p', {class:'hint'}, '目标为长期概率配置。每个玩家的短期实际 RTP 会波动；模型置信区间可在“模型与标定”查看。'),
    field('变更原因', input('reason','',{required:true,minlength:4,maxlength:300}))], '发布目标', async form => {
      const player = scope === 'player' ? form.get('player_id') : '';
      const merchant=scope==='platform'?'':form.get('merchant_id');
      const current = data.policies.find(p => p.scope === scope && p.merchant_id === merchant && p.player_id === player);
      await api('rtp/policy',{scope,merchant_id:merchant,player_id:player,game_id:1,model_id:form.get('model_id') || null,revision:current?.revision || 0,reason:form.get('reason')});
      closeModal(); await loadView(); notice('目标已发布，从下一次新付费整局生效。');
    });
}
function rtpModeEditor(row) {
  const merchant = merchants.find(m => m.id === row.merchant_id);
  formModal('切换概率模式', [field('商户',input('merchant_id',row.merchant_id,{readonly:true})),
    field('模式',select('mode',[['rtp','RTP 模型'],['prebet','平台预派彩']],row.mode)),
    field('预派彩 URL（平台模式时必填）',input('url',merchant?.pre_payout.url || '',{maxlength:1024})),
    el('p',{class:'hint'},'切换会同步修改预派彩开关。已开始的整局仍沿用原模型和预派彩计划；两种模式分别统计。'),
    field('原因',input('reason','',{required:true,minlength:4,maxlength:300}))], '确认切换', async form => {
      await api('rtp/mode',{merchant_id:row.merchant_id,mode:form.get('mode'),url:form.get('url'),revision:row.revision,reason:form.get('reason')});
      closeModal();await loadView();notice('概率模式已更新，新整局生效。');
    });
}
function rtpCalibrationEditor() {
  formModal('创建离线标定任务',[field('目标 RTP（%）',input('target','96.00',{type:'number',min:80,max:99,step:.01,required:true})),
    el('p',{class:'hint'},'完整模拟普通与购买免费流程，独立验证样本至少为 200 万与 20 万付费整局。任务由 RTP worker 执行，通过后还需发布模型。'),
    field('原因',input('reason','',{required:true,minlength:4,maxlength:300}))], '加入标定队列', async form => {
      await api('rtp/job',{target_bp:Math.round(Number(form.get('target'))*100),reason:form.get('reason')});
      closeModal();await loadView();notice('标定任务已排队，可刷新查看阶段和进度。');
    });
}
async function rtpPage() {
  const request = rtpTab==='merchants'?{game_id:1}:{...rtpFilters,game_id:1};
  const days = Number(request.period || 0);delete request.period;
  if (days) {const now = new Date();request.to_at = Math.floor(now.getTime()/1000);request.from_at = Math.floor(Date.UTC(now.getUTCFullYear(),now.getUTCMonth(),now.getUTCDate())/1000) - (days-1)*86400;}
  const data = await api('rtp/read',request);
  const canEditRTP = can('rtp.write');

  const tabs = [['merchants','商户 RTP'],['overview','统计明细'],['players','玩家 RTP'],['models','模型与标定'],['events','修改记录']];
  const tabbar=el('div',{class:'rtp-tabs',role:'tablist','aria-label':'RTP 模块'},tabs.map(([key,name])=>el('button',{type:'button',role:'tab','aria-selected':rtpTab===key,class:rtpTab===key?'active':'',onclick:()=>{rtpTab=key;loadView();}},name)));
  const filters=filterForm([!tenant()?field('商户',select('merchant_id',merchantOptions(),rtpFilters.merchant_id)):null,
    field('玩家 ID',input('player_id',rtpFilters.player_id || '',{placeholder:'查询玩家时指定商户'})),
    field('期间（UTC）',select('period',[['','累计'],['1','今天'],['7','近 7 天'],['30','近 30 天']],rtpFilters.period)),
    field('投注方式',select('play_mode',[['','全部'],['normal','普通'],['buy_free','购买免费']],rtpFilters.play_mode)),
    field('概率模式',select('mode',[['','全部'],['rtp','RTP 模型'],['prebet','平台预派彩'],['legacy','历史未标定']],rtpFilters.mode))],rtpFilters);
  let content;
  const moneyPair = row => [el('span',{class:'mono'},money(row.debit_minor,row)),el('span',{class:'mono'},money(row.credit_minor,row))];
  if(rtpTab==='overview') {
    content=el('div',{},el('div',{class:'rtp-summary-grid'},data.summary.map(row=>el('article',{class:'stat'},el('div',{class:'stat-label'},row.currency+' · 实际 RTP'),el('div',{class:'stat-number'},rtpPercent(row.actual_rtp)),el('p',{class:'stat-foot'},row.rounds+' 个已完成付费整局'),
      el('div',{class:'rtp-metric'},el('span',{},'确认投注'),el('strong',{},money(row.debit_minor,row))),el('div',{class:'rtp-metric'},el('span',{},'确认派彩'),el('strong',{},money(row.credit_minor,row))),
      el('div',{class:'rtp-metric'},el('span',{},'已知配置加权目标'),el('strong',{},rtpPercent(row.weighted_target))),el('p',{class:'hint'},'已知目标投注覆盖 '+rtpPercent(row.target_coverage)+' · '+row.sample_note)))),
      panel('整局结算状态','统计不把未结束整局当作已完成回合',el('div',{class:'panel-body rtp-status-grid'},[['待恢复操作',data.pending_operations],['准备中的整局',data.reserved_rounds],['未结束整局',data.open_rounds],['历史结算时间未知',data.historical_unknown_time],['已作废整局',data.voided_rounds]].map(([name,value])=>el('div',{},el('strong',{},value),el('span',{},name))))),
      panel('每日 RTP 趋势','按整局完成时间归属，最多展示最近 90 个日期／币种组合',table(['日期 UTC','币种','完整整局','投注','派彩','实际 RTP','加权目标'],data.daily.map(row=>[row.date,row.currency,row.rounds,...moneyPair(row),rtpPercent(row.actual_rtp),rtpPercent(row.weighted_target)]))));
  } else if(rtpTab==='merchants') {
    const metric = (label,value) => el('div',{},el('span',{},label),el('strong',{},value));
    const modify = row => button('修改 RTP',()=>rtpMerchantEditor(data,row),'primary');
    if (tenant()) {
      const row=data.merchants[0];
      content=el('section',{class:'rtp-focus panel'},
        el('div',{class:'rtp-focus-heading'},el('div',{},el('p',{class:'eyebrow'},row.name+' · '+row.merchant_id),el('h2',{},'商户 RTP')),badge(row.mode==='prebet'?'当前使用平台预派彩':'GTT RTP')),
        el('div',{class:'rtp-focus-main'},el('div',{},el('div',{class:'rtp-focus-number'},row.mode==='prebet'?'未启用':row.default.target_bp==null?'未设置':rtpPercent(row.default.target_bp/100)),el('p',{},'所有未单独设置 RTP 的玩家，统一使用此值。')),
          canEditRTP?modify(row):badge('只读')),
        el('div',{class:'rtp-focus-stats'},metric('实际 RTP',rtpPercent(row.actual_rtp)),metric('已完成整局',row.rounds),metric('累计投注',money(row.debit_minor,row)),metric('累计派彩',money(row.credit_minor,row))),
        el('div',{class:'rtp-focus-footer'},el('span',{},'保存后新整局生效，进行中的整局不变。'),canEditRTP?button('预派彩设置',()=>rtpModeEditor(row)):null));
    } else {
      content=panel('商户 RTP','每个商户只展示一个默认值，点击右侧即可修改。',table(['商户','商户 RTP','实际 RTP','操作'],data.merchants.map(row=>[
        el('div',{},el('strong',{},row.name),el('div',{class:'subtext mono'},row.merchant_id)),
        el('strong',{class:'rtp-table-target'},row.mode==='prebet'?'平台预派彩':row.default.target_bp==null?'未设置':rtpPercent(row.default.target_bp/100)),rtpPercent(row.actual_rtp),
        el('div',{class:'rtp-row-actions'},canEditRTP?modify(row):badge('只读'),canEditRTP?button('预派彩设置',()=>rtpModeEditor(row)):null)])));
    }
  } else if(rtpTab==='players') {
    content=panel('玩家 RTP','玩家身份由商户号 + 玩家 ID 共同确定；列表最多 200 位，可按玩家 ID 查询',table(['商户 / 玩家','当前目标 / 来源','完整整局','投注','派彩','实际 RTP','加权目标','操作'],data.players.map(row=>[
      el('div',{},el('div',{class:'subtext mono'},row.merchant_id),el('strong',{},row.player_id)),
      el('div',{},data.merchants.find(m=>m.merchant_id===row.merchant_id)?.mode==='prebet'?'平台预派彩':rtpPercent(row.effective.target_bp==null?null:row.effective.target_bp/100),el('div',{class:'subtext'},rtpSource(row.effective.scope))),
      row.rounds,...moneyPair(row),rtpPercent(row.actual_rtp),rtpPercent(row.weighted_target),canEditRTP?button('设置 / 继承',()=>rtpPolicyEditor(data,'player',row.merchant_id,row.player_id)):badge('只读')])));
  } else if(rtpTab==='models') {
    const report=model=>{const rows=Object.entries(model.validation).map(([name,v])=>[name==='normal'?'普通':'购买免费',v.rounds,rtpPercent(v.rtp*100),rtpPercent(v.ci_low*100)+' ～ '+rtpPercent(v.ci_high*100),v.unfinished_rounds]);modal('模型独立验证报告',[el('p',{class:'mono hint'},model.id),table(['方式','完整整局','测得 RTP','99% 近似置信区间','未完成'],rows),el('p',{class:'hint'},'报告采用完整回合 Monte Carlo 与正态近似区间，是统计验证，不是原厂或第三方认证的理论 RTP 证明。配置哈希：'+model.model_hash),button('关闭',closeModal,'secondary')]);};
    const publish=model=>formModal('发布标定模型',[el('p',{},'目标 '+(model.target_bp/100).toFixed(2)+'%'),field('原因',input('reason','',{required:true,minlength:4,maxlength:300}))],'发布模型',async form=>{await api('rtp/publish',{model_id:model.id,reason:form.get('reason')});closeModal();await loadView();notice('模型已发布，可用于配置目标。');});
    content=el('div',{},panel('可用模型','普通与购买免费分别验证；仅已发布模型可以配置给商户和玩家',table(['目标 RTP','模型 ID','状态','验证','操作'],data.models.map(model=>[(model.target_bp/100).toFixed(2)+'%',el('span',{class:'mono'},model.id),badge(model.published?'已发布':'待发布',model.published?'good':'pending'),button('查看报告',()=>report(model)),!model.published&&can('rtp.manage')?button('发布',()=>publish(model)):'—'])),can('rtp.manage')?button('+ 标定新目标',rtpCalibrationEditor,'primary'):null),
      can('rtp.manage')?panel('离线标定任务',(data.worker_online ? '标定服务在线' : '标定服务离线，请启动 RTP worker') + ' · 刷新查看真实进度，失败任务不会生成可发布模型',table(['目标','状态','阶段','进度 / 结果','创建时间'],data.jobs.map(job=>[(job.target_bp/100).toFixed(2)+'%',job.status,(job.progress.mode || '—')+' / '+(job.progress.stage || '等待运行'),job.error || job.result_id || (job.progress.done!=null?Math.round(job.progress.done*100)+'%':'等待下一阶段'),time(job.created_at)]))):null);
  } else {
    content=panel('配置与生效记录','当前配置来源见商户／玩家页，每个新整局的模型版本可在交易详情 rtp 字段核对',table(['时间','商户','操作者','动作','详情'],data.events.map(event=>[time(event.created_at),event.merchant_id || '平台',event.actor,event.action,button('查看',()=>detail('RTP 变更详情',event.details))])));
  }
  const extras=el('div',{class:'rtp-extra-actions'},can('rtp.manage')?button('平台默认 RTP',()=>rtpPolicyEditor(data,'platform')):null,
    canEditRTP&&rtpTab==='players'?button('设置玩家 RTP',()=>rtpPolicyEditor(data,'player',tenant()?data.merchants[0].merchant_id:rtpFilters.merchant_id || ''),'primary'):null);
  const advanced = rtpTab==='overview' || rtpTab==='players';
  return el('div',{class:'rtp-page'},rtpTab==='merchants'?[content,tabbar]:[tabbar,advanced?el('details',{class:'rtp-filter-disclosure'},el('summary',{},'筛选统计'),panel('统计筛选','按整局完成时间统计',filters)):null,extras,content],
    advanced?el('details',{class:'rtp-filter-disclosure'},el('summary',{},'统计口径'),el('p',{class:'hint rtp-definition'},data.definition+' 历史时间未知的回合只计入累计。')):null);

}
async function run(action) { try { await action(); } catch (error) { if (session) notice(error.message, true); else $('#login-error').textContent = error.message; } }
function navigate(next) { if (!Object.keys(pages).includes(next)) return; if(next==='rtp')rtpTab='merchants'; view = next; history.replaceState(null, '', '#' + next); $('#notice').hidden = true; loadView(); }
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
    if (tenant() && session.user.primary && merchants[0]) {
      session.user.login_name = merchants[0].name;
      $('#identity').textContent = session.user.login_name + ' · ' + roles[session.user.role];
    }
    $('#workspace-avatar').textContent = tenant() ? (merchants[0]?.name || 'M').slice(0,1) : 'G';
    const result = await ({overview, merchants: merchantPage, integration: integrationPage, games: gamePage, rtp: rtpPage, transactions: transactionPage, audit: auditPage, users: userPage})[view]();
    if (generation === current && session) { $('#content').replaceChildren(result); enhanceSelects($('#content')); }
  } catch (error) { if (session && generation === current) notice(error.message, true); }
  finally { if (generation === current || !session) $('#refresh-button').disabled = false; }
}
$('#navigation').addEventListener('click', event => { const target = event.target.closest('[data-view]'); if (target) navigate(target.dataset.view); });
window.addEventListener('hashchange', () => { if (session) navigate(location.hash.slice(1)); });
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
async function configurePortal() {
  const response = await fetch('/deployment.json', {credentials: 'same-origin'});
  if (!response.ok) throw new Error('Unable to load deployment configuration.');
  const config = (await response.json()).data;
  portal = config.portal ? config.portal === 'merchant' : portal;
  apiRoot = portal ? '/api/merchant/' : '/api/admin/';
  $('#portal-switch').href = portal ? config.admin_url : config.merchant_url;
  document.querySelectorAll('.sidebar-note a').forEach(link => { link.href = config.merchant_url; });
  document.querySelectorAll('.brand').forEach(link => { link.href = portal ? config.merchant_url : config.admin_url; });
  if (portal) {
    document.title = 'GTT · 商户工作台'; $('#login-title').textContent = '登录商户工作台';
    $('#login-description').textContent = '主账号使用商户名称登录，团队成员使用独立账号。';
    $('#login-form [name=username]').placeholder = '商户名称 / 团队账号';
    $('#login-form [name=username]').maxLength = 80; $('#portal-switch').textContent = '平台控制台 ↗';
  }
}
(async () => { try { await configurePortal(); const response = await fetch(apiRoot + 'me', {credentials: 'same-origin'}); if (!response.ok) { showLogin(); return; } await showApp((await response.json()).data); } catch { showLogin(); $('#login-error').textContent = '连接失败，请检查后台服务。'; } })();
