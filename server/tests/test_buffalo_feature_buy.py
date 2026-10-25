import concurrent.futures
import copy
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlencode

from server.adapters.pg.buffalo_win import PGAdapter
from server.core.contracts import Registry, ServiceError
from server.core.service import GameService
from server.games.buffalo_win.engine import BuffaloWin


FIXTURE = Path(__file__).resolve().parents[2] / 'clients/buffalo-win/fixtures/feature-buy-capture.json'


class CapturedBuy(BuffaloWin):
    """Inject recorded symbols only in the offline protocol/settlement oracle."""
    case = None

    def _start_board(self, rng, free):
        si = self.case['si']
        return copy.deepcopy((si['orl'], si['s'], si.get('es') or {}, si.get('bsc') or {}))

    def _buy_board(self, rng):
        return self._start_board(rng, False)

    def _column(self, rng, first=False):
        return self.case['si']['rs']['oecrl'][:]

    def _buy_column(self, rng, needs_scatter):
        return self._column(rng)

    def _new_blocks(self, board, rng, offset=0, first_id=1):
        si = self.case['si']
        blocks = (si.get('rs') or {}).get('nes') or {}
        return copy.deepcopy(blocks), {key: si['bsc'][key] for key in blocks}


def form(previous='0', **values):
    return urlencode({'id': previous, 'cs': '0.02', 'ml': 1, 'btt': 2, 'pf': 1, 'wk': '0_C', **values}).encode()


