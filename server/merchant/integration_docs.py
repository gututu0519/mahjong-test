"""Merchant-facing integration contract. One source for the guide and OpenAPI."""
from copy import deepcopy
import hashlib
import json
from urllib.parse import urlsplit

from .common import signature

VERSION = '1.2.0'
UPDATED = '2026-10-28'
LIMIT = 9_000_000_000_000_000
EXAMPLE_ORIGIN = 'https://gtt-gateway.example'


def obj(properties, required=()):
    return {'type': 'object', 'properties': properties, 'required': list(required)}


def ref(name):
    return {'$ref': '#/components/schemas/' + name}


def text_schema(description, **extra):
    return {'type': 'string', 'description': description, **extra}


def integer(description, maximum=LIMIT, minimum=0, **extra):
    return {'type': 'integer', 'minimum': minimum, 'maximum': maximum, 'description': description, **extra}


def identifier_schema(description):
    return text_schema(description, minLength=1, maxLength=128, pattern=r'^[A-Za-z0-9_.:-]+$')


def envelope(schema):
    return obj({'data': schema, 'error': {'type': 'null'}}, ('data', 'error'))


SCHEMAS = {
    'Error': obj({'data': {'type': 'null'}, 'error': obj({'code': text_schema('稳定的业务错误码'), 'message': text_schema('错误说明，不应作为程序分支判断依据')}, ('code', 'message'))}, ('data', 'error')),
    'Balance': obj({'player_id': identifier_schema('商户平台玩家唯一标识'), 'currency': text_schema('商户结算币种，目前新商户为 USD'), 'minor_unit': integer('金额精度，固定为 100', 100, 100), 'balance_minor': integer('钱包余额，整数美分')}, ('player_id', 'currency', 'minor_unit', 'balance_minor')),
    'Mutation': obj({'player_id': identifier_schema('玩家标识'), 'currency': text_schema('商户币种'), 'minor_unit': integer('固定为 100', 100, 100), 'balance_minor': integer('处理后的余额'), 'transaction_id': identifier_schema('原样返回请求交易号'), 'status': text_schema('成功入账状态', enum=['applied']), 'amount_minor': integer('原请求金额'), 'applied_minor': integer('实际变动金额；退款允许为 0'), 'balance_before_minor': integer('处理前余额')}, ('player_id', 'currency', 'minor_unit', 'balance_minor', 'transaction_id', 'status', 'amount_minor', 'applied_minor', 'balance_before_minor')),
    'Launch': obj({'game_id': integer('GTT 数字游戏 ID', minimum=1), 'launch_url': text_schema('生产环境为 play 域名的完整 HTTPS 地址；本机联调可为相对地址，包含会话凭据'), 'expires_at': integer('会话到期时间，Unix 秒'), 'balance_minor': integer('启动时平台余额快照'), 'currency': text_schema('商户币种'), 'minor_unit': integer('固定为 100', 100, 100)}, ('game_id', 'launch_url', 'expires_at', 'balance_minor', 'currency', 'minor_unit')),
    'Game': obj({'id': integer('GTT 数字游戏 ID', minimum=1), 'title': text_schema('游戏展示名称，以实际目录为准'), 'engine_version': text_schema('引擎版本'), 'ruleset_id': text_schema('规则版本'), 'target_rtp': {'type': ['number', 'null'], 'description': '商户默认目标百分比；已发布模型生效时返回数值。未配置或平台预派彩模式为 null；玩家覆盖及进行中整局以会话上下文为准。'}, 'rtp_status': text_schema('active（已配置模型）、prebet（平台预派彩）或 not_calibrated（未配置标定模型）')}, ('id',)),
    'GameResult': obj({'game_id': integer('GTT 数字游戏 ID', minimum=1), 'sid': identifier_schema('本次游戏操作 ID'), 'round_id': identifier_schema('付费整局 ID，续列和免费沿用'), 'engine_version': text_schema('引擎版本'), 'ruleset_id': text_schema('规则版本'), 'wallet': obj({'before_minor': integer('本次操作的钱包前快照'), 'debit_minor': integer('本次扣款'), 'credit_minor': integer('本次派彩'), 'after_minor': integer('钱包后快照')}, ('before_minor', 'debit_minor', 'credit_minor', 'after_minor')), 'outcome': {'type': 'object', 'description': '已提交的游戏事件；结构按游戏规则版本扩展'}}, ('game_id', 'sid', 'round_id', 'wallet', 'outcome')),
    'Operation': obj({'seq': integer('分页序号，按升序返回'), 'operation_id': identifier_schema('游戏操作 ID'), 'player_id': identifier_schema('玩家标识'), 'game_id': integer('GTT 数字游戏 ID', minimum=1), 'status': text_schema('操作终态或处理中状态', enum=['prepared', 'debited', 'settled', 'rejected']), 'error_code': {'type': ['string', 'null']}, 'debit_transaction_id': {'type': ['string', 'null'], 'description': '有扣款时为 operation_id:debit'}, 'credit_transaction_id': {'type': ['string', 'null'], 'description': '有派彩时为 operation_id:credit'}, 'result': {'anyOf': [ref('GameResult'), {'type': 'null'}], 'description': '已保存的游戏结果，尚未完成时可为 null'}}, ('seq', 'operation_id', 'player_id', 'game_id', 'status', 'result')),
    'WalletTransaction': obj({'transaction_id': identifier_schema('钱包交易号'), 'kind': text_schema('交易类型', enum=['debit', 'credit', 'refund']), 'status': text_schema('处理状态', enum=['applied', 'rejected']), 'error_code': {'type': ['string', 'null']}, 'data': {'anyOf': [ref('Mutation'), {'type': 'null'}]}}, ('transaction_id', 'kind', 'status', 'error_code', 'data')),
}
SCHEMAS['WalletHistory'] = obj({**SCHEMAS['Balance']['properties'], 'transactions': {'type': 'array', 'items': ref('WalletTransaction')}}, ('player_id', 'currency', 'minor_unit', 'balance_minor', 'transactions'))

