"""Small application facade; responsibilities live in separate components."""
from .storage import Storage
from .sessions import Sessions
from .queries import Queries
from .settlement import Settlement


class GameService:
    def __init__(self, database, registry):
        units = {getattr(game, 'minor_unit', 100) for game in registry.games()}
        if len(units) != 1:
            raise ValueError('Games with different monetary precision require separate services')
        minor_unit = units.pop()
        self.store = Storage(database, registry)
        self.sessions = Sessions(self.store, minor_unit)
        self.queries = Queries(self.store, self.sessions)
        self.settlement = Settlement(self.store, self.sessions, self.queries)
        self.database, self.registry = self.store.database, registry

    def connection(self, transaction=False):
        return self.store.connection(transaction)

    def create_session(self):
        return self.sessions.create_session()

    def ensure_local_demo(self):
        return self.sessions.ensure_local_demo()

    def wallet(self, token):
        return self.queries.wallet(token)

    def state(self, token, game_id):
        return self.queries.state(token, game_id)

    def history(self, token, limit=20):
        return self.queries.history(token, limit)

    def spin(self, token, game_id, request_key, previous_sid, bet_payload):
        return self.settlement.spin(token, game_id, request_key, previous_sid, bet_payload)
