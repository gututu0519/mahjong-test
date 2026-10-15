import copy
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from server.games.sweet_bonanza_pop.engine import SweetBonanzaPop, evaluate
from server.adapters.pp.sweet_bonanza_pop import transaction, PPAdapter
from server.core.service import GameService
from server.games.catalog import create_registry


class EvidenceTests(unittest.TestCase):
    def test_all_captured_steps(self):
        game = SweetBonanzaPop()
        state = game.initial_state('test')
        rows = json.loads(Path(__file__).with_name('fixtures').joinpath('sweet-pop-spins.json').read_text())['rows']
        compared = 0
        for row in rows:
            q, d = row['request'], row['response']
            command = game.normalize_bet({'coin_minor': int(Decimal(q.get('c', '.20')) * 100),
                'action': 'collect' if q['action'] == 'doCollect' else 'spin', 'request_index': int(q['index'])})
            if q['action'] == 'doCollect':
                state = game.step(state, command, 'capture', str(row['id'])).state
                continue
            orbs = dict(zip(d.get('slm_mp', '').split(','), map(int, d.get('slm_mv', '').split(',')))) if d.get('slm_mp') else {}
            board = list(d['s'])
            if state['phase'] in ('cascade', 'free_cascade'):
                removed = {p for ps in evaluate(state['board'], command['coin_minor'])['positions'].values() for p in ps}
                for col in range(3):
                    survivors = [state['board'][p] for p in range(col, 15, 3) if p not in removed]
                    if survivors:
                        self.assertEqual(board[col::3][-len(survivors):], survivors, row['id'])
            draw = (board, orbs, list(d['sa']), list(d['sb']))
            with patch.object(game, '_new_board', return_value=draw), patch.object(game, '_cascade', return_value=draw):
                outcome = game.step(state, command, 'capture', str(row['id']))
            actual = transaction(outcome.event)
            for field in ('w', 'tw', 'na', 'fs', 'fsmax', 'fswin', 'fsres', 'fs_total', 'fswin_total', 'fsend_total',
                          'fsmore', 'rs_iw', 'rs_win', 'rs_p', 'rs_c', 'rs_m', 'rs_t', 'rs_more', 'apwa', 'apt', 'apv', 'pw', 'trail', 's_mark'):
                self.assertEqual(actual.get(field), d.get(field), (row['id'], field))
            state = outcome.state
            compared += 1
        self.assertGreater(compared, 900)

    def test_pop_trigger_and_cap(self):
        game = SweetBonanzaPop()
        for count, multiplier in [(1, 50), (2, 500), (3, 25000)]:
            board = list('123456123456123')
            board[:3] = list('J' * count + 'S' * (3 - count))
            with patch.object(game, '_new_board', return_value=(board, {}, list('123'), list('456'))):
                result = game.step(game.initial_state('x'), game.normalize_bet({}), 'x', '1')
            self.assertEqual(result.event['jackpot_minor'], 200 * multiplier)
            self.assertEqual(result.state['phase'], 'collect' if count == 3 else 'free')

    def test_generated_rounds_and_wallet_idempotency(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = GameService(Path(tmp) / 'game.sqlite3', create_registry(['sweet-bonanza-pop']))
            token = service.create_session()['token']
            adapter = PPAdapter(service, {})
            for index in range(1, 100):
                state = service.state(token, adapter.game_id)['state']
                form = {k: [v] for k, v in {'symbol': 'vs10swtbnz', 'mgckey': token,
                    'action': 'doCollect' if state['phase'] == 'collect' else 'doSpin',
                    'index': str(index), 'counter': str(index * 2), 'c': '.20', 'l': '10'}.items()}
                first = adapter.handle(form)
                self.assertEqual(first, adapter.handle(form))
            self.assertGreaterEqual(service.wallet(token)['balance_minor'], 0)


if __name__ == '__main__':
    unittest.main()