WALLET_BASE = {'player_id': identifier_schema('玩家标识，必须由商户预先建立账户'), 'currency': text_schema('必须与商户币种一致', examples=['USD']), 'minor_unit': integer('固定为 100', 100, 100)}
WALLET_FIELDS = {**WALLET_BASE, 'transaction_id': identifier_schema('商户范围全局唯一的钱包交易号'), 'round_id': identifier_schema('付费整局 ID'), 'amount_minor': integer('非负整数美分，不接受浮点数或布尔值')}
BASE_EXAMPLE = {'player_id': 'player-10001', 'currency': 'USD', 'minor_unit': 100}
BALANCE_EXAMPLE = {**BASE_EXAMPLE, 'balance_minor': 200000}


def endpoint(key, title, direction, path, description, request_schema, request, response_schema, response, status=200, notes=()):
    return {'id': key, 'title': title, 'direction': direction, 'method': 'POST', 'path': path, 'description': description,
            'request_schema': request_schema, 'request_example': request, 'response_schema': response_schema,
            'response_example': response, 'status': status, 'notes': list(notes)}


ENDPOINTS = [
    endpoint('games-list', '获取已授权游戏', '商户 → GTT', '/gtt/v1/games/list', '只返回当前商户获准接入的游戏。当前商户钱包链路支持 Buffalo Win，新增游戏以该接口的实际返回为准。', obj({}), {}, envelope(obj({'games': {'type': 'array', 'items': ref('Game')}}, ('games',))), {'data': {'games': [{'id': 1, 'title': 'Buffalo Win', 'target_rtp': None, 'rtp_status': 'not_calibrated'}]}, 'error': None}),
    endpoint('games-launch', '创建玩家游戏会话', '商户 → GTT', '/gtt/v1/games/launch', '由商户服务端调用。GTT 先查询商户钱包，再返回绑定商户、玩家和游戏的会话链接。', obj({'player_id': identifier_schema('平台玩家唯一标识；不同商户可使用相同玩家号'), 'game_id': integer('已授权的 GTT 数字游戏 ID，Buffalo Win 为 1', minimum=1, default=1), 'language': text_schema('客户端语言', enum=['zh', 'en'], default='en'), 'external_username': text_schema('预派彩平台账号；首次启用预派彩时需要，与 player_id 分开绑定', minLength=1, maxLength=128), 'prebet_type': text_schema('普通付费回合类型；提供时也必须提供 external_username', enum=['NORMAL', 'SURE_WIN'], default='NORMAL')}, ('player_id',)), {'player_id': 'player-10001', 'game_id': 1, 'language': 'en'}, envelope(ref('Launch')), {'data': {'game_id': 1, 'launch_url': '/?mock=1&l=en&ops=SESSION_TOKEN&btt=2', 'expires_at': 1793275200, 'balance_minor': 200000, 'currency': 'USD', 'minor_unit': 100}, 'error': None}, 201, ('会话当前有效期为 24 小时。相同商户、玩家和游戏再次进入会恢复原有游戏状态。', 'launch_url 在生产配置下为 play 域名的完整 HTTPS 地址，直接打开；本机返回相对地址时使用本机 GTT origin 拼接；不要在本地日志或第三方统计中记录会话凭据。', '玩家账户必须已存在于商户钱包。启用预派彩后首次启动提供 external_username，后续沿用已保存映射。')),
]

for action, title, value, before, after in [('debit', '扣除投注费用', 100, 200000, 199900), ('credit', '发放游戏奖金', 250, 199900, 200150), ('refund', '退款或登记取消', 100, 199900, 200000)]:
    fields = dict(WALLET_FIELDS)
    required = list(fields)
    request = {**BASE_EXAMPLE, 'transaction_id': 'round-001:debit' if action == 'debit' else ('step-002:credit' if action == 'credit' else 'refund-001'), 'round_id': 'round-001', 'amount_minor': value}
    if action != 'debit':
        fields['reference_id'] = identifier_schema('原付费回合的扣款交易号，通常为 round_id:debit')
        required.append('reference_id')
        request['reference_id'] = 'round-001:debit'
    response = {**BASE_EXAMPLE, 'transaction_id': request['transaction_id'], 'status': 'applied', 'amount_minor': value, 'applied_minor': value, 'balance_before_minor': before, 'balance_minor': after}
    descriptions = {'debit': '一次付费投注或购买免费对应一笔扣款。余额不足必须持久化拒绝结果。', 'credit': '确认原扣款身份及回合后发放奖金。免费和续列可分步派彩，但不重复扣除投注。', 'refund': '仅可退还尚未成功派奖的原扣款；原扣款未到达时先建立取消标记，阻止迟到扣款。当前 GTT 不因超时自动发起退款。'}
    ENDPOINTS.append(endpoint('wallet-' + action, title, 'GTT → 商户钱包', '/wallet/v1/' + action, descriptions[action], obj(fields, required), request, envelope(ref('Mutation')), {'data': response, 'error': None}, notes=('相同 transaction_id 和业务参数重试必须返回原始回执，不能再次改变余额。', '响应金额必须满足余额等式。扣款／派彩的 applied_minor 等于请求 amount_minor；退款可为 0。')))
