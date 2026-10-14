"""Player creation, token validation and local demo identity."""
import hashlib
import secrets
import time
import uuid
from .contracts import ServiceError

class Sessions:
    def __init__(self, store):
        self.store = store

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

    @staticmethod
    def _create_player(db, player_id):
        now = int(time.time())
        db.execute('INSERT INTO players VALUES (?,?,?)', (player_id, 200000, now))
        db.execute('''INSERT INTO ledger(player_id,kind,debit_minor,credit_minor,balance_before,balance_after,created_at)
                      VALUES (?,'initial_credit',0,200000,0,200000,?)''', (player_id, now))

    def create_session(self):
        player_id, token = uuid.uuid4().hex, secrets.token_urlsafe(32)
        expiry = int(time.time()) + 86400
        with self.store.connection(True) as db:
            self._create_player(db, player_id)
            db.execute('INSERT INTO sessions VALUES (?,?,?)', (self._token_hash(token), player_id, expiry))
        return {'player_id': player_id, 'token': token, 'expires_at': expiry,
                'balance_minor': 200000, 'currency': 'DEMO', 'minor_unit': 100}

    def ensure_local_demo(self):
        # Fixed session is only for the existing captured client on loopback.
        with self.store.connection(True) as db:
            if db.execute("SELECT 1 FROM players WHERE id='local-demo'").fetchone() is None:
                self._create_player(db, 'local-demo')
            db.execute('INSERT OR REPLACE INTO sessions VALUES (?,?,?)',
                       (self._token_hash('local-demo-session'), 'local-demo', 253402300799))
