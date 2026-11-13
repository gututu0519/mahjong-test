"""Player creation, token validation and local demo identity."""
import hashlib
import secrets
import time
import uuid
from .contracts import ServiceError

class Sessions:
    def __init__(self, store, minor_unit=100):
        self.store = store
        if minor_unit not in (100, 10000):
            raise ValueError('Unsupported monetary precision')
        self.minor_unit = minor_unit
        self.initial_credit = 2000 * minor_unit
        with store.connection(True) as db:
            db.execute('CREATE TABLE IF NOT EXISTS wallet_settings (name TEXT PRIMARY KEY, value INTEGER NOT NULL)')
            row = db.execute("SELECT value FROM wallet_settings WHERE name='minor_unit'").fetchone()
            # Existing wallets predate precision metadata and use cents.
            old_unit = row[0] if row else 100 if db.execute('SELECT 1 FROM players LIMIT 1').fetchone() else minor_unit
            if old_unit != minor_unit:
                raise ValueError('Database wallet precision does not match the selected games')
            db.execute("INSERT OR IGNORE INTO wallet_settings VALUES ('minor_unit',?)", (minor_unit,))

    @staticmethod
    def _token_hash(token):
        if not isinstance(token, str) or not 1 <= len(token) <= 256:
            raise ServiceError('SESSION_INVALID', 'A valid local session is required.', 401)
        return hashlib.sha256(token.encode()).hexdigest()

    def _player(self, db, token):
        row = db.execute('''SELECT p.* FROM sessions s JOIN players p ON p.id=s.player_id
                            WHERE s.token_hash=? AND s.expires_at>?''',
                         (self._token_hash(token), int(time.time()))).fetchone()
        if row is None:
            raise ServiceError('SESSION_INVALID', 'Session is missing or expired.', 401)
        return row

    def _create_player(self, db, player_id):
        now = int(time.time())
        db.execute('INSERT INTO players VALUES (?,?,?)', (player_id, self.initial_credit, now))
        db.execute('''INSERT INTO ledger(player_id,kind,debit_minor,credit_minor,balance_before,balance_after,created_at)
                      VALUES (?,'initial_credit',0,?,0,?,?)''', (player_id, self.initial_credit, self.initial_credit, now))

    def create_session(self):
        player_id, token = uuid.uuid4().hex, secrets.token_urlsafe(32)
        expiry = int(time.time()) + 86400
        with self.store.connection(True) as db:
            self._create_player(db, player_id)
            db.execute('INSERT INTO sessions VALUES (?,?,?)', (self._token_hash(token), player_id, expiry))
        return {'player_id': player_id, 'token': token, 'expires_at': expiry,
                'balance_minor': self.initial_credit, 'currency': 'DEMO', 'minor_unit': self.minor_unit}

    def ensure_local_demo(self):
        # Fixed session is only for the existing captured client on loopback.
        with self.store.connection(True) as db:
            if db.execute("SELECT 1 FROM players WHERE id='local-demo'").fetchone() is None:
                self._create_player(db, 'local-demo')
            db.execute('INSERT OR REPLACE INTO sessions VALUES (?,?,?)',
                       (self._token_hash('local-demo-session'), 'local-demo', 253402300799))
