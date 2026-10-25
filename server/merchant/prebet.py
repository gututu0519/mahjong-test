"""Platform preBetDecision transport and full-round planning, before any wallet debit."""
import copy
import hashlib
import json
import secrets
import time
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from server.core.contracts import ServiceError
from .common import encode, read_object
from .control import wallet_origin
from .wallet import NoRedirect


def prebet_url(value):
    if not isinstance(value, str) or len(value) > 1024 or any(ord(c) < 33 for c in value):
        raise ServiceError('PREBET_CONFIG_INVALID', '请输入有效的平台预下注接口地址。')
    parsed = urlsplit(value)
    wallet_origin(parsed.scheme + '://' + parsed.netloc)
    if not parsed.path.startswith('/') or parsed.query or parsed.fragment:
        raise ServiceError('PREBET_CONFIG_INVALID', '平台接口地址须包含路径，且不能包含查询参数。')
    return value


def external_username(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 128 or value != value.strip() or any(ord(c) < 32 for c in value):
        raise ServiceError('PREBET_PLAYER_REQUIRED', '启用预派彩时，启动请求须提供玩家的 external_username。')
    return value


def multiplier_range(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ServiceError('PREBET_RANGE_INVALID', 'maxWinMulti 必须是两个数字组成的区间。', 503)
    try:
        if any(type(v) not in (int, float, str) for v in value):
            raise ValueError()
        low, high = (Decimal(str(v)) for v in value)
        if not low.is_finite() or not high.is_finite() or low < -1 or (-1 < low < 0) or high < 0 or (low >= 0 and high < low):
            raise ValueError()
        if max(abs(low), high) > 1_000_000:
            raise ValueError()
    except (ValueError, InvalidOperation):
        raise ServiceError('PREBET_RANGE_INVALID', '平台返回了无效的派彩倍数区间。', 503) from None
    return [str(low), str(high)]


class PreBetClient:
    def __init__(self, timeout=3):
        self.timeout = timeout
        self.opener = build_opener(NoRedirect)

    def decision(self, settings, payload):
        # Authentication is inserted only for transmission, never persisted in
        # decision records, browser responses, error messages or request logs.
        body = encode({**payload, 'operator_token': settings['operator_token'], 'secret_key': settings['secret_key']}).encode()
        request = Request(prebet_url(settings['url']), data=body, headers={'Content-Type': 'application/json'}, method='POST')
        try:
            try:
                response = self.opener.open(request, timeout=self.timeout)
            except HTTPError as error:
                response = error
            with response:
                raw = response.read(16385)
                if response.status != 200 or len(raw) > 16384:
                    raise ValueError()
                result = read_object(raw)
            if not isinstance(result, dict) or type(result.get('code')) is not int:
                raise ValueError()
            if result['code'] != 0:
                code = result['code']
                # Preserve platform business codes, not remotely supplied text (which
                # may contain credentials or other private platform details).
                raise ServiceError('PREBET_' + str(code), '平台预下注决策失败（code ' + str(code) + '）。', 409 if code == 3202 else 503)
            data = result.get('data')
            return {'maxWinMulti': multiplier_range(data.get('maxWinMulti') if isinstance(data, dict) else None)}
        except ServiceError:
            raise
        except (OSError, URLError, ValueError, TypeError, KeyError):
            raise ServiceError('PREBET_UNCERTAIN', '平台预下注响应未知；将使用原时间戳和参数重试，尚未扣款。', 503) from None


class RoundPlanner:
    def __init__(self, provider):
        self.provider = provider
        self.client = PreBetClient()
        self.max_attempts = 3000
        self.max_steps = 256
        with provider.connection(True) as db:
            columns = {row['name'] for row in db.execute('PRAGMA table_info(prebet_rounds)')}
            if 'fp_request_json' in columns:
                db.execute('ALTER TABLE prebet_rounds RENAME COLUMN fp_request_json TO prebet_request_json')
        with provider.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS merchant_players (
                    merchant_id TEXT NOT NULL,player_id TEXT NOT NULL,external_username TEXT NOT NULL,
                    prebet_type TEXT NOT NULL DEFAULT 'NORMAL',
                    PRIMARY KEY(merchant_id,player_id),UNIQUE(merchant_id,external_username));
                CREATE TABLE IF NOT EXISTS prebet_rounds (
                    id TEXT PRIMARY KEY,merchant_id TEXT NOT NULL,player_id TEXT NOT NULL,game_id TEXT NOT NULL,
                    initial_sid TEXT NOT NULL,request_json TEXT NOT NULL,initial_state_json TEXT NOT NULL,
                    bet_json TEXT NOT NULL,prebet_request_json TEXT NOT NULL,policy_json TEXT,plan_json TEXT,
                    created_at INTEGER NOT NULL,error_code TEXT);
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_prebet_start
                    ON prebet_rounds(merchant_id,player_id,game_id,initial_sid) WHERE error_code IS NULL;
            ''')

    def bind_player(self, merchant_id, player_id, name, kind='NORMAL'):
        name = external_username(name)
        if kind not in ('NORMAL', 'SURE_WIN'):
            raise ServiceError('PREBET_TYPE_INVALID', '启动 prebet_type 仅支持 NORMAL 或 SURE_WIN；购买免费自动使用 BUY_FREE_SPIN。')
        with self.provider.connection(True) as db:
            old = db.execute('SELECT external_username FROM merchant_players WHERE merchant_id=? AND player_id=?', (merchant_id, player_id)).fetchone()
            if old and old[0] != name:
                raise ServiceError('PREBET_PLAYER_CONFLICT', '该玩家已绑定不同的平台external_username。', 409)
            other = db.execute('SELECT player_id FROM merchant_players WHERE merchant_id=? AND external_username=?', (merchant_id, name)).fetchone()
            if other and other[0] != player_id:
                raise ServiceError('PREBET_PLAYER_CONFLICT', '平台 external_username 已绑定其他玩家。', 409)
            db.execute('INSERT OR IGNORE INTO merchant_players VALUES (?,?,?,?)', (merchant_id, player_id, name, kind))
            db.execute('UPDATE merchant_players SET prebet_type=? WHERE merchant_id=? AND player_id=?', (kind, merchant_id, player_id))

    def candidate(self, merchant_id, player_id, game, state, bet, canonical):
        service = self.provider
        settings = service.merchants[merchant_id].get('pre_payout', {})
        with service.connection(True) as db:
            if state['phase'] == 'ready':
                row = db.execute('SELECT * FROM prebet_rounds WHERE merchant_id=? AND player_id=? AND game_id=? AND initial_sid=? AND error_code IS NULL',
                                 (merchant_id, player_id, game.game_id, state['sid'])).fetchone()
                if row is None and not settings.get('enabled'):
                    return None
                if row is None:
                    player = db.execute('SELECT external_username,prebet_type FROM merchant_players WHERE merchant_id=? AND player_id=?', (merchant_id, player_id)).fetchone()
                    if player is None:
                        raise ServiceError('PREBET_PLAYER_REQUIRED', '请先通过启动接口绑定平台 external_username。')
                    base = bet['coin_minor'] * bet['level'] * 10
                    debit = base * (game.config['feature_buy']['bm'] if bet.get('buy_free') else 1)
                    now = max(int(time.time() * 1000), db.execute("SELECT COALESCE(MAX(CAST(json_extract(prebet_request_json,'$.timestamp') AS INTEGER)),0)+1 FROM prebet_rounds").fetchone()[0])
                    payload = {'player_name': player[0], 'timestamp': now, 'bet_amount': f'{debit // 100}.{debit % 100:02d}',
                               'type': 'BUY_FREE_SPIN' if bet.get('buy_free') else player['prebet_type']}
                    round_id = secrets.token_hex(16)
                    db.execute('INSERT INTO prebet_rounds VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (round_id, merchant_id, player_id, game.game_id, state['sid'], canonical, encode(state), encode(bet), encode(payload), None, None, int(time.time()), None))
                    row = db.execute('SELECT * FROM prebet_rounds WHERE id=?', (round_id,)).fetchone()
                if row['request_json'] != canonical:
                    raise ServiceError('PREBET_PENDING', '此局已有预下注请求，请使用原投注参数重试。', 409)
            else:
                row = db.execute('SELECT * FROM prebet_rounds WHERE id=? AND merchant_id=? AND player_id=? AND game_id=?',
                                 (state['round_id'], merchant_id, player_id, game.game_id)).fetchone()
                if row is None:
                    return None  # Preserve rounds started before this feature was enabled.
                if bet.get('buy_free') or {k: bet[k] for k in ('coin_minor', 'level')} != state['bet']:
                    raise ServiceError('BET_LOCKED', '请使用本局原投注继续。', 409)
            row = dict(row)
        if not row['policy_json']:
            if not settings.get('operator_token') or not settings.get('secret_key'):
                raise ServiceError('PREBET_CONFIG_INVALID', '请配置平台运营商 Token 和密钥。', 503)
            try:
                policy = self.client.decision(settings, json.loads(row['prebet_request_json']))
            except ServiceError as error:
                if error.code == 'PREBET_3202':
                    # A definite rejected decision has no wallet side effects.
                    # A later attempt may use a new timestamp after a top-up.
                    with service.connection(True) as db:
                        db.execute('UPDATE prebet_rounds SET error_code=? WHERE id=? AND policy_json IS NULL', (error.code, row['id']))
                raise
            with service.connection(True) as db:
                current = db.execute('SELECT policy_json FROM prebet_rounds WHERE id=?', (row['id'],)).fetchone()[0]
                if current and current != encode(policy):
                    raise ServiceError('PREBET_DECISION_CONFLICT', '同一预下注请求返回了不同区间，请核对平台去重。', 503)
                db.execute('UPDATE prebet_rounds SET policy_json=COALESCE(policy_json,?) WHERE id=?', (encode(policy), row['id']))
            row['policy_json'] = encode(policy)
        with service.connection(True) as db:
            stored = db.execute('SELECT plan_json FROM prebet_rounds WHERE id=?', (row['id'],)).fetchone()[0]
            if not stored:
                plan = self.generate(game, row)
                stored = encode(plan)
                db.execute('UPDATE prebet_rounds SET plan_json=? WHERE id=?', (stored, row['id']))
        plan = json.loads(stored)
        for step in plan['steps']:
            if step['previous_sid'] == state['sid']:
                return step['candidate']
        raise ServiceError('PREBET_PLAN_CONFLICT', '当前游戏状态与预派彩计划不一致。', 409)

    def generate(self, game, row):
        policy = json.loads(row['policy_json'])
        low, high = map(Decimal, policy['maxWinMulti'])
        unlimited = low == -1 and high == 0
        initial = json.loads(row['initial_state_json'])
        bet = json.loads(row['bet_json'])
        basis = int(Decimal(json.loads(row['prebet_request_json'])['bet_amount']) * 100)
        if not unlimited and (max(low, Decimal(0)) * basis).to_integral_value(rounding=ROUND_CEILING) > (high * basis).to_integral_value(rounding=ROUND_FLOOR):
            raise ServiceError('PREBET_RANGE_UNREACHABLE', '平台区间无法表示为整数美分；未扣款。', 503)
        for attempt in range(self.max_attempts):
            state, total, steps = copy.deepcopy(initial), 0, []
            seed = secrets.token_hex(32)
            for index in range(self.max_steps):
                sid = row['id'] if index == 0 else hashlib.sha256((row['id'] + ':' + str(index)).encode()).hexdigest()[:32]
                outcome = game.step(state, bet if index == 0 else {k: bet[k] for k in ('coin_minor', 'level')},
                                    hashlib.sha256((seed + ':' + str(index)).encode()).hexdigest(), sid)
                total += outcome.credit_minor
                if not unlimited and Decimal(total) > high * basis:
                    break
                candidate = {'state': outcome.state, 'event': outcome.event, 'debit_minor': outcome.debit_minor,
                             'credit_minor': outcome.credit_minor, 'engine_version': game.version, 'ruleset_id': game.ruleset_id}
                steps.append({'previous_sid': state['sid'], 'candidate': candidate})
                state = outcome.state
                if state['phase'] == 'ready':
                    if unlimited or Decimal(total) >= max(low, Decimal(0)) * basis:
                        assert sum(step['candidate']['debit_minor'] for step in steps) == basis
                        return {'steps': steps, 'total_credit_minor': total, 'basis_minor': basis, 'attempts': attempt + 1}
                    break
        raise ServiceError('PREBET_RANGE_UNREACHABLE', '未生成满足平台区间的完整合法回合；未扣款，请重试或核对区间。', 503)
