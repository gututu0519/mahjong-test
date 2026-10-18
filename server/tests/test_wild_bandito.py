import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.core.contracts import ServiceError
from server.games.wild_bandito.engine import WildBandito, evaluate, VISIBLE
from server.adapters.pg.wild_bandito import SCHEMA, encode_response
from server.adapters.pg.wire import decode
from server.adapters.pg.protocol import pack, unpack, text_field, field, double_field
from server.services.wild_bandito_demo import build_server, CLIENT


def losing_board():
    return [s for s in (2, 3, 4, 5, 6) for _ in range(5)]


class WildBanditoRulesTests(unittest.TestCase):
    def test_all_captured_normal_responses_and_gold(self):
        evidence = json.loads((CLIENT / 'fixtures/spin-evidence.json').read_text(encoding='utf-8'))
        self.assertGreaterEqual(evidence['checked'], 81)
        self.assertEqual(evidence['failures'], [])
        for row in evidence['spins']:
            tx = row['transaction']
            with self.subTest(request=row['request']):
                e = evaluate(tx['orl'], round(tx['cs'] * 100), tx['ml'], tx.get('gm', 0))
                self.assertEqual(e['winning_positions'], tx.get('wp', {}))
                self.assertEqual(e['ways'], tx.get('snww', {}))
                self.assertEqual(e['win_minor'], round(tx.get('tw', 0) * 100))
                won = {p for cells in tx.get('wp', {}).values() for p in cells}
                converted = won & set(tx.get('ssb', {}).values())
                self.assertEqual(set(tx.get('ptbr', [])), won - converted)
                self.assertEqual(tx['rl'], [0 if p in converted else s for p, s in enumerate(tx['orl'])])
                wire = encode_response(tx)
                result = decode(wire, SCHEMA['transaction']['nested'])
                self.assertEqual(result, tx)

    def test_hidden_symbols_do_not_pay(self):
        board = losing_board()
        for c in range(5):
            board[c * 5] = 10
        self.assertEqual(evaluate(board, 10, 2, 1)['win_minor'], 0)

    def test_free_trigger_and_retrigger_follow_published_rules(self):
        game = WildBandito()
        board = losing_board()
        for p in (1, 6, 11, 16):
            board[p] = 1
        state = game.initial_state('test')
        bet = state['bet']
        with patch.object(game, '_new_board', return_value=board):
            first = game.step(state, bet, 'seed', '1')
            self.assertEqual(first.debit_minor, 400)
            self.assertEqual(first.event['next_phase'], 'free_start')
            self.assertEqual(first.event['free']['remaining'], 14)
            second = game.step(first.state, bet, 'ignored', '2')
        self.assertEqual(second.debit_minor, 0)
        self.assertEqual(second.event['free']['remaining'], 27)
        self.assertEqual(second.event['free']['added'], 14)
        with self.assertRaises(ServiceError):
            game.step(first.state, {'coin_minor': 3, 'level': 2}, 'x', '3')

    def test_gold_conversion_cascade_and_free_multiplier_carry(self):
        game = WildBandito()
        board = losing_board()
        board[1] = board[6] = board[11] = 2
        state = game.initial_state('test')
        state.update(phase='free_start', seed='seed', free=dict(remaining=1, total=1, award_minor=0, added=0, multiplier=7))
        with patch.object(game, '_new_board', return_value=board):
            out = game.step(state, state['bet'], 'x', '1')
        self.assertEqual(out.event['multiplier'], 7)
        self.assertEqual(out.event['next_phase'], 'free_cascade')
        self.assertEqual(out.state['board'][11], 0)
        self.assertNotIn(11, out.event['removed'])
        self.assertTrue(all(out.event['board_before'][p] <= 1 or p in out.event['gold_before'].values() for p in range(10, 15)))
        with patch.object(game, '_draw_column', side_effect=lambda rng, count, has_scatter=False: [10] * count):
            following = game.step(out.state, state['bet'], 'x', '2')
        self.assertEqual(following.event['multiplier'], 8)
        self.assertEqual(following.debit_minor, 0)
        self.assertEqual(following.event['free']['remaining'], 0)
        self.assertEqual(following.event['broken_gold'], out.state['converted'])

    def test_binary_retry_wallet_and_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / 'game.sqlite3'
            http = build_server(0, db)
            try:
                session = http.service.create_session()
                token = session['token']
                req = (text_field(1, token) + field(2, 0, 2) + field(3, 0, 1) + text_field(5, '0')
                       + text_field(12, '0_C') + double_field(21, .1) + field(22, 0, 2) + field(24, 0, 0))
                board = losing_board()
                for c in range(3):
                    board[c * 5 + 1], board[c * 5 + 2] = 8, 10
                with patch.object(http.pg.game, '_new_board', return_value=board):
                    wire = http.pg.spin(pack(req, 17, salt=5), token)
                    retry = http.pg.spin(pack(req, 28, salt=5), token)
                a = unpack(wire, 17, salt=5)[0]
                self.assertEqual(a, unpack(retry, 28, salt=5)[0])
                state = http.service.state(token, 'wild-bandito')
                self.assertEqual(len(http.service.history(token)), 1)
                self.assertEqual(state['balance_minor'], 200000 - 400 + state['state']['last_event']['win_minor'])
                summary = http.pg.history(token, {}, summary=True)['dt']['bs']
                self.assertEqual(summary['bc'], 1)
                self.assertEqual(summary['btba'], 4)
                history = http.pg.history(token, {})['dt']['bh']
                self.assertEqual(history[0]['bd'][0]['gd']['sid'], state['state']['sid'])
                self.assertEqual(history[0]['gtwla'], (state['balance_minor'] - 200000) / 100)
                self.assertEqual(http.pg.history(token, {'dtf': ['253402300799000']})['dt']['bh'], [])
                other = http.service.create_session()
                self.assertEqual(http.pg.history(other['token'], {})['dt']['bh'], [])
            finally:
                http.server_close()
            resumed = build_server(0, db)
            try:
                self.assertEqual(resumed.service.state(token, 'wild-bandito'), state)
                info_req = text_field(1, token) + field(2, 0, 2) + field(3, 0, 1)
                raw = unpack(resumed.pg.game_info(pack(info_req, 31, salt=5), token), 31, salt=5)[0]
                info = decode(raw, SCHEMA['transaction']['nested'])
                self.assertEqual(info['sid'], state['state']['sid'])
                self.assertEqual(info['nst'], {'ready': 1, 'paid_cascade': 4, 'free_start': 21, 'free_cascade': 22}[state['state']['phase']])
            finally:
                resumed.server_close()

    def test_last_free_win_cascade_retrigger_does_not_end_early(self):
        game = WildBandito()
        game.config['gold_probability'] = 0
        state = game.initial_state('last-free')
        state.update(phase='free_start', seed='last-free', free=dict(remaining=1, total=12, award_minor=100, added=0, multiplier=7))
        board = losing_board()
        board[6] = board[11] = 2
        for p in (3, 8, 13):
            board[p] = 1
        with patch.object(game, '_new_board', return_value=board):
            win = game.step(state, state['bet'], 'unused', '1')
        self.assertEqual(win.event['win_minor'], 4200)
        self.assertEqual(win.event['free']['remaining'], 0)
        self.assertEqual(win.event['next_phase'], 'free_cascade')
        self.assertEqual(win.event['free']['added'], 0)
        with patch.object(game, '_draw_column', side_effect=lambda rng, count, has_scatter=False: [10] * count):
            end_cascade = game.step(win.state, state['bet'], 'unused', '2')
        self.assertEqual(end_cascade.event['win_minor'], 0)
        self.assertEqual(end_cascade.event['free']['remaining'], 12)
        self.assertEqual(end_cascade.event['free']['total'], 24)
        self.assertEqual(end_cascade.event['free']['added'], 12)
        self.assertEqual(end_cascade.event['free']['award_minor'], 4300)
        self.assertEqual(end_cascade.event['next_phase'], 'free_start')
        with patch.object(game, '_new_board', return_value=losing_board()):
            following = game.step(end_cascade.state, state['bet'], 'unused', '3')
        self.assertEqual(following.event['free']['remaining'], 11)
        self.assertEqual(following.event['free']['added'], 0)
        self.assertEqual(following.event['multiplier'], 8)
        self.assertEqual(following.debit_minor, 0)

    def test_complete_free_http_features_resume_and_unique_settlement(self):
        from tools.pg_capture.simulate_wild import simulate
        for scenario in ('basic', 'no-win', 'retrigger', 'last-retrigger'):
            with self.subTest(scenario=scenario):
                result = simulate(scenario, 3)
                self.assertTrue(result['resumed'])
                self.assertEqual(result['debit_minor'], 400)


if __name__ == '__main__':
    unittest.main()