ENDPOINTS.insert(2, endpoint('wallet-balance', '查询玩家余额', 'GTT → 商户钱包', '/wallet/v1/balance', '在创建游戏会话、读取游戏状态等场景调用。平台钱包是玩家余额的真实来源。', obj(WALLET_BASE, WALLET_BASE), BASE_EXAMPLE, envelope(ref('Balance')), {'data': BALANCE_EXAMPLE, 'error': None}))
for action in ('get', 'list'):
    fields = dict(WALLET_BASE)
    required = list(WALLET_BASE)
    example = dict(BASE_EXAMPLE)
    if action == 'get':
        fields['transaction_id'] = identifier_schema('需查询的钱包交易号')
        required.append('transaction_id')
        example['transaction_id'] = 'round-001:debit'
    fields['limit'] = integer('最多返回记录数，按 seq 降序；默认 20', 100, 1, default=20)
    if action == 'list':
        example['limit'] = 20
    ENDPOINTS.append(endpoint('wallet-transactions-' + action, '查询指定钱包交易' if action == 'get' else '查询玩家钱包流水', 'GTT → 商户钱包', '/wallet/v1/transactions/' + action,
        '返回该玩家的钱包快照及交易回执。未知 transaction_id 返回空 transactions 数组，不伪造成功入账记录。' if action == 'get' else '按玩家返回最近钱包交易，可用于逐笔核对；此接口没有游标分页参数。',
        obj(fields, required), example, envelope(ref('WalletHistory')), {'data': {**BALANCE_EXAMPLE, 'transactions': []}, 'error': None}))
ENDPOINTS.extend([
    endpoint('operations-list', '查询 GTT 游戏操作', '商户 → GTT', '/gtt/v1/transactions/list', '按 seq 升序查询本商户游戏操作，记录与钱包交易通过交易号关联。', obj({'after_seq': integer('返回 seq 大于此值的记录，首批传 0', default=0), 'limit': integer('每批条数，默认 20', 100, 1, default=20)}), {'after_seq': 0, 'limit': 100}, envelope(obj({'operations': {'type': 'array', 'items': ref('Operation')}}, ('operations',))), {'data': {'operations': [{'seq': 1, 'operation_id': 'round-001', 'player_id': 'player-10001', 'game_id': 1, 'status': 'prepared', 'error_code': None, 'debit_transaction_id': 'round-001:debit', 'credit_transaction_id': None, 'result': None}]}, 'error': None}, notes=('下一批 after_seq 使用上一批最后一条 seq，直到返回空数组。', '此序号适合枚举操作，不是状态变更事件游标。对已发现的 prepared／debited 操作，另行保留 operation_id 并持续恢复或复查，不要只靠递增游标发现终态。')),
    endpoint('operations-retry', '恢复同一游戏操作', '商户 → GTT', '/gtt/v1/transactions/retry', '继续已保存的候选结果与原钱包交易，不重抽牌面。已完成的操作返回原保存结果，明确拒绝的操作返回原拒绝错误。', obj({'operation_id': identifier_schema('待恢复的 GTT 操作 ID')}, ('operation_id',)), {'operation_id': 'round-001'}, envelope(ref('GameResult')), {'data': {'game_id': 1, 'sid': 'round-001', 'round_id': 'round-001', 'engine_version': 'EXAMPLE_VERSION', 'ruleset_id': 'EXAMPLE_RULESET', 'wallet': {'before_minor': 200000, 'debit_minor': 100, 'credit_minor': 0, 'after_minor': 199900}, 'outcome': {'next_phase': 'ready'}}, 'error': None}, notes=('由服务端调度恢复，采用有限次数退避。所有重试重新生成签名头，operation_id 保持不变。', '商户停用后普通接入签名会被拒绝；如需恢复已受理记录，由 GTT 授权运营处理，并确保商户钱包仍接受其有效结算请求。')),
    endpoint('prebet-decision', '整局预下注决策（可选）', 'GTT → 商户决策服务', '/api/v1/callbacks/gtt/preBetDecision', '仅在商户启用预派彩时调用。每个付费整局请求一次逻辑决策，商户返回允许的总派彩倍数区间；该接口本身不扣款或派奖。路径可按商户配置，必须按实际请求路径验签。', obj({'player_name': text_schema('启动时绑定的 external_username，不是 GTT 玩家号', minLength=1, maxLength=128), 'timestamp': integer('业务去重时间戳，Unix 毫秒，重试时固定', minimum=1), 'bet_amount': text_schema('实际扣款对应的主币种金额，固定两位小数字符串', pattern=r'^\d+\.\d{2}$'), 'type': text_schema('付费整局类型；续列／免费不单独请求', enum=['NORMAL', 'SURE_WIN', 'BUY_FREE_SPIN'])}, ('player_name', 'timestamp', 'bet_amount', 'type')), {'player_name': 'platform-alice', 'timestamp': 1793188800000, 'bet_amount': '2.00', 'type': 'NORMAL'}, obj({'code': {'type': 'integer'}, 'data': {'anyOf': [obj({'maxWinMulti': {'type': 'array', 'minItems': 2, 'maxItems': 2, 'items': {'type': ['number', 'string']}}}, ('maxWinMulti',)), {'type': 'null'}]}, 'msg': {'type': ['string', 'null']}}, ('code', 'data', 'msg')), {'code': 0, 'data': {'maxWinMulti': [3, 5]}, 'msg': None}, notes=('成功必须 HTTP 200 且 code 为整数 0；此接口使用 code/data/msg 信封，不使用钱包的 data/error 信封。', '当前调用超时 3 秒、响应最多 16 KiB，不跟随重定向。maxWinMulti 必须有两个有限数值（或数字字符串），边界绝对值不超过 1000000；下限仅允许 -1 或非负值，上限非负；非特殊无限制区间要求上限不小于下限。', '业务毫秒 timestamp 与签名头的秒级时间戳不同；业务去重参数固定，HTTP 签名头每次更新。')),
])

