import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.core.contracts import ServiceError
from server.games.captains_bounty.engine import CaptainsBounty, evaluate
from server.adapters.pg.captains_bounty import SCHEMA, SALT, encode_response, transaction
from server.adapters.pg.protocol import pack, unpack, text_field, field, double_field
from server.adapters.pg.wire import decode
from server.services.captains_bounty_demo import CLIENT, build_server


def binary_request(token, previous='0', seed=17, coin=.1):
    raw = (text_field(1, token) + field(2, 0, 2) + field(3, 0, 1) + text_field(5, previous)
           + text_field(12, '0_C') + double_field(21, coin) + field(22, 0, 2))
    return pack(raw, seed, salt=SALT)


class CaptainsBountyTests(unittest.TestCase):
    def test_wallet_retry_free_restart_and_history(self):
        rows = json.loads((CLIENT / 'fixtures/spin-evidence.json').read_text(encoding='utf-8'))['spins']
        first = next(i for i, r in enumerate(rows) if r['transaction']['st'] == 1 and r['transaction']['nst'] == 21)
        last = next(i for i in range(first + 1, len(rows)) if rows[i]['transaction']['nst'] == 1)
        captured = rows[first:last + 1]
        self._check_persisted_round(captured)

    def test_last_free_win_then_cascade_preserves_paid_and_bonus_totals(self):
        rows = json.loads((CLIENT / 'fixtures/spin-evidence.json').read_text(encoding='utf-8'))['spins']
        final_free = next(i for i, row in enumerate(rows) if row['transaction']['st'] == 21
                          and row['transaction']['nst'] == 22 and not row['transaction']['fs'].get('s'))
        first = max(i for i in range(final_free) if rows[i]['transaction']['st'] == 1)
        last = next(i for i in range(final_free + 1, len(rows)) if rows[i]['transaction']['nst'] == 1)
        self.assertEqual(rows[last]['transaction']['fs']['aw'], 40.8)
        self.assertEqual(rows[last]['transaction']['aw'], 42)
        self._check_persisted_round(rows[first:last + 1])

    def _check_persisted_round(self, captured):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'game.sqlite3'
            http = build_server(0, database)
            token = http.service.create_session()['token']
            previous = '0'
            try:
                for i, row in enumerate(captured):
                    tx = row['transaction']
                    if i == 3:
                        snapshot = http.service.state(token, 'captains-bounty')
                        http.server_close()
                        http = build_server(0, database)
                        self.assertEqual(http.service.state(token, 'captains-bounty'), snapshot)
                    refills = tx.get('rns', [[], [], [], [], []])
                    with patch.object(http.pg.game, '_new_board', return_value=tx['rl']), patch.object(
                            http.pg.game, '_draw_column', side_effect=lambda rng, count, column, has_scatter=False: refills[column]):
                        response = http.pg.spin(binary_request(token, previous, coin=tx['cs']), token)
                        retry = http.pg.spin(binary_request(token, previous, seed=29, coin=tx['cs']), token)
                    self.assertEqual(unpack(response, 17, salt=SALT)[0], unpack(retry, 29, salt=SALT)[0])
                    actual = decode(unpack(response, 17, salt=SALT)[0], SCHEMA['transaction']['nested'])
                    self.assertEqual(actual['nst'], tx['nst'])
                    self.assertAlmostEqual(actual.get('aw', 0), tx.get('aw', 0))
                    previous = http.service.state(token, 'captains-bounty')['state']['sid']
                state = http.service.state(token, 'captains-bounty')
                self.assertEqual(state['state']['phase'], 'ready')
                debit = round(captured[0]['transaction']['tbb'] * 100)
                self.assertEqual(state['balance_minor'], 200000 - debit + state['state']['round_award_minor'])
                group = http.pg.history(token, {})['dt']['bh'][0]
                self.assertEqual(group['gtba'], debit / 100)
                self.assertEqual(group['gtwa'], captured[-1]['transaction']['aw'])
                self.assertEqual(group['fscc'], 10)
                self.assertEqual(len(group['bd']), len(captured))
                info_body = pack(text_field(1, token) + field(2, 0, 2) + field(3, 0, 1), 11, salt=SALT)
                info = decode(unpack(http.pg.game_info(info_body, token), 11, salt=SALT)[0], SCHEMA['transaction']['nested'])
                for key in ('rl', 'sid', 'nst', 'fs', 'aw'):
                    self.assertEqual(info[key], actual[key])
            finally:
                http.server_close()

    def test_bet_lock_multiplier_and_generated_free_retrigger(self):
        game = CaptainsBounty()
        # A no-pay layout with three scatters starts ten free spins.
        board = [1, 8, 8, 1, 7, 7, 1, 6, 6, 5, 5, 5, 4, 4, 4]
        state = game.initial_state('free')
        with patch.object(game, '_new_board', return_value=board):
            outcome = game.step(state, state['bet'], 'free', '1')
            self.assertEqual(outcome.state['free']['remaining'], 10)
            self.assertEqual(outcome.state['free']['added'], 0)
            self.assertEqual(outcome.state['phase'], 'free_start')
            with self.assertRaises(ServiceError):
                game.step(outcome.state, dict(coin_minor=10, level=2), 'free', '2')
            again = game.step(outcome.state, state['bet'], 'free', '2')
            self.assertEqual(again.debit_minor, 0)
            self.assertEqual(again.event['multiplier'], 3)
            self.assertEqual(again.state['free']['remaining'], 19)
            self.assertEqual(again.state['free']['added'], 10)

    def test_captured_paylines_and_binary_roundtrip(self):
        rows = json.loads((CLIENT / 'fixtures/spin-evidence.json').read_text(encoding='utf-8'))['spins']
        self.assertGreater(len(rows), 0)
        for row in rows:
            tx = row['transaction']
            with self.subTest(request=row['request']):
                result = evaluate(tx['rl'], round(tx['cs'] * 100), tx['ml'], tx['wm'])
                self.assertEqual(result['winning_positions'], tx.get('wp', {}))
                self.assertEqual(result['base_awards_minor'], {k: round(v * 100) for k, v in tx.get('lw', {}).items()})
                self.assertEqual(result['win_minor'], round(tx.get('tw', 0) * 100))
                self.assertEqual(decode(encode_response(tx), SCHEMA['transaction']['nested']), tx)

    def test_captured_complete_state_sequences(self):
        rows = json.loads((CLIENT / 'fixtures/spin-evidence.json').read_text(encoding='utf-8'))['spins']
        game = CaptainsBounty()
        state = game.initial_state('capture-verification')
        for row in rows:
            tx = row['transaction']
            bet = dict(coin_minor=round(tx['cs'] * 100), level=tx['ml'])
            refills = tx.get('rns', [[], [], [], [], []])
            with patch.object(game, '_new_board', return_value=tx['rl']), patch.object(
                    game, '_draw_column', side_effect=lambda rng, count, column, has_scatter=False: refills[column]):
                outcome = game.step(state, bet, 'capture-verification', str(row['request']))
            state = outcome.state
            actual = transaction(outcome.event, dict(before_minor=1000000, debit_minor=outcome.debit_minor,
                                                      after_minor=1000000 - outcome.debit_minor + outcome.credit_minor))
            with self.subTest(request=row['request']):
                for key in ('st', 'nst', 'rl', 'wm', 'wp', 'lw', 'lwm', 'rns', 'rs', 'fs', 'ge', 'aw', 'tw', 'tb', 'tbb', 'np'):
                    # protobuf omits numeric defaults and empty maps/lists.
                    def normalized(value):
                        if isinstance(value, dict):
                            return {k: normalized(v) for k, v in value.items() if v not in (None, 0, 0.0, [], {}) or k == 'as'}
                        return value or None
                    self.assertEqual(normalized(actual.get(key)), normalized(tx.get(key)), key)


if __name__ == '__main__':
    unittest.main()
