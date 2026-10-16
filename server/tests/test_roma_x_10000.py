import json
import tempfile
import unittest
from pathlib import Path
from server.adapters.jili.roma_x_10000 import Adapter, pack, unpack
from server.core.contracts import ServiceError
from server.core.service import GameService
from server.games.catalog import create_registry
from server.games.roma_x_10000.engine import RomaX10000, evaluate


class RomaX10000Tests(unittest.TestCase):
    def test_original_tutorial_paylines_and_cascade_fills(self):
        samples = json.loads(Path(__file__).with_name('fixtures').joinpath('roma-x-10000-tutorial.json').read_text(encoding='utf-8'))
        game = RomaX10000()
        checked = 0
        for spin in samples.values():
            total = 0
            for record in spin['RoundQueue']:
                stages = record['ComboStageData']
                for index, stage in enumerate(stages):
                    plate = [col.get('Col', []) for col in stage['ComboStageSymbol']]
                    awards, removed, win = evaluate(plate, 12000, game.config)
                    expected = [dict(Symbol=a.get('Symbol', 0), Count=a.get('Count', 0), Line=a.get('Line', 0), Win=a.get('Win', 0))
                                for a in stage.get('AwardDataVec', []) if a.get('Symbol', 0) != 8]
                    self.assertEqual(awards, expected)
                    self.assertEqual(win, round(stage.get('ComboStageWin', 0) * 10000))
                    if index + 1 < len(stages):
                        filled = [[v for row, v in enumerate(col) if col_index * 3 + row not in removed] + stage['FillSymbols'][col_index].get('Col', []) for col_index, col in enumerate(plate)]
                        self.assertEqual(filled, [col.get('Col', []) for col in stages[index + 1]['ComboStageSymbol']])
                    total += win
                    checked += 1
            self.assertEqual(total + round((spin.get('BonusTotalWin', 0) + spin.get('BonusWheelWin', 0)) * 10000), round(spin['TotalWin'] * 10000))
        self.assertEqual(checked, 48)

    def test_generated_outcomes_balance_and_free_rounds(self):
        game = RomaX10000()
        features = set()
        cases = [(seed, seed % 3 - 1) for seed in range(100)] + [(262, -1)]
        for seed, buy in cases:
            buy = None if buy < 0 else buy
            outcome = game.step(game.initial_state('test'), dict(bet_minor=60000, buy=buy), str(seed), str(seed + 1))
            spin = outcome.event['spin']
            total = sum(round(r['RoundWin'] * 10000) for r in spin['RoundQueue']) + round((spin['BonusTotalWin'] + spin['BonusWheelWin']) * 10000)
            self.assertEqual(total, outcome.credit_minor)
            self.assertEqual(outcome.debit_minor, 60000 * (game.config['buy_multipliers'][buy] if buy is not None else 1))
            self.assertLessEqual(total, 60000 * 10000)
            self.assertEqual(unpack('SpinAck', pack('SpinAck', spin)), spin)
            self.assertEqual(spin['RoundQueue'][-1].get('FreeRemainRound', 0), 0)
            if len(spin['RoundQueue']) > 1:
                features.add('free')
            if spin['BonusInfo']:
                features.add('battle')
                self.assertEqual(spin['BonusInfo'][-1]['HealthPoint'], 0)
                self.assertEqual(round(sum(r['Win'] for r in spin['BonusInfo']) * (spin['BonusWheelMult'] or 1) * 10000), round(spin['BonusTotalWin'] * 10000))
            if spin['BonusWheelWin']:
                features.add('wheel')
        self.assertEqual(features, {'free', 'battle', 'wheel'})

    def test_purchase_validation_idempotency_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'wallet.sqlite3'
            service = GameService(path, create_registry(['roma-x-10000']))
            token = service.create_session()['token']
            adapter = Adapter(service)
            req = pack('SpinReq', dict(bet=1.2, mall=dict(Type=1, Index=0, Bet=60)))
            reply = adapter.handle(token, 0, req, 'one')
            balance = service.wallet(token)['balance_minor']
            outer = unpack('SpinResponse', reply['data'])
            self.assertEqual(balance, 20000000 - 600000 + round(outer['totalWin'] * 10000))
            self.assertEqual(adapter.handle(token, 0, req, 'one'), reply)
            for ack in (4, 36):
                adapter.handle(token, ack, [], 'end')
                self.assertEqual(service.wallet(token)['balance_minor'], balance)
            self.assertEqual(Adapter(GameService(path, create_registry(['roma-x-10000']))).handle(token, 0, req, 'one'), reply)
            for invalid in [dict(bet=1), dict(bet=1.2, extraSpin={}), dict(bet=1.2, mall=dict(Type=1, Index=2, Bet=60)), dict(bet=1.2, mall=dict(Type=1, Index=1, Bet=60))]:
                with self.assertRaises(ServiceError):
                    adapter.handle(token, 0, pack('SpinReq', invalid), 'invalid')
            self.assertEqual(service.wallet(token)['balance_minor'], balance)


if __name__ == '__main__':
    unittest.main()