PYTHON_EXAMPLE = '''import hashlib, hmac, json, secrets, time
from urllib.request import Request, urlopen

def sign_headers(merchant_id, merchant_secret, path, body, timestamp=None, nonce=None):
    timestamp = str(int(time.time()) if timestamp is None else timestamp)
    nonce = secrets.token_hex(16) if nonce is None else nonce
    canonical = "\\n".join(("POST", path, timestamp, nonce,
                           hashlib.sha256(body).hexdigest()))
    signature = hmac.new(merchant_secret.encode("utf-8"),
                         canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return {"Content-Type": "application/json", "X-GTT-Merchant": merchant_id,
            "X-GTT-Timestamp": timestamp, "X-GTT-Nonce": nonce,
            "X-GTT-Signature": signature}

def post(origin, merchant_id, merchant_secret, path, payload):
    # 签名之后，发送同一份 body 字节；不要再次序列化。
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")
    request = Request(origin.rstrip("/") + path, data=body,
                      headers=sign_headers(merchant_id, merchant_secret, path, body),
                      method="POST")
    with urlopen(request, timeout=10) as response:
        return json.load(response)

# 从受保护的服务端配置读取真实商户号、密钥与 GTT origin 后调用：
# result = post(origin, merchant_id, merchant_secret, "/gtt/v1/games/list", {})
# HTTP 非 2xx 时还应解析 HTTPError 响应体，按文档错误码分类处理。
'''
NODE_EXAMPLE = '''import { createHash, createHmac, randomBytes, timingSafeEqual } from 'node:crypto';

export function signHeaders(merchantId, merchantSecret, path, body,
                            timestamp = String(Math.floor(Date.now() / 1000)),
                            nonce = randomBytes(16).toString('hex')) {
  const canonical = ['POST', path, timestamp, nonce,
    createHash('sha256').update(body).digest('hex')].join('\\n');
  return { 'Content-Type': 'application/json', 'X-GTT-Merchant': merchantId,
    'X-GTT-Timestamp': timestamp, 'X-GTT-Nonce': nonce,
    'X-GTT-Signature': createHmac('sha256', Buffer.from(merchantSecret, 'utf8'))
      .update(canonical, 'utf8').digest('hex') };
}

export function signatureMatches(expected, supplied) {
  if (!/^[0-9a-f]{64}$/.test(supplied)) return false;
  return timingSafeEqual(Buffer.from(expected, 'hex'), Buffer.from(supplied, 'hex'));
}

export async function post(origin, merchantId, merchantSecret, path, payload) {
  const body = Buffer.from(JSON.stringify(payload), 'utf8');
  const response = await fetch(origin.replace(/\\/$/, '') + path, {
    method: 'POST', redirect: 'error', signal: AbortSignal.timeout(10000),
    headers: signHeaders(merchantId, merchantSecret, path, body), body
  });
  const result = await response.json();
  if (!response.ok) {
    const error = new Error(result.error?.message || `HTTP ${response.status}`);
    error.code = result.error?.code; error.status = response.status;
    throw error;
  }
  return result;
}

// body 为已确定的 UTF-8 请求体。签名后把同一个 body 交给 HTTP 客户端：
// const body = Buffer.from(JSON.stringify({player_id:'player-10001',
//   game_id:1, language:'en'}), 'utf8');
// const headers = signHeaders(merchantId, merchantSecret, '/gtt/v1/games/launch', body);
// 处理非 2xx 响应，勿将 merchantSecret、签名头或会话链接写入日志。
'''
VECTOR = {'merchant_id': 'GTT000001', 'merchant_secret': '0123456789abcdef' * 4, 'method': 'POST', 'path': '/gtt/v1/games/launch', 'timestamp': '1700000000', 'nonce': '0123456789abcdef0123456789abcdef', 'body': '{"game_id":1,"language":"en","player_id":"player-10001"}'}
VECTOR['body_sha256'] = hashlib.sha256(VECTOR['body'].encode()).hexdigest()
VECTOR['signature'] = signature(VECTOR['merchant_secret'], 'POST', VECTOR['path'], VECTOR['timestamp'], VECTOR['nonce'], VECTOR['body'].encode())