class BuffaloFeatureBuyTests(unittest.TestCase):
    def test_captured_complete_purchase_protocol_and_ledger(self):
        fixture = json.loads(FIXTURE.read_bytes())
        self.assertEqual(len(fixture['spins']), 25)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'buy.sqlite3'
            game = CapturedBuy()
            service = GameService(path, Registry([game]))
            token = service.create_session()['token']
            adapter = PGAdapter(service)
            info = adapter.game_info(token)['dt']
            self.assertEqual(info['fb'], fixture['game_info']['data']['fb'])
            self.assertEqual(info['gcs'], fixture['game_info']['data']['gcs'])
            self.assertTrue(set(fixture['game_info']['data']['cs']).issubset(info['cs']))
            previous, balance = '0', service.wallet(token)['balance_minor']
            for case in fixture['spins']:
                with self.subTest(row=case['row']):
                    game.case = case
                    request = form(previous, **case['request'])
                    result = adapter.spin(request, token)
                    tx = result['dt']['si']
                    for key in ('st', 'nst', 'cs', 'ml', 'tb', 'tbb', 'tw', 'aw', 'fs', 'gm', 's',
                                'sc', 'rl', 'orl', 'es', 'bsc', 'wp', 'ix',
                                'ctw', 'acw', 'twbm', 'ge', 'fstc'):
                        self.assertEqual(tx[key], case['si'].get(key), key)
                    # Optional animation hints differ between client versions.
                    # Compare captured reel symbols/blocks; pr/sr are not rules.
                    for key in ('ecrl', 'oecrl', 'nes'):
                        self.assertEqual((tx.get('rs') or {}).get(key),
                                         (case['si'].get('rs') or {}).get(key), 'rs.' + key)
                    # sw[0] differs between captures; its full meaning is not
                    # confirmed. Verify the actual base award in sw[1].
                    self.assertEqual({key: value[1] for key, value in (tx.get('sw') or {}).items()},
                                     {key: value[1] for key, value in (case['si'].get('sw') or {}).items()})
                    balance += case['wallet_change_minor']
                    self.assertEqual(service.wallet(token)['balance_minor'], balance)
                    self.assertEqual(adapter.spin(request, token), result)
                    self.assertEqual(adapter.game_info(token)['dt']['ls']['si'], tx)
                    previous = tx['sid']
                    # Reopen SQLite mid-trigger and mid-free; no outcome regeneration.
                    service = GameService(path, Registry([game]))
                    adapter = PGAdapter(service)
                    self.assertEqual(adapter.spin(request, token), result)
            self.assertEqual(service.state(token, game.game_id)['state']['phase'], 'ready')
            self.assertEqual(balance, 200196)
            with service.connection() as db:
                self.assertEqual(db.execute("SELECT COUNT(*),SUM(debit_minor),SUM(credit_minor) FROM ledger WHERE kind='spin'").fetchone()[:],
                                 (25, 1500, 1696))

    def test_generated_purchase_guarantees_feature_and_single_debit(self):
        game = BuffaloWin()
        boards = set()
        for seed in range(40):
            state = game.initial_state('initial')
            bet = game.normalize_bet({'cs': '0.02', 'ml': 1, 'buy_free': True})
            first = game.step(state, bet, str(seed), '1')
            self.assertEqual(first.debit_minor, 1500)
            self.assertEqual(first.state['phase'], 'paid_extension')
            self.assertEqual(first.event['scatter_count'], 2)
            boards.add(tuple(first.event['board']))
            state = first.state
            for step in range(2, 200):
                outcome = game.step(state, state['bet'], f'{seed}-{step}', str(step))
                self.assertEqual(outcome.debit_minor, 0)
                state = json.loads(json.dumps(outcome.state))
                if state['phase'] == 'free_start':
                    self.assertEqual(state['free']['total'], 10)
                    self.assertEqual(state['free']['remaining'], 10)
                    self.assertEqual(state['multiplier'], 1)
                    break
            else:
                self.fail('Bought feature did not start')
        self.assertGreater(len(boards), 30)

    def test_buy_retry_balance_locking_and_invalid_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            game = BuffaloWin()
            service = GameService(Path(directory) / 'buy.sqlite3', Registry([game]))
            token = service.create_session()['token']
            adapter = PGAdapter(service)
            request = form(fb=2)
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
                results = list(pool.map(lambda _: adapter.spin(request, token), range(12)))
            self.assertTrue(all(result == results[0] for result in results))
            self.assertEqual(service.wallet(token)['balance_minor'], 198500)
            with self.assertRaises(ServiceError) as stale:
                adapter.spin(form(), token)
            self.assertEqual(stale.exception.code, 'STALE_STATE')
            previous = results[0]['dt']['si']['sid']
            before = service.state(token, game.game_id)
            for body, code in [(form(previous, fb=2), 'FEATURE_LOCKED'),
                               (form(previous, ml=2), 'BET_LOCKED'),
                               (form(previous, fb=1), 'BET_INVALID'),
                               (form(previous, ab=1), 'BET_INVALID'),
                               (form(previous, fb='2.0'), 'BET_INVALID')]:
                with self.assertRaises(ServiceError) as error:
                    adapter.spin(body, token)
                self.assertEqual(error.exception.code, code)
                self.assertEqual(service.state(token, game.game_id), before)
            for _ in range(200):
                state = service.state(token, game.game_id)['state']
                if state['phase'] == 'free_start':
                    break
                adapter.spin(form(state['sid']), token)
            else:
                self.fail('Bought feature did not reach free spins')
            before = service.state(token, game.game_id)
            with self.assertRaises(ServiceError) as locked:
                adapter.spin(form(before['state']['sid'], fb=2), token)
            self.assertEqual(locked.exception.code, 'FEATURE_LOCKED')
            self.assertEqual(service.state(token, game.game_id), before)
            poor = service.create_session()['token']
            service.state(poor, game.game_id)
            with service.connection(True) as db:
                db.execute('UPDATE players SET balance_minor=1499 WHERE id=?', (service.wallet(poor)['player_id'],))
            before = service.state(poor, game.game_id)
            with self.assertRaises(ServiceError) as error:
                adapter.spin(form(fb=2), poor)
            self.assertEqual(error.exception.code, 'INSUFFICIENT_BALANCE')
            self.assertEqual(service.state(poor, game.game_id), before)

    def test_upgrade_finishes_legacy_natural_round_and_preserves_bets(self):
        game = BuffaloWin()
        for coin in (3, 10, 30, 90):
            self.assertEqual(game.normalize_bet({'coin_minor': coin})['coin_minor'], coin)
        state = game.initial_state('initial')
        state.update(phase='free_start', ruleset_id=game.compatible_ruleset_id,
                     free={'remaining': 1, 'total': 10, 'added': 0, 'rc': 0, 'award_minor': 1234})
        result = game.step(state, state['bet'], 'continue-old-free', '1')
        self.assertEqual(result.debit_minor, 0)
        self.assertGreaterEqual(result.state['free']['award_minor'], 1234)


if __name__ == '__main__':
    unittest.main()
