import copy
import json
import tempfile
import unittest
from pathlib import Path
from server.adapters.jili.super_ace import Adapter, SCHEMAS, pack, unpack
from server.core.contracts import ServiceError
from server.core.service import GameService
from server.games.catalog import create_registry
from server.games.super_ace.engine import SuperAce, evaluate


class SuperAceTests(unittest.TestCase):
    def setUp(self):
        self.game = SuperAce()

    def test_captured_awards_and_flips(self):
        samples = json.loads(Path(__file__).with_name('fixtures').joinpath('super-ace-spins.json').read_text())
        for sample in samples:
            bet = round(sample['spinReq']['bet'] * 10000)
            total = 0
            for index, plate in enumerate(sample['data']['plate']):
                board = copy.deepcopy(plate['column'])
                plate_total = 0
                for step, combo in enumerate(plate['combo']):
                    awards = evaluate(board, bet, self.game.config['paytable_twentieths'])
                    expected = {a.get('symbol', 0): round(a.get('win', 0) * 10000) for a in combo['award']}
                    self.assertEqual({a['symbol']:a['win_minor'] for a in awards}, expected)
                    mult = [1, 2, 3, 5][min(step, 3)] * (2 if index else 1)
                    self.assertEqual(combo['comboBonus'], mult)
                    win = sum(expected.values()) * mult
                    self.assertEqual(win, round(combo['win'] * 10000))
                    plate_total += win
                    for c in combo['change'] + combo['extraChange']:
                        col, row = c.get('column', 0), c.get('row', 0)
                        board[col]['row'][row], board[col]['isGold'][row] = c.get('symbol', 0), c.get('isGold', 0)
                self.assertEqual(plate_total, round(plate.get('win', 0) * 10000))
                total += plate_total
            self.assertEqual(total, round(sample['totalWin'] * 10000))
            # Real nested messages survive encoding into the original protobuf layout.
            encoded = pack('AllPlate', sample['data'])
            self.assertEqual(unpack('AllPlate', encoded), sample['data'])

    def test_generated_rounds_and_purchase(self):
        for seed in range(60):
            bet = {'bet_minor':5000, 'buy_bonus':bool(seed % 2)}
            outcome = self.game.step(self.game.initial_state('x'), bet, str(seed), str(seed+1))
            self.assertEqual(outcome.debit_minor, 202500 if bet['buy_bonus'] else 5000)
            self.assertLessEqual(outcome.credit_minor, 5000*10000)
            self.assertEqual(outcome.credit_minor, sum(round(p['win']*10000) for p in outcome.event['plates']))
            if bet['buy_bonus']:
                self.assertTrue(outcome.event['plates'][0]['isBonus'])
                self.assertGreaterEqual(len(outcome.event['plates']), 11)
            for plate in outcome.event['plates']:
                for c in (0, 4):
                    self.assertEqual(plate['column'][c]['isGold'], [0]*4)

    def test_wallet_precision_retry_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'wallet.sqlite3'
            service = GameService(path, create_registry(['super-ace']))
            token = service.create_session()['token']
            self.assertEqual(service.wallet(token)['minor_unit'], 10000)
            self.assertEqual(service.wallet(token)['balance_minor'], 20000000)
            adapter = Adapter(service)
            payload = pack('SpinReq', {'bet':0.5, 'mall':{'Bet':20.25}})
            first = adapter.handle(token, 0, payload, 'purchase-1')
            after = service.wallet(token)['balance_minor']
            self.assertEqual(first, adapter.handle(token, 0, payload, 'purchase-1'))
            self.assertEqual(service.wallet(token)['balance_minor'], after)
            restarted = GameService(path, create_registry(['super-ace']))
            self.assertEqual(Adapter(restarted).handle(token, 0, payload, 'purchase-1'), first)
            with self.assertRaises(ServiceError):
                adapter.handle(token, 0, pack('SpinReq', {'bet':1}), 'purchase-1')
            other = restarted.create_session()['token']
            self.assertEqual(restarted.wallet(other)['balance_minor'], 20000000)
            with self.assertRaises(ValueError):
                GameService(path, create_registry(['mahjong-ways2']))

    def test_fractional_award_and_validation(self):
        board = [{'row':[8,2,3,4],'isGold':[0]*4}, {'row':[8,5,6,7],'isGold':[0]*4},
                 {'row':[8,5,6,7],'isGold':[0]*4}, {'row':[2,3,4,9],'isGold':[0]*4},
                 {'row':[2,3,4,9],'isGold':[0]*4}]
        self.assertEqual(evaluate(board, 5000, self.game.config['paytable_twentieths'])[0]['win_minor'], 250)
        for payload in ({'bet_minor':True}, {'bet_minor':1}, {'buy_bonus':1}, {'extra':1}):
            with self.assertRaises(ServiceError):
                self.game.normalize_bet(payload)


if __name__ == '__main__':
    unittest.main()