def paragraph(value): return {'type': 'paragraph', 'text': value}
def listing(items): return {'type': 'list', 'items': items}
def table(headers, rows): return {'type': 'table', 'headers': headers, 'rows': rows}
def code(language, value, title=''): return {'type': 'code', 'language': language, 'code': value, 'title': title}
def api_blocks(ids): return [{'type': 'endpoint', 'endpoint_id': value} for value in ids]

SECTIONS = [
    {'id': 'start', 'title': '01 · 接入概览与准备', 'summary': '明确系统职责，完成第一条签名请求。', 'blocks': [paragraph('商户名称是后台主账号的登录名称；商户号按 GTT000001、GTT000002 顺序分配，用于请求头 X-GTT-Merchant。后台密码、商户号和 merchant_secret 各有用途。GTT 提供游戏客户端、游戏结果与操作记录；商户维护玩家身份、账户余额及钱包账本。玩家浏览器只接收短期游戏会话，不持有 merchant_secret，也不直接操作钱包。'), table(['事项', '接入约定'], [['接口版本', 'v1；当前商户钱包链路接入 Buffalo Win，数字游戏 ID 为 1；后续编号按顺序追加且不重排。授权与游戏信息以 games/list 为准。'], ['结算币种', '新商户仅 USD；minor_unit 固定 100，200000 表示 2000.00 USD。'], ['地址与环境', '下方显示当前配置的 API origin 和游戏 play origin。服务后端监听本机地址；生产配置通过 HTTPS 反向代理按域名分流，域名访问、证书与回调可达性应在联合验收时确认。示例域名不是真实服务地址。'], ['商户准备', '后台中的商户号（如 GTT000001）与 64 字符 merchant_secret；钱包 HTTPS origin；预先建立的玩家账户；已启用游戏授权。'], ['可选预派彩', '只有启用时才提供决策 URL 与 external_username 映射，不另发 Token 或第二把密钥。']]), listing(['在接入中心复制商户号与完整 merchant_secret，保存到商户服务端配置。', '实现钱包接口，先验证签名、nonce 去重及 balance 响应格式。', '调用 games/list，确认实际授权。', '用已有钱包账户调用 games/launch，将返回的完整 launch_url 交给该玩家；仅在本机返回相对地址时拼接本机 GTT origin。', '完成普通投注、购买免费和免费／续列流程，核对钱包交易及 GTT 操作。', '模拟超时、重复请求与重启，按原操作恢复，确认没有重复扣款或派奖。'])]},
    {'id': 'authentication', 'title': '02 · 统一签名与验签', 'summary': '一把密钥，四个请求头，所有方向使用相同规则。', 'blocks': [table(['项目', '规则'], [['请求方法', '全部 POST，Content-Type: application/json；无 URL 查询参数，GTT 请求体最多 16 KiB。'], ['JSON', '使用 UTF-8；禁止重复字段、NaN、Infinity。签名依据实际发送的原始字节，不要求 JSON 键排序。'], ['密钥编码', 'merchant_secret 是 64 个十六进制字符的文本。HMAC key 使用该文本的 UTF-8 字节，不做 hex 解码。'], ['签名路径', '只使用实际 URL 的 path，包含开头 /，不含 scheme、host、fragment 或 query。'], ['时间与去重', '签名时间戳为 10 位 Unix 秒，容差 ±300 秒；nonce 为 16–64 位 [A-Za-z0-9_-]，每次请求重新生成并持久化去重。']]), table(['请求头', '内容'], [['X-GTT-Merchant', 'GTT 分配的商户号，格式 GTT 加六位数字，例如 GTT000001'], ['X-GTT-Timestamp', 'Unix 秒时间戳，例如 1700000000（测试向量）'], ['X-GTT-Nonce', '本次请求唯一随机串'], ['X-GTT-Signature', 'HMAC-SHA256 小写十六进制，64 字符']]), code('text', 'POST\n<实际请求路径>\n<秒级 timestamp>\n<nonce>\n<SHA256(body) 的小写十六进制>', '签名原文：五行使用 LF 连接，最后一行之后没有换行'), paragraph('对原文 UTF-8 字节以 merchant_secret 文本的 UTF-8 字节计算 HMAC-SHA256。接收端先验证商户、时间戳及格式，再恒定时间比较签名，并原子记录 nonce；验签后才执行余额更新。GTT 的 nonce 保留到签名不可能再次通过时间检查为止；双方都应将去重持久化，不能仅放在进程内存。'), code('python', PYTHON_EXAMPLE, 'Python 签名与调用参考'), code('javascript', NODE_EXAMPLE, 'Node.js 签名与恒定时间比较'), paragraph('验签示例中的比较函数只负责签名相等判断，商户还需实现时间窗口、商户绑定、内容大小检查和持久化 nonce 去重。签名重放防护与钱包 transaction_id 业务幂等是两层独立约束。'), code('json', json.dumps(VECTOR, ensure_ascii=False, indent=2), '固定签名测试向量（仅离线计算；过期时间戳不可用于在线请求）')]},
    {'id': 'games', 'title': '03 · 游戏目录与启动', 'summary': '服务端创建会话，浏览器打开 GTT 返回的游戏地址。', 'blocks': api_blocks(['games-list', 'games-launch'])},
    {'id': 'wallet', 'title': '04 · 钱包回调接口', 'summary': '由商户实现，GTT 使用统一密钥调用。', 'blocks': [paragraph('钱包 origin 只填写协议、主机和端口，不含路径；GTT 在其后拼接以下固定路径。回调要求 HTTPS，本机 loopback 联调可用 HTTP，不跟随重定向。当前钱包 HTTP 调用超时为 3 秒，响应最大 64 KiB；商户应在此时间预算内完成原子入账并返回。以下各接口示例独立，退款示例不表示可在成功派奖之后退款。')] + api_blocks(['wallet-balance', 'wallet-debit', 'wallet-credit', 'wallet-refund', 'wallet-transactions-get', 'wallet-transactions-list'])},
    {'id': 'settlement', 'title': '05 · 幂等与结算责任', 'summary': '余额与交易去重必须在同一数据库事务中提交。', 'blocks': [table(['约束', '必须遵守的行为'], [['交易号唯一', 'transaction_id 在单商户范围全局唯一，不可跨玩家或交易类型复用；同号同参返回原结果，同号异参返回 TRANSACTION_CONFLICT。'], ['明确拒绝', '余额不足等拒绝也持久化；同一交易号不能因后来充值而由拒绝变成成功。'], ['回执一致', 'debit: after = before - applied；credit/refund: after = before + applied。debit/credit 的 applied 必须等于请求金额。'], ['操作与回合', '一次 GTT 操作最多一次 debit 和一次 credit；续列／免费操作可以只有派彩。原付费整局的 round_id 与扣款引用沿用，不把每个免费步骤当成新投注。'], ['退款取消', '核对原交易玩家、币种、回合与金额，已成功派奖不可用简单退款撤销。原扣款未到达时先登记取消，迟到扣款必须拒绝。'], ['不确定结果', '超时、丢失响应、畸形回执并不证明未入账。保留原 ID 与请求参数，查询／重试原交易，不换号重扣，也不自动退款。']]), paragraph('对账按商户、玩家、round_id、transaction_id、金额和状态逐项核对。GTT 操作中的钱包前后余额是回调时快照；商户同时发生其他业务时，不能把不同操作的余额快照当成全局连续余额证明。当前没有自动对账差异报表，商户可将 GTT 操作记录与自己的钱包账本关联。')]},
    {'id': 'prebet', 'title': '06 · 可选预下注决策', 'summary': '决策约束整局派彩，实际入账仍走钱包回调。', 'blocks': api_blocks(['prebet-decision']) + [table(['maxWinMulti', '整局总派彩含义'], [['[0,0]', '整局总派彩为 0'], ['[-1,10]', '不指定下限，不超过实际扣款 10 倍'], ['[5,10]', '实际扣款的 5～10 倍，包含边界'], ['[10,10]', '恰好 10 倍'], ['[0.9,1.1]', '0.9～1.1 倍'], ['[-1,0]', '特殊约定：不限制派彩，并非最高 0 倍']]), paragraph('倍数基数为本局实际扣款，购买免费以购买费用为基数；总派彩包含全部续列、免费旋转及追加，是总派彩而非净盈利。投注 2.00 USD 返回 [3,5] 表示整局总派彩为 6.00～10.00 USD。'), paragraph('同一逻辑决策使用固定 player_name + timestamp + bet_amount + type 去重；超时重试返回原决策，不重新抽取区间。NORMAL／SURE_WIN 用于普通付费，BUY_FREE_SPIN 用于购买免费，免费与续列沿用整局决策，不单独发送零金额 FREE_SPIN 请求。'), paragraph('响应超时、非 200 或无效区间时不自动退回无约束开奖。GTT 无法在现有规则内找到满足区间的合法回合时返回 PREBET_RANGE_UNREACHABLE，不扣款、不截断中奖、不擅自放宽区间。业务 code 3202 表示明确余额不足且未扣款；重新尝试可使用新业务时间戳，其他不确定决策保持原去重参数恢复。')]},
    {'id': 'operations', 'title': '07 · 操作查询与恢复', 'summary': '使用原 operation_id 继续，不重建游戏结果。', 'blocks': api_blocks(['operations-list', 'operations-retry']) + [table(['状态', '解释与下一步'], [['prepared', '候选结果已保存；可能尚未扣款或扣款响应未知，恢复同一 operation_id。'], ['debited', '扣款已确认，等待结算确认；重试原操作，不重新扣费。'], ['settled', '钱包结算与游戏状态已提交；再次恢复返回保存结果。'], ['rejected', '已明确拒绝，游戏状态未推进；不得将该 ID 改为一笔新交易。']]), paragraph('当前恢复由玩家读取状态或商户／GTT 运营请求触发，没有后台定时重试线程。商户可对自己的待处理操作建立有限次数、指数退避的恢复队列；错误持续时告警并保留原业务标识。超时只说明结果未知，不是退款依据。')]},
    {'id': 'errors', 'title': '08 · 错误码与处理策略', 'summary': '区分参数错误、明确拒绝和不确定结果。', 'blocks': [code('json', '{"data":null,"error":{"code":"AUTH_INVALID","message":"Invalid signature."}}', 'GTT／钱包错误信封；预派彩使用独立 code/data/msg'), table(['HTTP / code', '处理建议'], [['400 / BAD_REQUEST、INVALID_ARGUMENT、GAME_ID_INVALID', '修正请求格式、标识和字段，不盲目重试同一非法请求。'], ['401 / AUTH_INVALID', '核对商户号、完整密钥、实际 body 字节、path、服务器时间及 key 文本编码。'], ['409 / AUTH_REPLAY', '生成新的秒级时间戳、nonce 和签名；业务交易号与参数保持不变。'], ['403 / GAME_FORBIDDEN', '联系 GTT 核对游戏授权；商户停用时为 401 / AUTH_INVALID。'], ['409 / INSUFFICIENT_BALANCE', '明确拒绝；不推进局面、不重扣同一交易号。'], ['409 / TRANSACTION_CONFLICT、IDEMPOTENCY_CONFLICT', '停止冲突请求并排查 ID 复用，不以新 ID 掩盖重复结算。'], ['409 / STALE_STATE、OPERATION_PENDING', '读取最新游戏状态，先恢复待处理操作。'], ['404 / ACCOUNT_NOT_FOUND；409 / CURRENCY_MISMATCH', '钱包中核对玩家账户与商户币种；GTT 包装钱包的明确拒绝时返回 409。'], ['400 / LANGUAGE_INVALID、PREBET_PLAYER_REQUIRED、PREBET_TYPE_INVALID', '修正语言或预派彩玩家映射与启动类型。'], ['409 / PREBET_3202；503 / PREBET_<业务码>', '平台业务拒绝；3202 为余额不足，其他业务码按平台原因修复后以原参数恢复。'], ['503 / WALLET_UNCERTAIN', '保留原 operation_id／transaction_id，查询或恢复原操作。'], ['503 / PREBET_UNCERTAIN、PREBET_RANGE_INVALID', '保持原逻辑决策去重参数，修复回调／区间后恢复。'], ['503 / PREBET_RANGE_UNREACHABLE', '当前区间无法生成合法回合，未扣款；与平台协商可实现区间。'], ['413 / BODY_TOO_LARGE；415 / CONTENT_TYPE', '缩小 JSON 请求体或设置 application/json。']])]},
    {'id': 'acceptance', 'title': '09 · 联调验收清单', 'summary': '完成以下场景后再安排上线验收。', 'blocks': [table(['场景', '预期结果'], [['固定签名向量', 'Python、Node.js 或商户语言计算出相同 body hash 与签名。'], ['签名篡改／过期／重放', '请求被拒绝；nonce 持久化，进程重启后也不能重放有效旧请求。'], ['已授权／未授权游戏', '目录与启动遵守商户授权，未授权不能进入。'], ['未知玩家／余额不足', '未知账户不能启动；不足余额不会推进游戏或产生成功扣款。'], ['普通、购买免费、续列、免费追加', '一笔实际购买成本只扣一次，整局引用一致，逐步派彩与钱包账本相符。'], ['重复 debit／credit', '同号同参回原结果，余额只变动一次；异参返回冲突。'], ['已入账但响应丢失', '重试原 ID 得到原回执，不重抽结果、不重复入账。'], ['双方重启与并发恢复', '待处理操作可继续，结果和账本不重复。'], ['预派彩开启／关闭与失败', '关闭时无决策调用；开启时决策去重，失败或不可达区间不扣款。'], ['密钥重置', '新密钥用于所有请求；旧密钥立即失效，双方服务端同步更新。'], ['逐笔对账', '商户／玩家／回合／交易号／金额／终态可关联，明确未结束回合口径。']]), paragraph('排障资料提供商户号、operation_id／transaction_id、UTC 时间、接口路径、HTTP 状态和错误码。不要提交 merchant_secret、签名头、完整玩家会话链接或含这些内容的访问日志。当前未提供自动对账、自动后台重试和额外游戏商户钱包接入的承诺，实际范围以本版本和联合验收为准。')]},
]


