import copy
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs
from server.core.contracts import ServiceError, Registry
from server.core.service import GameService
from server.games.gates_of_olympus.engine import GatesOfOlympus, PAYTABLE, evaluate
from server.adapters.pp.gates_of_olympus import PPAdapter, transaction
from server.run import ROOT
from tools.pp_capture.analyze_spins import audit


class OlympusEngineTests(unittest.TestCase):
    def setUp(self):
        self.game = GatesOfOlympus()

    def command(self, **kw):
        return self.game.normalize_bet(kw)

    def board_step(self, s, board, orbs=None, **command):
        result = (board, orbs or {}, [3] * 6, [4] * 6)
        with patch.object(self.game, '_new_board', return_value=result), patch.object(self.game, '_cascade', return_value=result):
            return self.game.step(s, self.command(**command), 'test', str(int(s['sid']) + 1))

    def test_paytable_count_boundaries(self):
        for symbol, rates in PAYTABLE.items():
            for count, rate in ((7, 0), (8, rates[0]), (9, rates[0]), (10, rates[1]), (11, rates[1]), (12, rates[2]), (30, rates[2])):
                board = [symbol] * count + [12] * (30 - count)
                self.assertEqual(evaluate(board, 3)['base_minor'], rate * 3)

    def test_scatter_free_retrigger_multiplier_and_collect(self):
        plain = [3 + i % 9 for i in range(30)]
        trigger = plain[:]; trigger[:4] = [1] * 4
        out = self.board_step(self.game.initial_state('s'), trigger)
        self.assertEqual((out.debit_minor, out.credit_minor, out.state['phase']), (200, 0, 'free'))
        self.assertEqual(out.state['total_minor'], 600)
        self.assertEqual(out.state['free']['total'], 15)
        win = [11] * 8 + [3 + i % 8 for i in range(22)]
        win[29] = 12
        out = self.board_step(out.state, win, {'29': 5})
        self.assertEqual(out.debit_minor, 0)
        self.assertEqual(out.event['base_minor'], 50)
        ending = plain[:]; ending[29] = 12
        out = self.board_step(out.state, ending, {'29': 5})
        self.assertEqual(out.state['free']['multiplier'], 5)
        self.assertEqual(out.state['free']['win_minor'], 250)
        no_win = plain[:]; no_win[29] = 12
        out = self.board_step(out.state, no_win, {'29': 500})
        self.assertEqual(out.state['free']['multiplier'], 5, 'Losing orbs must not accumulate')
        retrigger = plain[:]; retrigger[:3] = [1] * 3
        out = self.board_step(out.state, retrigger)
        self.assertEqual(out.state['free']['total'], 20)
        # An existing accumulator alone does not multiply a spin without a new orb.
        win[29] = 3
        out = self.board_step(out.state, win)
        out = self.board_step(out.state, plain)
        self.assertEqual(out.event['extra_minor'], 0)
        out.state['free']['played'] = 19
        out = self.board_step(out.state, plain)
        self.assertEqual(out.state['phase'], 'collect')
        pending = out.state['total_minor']
        out = self.game.step(out.state, self.command(action='collect'), 'collect', '999')
        self.assertEqual(out.credit_minor, pending)
        self.assertEqual(out.state['phase'], 'ready')
        with self.assertRaises(ServiceError):
            self.game.step(out.state, self.command(action='collect'), 'again', '1000')

    def test_ante_cap_and_bet_lock(self):
        win = [3] * 30
        out = self.board_step(self.game.initial_state('s'), win, ante=True)
        self.assertEqual(out.debit_minor, 250)
        self.assertEqual(out.event['base_minor'], 10000)
        with self.assertRaises(ServiceError):
            self.board_step(out.state, win, ante=False)
        old = copy.deepcopy(out.state); old['ruleset_id'] = 'old'
        with self.assertRaises(ServiceError):
            self.board_step(old, win, ante=True)
        out.state['total_minor'] = 999999
        out = self.board_step(out.state, win, ante=True)
        self.assertTrue(out.event['capped'])
        self.assertEqual(out.state['total_minor'], 1000000)
        self.assertEqual(out.state['phase'], 'collect')

    def test_generated_invariants(self):
        s = self.game.initial_state('s')
        for i in range(1200):
            command = self.command(action='collect' if s['phase'] == 'collect' else 'spin')
            before = copy.deepcopy(s)
            out = self.game.step(s, command, str(i), str(i + 1))
            self.assertEqual(s, before)
            self.assertGreaterEqual(out.debit_minor, 0)
            self.assertGreaterEqual(out.credit_minor, 0)
            self.assertLessEqual(out.state['total_minor'], 1000000)
            self.assertEqual({int(p) for p in out.state['orbs']}, {i for i, v in enumerate(out.state['board']) if v == 12})
            if s['phase'] != 'ready':
                self.assertEqual(out.debit_minor, 0)
            s = out.state

    def test_capture_rules_and_protocol_recalculation(self):
        data = json.loads((ROOT / 'server/tests/fixtures/olympus-spins.json').read_text())
        self.assertEqual(audit(data)['errors'], [])
        with tempfile.TemporaryDirectory() as tmp:
            service = GameService(Path(tmp) / 'g.sqlite3', Registry([self.game]))
            token = service.create_session()['token']
            initial = {k: v[0] for k, v in parse_qs((ROOT / 'clients/gates-of-olympus/fixtures/init.txt').read_text()).items()}
            adapter = PPAdapter(service, initial)
            for row in data['rows']:
                req, expected = row['request'], row['response']
                form = {k: [v] for k, v in req.items()}
                form.update(symbol=['vs20olympgate'], mgckey=[token])
                if req['action'] == 'doSpin':
                    board = list(map(int, expected['s'].split(',')))
                    orbs = {p: int(v) for _, p, v in (item.split('~') for item in expected.get('rmul', '').split(';') if item)}
                    draw = (board, orbs, list(map(int, expected['sa'].split(','))), list(map(int, expected['sb'].split(','))))
                    with patch.object(self.game, '_new_board', return_value=draw), patch.object(self.game, '_cascade', return_value=draw), patch.object(self.game, '_purchase_board', return_value=draw):
                        actual = adapter.handle(form)
                    for key in ('puri', 'purtr', 'w', 'tw', 'na', 'tmb_win', 'tmb_res', 'apwa', 'apv', 'accv', 'fs', 'fsmax', 'fswin', 'fs_total', 'fsend_total', 'fswin_total', 'psym'):
                        self.assertEqual(actual.get(key), expected.get(key), (row['id'], key))
                else:
                    actual = adapter.handle(form)
                balance = int(Decimal(expected['balance'].replace(',', '')) * 100) - 10000000 + 200000
                self.assertEqual(int(Decimal(actual['balance']) * 100), balance, row['id'])


if __name__ == '__main__':
    unittest.main()
