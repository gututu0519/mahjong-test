"""SQLite schema, connections and transaction boundary."""
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from .encoding import encode

class Storage:
    def __init__(self, database, registry):
        self.database = str(Path(database).resolve())
        Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        self.registry = registry
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError(f'Unsupported database version: {version}')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS players (
                    id TEXT PRIMARY KEY, balance_minor INTEGER NOT NULL CHECK(balance_minor >= 0),
                    created_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, player_id TEXT NOT NULL REFERENCES players(id),
                    expires_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS game_states (
                    player_id TEXT NOT NULL REFERENCES players(id), game_id TEXT NOT NULL,
                    state_json TEXT NOT NULL, PRIMARY KEY(player_id,game_id));
                CREATE TABLE IF NOT EXISTS rulesets (
                    game_id TEXT NOT NULL, ruleset_id TEXT NOT NULL, config_json TEXT NOT NULL,
                    PRIMARY KEY(game_id,ruleset_id));
                CREATE TABLE IF NOT EXISTS spins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, player_id TEXT NOT NULL REFERENCES players(id),
                    game_id TEXT NOT NULL, round_id TEXT NOT NULL, request_key TEXT NOT NULL,
                    request_json TEXT NOT NULL, response_json TEXT NOT NULL, state_json TEXT NOT NULL,
                    ruleset_id TEXT NOT NULL, created_at INTEGER NOT NULL,
                    UNIQUE(player_id,game_id,request_key));
                CREATE TABLE IF NOT EXISTS ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, player_id TEXT NOT NULL REFERENCES players(id),
                    spin_id INTEGER UNIQUE REFERENCES spins(id), kind TEXT NOT NULL,
                    debit_minor INTEGER NOT NULL CHECK(debit_minor >= 0),
                    credit_minor INTEGER NOT NULL CHECK(credit_minor >= 0),
                    balance_before INTEGER NOT NULL, balance_after INTEGER NOT NULL CHECK(balance_after >= 0),
                    created_at INTEGER NOT NULL,
                    CHECK(balance_after = balance_before - debit_minor + credit_minor));
                CREATE INDEX IF NOT EXISTS ledger_player ON ledger(player_id,id);
                CREATE INDEX IF NOT EXISTS spins_player ON spins(player_id,id);
                PRAGMA user_version=1;
            ''')
            for game in self.registry.games():
                db.execute('INSERT OR IGNORE INTO rulesets VALUES (?,?,?)',
                           (game.game_id, game.ruleset_id, encode(game.config)))

    @contextmanager
    def connection(self, transaction=False):
        db = sqlite3.connect(self.database, isolation_level=None, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA synchronous=FULL')
        try:
            if transaction:
                db.execute('BEGIN IMMEDIATE')
            yield db
            if transaction:
                db.commit()
        except BaseException:
            if transaction:
                db.rollback()
            raise
        finally:
            db.close()