def gateway_origin(value=None):
    parsed = urlsplit(value or '')
    return (value or '').rstrip('/') if parsed.scheme in ('http', 'https') and parsed.netloc and parsed.path in ('', '/') and not parsed.query and not parsed.fragment and not parsed.username and not parsed.password else EXAMPLE_ORIGIN


def document(origin=None, play_origin=None):
    result = {'title': 'GTT 商户接入规范', 'version': VERSION, 'updated': UPDATED, 'gateway_origin': gateway_origin(origin), 'play_origin': gateway_origin(play_origin or origin),
            'environment': '本机联调' if urlsplit(gateway_origin(origin)).hostname in ('127.0.0.1', 'localhost', '::1') else '以 GTT 提供的接入环境为准',
            'sections': deepcopy(SECTIONS), 'endpoints': deepcopy(ENDPOINTS), 'schemas': deepcopy(SCHEMAS)}
    if play_origin:
        launch = next(endpoint for endpoint in result['endpoints'] if endpoint['id'] == 'games-launch')
        launch['response_example']['data']['launch_url'] = gateway_origin(play_origin) + launch['response_example']['data']['launch_url']
    return result


def schema_rows(schema, prefix='', depth=0):
    if '$ref' in schema:
        schema = SCHEMAS[schema['$ref'].rsplit('/', 1)[-1]]
    rows = []
    for name, prop in schema.get('properties', {}).items():
        type_name = prop.get('type', prop.get('$ref', 'object').rsplit('/', 1)[-1])
        details = [prop.get('description', '')]
        if 'enum' in prop:
            details.append('允许值：' + ' / '.join(map(str, prop['enum'])))
        for key, label in [('default', '默认'), ('minimum', '最小'), ('maximum', '最大'), ('maxLength', '最长')]:
            if key in prop:
                details.append(label + '：' + str(prop[key]))
        rows.append([prefix + name, type_name if isinstance(type_name, str) else ' / '.join(type_name),
                     '必填' if name in schema.get('required', []) else '可选', '；'.join(filter(None, details)) or '—'])
        nested = prop.get('items', prop)
        if 'anyOf' in nested:
            nested = next((v for v in nested['anyOf'] if v.get('type') != 'null'), {})
        if depth < 5 and ('$ref' in nested or 'properties' in nested):
            rows.extend(schema_rows(nested, prefix + name + ('[].' if 'items' in prop else '.'), depth + 1))
    return rows


