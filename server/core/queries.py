"""Wallet, game state and history access; no settlement writes."""
import json
import secrets
from .contracts import ServiceError
from .encoding import encode

class Queries:
    def __init__(self, store, sessions):
        self.store, self.sessions = store, sessions

    def wallet(self, token):
        with self.store.connection() as db:
            p = self.sessions._player(db, token)
            return {'player_id': p['id'], 'balance_minor': p['balance_minor'],
                    'currency': 'DEMO', 'minor_unit': 100}

    def _state(self, db, player_id, game):
        row = db.execute('SELECT state_json FROM game_states WHERE player_id=? AND game_id=?',
                         (player_id, game.game_id)).fetchone()
        if row:
            return json.loads(row[0])
        state = game.initial_state(secrets.token_hex(32))
        db.execute('INSERT INTO game_states VALUES (?,?,?)', (player_id, game.game_id, encode(state)))
        return state

    def state(self, token, game_id):
        game = self.store.registry.get(game_id)
        with self.store.connection(True) as db:
            p = self.sessions._player(db, token)
            state = self._state(db, p['id'], game)
            return {'game_id': game_id, 'balance_minor': p['balance_minor'],
                    'engine_version': game.version, 'ruleset_id': game.ruleset_id,
                    'state': game.public_state(state)}

    def history(self, token, limit=20):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ServiceError('LIMIT_INVALID', 'limit must be between 1 and 100.')
        with self.store.connection() as db:
            player = self.sessions._player(db, token)
            rows = db.execute('SELECT response_json FROM spins WHERE player_id=? ORDER BY id DESC LIMIT ?',
                              (player['id'], limit)).fetchall()
            return [json.loads(row[0]) for row in rows]
