from dataclasses import dataclass
from typing import Protocol


class ServiceError(ValueError):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.status = code, status


@dataclass(frozen=True)
class Outcome:
    state: dict
    event: dict
    debit_minor: int
    credit_minor: int


class Game(Protocol):
    game_id: str
    title: str
    version: str
    ruleset_id: str
    config: dict

    def initial_state(self, seed: str) -> dict: ...
    def normalize_bet(self, payload: dict) -> dict: ...
    def step(self, state: dict, bet: dict, seed: str, sid: str) -> Outcome: ...
    def public_state(self, state: dict) -> dict: ...


class Registry:
    def __init__(self, games=()):
        self._games = {}
        self._metadata = {}
        for game in games:
            self.register(game)

    def register(self, game: Game, metadata=None):
        if game.game_id in self._games:
            raise ValueError('Duplicate game ID: ' + game.game_id)
        self._games[game.game_id] = game
        self._metadata[game.game_id] = metadata or {}

    def games(self):
        return tuple(self._games.values())

    def get(self, game_id):
        try:
            return self._games[game_id]
        except KeyError:
            raise ServiceError('GAME_NOT_FOUND', 'Unknown game.', 404) from None

    def catalog(self):
        return [{**self._metadata[g.game_id], 'id': g.game_id, 'title': g.title, 'engine_version': g.version,
                 'ruleset_id': g.ruleset_id} for g in self._games.values()]