def markdown(origin=None, play_origin=None):
    doc = document(origin, play_origin)
    parts = [f"# {doc['title']}", f"版本 {VERSION} · 更新 {UPDATED} · API origin：{doc['gateway_origin']} · Play origin：{doc['play_origin']}", '> 本文档不包含任何商户真实密钥；所有标识、金额和签名向量均为示例。']
    index = {e['id']: e for e in doc['endpoints']}
    def render_table(headers, rows):
        esc = lambda x: str(x).replace('|', '\\|').replace('\n', '<br>')
        return '\n'.join(['| ' + ' | '.join(map(esc, headers)) + ' |', '| ' + ' | '.join('---' for _ in headers) + ' |', *['| ' + ' | '.join(map(esc, row)) + ' |' for row in rows]])
    for section in doc['sections']:
        parts += ['## ' + section['title'], section['summary']]
        for block in section['blocks']:
            kind = block['type']
            if kind == 'paragraph': parts.append(block['text'])
            elif kind == 'list': parts.append('\n'.join(f'{i}. {v}' for i, v in enumerate(block['items'], 1)))
            elif kind == 'table': parts.append(render_table(block['headers'], block['rows']))
            elif kind == 'code': parts += [block['title'], '```' + block['language'] + '\n' + block['code'] + '\n```']
            elif kind == 'endpoint':
                e = index[block['endpoint_id']]
                parts += ['### ' + e['title'], f"**{e['method']} {e['path']}** · {e['direction']}", e['description'], render_table(['请求字段', '类型', '要求', '说明'], schema_rows(e['request_schema'])) if e['request_schema'].get('properties') else '请求体：空 JSON 对象 `{}`。', '请求示例：\n```json\n' + json.dumps(e['request_example'], ensure_ascii=False, indent=2) + '\n```', f"成功响应 HTTP {e['status']}：\n```json\n" + json.dumps(e['response_example'], ensure_ascii=False, indent=2) + '\n```']
                parts.append('响应字段：\n' + render_table(['字段', '类型', '要求', '说明'], schema_rows(e['response_schema'])))
                if e['notes']: parts.append('\n'.join('- ' + n for n in e['notes']))
    return '\n\n'.join(parts) + '\n'


