import json
import tempfile
import unittest
from pathlib import Path
from server.adapters.jili.money_pot_deluxe import Adapter, pack, unpack
from server.core.contracts import ServiceError
from server.core.service import GameService
from server.games.catalog import create_registry
from server.games.money_pot_deluxe.engine import MoneyPotDeluxe, evaluate, money


class MoneyPotDeluxeTests(unittest.TestCase):
    def test_original_rounds_and_collectors(self):
        samples = json.loads(Path(__file__).with_name('fixtures').joinpath('money-pot-deluxe-spins.json').read_text(encoding='utf-8'))
        self.assertGreaterEqual(len(samples), 80)
        bonus_count = 0
        for sample in samples:
            spin, amount = sample['spin'], money(10000, sample['request']['bet'])
            bonus = spin['RoundQueue'][0].get('GetReSpin', False)
            bonus_count += bonus
            total = 0
            for index, record in enumerate(spin['RoundQueue']):
                syms = [col['Col'] for col in record['FinalSymbol']]
                values = [col['Col'] for col in record['FinalMul']]
                if not bonus:
                    awards, win = evaluate(syms, values, amount)
                    self.assertEqual(win, money(10000, record.get('RoundWin', 0)))
                    self.assertEqual([(a['Atype'], a['Index'], a['Count'], a['Win']) for a in awards],
                        [(a.get('Atype', 0), a.get('Index', 0), a.get('Count', 0), a.get('Win', 0)) for a in record['AwardDataVec']])
                for collect in record['CollectList']:
                    raw = record['Symbol']
                    # Pot coins are inserted before collection, mysteries after.
                    coins = {(col * 3 + row): record['Mul'][col]['Col'][row]
                             for col in range(5) for row in range(3) if raw[col]['Col'][row] == 1}
                    coins.update({p['Pos']:p.get('Mul', 0) for p in record['PotList'] if p.get('Symbol') == 1})
                    collected = sum(money(10000, coins[p]) for p in collect['CPos'])
                    self.assertEqual(collected, money(10000, collect.get('Mul', 0)))
                    pos = collect.get('Pos', 0)
                    self.assertEqual(money(10000, values[pos // 3][pos % 3]), money(collected, collect.get('SymbolMul', 1)))
                if index:
                    previous = spin['RoundQueue'][index - 1]['FinalSymbol']
                    for col in range(5):
                        for row in range(3):
                            if previous[col]['Col'][row]:
                                self.assertTrue(record['Symbol'][col]['Col'][row])
                    self.assertEqual(record.get('ReSpinRemainRound', 0),
                        3 if record.get('GetAdd') else spin['RoundQueue'][index - 1].get('ReSpinRemainRound', 0) - 1)
                self.assertEqual(sum(money(10000, a.get('Win', 0)) for a in record['AwardDataVec']), money(10000, record.get('RoundWin', 0)))
                total += money(10000, record.get('RoundWin', 0))
            self.assertEqual(total, money(10000, spin.get('TotalWin', 0)))
            self.assertEqual(unpack('SpinAck', pack('SpinAck', spin)), spin)
        self.assertGreaterEqual(bonus_count, 2)

    def test_five_symbols_count_once_and_mixed_values_add(self):
        awards, win = evaluate([[1,0,0],[2,0,0],[5,0,0],[1,0,0],[1,0,0]],
                               [[.3,0,0],[15,0,0],[2,0,0],[.5,0,0],[1,0,0]], 10000)
        self.assertEqual(len(awards), 1)
        self.assertEqual(awards[0]['Atype'], 2)
        self.assertEqual(win, 188000)

    def test_generated_bonus_and_wallet_accounting(self):
        game = MoneyPotDeluxe()
        found = 0
        for seed in range(200):
            extra = seed % 4
            outcome = game.step(game.initial_state('x'), {'bet_minor':10000, 'extra':extra}, str(seed), str(seed + 1))
            rounds = outcome.event['spin']['RoundQueue']
            found += len(rounds) > 1
            self.assertEqual(outcome.debit_minor, [10000,15000,30000,60000][extra])
            self.assertEqual(outcome.credit_minor, sum(money(10000, r['RoundWin']) for r in rounds))
            self.assertEqual(outcome.credit_minor, sum(money(10000, a['Win']) for r in rounds for a in r['AwardDataVec']))
            self.assertLessEqual(outcome.credit_minor, 5000 * 10000)
            self.assertEqual(rounds[-1].get('ReSpinRemainRound', 0), 0)
            self.assertEqual(unpack('SpinAck', pack('SpinAck', outcome.event['spin'])), outcome.event['spin'])
        self.assertGreater(found, 0)

    def test_duplicate_requests_round_end_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'wallet.sqlite3'
            service = GameService(path, create_registry(['money-pot-deluxe']))
            token = service.create_session()['token']
            adapter = Adapter(service)
            req = pack('SpinReq', {'bet':1, 'extraSpin':{'Index':2}})
            reply = adapter.handle(token, 0, req, 'one')
            balance = service.wallet(token)['balance_minor']
            outer = unpack('SpinResponse', reply['data'])
            self.assertEqual(balance, 20000000 - 60000 + money(10000, outer['totalWin']))
            self.assertEqual(adapter.handle(token, 0, req, 'one'), reply)
            for ack in (4, 36):
                adapter.handle(token, ack, [], 'end')
                self.assertEqual(service.wallet(token)['balance_minor'], balance)
            restarted = GameService(path, create_registry(['money-pot-deluxe']))
            self.assertEqual(Adapter(restarted).handle(token, 0, req, 'one'), reply)
            for payload in ({'bet':1.1}, {'bet':1,'extraSpin':{'Index':3}}, {'bet':1,'mall':{}}):
                with self.assertRaises(ServiceError):
                    adapter.handle(token, 0, pack('SpinReq', payload), 'invalid')
            self.assertEqual(service.wallet(token)['balance_minor'], balance)

    def test_full_reel_grand_replaces_symbol_awards(self):
        game = MoneyPotDeluxe()
        game.config.update(bonus_chance=1, bonus_add_chance=1)
        for seed in range(10):
            outcome = game.step(game.initial_state('x'), {'bet_minor':10000, 'extra':3}, str(seed), str(seed + 1))
            final = outcome.event['spin']['RoundQueue'][-1]
            self.assertEqual(outcome.credit_minor, 50000000)
            self.assertEqual(final['ReSpinRemainRound'], 0)
            self.assertEqual(len(final['AwardDataVec']), 1)
            self.assertEqual(final['AwardDataVec'][0]['Win'], 5000)
            self.assertEqual(final['AwardDataVec'][0]['Index'], 99)


if __name__ == '__main__':
    unittest.main()
