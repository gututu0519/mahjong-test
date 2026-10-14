import concurrent.futures
import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from server.core.contracts import Registry, ServiceError
from server.core.service import GameService
from server.games.mahjong_ways2.engine import MahjongWays2
from server.tests.test_engine import Scripted, blank


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'test.sqlite3'
        self.game = Scripted([])
        second = Scripted([])
        second.game_id = 'test-second-game'
        self.registry = Registry([self.game, second])
        self.service = GameService(self.path, self.registry)
        self.token = self.service.create_session()['token']

    def spin(self, key='one', sid='0', game='mahjong-ways2', bet=None):
        return self.service.spin(self.token, game, key, sid, bet or {'coin_minor': 1, 'level': 5})

    def test_durable_idempotency_and_restart(self):
        response = self.spin()
        self.assertEqual(response['wallet']['after_minor'], 199900)
        self.assertEqual(self.spin(), response)
        restarted = GameService(self.path, self.registry)
        self.assertEqual(restarted.spin(self.token, 'mahjong-ways2', 'one', '0', {'coin_minor': 1, 'level': 5}), response)
        self.assertEqual(restarted.state(self.token, 'mahjong-ways2')['state']['sid'], response['sid'])
        with restarted.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM ledger WHERE kind='spin'").fetchone()[0], 1)

    def test_concurrent_same_request_charged_once(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.spin(), range(16)))
        self.assertTrue(all(item == results[0] for item in results))
        self.assertEqual(self.service.wallet(self.token)['balance_minor'], 199900)

    def test_stale_and_conflicting_requests(self):
        self.spin()
        for key, sid, bet, code in [
            ('two', '0', {}, 'STALE_STATE'),
            ('one', '0', {'coin_minor': 6, 'level': 5}, 'IDEMPOTENCY_CONFLICT'),
        ]:
            with self.assertRaises(ServiceError) as result:
                self.spin(key, sid, bet=bet)
            self.assertEqual(result.exception.code, code)
        self.assertEqual(self.service.wallet(self.token)['balance_minor'], 199900)

    def test_two_games_share_wallet_but_not_state(self):
        first = self.spin()
        second = self.spin(game='test-second-game')
        self.assertEqual(second['wallet']['before_minor'], first['wallet']['after_minor'])
        self.assertEqual(self.service.state(self.token, 'mahjong-ways2')['state']['sid'], first['sid'])
        self.assertEqual(self.service.state(self.token, 'test-second-game')['state']['sid'], second['sid'])

    def test_player_isolation(self):
        other = self.service.create_session()['token']
        self.spin()
        self.assertEqual(self.service.wallet(other)['balance_minor'], 200000)
        self.assertEqual(self.service.history(other), [])

    def test_insufficient_balance_rolls_back(self):
        with self.service.connection(True) as db:
            db.execute('UPDATE players SET balance_minor=0')
        before = self.service.state(self.token, 'mahjong-ways2')
        with self.assertRaises(ServiceError) as result:
            self.spin()
        self.assertEqual(result.exception.code, 'INSUFFICIENT_BALANCE')
        self.assertEqual(self.service.state(self.token, 'mahjong-ways2'), before)
        self.assertEqual(self.service.history(self.token), [])

    def test_engine_failure_rolls_back(self):
        before = self.service.wallet(self.token)
        def fail(*args):
            raise RuntimeError('injected failure')
        self.game.step = fail
        with self.assertRaises(RuntimeError):
            self.spin()
        self.assertEqual(self.service.wallet(self.token), before)
        self.assertEqual(self.service.history(self.token), [])

    def test_ledger_failure_rolls_back_inserted_spin_and_state(self):
        before = self.service.state(self.token, 'mahjong-ways2')
        with self.service.connection() as db:
            db.execute("""CREATE TRIGGER reject_settlement BEFORE INSERT ON ledger
                          WHEN NEW.kind='spin' BEGIN SELECT RAISE(ABORT,'injected ledger failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.spin()
        self.assertEqual(self.service.state(self.token, 'mahjong-ways2'), before)
        self.assertEqual(self.service.history(self.token), [])

    def test_concurrent_different_keys_cannot_advance_same_state_twice(self):
        def attempt(key):
            try:
                return self.spin(key)
            except ServiceError as error:
                return error.code
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, ['first', 'second']))
        self.assertEqual(sum(isinstance(r, dict) for r in results), 1)
        self.assertIn('STALE_STATE', results)
        self.assertEqual(self.service.wallet(self.token)['balance_minor'], 199900)

    def test_round_bet_is_locked_and_seed_is_not_public(self):
        board = blank()
        board[8] = board[15] = 2
        self.service.state(self.token, 'mahjong-ways2')
        self.game.boards = [board]
        first = self.spin()
        state = self.service.state(self.token, 'mahjong-ways2')['state']
        self.assertEqual(state['phase'], 'paid_cascade')
        self.assertNotIn('seed', state)
        with self.assertRaises(ServiceError) as result:
            self.spin('next', first['sid'], bet={'coin_minor': 6, 'level': 5})
        self.assertEqual(result.exception.code, 'BET_LOCKED')

    def test_ledger_reconciles(self):
        sid = '0'
        for index in range(20):
            sid = self.spin(str(index), sid)['sid']
        with self.service.connection() as db:
            total = db.execute('SELECT SUM(credit_minor-debit_minor) FROM ledger').fetchone()[0]
        self.assertEqual(total, self.service.wallet(self.token)['balance_minor'])


if __name__ == '__main__':
    unittest.main()
