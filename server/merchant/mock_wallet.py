"""Authoritative platform wallet, isolated from every game-service database."""
import json
import time
from decimal import Decimal, InvalidOperation

from server.core.contracts import ServiceError
from .common import Database, amount, encode, identifier, limit


class MockWallet(Database):
    def __init__(self, path, merchants):
        super().__init__(path)
        self.merchants = merchants
        with self.connection(True) as db:
            for old, new in (('fp_players', 'prebet_players'), ('fp_policies', 'prebet_policies'), ('fp_decisions', 'prebet_decisions')):
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (old,)).fetchone():
                    db.execute('ALTER TABLE ' + old + ' RENAME TO ' + new)
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS accounts (
                    merchant_id TEXT NOT NULL, player_id TEXT NOT NULL, currency TEXT NOT NULL,
                    balance_minor INTEGER NOT NULL CHECK(balance_minor>=0), PRIMARY KEY(merchant_id,player_id));
                CREATE TABLE IF NOT EXISTS transactions (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, merchant_id TEXT NOT NULL,
                    transaction_id TEXT NOT NULL, player_id TEXT NOT NULL, kind TEXT NOT NULL,
                    reference_id TEXT, request_json TEXT NOT NULL, response_json TEXT,
                    error_code TEXT, created_at INTEGER NOT NULL, UNIQUE(merchant_id,transaction_id));
                CREATE TABLE IF NOT EXISTS canceled_debits (
                    merchant_id TEXT NOT NULL, transaction_id TEXT NOT NULL, request_json TEXT NOT NULL,
                    PRIMARY KEY(merchant_id,transaction_id));
                CREATE UNIQUE INDEX IF NOT EXISTS refund_once ON transactions(merchant_id,reference_id)
                    WHERE kind='refund' AND error_code IS NULL;
                CREATE TABLE IF NOT EXISTS prebet_players (
                    merchant_id TEXT NOT NULL,player_name TEXT NOT NULL,player_id TEXT NOT NULL,
                    PRIMARY KEY(merchant_id,player_name));
                CREATE TABLE IF NOT EXISTS prebet_policies (merchant_id TEXT PRIMARY KEY,range_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS prebet_decisions (
                    merchant_id TEXT NOT NULL,player_name TEXT NOT NULL,timestamp INTEGER NOT NULL,
                    bet_amount_minor INTEGER NOT NULL,type TEXT NOT NULL,response_json TEXT NOT NULL,
                    PRIMARY KEY(merchant_id,player_name,timestamp,bet_amount_minor,type));
            ''')

    def bind_prebet_player(self, merchant_id, player_id, player_name):
        from .prebet import external_username
        external_username(player_name)
        with self.connection(True) as db:
            db.execute('INSERT OR REPLACE INTO prebet_players VALUES (?,?,?)', (merchant_id, player_name, player_id))

    def prebet_policy(self, merchant_id, value=None):
        from .prebet import multiplier_range
        if value is not None:
            multiplier_range(value)
            with self.connection(True) as db:
                db.execute('INSERT OR REPLACE INTO prebet_policies VALUES (?,?)', (merchant_id, encode(value)))
        with self.connection() as db:
            row = db.execute('SELECT range_json FROM prebet_policies WHERE merchant_id=?', (merchant_id,)).fetchone()
            return json.loads(row[0]) if row else [-1, 0]

    def prebet_decision(self, merchant_id, payload):
        def failure(code, message):
            return {'code': code, 'data': None, 'msg': message}
        name, timestamp, kind = payload.get('player_name'), payload.get('timestamp'), payload.get('type')
        try:
            raw = payload.get('bet_amount')
            if type(raw) not in (str, int, float):
                raise ValueError()
            amount_decimal = Decimal(str(raw)) * 100
            if not amount_decimal.is_finite() or amount_decimal != amount_decimal.to_integral_value():
                raise ValueError()
            bet = amount(int(amount_decimal))
            if type(timestamp) is not int or timestamp <= 0 or kind not in ('NORMAL', 'SURE_WIN', 'FREE_SPIN', 'BUY_FREE_SPIN') or not isinstance(name, str):
                raise ValueError()
        except (ValueError, InvalidOperation):
            return failure(3001, 'Invalid preBetDecision parameters')
        policy = self.prebet_policy(merchant_id)
        with self.connection(True) as db:
            old = db.execute('SELECT response_json FROM prebet_decisions WHERE merchant_id=? AND player_name=? AND timestamp=? AND bet_amount_minor=? AND type=?',
                             (merchant_id, name, timestamp, bet, kind)).fetchone()
            if old:
                return json.loads(old[0])
            player = db.execute('SELECT player_id FROM prebet_players WHERE merchant_id=? AND player_name=?', (merchant_id, name)).fetchone()
            account = db.execute('SELECT balance_minor FROM accounts WHERE merchant_id=? AND player_id=?', (merchant_id, player[0])).fetchone() if player else None
            if not account:
                return failure(3004, 'Player does not exist or wallet unavailable')
            result = failure(3202, 'Insufficient available balance') if bet > account[0] else {'code': 0, 'data': {'maxWinMulti': policy}, 'msg': None}
            db.execute('INSERT INTO prebet_decisions VALUES (?,?,?,?,?,?)', (merchant_id, name, timestamp, bet, kind, encode(result)))
            return result

    def seed(self, merchant_id, player_id, balance_minor):
        identifier(player_id, 'player_id')
        amount(balance_minor)
        with self.connection(True) as db:
            # Restarting the simulator must never refill an existing wallet.
            db.execute('INSERT OR IGNORE INTO accounts VALUES (?,?,?,?)',
                       (merchant_id, player_id, self.merchants[merchant_id]['currency'], balance_minor))

    def _account(self, db, merchant_id, payload):
        player_id = identifier(payload.get('player_id'), 'player_id')
        merchant = self.merchants[merchant_id]
        if payload.get('currency') != merchant['currency'] or payload.get('minor_unit') != 100:
            raise ServiceError('CURRENCY_MISMATCH', 'Currency and minor_unit must match the merchant.', 409)
        row = db.execute('SELECT * FROM accounts WHERE merchant_id=? AND player_id=?',
                         (merchant_id, player_id)).fetchone()
        if row is None:
            raise ServiceError('ACCOUNT_NOT_FOUND', 'Platform player does not exist.', 404)
        return row

    @staticmethod
    def snapshot(row):
        return {'player_id': row['player_id'], 'currency': row['currency'], 'minor_unit': 100,
                'balance_minor': row['balance_minor']}

    def call(self, merchant_id, action, payload):
        if action == 'balance':
            with self.connection() as db:
                return self.snapshot(self._account(db, merchant_id, payload))
        if action in ('transactions/get', 'transactions/list'):
            with self.connection() as db:
                self._account(db, merchant_id, payload)
                params = [merchant_id, payload['player_id']]
                query = 'SELECT * FROM transactions WHERE merchant_id=? AND player_id=?'
                if action.endswith('/get'):
                    query += ' AND transaction_id=?'
                    params.append(identifier(payload.get('transaction_id'), 'transaction_id'))
                query += ' ORDER BY seq DESC LIMIT ?'
                params.append(limit(payload.get('limit', 20)))
                rows = db.execute(query, params).fetchall()
                return {**self.snapshot(self._account(db, merchant_id, payload)),
                        'transactions': [{'transaction_id': r['transaction_id'], 'kind': r['kind'],
                                          'status': 'rejected' if r['error_code'] else 'applied',
                                          'error_code': r['error_code'],
                                          'data': json.loads(r['response_json']) if r['response_json'] else None}
                                         for r in rows]}
        if action not in ('debit', 'credit', 'refund'):
            raise ServiceError('NOT_FOUND', 'Unknown wallet operation.', 404)
        transaction_id = identifier(payload.get('transaction_id'), 'transaction_id')
        identifier(payload.get('round_id'), 'round_id')
        value = amount(payload.get('amount_minor'))
        reference = identifier(payload.get('reference_id'), 'reference_id') if action != 'debit' else None
        canonical = encode({'kind': action, **{k: payload.get(k) for k in
                           ('player_id', 'currency', 'minor_unit', 'transaction_id', 'round_id', 'amount_minor')},
                            'reference_id': reference})
        rejection = None
        with self.connection(True) as db:
            account = self._account(db, merchant_id, payload)
            existing = db.execute('SELECT * FROM transactions WHERE merchant_id=? AND transaction_id=?',
                                  (merchant_id, transaction_id)).fetchone()
            if existing:
                if existing['request_json'] != canonical:
                    raise ServiceError('TRANSACTION_CONFLICT', 'Transaction ID was used for a different request.', 409)
                if existing['error_code']:
                    raise ServiceError(existing['error_code'], 'Stored wallet rejection.', 409)
                return json.loads(existing['response_json'])
            before, change = account['balance_minor'], value if action != 'debit' else -value
            if action == 'debit':
                canceled = db.execute('SELECT request_json FROM canceled_debits WHERE merchant_id=? AND transaction_id=?',
                                      (merchant_id, transaction_id)).fetchone()
                if canceled:
                    rejection = 'TRANSACTION_CANCELED'
                elif before < value:
                    rejection = 'INSUFFICIENT_BALANCE'
            else:
                debit = db.execute('SELECT * FROM transactions WHERE merchant_id=? AND transaction_id=?',
                                   (merchant_id, reference)).fetchone()
                debit_request = json.loads(debit['request_json']) if debit else None
                if debit and (debit['kind'] != 'debit' or debit['player_id'] != payload['player_id']
                              or debit_request['round_id'] != payload['round_id']):
                    rejection = 'REFERENCE_INVALID'
                refunded = db.execute("SELECT 1 FROM transactions WHERE merchant_id=? AND reference_id=? AND kind='refund' AND error_code IS NULL",
                                      (merchant_id, reference)).fetchone()
                if refunded:
                    rejection = 'ALREADY_REFUNDED'
                if action == 'credit':
                    if not debit or debit['error_code']:
                        rejection = 'REFERENCE_INVALID'
                elif not rejection:
                    if debit and debit_request['amount_minor'] != value:
                        rejection = 'REFERENCE_INVALID'
                    elif db.execute("SELECT 1 FROM transactions WHERE merchant_id=? AND reference_id=? AND kind='credit' AND error_code IS NULL",
                                    (merchant_id, reference)).fetchone():
                        rejection = 'REFERENCE_INVALID'
                    else:
                        db.execute('INSERT OR IGNORE INTO canceled_debits VALUES (?,?,?)',
                                   (merchant_id, reference, canonical))
                        if not debit or debit['error_code']:
                            change = 0
            if before + change > 9_000_000_000_000_000:
                raise ServiceError('BALANCE_LIMIT', 'Platform wallet limit reached.', 409)
            result = {**self.snapshot(account), 'transaction_id': transaction_id, 'status': 'applied',
                      'amount_minor': value, 'applied_minor': abs(change), 'balance_before_minor': before,
                      'balance_minor': before + change}
            db.execute('INSERT INTO transactions(merchant_id,transaction_id,player_id,kind,reference_id,request_json,response_json,error_code,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
                       (merchant_id, transaction_id, payload['player_id'], action, reference, canonical,
                        None if rejection else encode(result), rejection, int(time.time())))
            if not rejection:
                db.execute('UPDATE accounts SET balance_minor=? WHERE merchant_id=? AND player_id=?',
                           (result['balance_minor'], merchant_id, payload['player_id']))
        if rejection:
            raise ServiceError(rejection, 'Wallet transaction rejected.', 409)
        return result
