"""One atomic operation: idempotency, engine result, wallet and ledger."""
import json
import secrets
import time
from .contracts import ServiceError
from .encoding import encode

class Settlement:
    def __init__(self, store, sessions, queries):
        self.store, self.sessions, self.queries = store, sessions, queries

    def spin(self, token, game_id, request_key, previous_sid, bet_payload):
        if not isinstance(request_key, str) or not 1 <= len(request_key) <= 128:
            raise ServiceError('REQUEST_KEY_INVALID', 'Use a 1..128 character idempotency key.')
        if not isinstance(previous_sid, str) or len(previous_sid) > 64:
            raise ServiceError('PREVIOUS_SID_INVALID', 'previous_sid must be a string from the last state.')
        game = self.store.registry.get(game_id)
        bet = game.normalize_bet(bet_payload)
        request_json = encode({'previous_sid': previous_sid, 'bet': bet})
        with self.store.connection(True) as db:
            player = self.sessions._player(db, token)
            cached = db.execute('''SELECT request_json,response_json FROM spins
                                   WHERE player_id=? AND game_id=? AND request_key=?''',
                                (player['id'], game_id, request_key)).fetchone()
            if cached:
                if cached['request_json'] != request_json:
                    raise ServiceError('IDEMPOTENCY_CONFLICT', 'This key was used for a different request.', 409)
                return json.loads(cached['response_json'])
            state = self.queries._state(db, player['id'], game)
            if previous_sid != state['sid']:
                raise ServiceError('STALE_STATE', 'Refresh game state before continuing.', 409)
            sid = str(db.execute('SELECT COALESCE(MAX(id),0)+1 FROM spins').fetchone()[0])
            outcome = game.step(state, bet, secrets.token_hex(32), sid)
            debit, credit = outcome.debit_minor, outcome.credit_minor
            if type(debit) is not int or type(credit) is not int or min(debit, credit) < 0:
                raise RuntimeError('Game returned invalid settlement amounts')
            before = player['balance_minor']
            if before < debit:
                raise ServiceError('INSUFFICIENT_BALANCE', 'Insufficient virtual credits.', 409)
            after = before - debit + credit
            if after > 9_000_000_000_000_000:
                raise ServiceError('BALANCE_LIMIT', 'Local account balance limit reached.', 409)
            response = {'game_id': game_id, 'sid': sid, 'round_id': outcome.event['round_id'],
                        'engine_version': game.version, 'ruleset_id': game.ruleset_id,
                        'wallet': {'before_minor': before, 'debit_minor': debit,
                                   'credit_minor': credit, 'after_minor': after},
                        'outcome': outcome.event}
            now = int(time.time())
            db.execute('''INSERT INTO spins(id,player_id,game_id,round_id,request_key,request_json,
                          response_json,state_json,ruleset_id,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)''',
                       (int(sid), player['id'], game_id, response['round_id'], request_key,
                        request_json, encode(response), encode(outcome.state), game.ruleset_id, now))
            db.execute('''INSERT INTO ledger(player_id,spin_id,kind,debit_minor,credit_minor,
                          balance_before,balance_after,created_at) VALUES (?,?,'spin',?,?,?,?,?)''',
                       (player['id'], int(sid), debit, credit, before, after, now))
            db.execute('UPDATE players SET balance_minor=? WHERE id=?', (after, player['id']))
            db.execute('UPDATE game_states SET state_json=? WHERE player_id=? AND game_id=?',
                       (encode(outcome.state), player['id'], game_id))
            return response
