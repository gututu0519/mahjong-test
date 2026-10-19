import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.core.contracts import ServiceError
from server.games.fortune_rabbit.engine import FortuneRabbit, evaluate, VISIBLE
from server.adapters.pg.fortune_rabbit import SCHEMA, SALT, encode_response, transaction
from server.adapters.pg.wire import decode
from server.adapters.pg.protocol import pack, unpack, text_field, field, double_field
from server.services.fortune_rabbit_demo import build_server, CLIENT


def binary_request(token, previous='0', seed=17):
    raw = (text_field(1, token) + field(2, 0, 2) + field(3, 0, 1) + text_field(5, previous)
           + text_field(12, '0_C') + double_field(21, .3) + field(22, 0, 2))
    return pack(raw, seed, salt=SALT)


def losing_board():
    return [2, 2, 2, 99, 3, 3, 3, 3, 4, 4, 4, 99]


class FortuneRabbitTests(unittest.TestCase):
    def test_all_original_responses_paylines_prizes_and_wire(self):
        evidence = json.loads((CLIENT / 'fixtures/spin-evidence.json').read_text(encoding='utf-8'))
        self.assertTrue(evidence['spins'])
        seen = set()
        for row in evidence['spins']:
            tx = row['transaction']
            with self.subTest(request=row['request']):
                result = evaluate(tx['orl'], round(tx['cs'] * 100), tx['ml'], tx.get('cpf', {}))
                self.assertEqual(result['winning_positions'], tx.get('wp', {}))
                self.assertEqual(result['rates'], json.loads(tx.get('rwsp', '{}')))
                self.assertEqual(result['line_awards_minor'], {k: round(v * 100) for k, v in tx.get('lw', {}).items()})
                self.assertEqual(result['cash_win_minor'], round(tx.get('cptw', 0) * 100))
                self.assertEqual(result['win_minor'], round(tx.get('tw', 0) * 100))
                self.assertEqual(decode(encode_response(tx), SCHEMA['transaction']['nested']), tx)
                seen.update(tx.get('wp', {}))
        self.assertEqual(seen, set(map(str, range(1, 11))))

    def test_wild_highest_line_and_prize_minimum(self):
        board = [0] * 12
        board[3] = board[11] = 99
        result = evaluate(board, 3, 1, {})
        self.assertEqual(result['win_minor'], 3 * 200 * 10)
        self.assertEqual(len(result['winning_positions']), 10)
        for count in (4, 5):
            board = losing_board()
            prizes = {}
            for i, p in enumerate(VISIBLE[:count], 1):
                board[p] = 8
                prizes[str(i)] = dict(p=p, bv=.15, m=.5)
            self.assertEqual(evaluate(board, 3, 1, prizes)['cash_win_minor'], 0 if count == 4 else 75)
        with self.assertRaises(ValueError):
            evaluate(board, 3, 1, {})

    def test_feature_eight_spins_single_debit_and_bet_lock(self):
        game = FortuneRabbit()
        game.config['feature_probability'] = 1
        state = game.initial_state('test')
        blank = [1, 1, 1, 99, 1, 1, 1, 1, 1, 1, 1, 99]
        with patch.object(game, '_new_board', return_value=blank):
            first = game.step(state, state['bet'], 'seed', '1')
        self.assertEqual(first.debit_minor, 600)
        self.assertEqual(first.state['free']['remaining'], 7)
        self.assertEqual(first.state['phase'], 'free')
        with self.assertRaises(ServiceError):
            game.step(first.state, dict(coin_minor=10, level=2), 'x', '2')
        state = first.state
        credit = 0
        for i in range(7):
            outcome = game.step(state, state['bet'], 'ignored', str(i + 2))
            self.assertEqual(outcome.debit_minor, 0)
            self.assertEqual(outcome.state['free']['remaining'], 6 - i)
            self.assertTrue(all(outcome.state['board'][p] in (1, 8) for p in VISIBLE))
            credit += outcome.credit_minor
            state = outcome.state
        self.assertEqual(state['phase'], 'ready')
        self.assertEqual(state['free']['award_minor'], credit)
        self.assertNotIn('seed', game.public_state(state))
        with patch.object(game, '_new_board', return_value=losing_board()):
            self.assertEqual(game.step(state, state['bet'], 'new', '10').debit_minor, 600)

    def test_maximum_ends_feature_and_ruleset_change_refused(self):
        game = FortuneRabbit()
        game.config['feature_prize_probability'] = 1
        state = game.initial_state('test')
        state.update(phase='free', seed='test', free=dict(remaining=4, total=8, award_minor=0),
                     round_award_minor=600 * 5000 - 3)
        result = game.step(state, state['bet'], 'ignored', '1')
        self.assertEqual(result.credit_minor, 3)
        self.assertTrue(result.event['max_win'])
        self.assertEqual(result.state['phase'], 'ready')
        self.assertEqual(result.state['free']['remaining'], 0)
        state['ruleset_id'] = 'old-rules'
        with self.assertRaises(ServiceError):
            game.step(state, state['bet'], 'ignored', '2')

    def test_original_full_feature_and_normal_sequence(self):
        rows = json.loads((CLIENT / 'fixtures/spin-evidence.json').read_text(encoding='utf-8'))['spins']
        game = FortuneRabbit()
        state = game.initial_state('original-rule-audit')
        feature_steps = 0
        for i, row in enumerate(rows):
            tx = row['transaction']
            bet = game.normalize_bet({'cs': tx['cs'], 'ml': tx['ml']})
            trigger = tx['st'] == 1 and (tx['nst'] == 2 or bool(tx.get('fs')))
            game.config['feature_teaser_probability'] = int(bool(tx.get('ift')))
            with self.subTest(request=row['request']), patch.object(game, '_trigger_feature', return_value=trigger), \
                    patch.object(game, '_new_board', return_value=tx['orl']), \
                    patch.object(game, '_prizes', return_value=tx.get('cpf', {})):
                outcome = game.step(state, bet, 'audit', str(i + 1))
                state = outcome.state
                event = outcome.event
                wallet = dict(before_minor=200000, after_minor=200000 - outcome.debit_minor + outcome.credit_minor,
                              debit_minor=outcome.debit_minor)
                actual = transaction(event, wallet, game.config['win_thresholds'])
                for key in ('st', 'nst', 'aw', 'tb', 'tbb', 'tw', 'np', 'ctw', 'cwc', 'pcwc',
                            'iff', 'ift', 'imw', 'cptw', 'crtw', 'gwt'):
                    self.assertEqual(actual[key], tx.get(key, 0), key)
                for key in ('wp', 'lw', 'cpf', 'fstc'):
                    self.assertEqual(actual.get(key) or {}, tx.get(key) or {}, key)
                self.assertEqual(actual['ge'], tx['ge'])
                if tx.get('fs'):
                    feature_steps += 1
                    for key in ('aw', 's', 'ts'):
                        self.assertEqual(actual['fs'][key], tx['fs'].get(key, 0))
        self.assertGreaterEqual(feature_steps, 8)

    def test_binary_idempotency_restart_history_and_isolation(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'wallet.sqlite3'
            http = build_server(0, database)
            try:
                token = http.service.create_session()['token']
                other = http.service.create_session()['token']
                with patch.object(http.pg.game, '_new_board', return_value=losing_board()):
                    first = http.pg.spin(binary_request(token), token)
                    retry = http.pg.spin(binary_request(token, seed=23), token)
                self.assertEqual(unpack(first, 17, salt=SALT)[0], unpack(retry, 23, salt=SALT)[0])
                state = http.service.state(token, 'fortune-rabbit')
                self.assertEqual(state['balance_minor'], 199400)
                self.assertEqual(http.service.wallet(other)['balance_minor'], 200000)
                self.assertEqual(len(http.service.history(token)), 1)
                self.assertEqual(http.pg.history(token, {}, True)['dt']['bs']['btba'], 6)
                self.assertEqual(http.pg.history(other, {})['dt']['bh'], [])
            finally:
                http.server_close()
            resumed = build_server(0, database)
            try:
                self.assertEqual(resumed.service.state(token, 'fortune-rabbit'), state)
                info_raw = text_field(1, token) + field(2, 0, 2) + field(3, 0, 1)
                raw = unpack(resumed.pg.game_info(pack(info_raw, 9, salt=SALT), token), 9, salt=SALT)[0]
                tx = decode(raw, SCHEMA['transaction']['nested'])
                self.assertEqual(tx['sid'], state['state']['sid'])
                self.assertEqual(tx['rl'], state['state']['board'])
            finally:
                resumed.server_close()

    def test_feature_restart_retry_and_final_settlement(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'feature.sqlite3'
            http = build_server(0, database)
            try:
                token = http.service.create_session()['token']
                with patch.object(http.pg.game, '_trigger_feature', return_value=True):
                    http.pg.spin(binary_request(token), token)
                state = http.service.state(token, 'fortune-rabbit')
                self.assertEqual(state['state']['free']['remaining'], 7)
                self.assertEqual(state['state']['phase'], 'free')
            finally:
                http.server_close()
            resumed = build_server(0, database)
            try:
                self.assertEqual(resumed.service.state(token, 'fortune-rabbit'), state)
                for remaining in range(6, -1, -1):
                    previous = state['state']['sid']
                    wire = resumed.pg.spin(binary_request(token, previous), token)
                    retry = resumed.pg.spin(binary_request(token, previous, 21), token)
                    self.assertEqual(unpack(wire, 17, salt=SALT)[0], unpack(retry, 21, salt=SALT)[0])
                    state = resumed.service.state(token, 'fortune-rabbit')
                    self.assertEqual(state['state']['free']['remaining'], remaining)
                    tx = decode(unpack(wire, 17, salt=SALT)[0], SCHEMA['transaction']['nested'])
                    self.assertEqual(tx['tb'], 0)
                self.assertEqual(state['state']['phase'], 'ready')
                self.assertEqual(state['balance_minor'], 200000 - 600 + state['state']['round_award_minor'])
                self.assertEqual(len(resumed.service.history(token)), 8)
                group = resumed.pg.history(token, {})['dt']['bh'][0]
                self.assertEqual(group['gtba'], 6)
                self.assertEqual(len(group['bd']), 8)
            finally:
                resumed.server_close()

    def test_original_last_spin_prize_retry_and_reload(self):
        evidence = json.loads((CLIENT / 'fixtures/spin-evidence.json').read_text(encoding='utf-8'))['spins']
        final_index = next(i for i, r in enumerate(evidence)
                           if r['transaction']['st'] == 2 and r['transaction']['nst'] == 1
                           and r['transaction'].get('tw', 0) > 0)
        captured = evidence[final_index - 7:final_index + 1]
        self.assertEqual(captured[0]['transaction']['st'], 1)
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'last-prize.sqlite3'
            http = build_server(0, database)
            token = http.service.create_session()['token']
            previous = '0'
            try:
                # Settle the captured layouts through the generated-game rules
                # and real wallet transaction, including a process restart just
                # before the last winning spin. No recorded response is replayed.
                for i, row in enumerate(captured[:7]):
                    tx = row['transaction']
                    with patch.object(http.pg.game, '_trigger_feature', return_value=i == 0), \
                            patch.object(http.pg.game, '_new_board', return_value=tx['orl']), \
                            patch.object(http.pg.game, '_prizes', return_value=tx.get('cpf', {})):
                        http.pg.spin(binary_request(token, previous), token)
                    previous = http.service.state(token, 'fortune-rabbit')['state']['sid']
                before_last = http.service.state(token, 'fortune-rabbit')
                self.assertEqual(before_last['state']['free']['remaining'], 1)
            finally:
                http.server_close()
            resumed = build_server(0, database)
            try:
                tx = captured[-1]['transaction']
                with patch.object(resumed.pg.game, '_new_board', return_value=tx['orl']), \
                        patch.object(resumed.pg.game, '_prizes', return_value=tx['cpf']):
                    wire = resumed.pg.spin(binary_request(token, previous), token)
                    retry = resumed.pg.spin(binary_request(token, previous, 29), token)
                raw = unpack(wire, 17, salt=SALT)[0]
                self.assertEqual(raw, unpack(retry, 29, salt=SALT)[0])
                actual = decode(raw, SCHEMA['transaction']['nested'])
                for key in ('aw', 'tw', 'cptw', 'ctw', 'nst'):
                    self.assertEqual(actual[key], tx[key])
                self.assertEqual(actual['fs'].get('aw', 0), tx['fs'].get('aw', 0))
                self.assertEqual(actual['fs'].get('s', 0), 0)
                completed = resumed.service.state(token, 'fortune-rabbit')
                self.assertEqual(completed['balance_minor'], before_last['balance_minor'] + round(tx['tw'] * 100))
                self.assertEqual(completed['state']['free']['award_minor'], round(tx['aw'] * 100))
                self.assertEqual(completed['balance_minor'], 200000 - 600 + round(tx['aw'] * 100))
                group = resumed.pg.history(token, {})['dt']['bh'][0]
                self.assertEqual(group['gtba'], 6)
                self.assertEqual(group['gtwa'], tx['aw'])
                self.assertEqual(len(group['bd']), 8)
                self.assertEqual(group['bd'][-1]['gd']['fs']['aw'], tx['fs']['aw'])
            finally:
                resumed.server_close()
            reloaded = build_server(0, database)
            try:
                info_raw = text_field(1, token) + field(2, 0, 2) + field(3, 0, 1)
                info = reloaded.pg.game_info(pack(info_raw, 11, salt=SALT), token)
                restored = decode(unpack(info, 11, salt=SALT)[0], SCHEMA['transaction']['nested'])
                for key in ('aw', 'tw', 'fs', 'rl', 'sid', 'nst'):
                    self.assertEqual(restored[key], actual[key])
                self.assertEqual(reloaded.service.state(token, 'fortune-rabbit'), completed)
                with patch.object(reloaded.pg.game, '_trigger_feature', return_value=False), \
                        patch.object(reloaded.pg.game, '_new_board', return_value=losing_board()):
                    reloaded.pg.spin(binary_request(token, completed['state']['sid']), token)
                normal = reloaded.service.state(token, 'fortune-rabbit')
                self.assertEqual(normal['balance_minor'], completed['balance_minor'] - 600)
                self.assertIsNone(normal['state']['free'])
            finally:
                reloaded.server_close()


if __name__ == '__main__':
    unittest.main()
