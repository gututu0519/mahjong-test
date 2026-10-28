"""Versioned RTP policies, immutable round bindings and completed-round accounting."""
from contextlib import contextmanager
import copy
import hashlib
import json
import math
from pathlib import Path
import secrets
import sqlite3
import time

from server.core.contracts import ServiceError
from server.games.buffalo_win.engine import BuffaloWin
from .common import encode, identifier
from .identifiers import game_code, game_number


class RTPStore:
    def __init__(self, provider):
        self.provider = provider
        self.control = getattr(provider.merchants, 'store', None)
        self.cache = {}
        with provider.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS rtp_models (
                    id TEXT PRIMARY KEY,target_bp INTEGER,model_hash TEXT NOT NULL,report_json TEXT NOT NULL,
                    published INTEGER NOT NULL,created_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS rtp_policies (
                    scope TEXT NOT NULL,merchant_id TEXT NOT NULL,player_id TEXT NOT NULL,game_id INTEGER NOT NULL,
                    model_id TEXT REFERENCES rtp_models(id),revision INTEGER NOT NULL,actor TEXT NOT NULL,updated_at INTEGER NOT NULL,
                    PRIMARY KEY(scope,merchant_id,player_id,game_id));
                CREATE TABLE IF NOT EXISTS rtp_modes (
                    merchant_id TEXT PRIMARY KEY,mode TEXT NOT NULL,revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS rtp_bindings (
                    merchant_id TEXT NOT NULL,player_id TEXT NOT NULL,game_id TEXT NOT NULL,initial_sid TEXT NOT NULL,
                    round_id TEXT,model_id TEXT NOT NULL REFERENCES rtp_models(id),play_mode TEXT NOT NULL,mode TEXT NOT NULL,
                    source TEXT NOT NULL,revision INTEGER NOT NULL,settings_json TEXT NOT NULL,created_at INTEGER NOT NULL,
                    PRIMARY KEY(merchant_id,player_id,game_id,initial_sid));
                CREATE INDEX IF NOT EXISTS rtp_binding_round ON rtp_bindings(merchant_id,player_id,game_id,round_id);
                CREATE TABLE IF NOT EXISTS rtp_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,merchant_id TEXT NOT NULL,actor TEXT NOT NULL,action TEXT NOT NULL,
                    details_json TEXT NOT NULL,created_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS rtp_jobs (
                    id TEXT PRIMARY KEY,target_bp INTEGER NOT NULL,status TEXT NOT NULL,actor TEXT NOT NULL,
                    progress_json TEXT NOT NULL,result_id TEXT,error TEXT,lease TEXT,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS rtp_workers (id TEXT PRIMARY KEY,updated_at INTEGER NOT NULL,processes INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS rtp_accounted_ops (operation_id TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS rtp_facts (
                    merchant_id TEXT NOT NULL,player_id TEXT NOT NULL,game_id INTEGER NOT NULL,round_id TEXT NOT NULL,
                    play_mode TEXT NOT NULL,mode TEXT NOT NULL,target_bp INTEGER,model_id TEXT,
                    debit_minor TEXT NOT NULL,credit_minor TEXT NOT NULL,closed INTEGER NOT NULL,
                    started_at INTEGER NOT NULL,closed_at INTEGER,voided INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(merchant_id,player_id,game_id,round_id));
                CREATE INDEX IF NOT EXISTS rtp_facts_scope ON rtp_facts(merchant_id,player_id,game_id,closed_at);
            ''')
        with provider.connection(True) as db:
            columns = {row['name'] for row in db.execute('PRAGMA table_info(game_operations)')}
            if 'settled_at' not in columns:
                db.execute('ALTER TABLE game_operations ADD COLUMN settled_at INTEGER')
            game = provider.registry.get('buffalo-win')
            self.legacy_id = 'legacy:' + game.ruleset_id
            report = {'legacy': True, 'config': game.config, 'ruleset_id': game.ruleset_id}
            db.execute('INSERT OR IGNORE INTO rtp_models VALUES (?,?,?,?,?,?)',
                       (self.legacy_id, None, game.ruleset_id, encode(report), 0, int(time.time())))
            for row in db.execute("SELECT * FROM game_operations WHERE status='settled' AND id NOT IN (SELECT operation_id FROM rtp_accounted_ops) ORDER BY seq").fetchall():
                self.record(db, row)
        if self.control:
            self.control.rtp_database = provider.path
        bundled = Path(__file__).resolve().parents[2] / 'services/gtt-gateway/config/rtp-models.json'
        if bundled.is_file():
            for report in json.loads(bundled.read_bytes())['models']:
                self.import_model(report, 'system', publish=True)

    @contextmanager
    def write(self):
        db = sqlite3.connect(self.provider.path, isolation_level=None, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            if self.control:
                db.execute('ATTACH DATABASE ? AS control', (self.control.path,))
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def check_game(value):
        if game_code(value) != 'buffalo-win':
            raise ServiceError('RTP_GAME_UNAVAILABLE', '当前 RTP 模型仅适用于游戏 1。')

    @staticmethod
    def reason(payload):
        value = payload.get('reason', '')
        if not isinstance(value, str) or not 4 <= len(value.strip()) <= 300:
            raise ServiceError('REASON_REQUIRED', '请输入 4–300 个字符的修改原因。')
        return value.strip()

    def event(self, db, actor, action, merchant_id='', **details):
        db.execute('INSERT INTO rtp_events(merchant_id,actor,action,details_json,created_at) VALUES (?,?,?,?,?)',
                   (merchant_id, actor, action, encode(details), int(time.time())))
        if self.control and actor != 'system':
            self.control.audit(db, actor, action, merchant_id or 'platform',
                               details={'merchant_id': merchant_id or None, **details})

    def import_model(self, report, actor, publish=False):
        if report.get('engine_version') != BuffaloWin.version or report.get('game_id') != 1:
            raise ServiceError('RTP_MODEL_INVALID', '模型引擎版本不匹配。')
        target = report.get('target_bp')
        if type(target) is not int or not 8000 <= target <= 9900:
            raise ServiceError('RTP_MODEL_INVALID', '模型目标超出标定范围。')
        if set(report.get('modes', {})) != {'normal', 'buy_free'}:
            raise ServiceError('RTP_MODEL_INVALID', '普通与购买免费都需要独立验证。')
        for mode, data in report['modes'].items():
            BuffaloWin(configuration=data['config'])
            sample = data['validation']
            minimum = 200000 if mode == 'buy_free' else 2000000
            n, cost = sample['rounds'], sample['cost']
            if type(n) is not int or n < minimum or cost != (1500 if mode == 'buy_free' else 20):
                raise ServiceError('RTP_MODEL_INVALID', '模型完整回合样本不足。')
            mean = sample['credit'] / (n * cost)
            variance = max(0, (sample['credit_squared'] - sample['credit'] ** 2 / n) / (n - 1)) / cost ** 2
            half = 2.576 * math.sqrt(variance / n)
            if (sample.get('unfinished_rounds') != 0 or half > .015 or not mean - half <= target / 10000 <= mean + half
                    or abs(sample['rtp'] - mean) > 1e-10 or abs(sample['ci_half'] - half) > 1e-10):
                raise ServiceError('RTP_MODEL_INVALID', '独立验证未通过，不能发布。')
        digest = hashlib.sha256(json.dumps({name: data['config'] for name, data in report['modes'].items()}, sort_keys=True).encode()).hexdigest()
        if digest != report.get('model_hash'):
            raise ServiceError('RTP_MODEL_INVALID', '模型校验和不匹配。')
        model_id = f'bw-{target}-{digest[:16]}'
        with self.write() as db:
            exists = db.execute('SELECT id FROM rtp_models WHERE id=?', (model_id,)).fetchone()
            if not exists:
                db.execute('INSERT INTO rtp_models VALUES (?,?,?,?,?,?)',
                           (model_id, target, digest, encode(report), int(publish), int(time.time())))
                self.event(db, actor, 'rtp.model.import', model_id=model_id, target_bp=target, published=publish)
        return model_id

    def models(self):
        with self.provider.connection() as db:
            rows = db.execute('SELECT * FROM rtp_models WHERE target_bp IS NOT NULL ORDER BY target_bp,created_at').fetchall()
        return [{'id': row['id'], 'target_bp': row['target_bp'], 'model_hash': row['model_hash'],
                 'published': bool(row['published']), 'created_at': row['created_at'],
                 'validation': {mode: data['validation'] for mode, data in json.loads(row['report_json'])['modes'].items()},
                 'certified_theoretical': False} for row in rows]

    def mode(self, db, merchant_id):
        merchant = self.provider.merchants[merchant_id]
        record = db.execute('SELECT * FROM rtp_modes WHERE merchant_id=?', (merchant_id,)).fetchone()
        enabled = merchant.get('pre_payout', {}).get('enabled')
        mode = record['mode'] if record else ('prebet' if enabled else 'rtp')
        if mode == 'prebet' and not enabled:
            mode = 'rtp'
        return mode, record['revision'] if record else 0

    def resolve(self, db, merchant_id, player_id='', game_id=1):
        for scope, mid, pid in [('player', merchant_id, player_id), ('merchant', merchant_id, ''), ('platform', '', '')]:
            if scope == 'player' and not player_id:
                continue
            row = db.execute('SELECT p.*,m.target_bp FROM rtp_policies p JOIN rtp_models m ON m.id=p.model_id '
                             'WHERE scope=? AND merchant_id=? AND player_id=? AND game_id=?', (scope, mid, pid, game_id)).fetchone()
            if row:
                return dict(row)
        return {'model_id': self.legacy_id, 'target_bp': None, 'scope': 'legacy', 'revision': 0}

    def bind(self, db, merchant_id, player_id, game, state, bet):
        if state['phase'] != 'ready':
            row = db.execute('SELECT * FROM rtp_bindings WHERE merchant_id=? AND player_id=? AND game_id=? AND round_id=?',
                             (merchant_id, player_id, game.game_id, state['round_id'])).fetchone()
        else:
            row = db.execute('SELECT * FROM rtp_bindings WHERE merchant_id=? AND player_id=? AND game_id=? AND initial_sid=?',
                             (merchant_id, player_id, game.game_id, state['sid'])).fetchone()
        if row:
            initial_bet = json.loads(row['settings_json']).get('_initial_bet')
            if state['phase'] == 'ready' and initial_bet is not None and initial_bet != bet:
                raise ServiceError('ROUND_PREPARING', '此整局已预留原投注参数，请使用原参数重试。', 409)
            return dict(row)
        mode, _ = self.mode(db, merchant_id)
        settings = self.provider.merchants[merchant_id].get('pre_payout', {})
        legacy = state['phase'] != 'ready'
        prebet = db.execute('SELECT 1 FROM prebet_rounds WHERE merchant_id=? AND player_id=? AND game_id=? AND error_code IS NULL AND '
                            + ('id=?' if legacy else 'initial_sid=?'),
                            (merchant_id, player_id, game.game_id, state['round_id'] if legacy else state['sid'])).fetchone()
        if prebet:
            mode = 'prebet'
        if mode == 'rtp' and settings.get('enabled'):
            raise ServiceError('RTP_MODE_CONFLICT', 'RTP 模型与平台预派彩配置冲突，请在 RTP 中心明确切换模式。', 409)
        policy = self.resolve(db, merchant_id, player_id) if mode == 'rtp' and not legacy else {'model_id': self.legacy_id, 'scope': 'legacy', 'revision': 0}
        play_mode = 'buy_free' if (state.get('bought_feature') if legacy else bet.get('buy_free')) else 'normal'
        values = (merchant_id, player_id, game.game_id, 'legacy:' + state['round_id'] if legacy else state['sid'],
                  state['round_id'] if legacy else None, policy['model_id'], play_mode, mode, policy['scope'], policy['revision'],
                  encode({**settings, 'enabled': mode == 'prebet', '_initial_bet': bet if not legacy else None}), int(time.time()))
        db.execute('INSERT INTO rtp_bindings VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', values)
        return dict(db.execute('SELECT * FROM rtp_bindings WHERE merchant_id=? AND player_id=? AND game_id=? AND initial_sid=?', values[:4]).fetchone())

    def engine(self, binding, default):
        key = (binding['model_id'], binding['play_mode'])
        if key not in self.cache:
            with self.provider.connection() as db:
                row = db.execute('SELECT * FROM rtp_models WHERE id=?', (binding['model_id'],)).fetchone()
            if row is None:
                raise ServiceError('RTP_MODEL_MISSING', '回合模型缺失，不能改用其他配置。', 503)
            report = json.loads(row['report_json'])
            config = report['config'] if report.get('legacy') else report['modes'][binding['play_mode']]['config']
            engine = BuffaloWin(configuration=config)
            self.cache[key] = default if report.get('legacy') and engine.ruleset_id == default.ruleset_id else engine
        return self.cache[key]

    def policy(self, actor, payload, platform=False):
        self.check_game(payload.get('game_id', 1))
        reason = self.reason(payload)
        scope = payload.get('scope', 'merchant')
        if scope not in ('platform', 'merchant', 'player') or scope == 'platform' and not platform:
            raise ServiceError('FORBIDDEN', '不能修改平台 RTP 默认配置。', 403)
        mid = '' if scope == 'platform' else identifier(payload.get('merchant_id'), 'merchant_id')
        pid = identifier(payload.get('player_id'), 'player_id') if scope == 'player' else ''
        if mid and mid not in self.provider.merchants:
            raise ServiceError('NOT_FOUND', '商户不存在。', 404)
        model_id = payload.get('model_id') or None
        activate = payload.get('activate_rtp', False)
        if type(activate) is not bool or activate and (scope != 'merchant' or not model_id):
            raise ServiceError('INVALID_ARGUMENT', '一并启用 RTP 只适用于商户目标设置。')
        with self.write() as db:
            old = db.execute('SELECT * FROM rtp_policies WHERE scope=? AND merchant_id=? AND player_id=? AND game_id=1', (scope, mid, pid)).fetchone()
            revision = old['revision'] if old else 0
            if type(payload.get('revision')) is not int or payload['revision'] != revision:
                raise ServiceError('VERSION_CONFLICT', 'RTP 配置已改变，请刷新后重试。', 409)
            if model_id:
                if not db.execute('SELECT 1 FROM rtp_models WHERE id=? AND published=1 AND target_bp IS NOT NULL', (model_id,)).fetchone():
                    raise ServiceError('RTP_MODEL_UNAVAILABLE', '请选择已发布且通过标定的模型。')
                if mid:
                    mode, mode_revision = self.mode(db, mid)
                    if activate:
                        if type(payload.get('mode_revision')) is not int or payload['mode_revision'] != mode_revision:
                            raise ServiceError('VERSION_CONFLICT', '商户模式已改变，请刷新后重试。', 409)
                        if mode != 'rtp' or self.provider.merchants[mid].get('pre_payout', {}).get('enabled'):
                            self.change_mode(db, actor, mid, 'rtp', reason=reason)
                            mode = 'rtp'
                    elif mode != 'rtp' or self.provider.merchants[mid].get('pre_payout', {}).get('enabled'):
                        raise ServiceError('RTP_MODE_CONFLICT', '请先明确切换到 RTP 模型模式。', 409)
            db.execute('INSERT INTO rtp_policies VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(scope,merchant_id,player_id,game_id) '
                       'DO UPDATE SET model_id=excluded.model_id,revision=excluded.revision,actor=excluded.actor,updated_at=excluded.updated_at',
                       (scope, mid, pid, 1, model_id, revision + 1, actor, int(time.time())))
            self.event(db, actor, 'rtp.policy.publish', mid, player_id=pid, scope=scope, before=dict(old) if old else None,
                       model_id=model_id, revision=revision + 1, reason=reason)
        return {'revision': revision + 1, 'effective': 'next_paid_round'}

    def set_mode(self, actor, payload):
        mid, reason = identifier(payload.get('merchant_id'), 'merchant_id'), self.reason(payload)
        mode = payload.get('mode')
        if mode not in ('rtp', 'prebet') or mid not in self.provider.merchants or not self.control:
            raise ServiceError('RTP_MODE_INVALID', '请选择商户及概率模式。')
        with self.write() as db:
            old, revision = self.mode(db, mid)
            if type(payload.get('revision')) is not int or payload['revision'] != revision:
                raise ServiceError('VERSION_CONFLICT', '模式已改变，请刷新后重试。', 409)
            self.change_mode(db, actor, mid, mode, payload.get('url'), reason)
        return {'mode': mode, 'revision': revision + 1, 'effective': 'next_paid_round'}

    def change_mode(self, db, actor, mid, mode, url=None, reason=''):
        if not self.control:
            raise ServiceError('RTP_MODE_INVALID', '商户配置存储不可用。', 503)
        old, revision = self.mode(db, mid)
        settings = self.provider.merchants[mid]['pre_payout']
        self.control.save_prebet(db, mid, {'enabled': mode == 'prebet', 'url': settings.get('url', '') if url is None else url}, allow_rtp_transition=True)
        db.execute('UPDATE control.merchants SET version=version+1,updated_at=? WHERE id=?', (int(time.time()), mid))
        db.execute('INSERT INTO rtp_modes VALUES (?,?,?) ON CONFLICT(merchant_id) DO UPDATE SET mode=excluded.mode,revision=excluded.revision', (mid, mode, revision + 1))
        self.event(db, actor, 'rtp.mode.change', mid, before=old, mode=mode, reason=reason)

    def record(self, db, operation):
        if operation['status'] != 'settled' or not operation['response_json']:
            return
        if not db.execute('INSERT OR IGNORE INTO rtp_accounted_ops VALUES (?)', (operation['id'],)).rowcount:
            return
        result = json.loads(operation['response_json'])
        wallet, event = result['wallet'], result['outcome']
        mid, pid, gid, rid = operation['merchant_id'], operation['player_id'], game_number(operation['game_id']), event['round_id']
        binding = db.execute('SELECT b.*,m.target_bp FROM rtp_bindings b JOIN rtp_models m ON m.id=b.model_id WHERE '
                             'b.merchant_id=? AND b.player_id=? AND b.game_id=? AND b.round_id=?', (mid, pid, operation['game_id'], rid)).fetchone()
        old = db.execute('SELECT * FROM rtp_facts WHERE merchant_id=? AND player_id=? AND game_id=? AND round_id=?', (mid, pid, gid, rid)).fetchone()
        prebet = db.execute('SELECT 1 FROM prebet_rounds WHERE id=?', (rid,)).fetchone()
        mode = binding['mode'] if binding else ('prebet' if prebet else 'legacy')
        if mode != 'prebet' and (not binding or binding['target_bp'] is None):
            mode = 'legacy'
        closed = event['next_phase'] == 'ready'
        debit = (int(old['debit_minor']) if old else 0) + int(wallet['debit_minor'])
        credit = (int(old['credit_minor']) if old else 0) + int(wallet['credit_minor'])
        db.execute('INSERT INTO rtp_facts(merchant_id,player_id,game_id,round_id,play_mode,mode,target_bp,model_id,debit_minor,credit_minor,closed,started_at,closed_at) '
                   'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(merchant_id,player_id,game_id,round_id) DO UPDATE SET '
                   'debit_minor=excluded.debit_minor,credit_minor=excluded.credit_minor,closed=excluded.closed,closed_at=excluded.closed_at',
                   (mid, pid, gid, rid, 'buy_free' if event.get('bought_feature') else 'normal', mode,
                    binding['target_bp'] if binding and mode == 'rtp' else None, binding['model_id'] if binding else None,
                    str(debit), str(credit), int(closed), old['started_at'] if old else operation['created_at'],
                    operation['settled_at'] if closed else None))

    def snapshot(self, payload, scope=None):
        self.check_game(payload.get('game_id', 1))
        mid = scope or payload.get('merchant_id', '')
        pid = payload.get('player_id', '')
        if mid:
            identifier(mid, 'merchant_id')
            if mid not in self.provider.merchants:
                raise ServiceError('NOT_FOUND', '商户不存在。', 404)
        if pid:
            identifier(pid, 'player_id')
            if not mid:
                raise ServiceError('INVALID_ARGUMENT', '查询玩家时须指定商户。')
        start, end = payload.get('from_at', 0), payload.get('to_at', 0)
        if any(type(value) is not int or not 0 <= value <= 9_000_000_000_000_000 for value in (start, end)) or end and end <= start:
            raise ServiceError('INVALID_ARGUMENT', '统计时间区间无效。')
        clauses, params = ['game_id=1'], []
        if mid:
            clauses.append('merchant_id=?'); params.append(mid)
        if pid:
            clauses.append('player_id=?'); params.append(pid)
        for field, allowed in [('play_mode', ('normal', 'buy_free')), ('mode', ('rtp', 'prebet', 'legacy'))]:
            value = payload.get(field, '')
            if value:
                if value not in allowed:
                    raise ServiceError('INVALID_ARGUMENT', '统计筛选无效。')
                clauses.append(field + '=?'); params.append(value)
        with self.provider.connection() as db:
            facts = [dict(row) for row in db.execute('SELECT * FROM rtp_facts WHERE ' + ' AND '.join(clauses), params)]
            operations = db.execute("SELECT merchant_id,player_id,status FROM game_operations WHERE status IN ('prepared','debited')"
                                    + (' AND merchant_id=?' if mid else '') + (' AND player_id=?' if pid else ''),
                                    (*([mid] if mid else []), *([pid] if pid else []))).fetchall()
            policies = [dict(row) for row in db.execute('SELECT * FROM rtp_policies' + (' WHERE merchant_id IN (?,?)' if mid else ''), (mid, '') if mid else ())]
            modes = {merchant_id: {'mode': self.mode(db, merchant_id)[0], 'revision': self.mode(db, merchant_id)[1],
                                  'default': self.resolve(db, merchant_id)}
                     for merchant_id in ([mid] if mid else list(self.provider.merchants))}
            events = [dict(row) for row in db.execute('SELECT * FROM rtp_events' + (' WHERE merchant_id=?' if mid else '') + ' ORDER BY seq DESC LIMIT 100', (mid,) if mid else ())]
            jobs = [dict(row) for row in db.execute('SELECT * FROM rtp_jobs ORDER BY created_at DESC LIMIT 30')] if not scope else []
            reserved = db.execute('SELECT COUNT(*) FROM rtp_bindings WHERE round_id IS NULL' + (' AND merchant_id=?' if mid else '')
                                  + (' AND player_id=?' if pid else ''), (*([mid] if mid else []), *([pid] if pid else []))).fetchone()[0]
            worker = db.execute('SELECT MAX(updated_at) FROM rtp_workers').fetchone()[0]
        names = {merchant_id: self.provider.merchants[merchant_id] for merchant_id in ([mid] if mid else list(self.provider.merchants))}
        rows = [row for row in facts if row['merchant_id'] in names and row['closed'] and not row['voided'] and int(row['debit_minor']) > 0
                and (not start or row['closed_at'] is not None and row['closed_at'] >= start)
                and (not end or row['closed_at'] is not None and row['closed_at'] < end)]
        def aggregate(values):
            debit = sum(int(row['debit_minor']) for row in values)
            credit = sum(int(row['credit_minor']) for row in values)
            known = sum(int(row['debit_minor']) for row in values if row['target_bp'] is not None)
            expected = sum(int(row['debit_minor']) * row['target_bp'] for row in values if row['target_bp'] is not None)
            return {'debit_minor': str(debit), 'credit_minor': str(credit), 'rounds': len(values),
                    'actual_rtp': credit / debit * 100 if debit else None,
                    'weighted_target': expected / known / 100 if known else None,
                    'target_coverage': known / debit * 100 if debit else 0,
                    'sample_note': '少量回合波动较大' if len(values) < 10000 else '实际返还率，非理论证明'}
        merchants = []
        players = []
        for merchant_id, merchant in names.items():
            values = [row for row in rows if row['merchant_id'] == merchant_id]
            merchants.append({'merchant_id': merchant_id, 'name': merchant['name'], 'currency': merchant['currency'], 'minor_unit': 100,
                              **aggregate(values), **modes[merchant_id]})
        player_keys = {(row['merchant_id'], row['player_id']) for row in facts}
        player_keys.update((row['merchant_id'], row['player_id']) for row in operations)
        player_keys.update((row['merchant_id'], row['player_id']) for row in policies if row['scope'] == 'player')
        if pid and mid:
            player_keys.add((mid, pid))
        with self.provider.connection() as db:
            for merchant_id, player_id in sorted(player_keys):
                if merchant_id not in names or pid and player_id != pid:
                    continue
                merchant = names[merchant_id]
                policy = self.resolve(db, merchant_id, player_id)
                players.append({'merchant_id': merchant_id, 'player_id': player_id, 'currency': merchant['currency'], 'minor_unit': 100,
                                **aggregate([row for row in rows if row['merchant_id'] == merchant_id and row['player_id'] == player_id]), 'effective': policy})
        summaries = [{'currency': currency, 'minor_unit': 100, **aggregate([row for row in rows if names[row['merchant_id']]['currency'] == currency])}
                     for currency in sorted({merchant['currency'] for merchant in names.values()})]
        for event in events:
            event['details'] = json.loads(event.pop('details_json'))
        for job in jobs:
            job['progress'] = json.loads(job.pop('progress_json'))
            job.pop('lease', None)
        days = sorted({(time.strftime('%Y-%m-%d', time.gmtime(row['closed_at'])), names[row['merchant_id']]['currency']) for row in rows if row['closed_at']})
        daily = [{'date': day, 'currency': currency, 'minor_unit': 100,
                  **aggregate([row for row in rows if row['closed_at'] and time.strftime('%Y-%m-%d', time.gmtime(row['closed_at'])) == day and names[row['merchant_id']]['currency'] == currency])} for day, currency in days[-90:]]
        return {'summary': summaries, 'merchants': merchants, 'players': players[:200], 'players_total': len(players), 'daily': daily,
                'policies': policies, 'models': self.models(), 'events': events, 'jobs': jobs,
                'pending_operations': len(operations), 'open_rounds': sum(not row['closed'] for row in facts),
                'reserved_rounds': reserved,
                'worker_online': bool(worker and worker >= int(time.time()) - 120),
                'historical_unknown_time': sum(row['closed'] and row['closed_at'] is None for row in facts),
                'voided_rounds': sum(row['voided'] for row in facts), 'timezone': 'UTC',
                'definition': '确认结算且已完成整局的派彩 / 实际投注；免费及续列计入原付费整局。金额字段为整数美分字符串。'}

    def create_job(self, actor, payload):
        target = payload.get('target_bp')
        if type(target) is not int or not 8000 <= target <= 9900:
            raise ServiceError('RTP_TARGET_INVALID', '新模型标定目标须为 80.00%–99.00%。')
        reason = self.reason(payload)
        with self.write() as db:
            if db.execute("SELECT 1 FROM rtp_jobs WHERE target_bp=? AND status IN ('queued','running')", (target,)).fetchone():
                raise ServiceError('RTP_JOB_EXISTS', '该目标已有待运行的标定任务。', 409)
            job_id, now = secrets.token_hex(16), int(time.time())
            db.execute('INSERT INTO rtp_jobs VALUES (?,?,?,?,?,?,?,?,?,?)', (job_id, target, 'queued', actor, '{}', None, None, None, now, now))
            self.event(db, actor, 'rtp.calibration.queue', target_bp=target, reason=reason, job_id=job_id)
        return {'id': job_id, 'status': 'queued'}

    def publish_model(self, actor, payload):
        reason = self.reason(payload)
        with self.write() as db:
            row = db.execute('SELECT * FROM rtp_models WHERE id=? AND target_bp IS NOT NULL', (payload.get('model_id'),)).fetchone()
            if not row:
                raise ServiceError('NOT_FOUND', '模型不存在。', 404)
            if not row['published']:
                db.execute('UPDATE rtp_models SET published=1 WHERE id=?', (row['id'],))
                self.event(db, actor, 'rtp.model.publish', model_id=row['id'], reason=reason)
        return {'published': True}

    def public_context(self, merchant_id, player_id, game_id, state):
        with self.provider.connection() as db:
            binding = db.execute('SELECT b.*,m.target_bp FROM rtp_bindings b JOIN rtp_models m ON m.id=b.model_id WHERE '
                                 'b.merchant_id=? AND b.player_id=? AND b.game_id=? AND '
                                 + ('b.round_id=?' if state['phase'] != 'ready' else 'b.initial_sid=? AND b.round_id IS NULL'),
                                 (merchant_id, player_id, game_id, state['round_id'] if state['phase'] != 'ready' else state['sid'])).fetchone()
            if binding:
                mode, target, model, source = binding['mode'], binding['target_bp'], binding['model_id'], binding['source']
            elif state['phase'] != 'ready':
                prebet = db.execute('SELECT 1 FROM prebet_rounds WHERE id=?', (state['round_id'],)).fetchone()
                mode, target, model, source = 'prebet' if prebet else 'legacy', None, self.legacy_id, 'legacy'
            else:
                mode, _ = self.mode(db, merchant_id)
                policy = self.resolve(db, merchant_id, player_id)
                target, model, source = policy.get('target_bp'), policy['model_id'], policy['scope']
        return {'mode': mode, 'target_rtp': target / 100 if mode == 'rtp' and target is not None else None,
                'model_id': model, 'source': source, 'status': 'active' if mode == 'rtp' and target is not None else 'prebet' if mode == 'prebet' else 'not_calibrated'}
