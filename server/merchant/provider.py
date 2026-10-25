"""Durable game operations with an external, authoritative platform wallet."""
import hashlib
import json
import secrets
import time
import uuid
from urllib.parse import urlencode

from server.core.contracts import Outcome, Registry, ServiceError
from server.games.buffalo_win.engine import BuffaloWin
from .common import Database, encode, identifier, limit
from .wallet import WalletClient
from .prebet import RoundPlanner


class MerchantService(Database):
    def __init__(self, path, merchants, game=None, wallet=None):
        super().__init__(path)
        self.merchants = merchants
        self.registry = Registry([game or BuffaloWin()])
        self.wallet_client = wallet or WalletClient(merchants)
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS merchant_sessions (
                    token_hash TEXT PRIMARY KEY, merchant_id TEXT NOT NULL, player_id TEXT NOT NULL,
                    game_id TEXT NOT NULL, expires_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS merchant_states (
                    merchant_id TEXT NOT NULL, player_id TEXT NOT NULL, game_id TEXT NOT NULL,
                    state_json TEXT NOT NULL, PRIMARY KEY(merchant_id,player_id,game_id));
                CREATE TABLE IF NOT EXISTS game_operations (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
                    merchant_id TEXT NOT NULL, player_id TEXT NOT NULL, game_id TEXT NOT NULL,
                    request_key TEXT NOT NULL, request_json TEXT NOT NULL,
                    status TEXT NOT NULL, candidate_json TEXT NOT NULL, debit_json TEXT,
                    response_json TEXT, error_code TEXT, created_at INTEGER NOT NULL,
                    UNIQUE(merchant_id,player_id,game_id,request_key));
                CREATE UNIQUE INDEX IF NOT EXISTS one_pending_game_operation
                    ON game_operations(merchant_id,player_id,game_id) WHERE status IN ('prepared','debited');
            ''')
        self.prebet = RoundPlanner(self)

    def merchant(self, merchant_id, game_id=None, allow_disabled=False):
        merchant = self.merchants.get(merchant_id)
        if not merchant or (not merchant.get('enabled') and not allow_disabled):
            raise ServiceError('MERCHANT_DISABLED', 'Merchant is unavailable.', 403)
        if merchant.get('minor_unit') != 100 or not isinstance(merchant.get('currency'), str):
            raise ServiceError('MERCHANT_CONFIG_INVALID', 'Unsupported merchant currency configuration.', 503)
        if game_id is not None:
            self.registry.get(game_id)
            if game_id not in merchant.get('games', []):
                raise ServiceError('GAME_FORBIDDEN', 'Game is not enabled for this merchant.', 403)
        return merchant

    def _wallet_payload(self, merchant_id, player_id, allow_disabled=False):
        merchant = self.merchant(merchant_id, allow_disabled=allow_disabled)
        return {'player_id': player_id, 'currency': merchant['currency'], 'minor_unit': 100}

    def catalog(self, merchant_id):
        merchant = self.merchant(merchant_id)
        return {'games': [{**game, 'target_rtp': None, 'rtp_status': 'not_calibrated'}
                          for game in self.registry.catalog() if game['id'] in merchant['games']]}

    def launch(self, merchant_id, payload):
        player_id = identifier(payload.get('player_id'), 'player_id')
        game_id = payload.get('game_id', 'buffalo-win')
        merchant = self.merchant(merchant_id, game_id)
        if 'prebet_type' in payload and 'external_username' not in payload:
            raise ServiceError('PREBET_PLAYER_REQUIRED', '设置 prebet_type 时请同时提供 external_username。')
        if 'external_username' in payload:
            self.prebet.bind_player(merchant_id, player_id, payload['external_username'], payload.get('prebet_type', 'NORMAL'))
        if merchant.get('pre_payout', {}).get('enabled'):
            with self.connection() as db:
                if not db.execute('SELECT 1 FROM merchant_players WHERE merchant_id=? AND player_id=?', (merchant_id, player_id)).fetchone():
                    raise ServiceError('PREBET_PLAYER_REQUIRED', '启动请求须提供平台 external_username，不能用平台用户 ID 代替。')
        language = payload.get('language', 'en')
        if language not in ('zh', 'en'):
            raise ServiceError('LANGUAGE_INVALID', 'Supported languages: zh, en.')
        balance = self.wallet_client.call(merchant_id, 'balance', self._wallet_payload(merchant_id, player_id))
        token, expiry = secrets.token_urlsafe(32), int(time.time()) + 86400
        with self.connection(True) as db:
            db.execute('INSERT INTO merchant_sessions VALUES (?,?,?,?,?)',
                       (hashlib.sha256(token.encode()).hexdigest(), merchant_id, player_id, game_id, expiry))
            self._state(db, merchant_id, player_id, game_id)
        return {'game_id': game_id, 'launch_url': '/?' + urlencode({'mock': 1, 'l': language, 'ops': token, 'btt': 2}),
                'expires_at': expiry, 'balance_minor': balance['balance_minor'],
                'currency': balance['currency'], 'minor_unit': 100}

    def _session(self, token, game_id=None):
        if not isinstance(token, str) or not 1 <= len(token) <= 256:
            raise ServiceError('SESSION_INVALID', 'A merchant game session is required.', 401)
        with self.connection() as db:
            row = db.execute('SELECT * FROM merchant_sessions WHERE token_hash=? AND expires_at>?',
                             (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()
        if row is None or (game_id is not None and row['game_id'] != game_id):
            raise ServiceError('SESSION_INVALID', 'Session is missing, expired or belongs to another game.', 401)
        self.merchant(row['merchant_id'], row['game_id'])
        return dict(row)

    def _state(self, db, merchant_id, player_id, game_id):
        row = db.execute('SELECT state_json FROM merchant_states WHERE merchant_id=? AND player_id=? AND game_id=?',
                         (merchant_id, player_id, game_id)).fetchone()
        if row:
            return json.loads(row[0])
        state = self.registry.get(game_id).initial_state(secrets.token_hex(32))
        db.execute('INSERT INTO merchant_states VALUES (?,?,?,?)', (merchant_id, player_id, game_id, encode(state)))
        return state

    def create_session(self):
        raise ServiceError('MERCHANT_AUTH_REQUIRED', 'Use the signed merchant launch endpoint.', 401)

    def wallet(self, token):
        session = self._session(token)
        return self.wallet_client.call(session['merchant_id'], 'balance',
                                       self._wallet_payload(session['merchant_id'], session['player_id']))

    def state(self, token, game_id):
        session = self._session(token, game_id)
        merchant_id, player_id = session['merchant_id'], session['player_id']
        with self.connection() as db:
            pending = db.execute("SELECT id FROM game_operations WHERE merchant_id=? AND player_id=? AND game_id=? AND status IN ('prepared','debited')",
                                 (merchant_id, player_id, game_id)).fetchone()
        if pending:
            self.retry(merchant_id, pending['id'])
        balance = self.wallet(token)
        with self.connection(True) as db:
            state = self._state(db, merchant_id, player_id, game_id)
        game = self.registry.get(game_id)
        return {'game_id': game_id, 'balance_minor': balance['balance_minor'],
                'engine_version': game.version, 'ruleset_id': game.ruleset_id, 'state': game.public_state(state)}

    def spin(self, token, game_id, request_key, previous_sid, bet_payload):
        session = self._session(token, game_id)
        merchant_id, player_id = session['merchant_id'], session['player_id']
        if not isinstance(request_key, str) or not 1 <= len(request_key) <= 128:
            raise ServiceError('REQUEST_KEY_INVALID', 'Use a 1..128 character idempotency key.')
        if not isinstance(previous_sid, str) or len(previous_sid) > 64:
            raise ServiceError('PREVIOUS_SID_INVALID', 'Use the previous game state sid.')
        game = self.registry.get(game_id)
        bet = game.normalize_bet(bet_payload)
        canonical = encode({'previous_sid': previous_sid, 'bet': bet})
        operation_id = None
        with self.connection(True) as db:
            existing = db.execute('SELECT * FROM game_operations WHERE merchant_id=? AND player_id=? AND game_id=? AND request_key=?',
                                  (merchant_id, player_id, game_id, request_key)).fetchone()
            if existing:
                if existing['request_json'] != canonical:
                    raise ServiceError('IDEMPOTENCY_CONFLICT', 'This key was used with different parameters.', 409)
                operation_id = existing['id']
            else:
                pending = db.execute("SELECT id FROM game_operations WHERE merchant_id=? AND player_id=? AND game_id=? AND status IN ('prepared','debited')",
                                     (merchant_id, player_id, game_id)).fetchone()
                if pending:
                    raise ServiceError('OPERATION_PENDING', 'Recover the pending operation ' + pending['id'], 409)
                state = self._state(db, merchant_id, player_id, game_id)
                if state['sid'] != previous_sid:
                    raise ServiceError('STALE_STATE', 'Refresh game state before continuing.', 409)
        if operation_id is not None:
            return self.retry(merchant_id, operation_id)
        # Reserve/persist the platform decision timestamp before contacting the platform. No
        # game-operation debit can occur until the full valid plan is committed.
        planned = self.prebet.candidate(merchant_id, player_id, game, state, bet, canonical)
        with self.connection(True) as db:
            existing = db.execute('SELECT * FROM game_operations WHERE merchant_id=? AND player_id=? AND game_id=? AND request_key=?',
                                  (merchant_id, player_id, game_id, request_key)).fetchone()
            if existing:
                if existing['request_json'] != canonical:
                    raise ServiceError('IDEMPOTENCY_CONFLICT', 'This key was used with different parameters.', 409)
                operation_id = existing['id']
            else:
                current = self._state(db, merchant_id, player_id, game_id)
                if current['sid'] != previous_sid:
                    raise ServiceError('STALE_STATE', 'Refresh game state before continuing.', 409)
                if db.execute("SELECT 1 FROM game_operations WHERE merchant_id=? AND player_id=? AND game_id=? AND status IN ('prepared','debited')",
                              (merchant_id, player_id, game_id)).fetchone():
                    raise ServiceError('OPERATION_PENDING', 'Recover the existing wallet operation.', 409)
                operation_id = planned['state']['sid'] if planned else uuid.uuid4().hex
                outcome = None if planned else game.step(current, bet, secrets.token_hex(32), operation_id)
                if planned:
                    outcome = Outcome(planned['state'], planned['event'], planned['debit_minor'], planned['credit_minor'])
                if (type(outcome.debit_minor) is not int or type(outcome.credit_minor) is not int
                        or min(outcome.debit_minor, outcome.credit_minor) < 0):
                    raise RuntimeError('Game returned invalid wallet amounts')
                candidate = {'state': outcome.state, 'event': outcome.event, 'debit_minor': outcome.debit_minor,
                             'credit_minor': outcome.credit_minor, 'engine_version': game.version, 'ruleset_id': game.ruleset_id}
                # Commit the generated result BEFORE contacting the platform.
                db.execute('INSERT INTO game_operations(id,merchant_id,player_id,game_id,request_key,request_json,status,candidate_json,created_at) VALUES (?,?,?,?,?,?,?, ?,?)',
                           (operation_id, merchant_id, player_id, game_id, request_key, canonical, 'prepared',
                            encode(candidate), int(time.time())))
        return self.retry(merchant_id, operation_id)

    def retry(self, merchant_id, operation_id, allow_disabled=False):
        identifier(operation_id, 'operation_id')
        self.merchant(merchant_id, allow_disabled=allow_disabled)
        with self.connection() as db:
            operation = db.execute('SELECT * FROM game_operations WHERE merchant_id=? AND id=?',
                                   (merchant_id, operation_id)).fetchone()
        if not operation:
            raise ServiceError('NOT_FOUND', 'Unknown merchant operation.', 404)
        # A permission change must not cancel an already accepted wallet operation.
        # New launches/spins check current game permissions before preparing work.
        if operation['status'] == 'settled':
            return json.loads(operation['response_json'])
        if operation['status'] == 'rejected':
            raise ServiceError(operation['error_code'], 'Stored wallet rejection; game state was not advanced.', 409)
        candidate = json.loads(operation['candidate_json'])
        event, debit, credit = candidate['event'], candidate['debit_minor'], candidate['credit_minor']
        base = {**self._wallet_payload(merchant_id, operation['player_id'], allow_disabled), 'round_id': event['round_id']}
        debit_result = json.loads(operation['debit_json']) if operation['debit_json'] else None
        if debit and debit_result is None:
            try:
                debit_result = self.wallet_client.call(merchant_id, 'debit',
                    {**base, 'transaction_id': operation_id + ':debit', 'amount_minor': debit})
            except ServiceError as error:
                if error.code != 'WALLET_UNCERTAIN':
                    with self.connection(True) as db:
                        db.execute("UPDATE game_operations SET status='rejected',error_code=? WHERE id=? AND status='prepared'",
                                   (error.code, operation_id))
                        db.execute('UPDATE prebet_rounds SET error_code=? WHERE id=?', (error.code, event['round_id']))
                    raise
                raise ServiceError('WALLET_UNCERTAIN', 'Retry operation ' + operation_id + '; debit outcome is unknown.', 503) from None
            with self.connection(True) as db:
                db.execute("UPDATE game_operations SET status='debited',debit_json=? WHERE id=? AND status='prepared'",
                           (encode(debit_result), operation_id))
        try:
            if credit:
                final_wallet = self.wallet_client.call(merchant_id, 'credit',
                    {**base, 'transaction_id': operation_id + ':credit', 'amount_minor': credit,
                     'reference_id': event['round_id'] + ':debit'})
            else:
                final_wallet = debit_result or self.wallet_client.call(merchant_id, 'balance',
                    self._wallet_payload(merchant_id, operation['player_id'], allow_disabled))
        except ServiceError:
            raise ServiceError('WALLET_UNCERTAIN', 'Retry operation ' + operation_id + '; settlement is pending.', 503) from None
        after = final_wallet['balance_minor']
        before = debit_result['balance_before_minor'] if debit_result else final_wallet.get('balance_before_minor', after)
        response = {'game_id': operation['game_id'], 'sid': operation_id, 'round_id': event['round_id'],
                    'engine_version': candidate['engine_version'], 'ruleset_id': candidate['ruleset_id'],
                    'wallet': {'before_minor': before, 'debit_minor': debit, 'credit_minor': credit, 'after_minor': after},
                    'outcome': event}
        with self.connection(True) as db:
            current = db.execute('SELECT status,response_json FROM game_operations WHERE id=?', (operation_id,)).fetchone()
            if current['status'] == 'settled':
                return json.loads(current['response_json'])
            if current['status'] == 'rejected':
                raise ServiceError('OPERATION_REJECTED', 'Operation has been rejected.', 409)
            db.execute('UPDATE merchant_states SET state_json=? WHERE merchant_id=? AND player_id=? AND game_id=?',
                       (encode(candidate['state']), merchant_id, operation['player_id'], operation['game_id']))
            db.execute("UPDATE game_operations SET status='settled',response_json=? WHERE id=?", (encode(response), operation_id))
        return response

    def operations(self, merchant_id, payload):
        self.merchant(merchant_id)
        count = limit(payload.get('limit', 20))
        with self.connection() as db:
            rows = db.execute('SELECT * FROM game_operations WHERE merchant_id=? AND seq>? ORDER BY seq LIMIT ?',
                              (merchant_id, amount_cursor(payload.get('after_seq', 0)), count)).fetchall()
        return {'operations': [{'seq': row['seq'], 'operation_id': row['id'], 'player_id': row['player_id'],
                                'game_id': row['game_id'], 'status': row['status'], 'error_code': row['error_code'],
                                'debit_transaction_id': row['id'] + ':debit' if json.loads(row['candidate_json'])['debit_minor'] else None,
                                'credit_transaction_id': row['id'] + ':credit' if json.loads(row['candidate_json'])['credit_minor'] else None,
                                'result': json.loads(row['response_json']) if row['response_json'] else None}
                               for row in rows]}

    def history(self, token, count=20):
        session = self._session(token)
        with self.connection() as db:
            rows = db.execute("SELECT response_json FROM game_operations WHERE merchant_id=? AND player_id=? AND status='settled' ORDER BY seq DESC LIMIT ?",
                              (session['merchant_id'], session['player_id'], limit(count))).fetchall()
        return [json.loads(row[0]) for row in rows]


def amount_cursor(value):
    if type(value) is not int or not 0 <= value <= 9_000_000_000_000_000:
        raise ServiceError('INVALID_ARGUMENT', 'after_seq must be a nonnegative integer.')
    return value