def openapi(origin=None, play_origin=None):
    paths = {}
    for e in document(origin, play_origin)['endpoints']:
        operation = {'operationId': e['id'].replace('-', '_'), 'summary': e['title'], 'description': e['description'] + '\n\n' + '\n'.join(e['notes']),
                     'tags': [e['direction']], 'requestBody': {'required': True, 'content': {'application/json': {'schema': e['request_schema'], 'example': e['request_example']}}},
                     'responses': {str(e['status']): {'description': '成功响应', 'content': {'application/json': {'schema': e['response_schema'], 'example': e['response_example']}}}, 'default': {'description': '鉴权、参数错误或未完成的结果，按错误码处理', 'content': {'application/json': {'schema': ref('Error')}}}}}
        if e['direction'] != '商户 → GTT':
            operation['servers'] = [{'url': 'https://wallet.merchant.example' if '钱包' in e['direction'] else 'https://decision.merchant.example', 'description': '商户提供的服务地址占位符，需替换为实际地址'}]
        paths[e['path']] = {'post': operation}
    headers = {'Merchant': 'X-GTT-Merchant', 'Timestamp': 'X-GTT-Timestamp', 'Nonce': 'X-GTT-Nonce', 'Signature': 'X-GTT-Signature'}
    return {'openapi': '3.1.0', 'info': {'title': 'GTT Merchant Integration API', 'version': VERSION, 'description': '统一 merchant_secret / HMAC-SHA256。四个请求头必须同时提供，签名算法见配套指南。商户钱包和预派彩 operation 的 server 为占位符。'},
            'servers': [{'url': gateway_origin(origin), 'description': 'GTT 接入地址，以交付环境为准'}],
            'security': [{key: [] for key in headers}], 'paths': paths,
            'components': {'securitySchemes': {key: {'type': 'apiKey', 'in': 'header', 'name': name} for key, name in headers.items()}, 'schemas': deepcopy(SCHEMAS)},
            'x-gtt-play-origin': gateway_origin(play_origin or origin), 'x-gtt-signature': {'algorithm': 'HMAC-SHA256', 'keyEncoding': 'UTF-8 text; do not hex-decode merchant_secret', 'canonical': 'METHOD\\nPATH\\nTIMESTAMP\\nNONCE\\nSHA256(BODY)', 'testVector': deepcopy(VECTOR)}}
