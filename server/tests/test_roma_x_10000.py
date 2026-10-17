import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from server.adapters.jili.roma_x_10000 import Adapter, pack, unpack
from server.core.contracts import ServiceError
from server.core.service import GameService
from server.games.catalog import create_registry
from server.games.roma_x_10000.engine import RomaX10000, evaluate, free_rounds_for_wins


class RomaX10000Tests(unittest.TestCase):
    def test_all_wheel_prizes_and_maximum_award(self):
        game = RomaX10000()
        seeds = {0: '189', 1: '12', 2: '68', 3: '23', 4: '0', 5: '1', 6: '3'}
        for result, seed in seeds.items():
            with self.subTest(result=result):
                outcome = game.step(game.initial_state('test'), {'bet_minor': 60000, 'buy': 1}, seed, '1')
                spin = outcome.event['spin']
                self.assertEqual(spin['BonusWheelResult'], result)
                self.assertTrue(spin['RoundQueue'][0]['ComboStageData'][0]['BonusWheelHit'])
                if result < 3:
                    self.assertEqual(spin['BonusWheelWin'], 6 * [10000, 5000, 1000][result])
                    self.assertEqual(spin['BonusInfo'], [])
                else:
                    self.assertEqual(spin['BonusWheelMult'], [10, 5, 3, 2][result - 3])
                    self.assertTrue(spin['BonusInfo'])
                self.assertLessEqual(outcome.credit_minor, 60000 * 10000)
                self.assertEqual(spin['BonusMaxFlag'], outcome.credit_minor == 60000 * 10000)
                self.assertEqual(outcome.debit_minor, 15000000)

    def test_free_award_tiers_and_retrigger_on_last_game(self):
        for wins, awarded in [(0, 0), (3, 0), (4, 3), (5, 5), (6, 10), (7, 20)]:
            self.assertEqual(free_rounds_for_wins(wins), awarded)
        # Exercise every tier on the last remaining free game: it must extend
        # the same paid round rather than end it or charge another bet.
        for wins, awarded in [(4, 3), (5, 5), (6, 10), (7, 20)]:
            with self.subTest(wins=wins):
                game = RomaX10000()
                def record(count):
                    return dict(ComboStageData=[{'ComboStageWin': 1}] * count + [{'ComboStageWin': 0}],
                                RoundWin=count, AwardTypeFlag=int(bool(count)))
                rounds = [record(4), record(0), record(0), record(wins)] + [record(0) for _ in range(awarded)]
                with patch.object(game, '_round', side_effect=rounds):
                    outcome = game.step(game.initial_state('test'), {'bet_minor': 60000, 'buy': None}, 'test', '1')
                queue = outcome.event['spin']['RoundQueue']
                self.assertEqual(len(queue), 4 + awarded)
                self.assertEqual(queue[3]['AddRound'], awarded)
                self.assertEqual(queue[3]['FreeRemainRound'], awarded)
                self.assertFalse(queue[3]['AwardTypeFlag'] & 8)
                self.assertTrue(queue[-1]['AwardTypeFlag'] & 8)
                self.assertEqual(queue[-1]['FreeRemainRound'], 0)
                self.assertEqual(outcome.event['spin']['FreeTotalWin'], wins)
                self.assertEqual(outcome.credit_minor, (4 + wins) * 10000)
                self.assertEqual(outcome.debit_minor, 60000)

    def test_seeded_free_retrigger_counters_and_atomic_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'wallet.sqlite3'
            registry = create_registry(['roma-x-10000'])
            game = registry.get('roma-x-10000')
            original_step = game.step
            service = GameService(path, registry)
            token = service.create_session()['token']
            adapter = Adapter(service)
            request = pack('SpinReq', {'bet': 6})
            with patch.object(game, 'step', side_effect=lambda state, bet, seed, sid: original_step(state, bet, '40720', sid)):
                reply = adapter.handle(token, 0, request, 'free-retrigger')
            spin = unpack('SpinAck', unpack('SpinResponse', reply['data'])['data'])
            queue = spin['RoundQueue']
            self.assertEqual([r['AddRound'] for r in queue], [3, 0, 0, 3, 0, 0, 0])
            self.assertEqual([r['FreeRemainRound'] for r in queue], [3, 2, 1, 3, 2, 1, 0])
            self.assertEqual([r.get('FreeNowRound', 0) for r in queue], list(range(7)))
            self.assertEqual([r['FreeTotalRound'] for r in queue], [3, 3, 3, 6, 6, 6, 6])
            self.assertEqual(round(spin['FreeTotalWin'] * 10000), sum(round(r['RoundWin'] * 10000) for r in queue[1:]))
            self.assertEqual(spin['TotalWin'], 54)
            balance = service.wallet(token)['balance_minor']
            self.assertEqual(balance, 20000000 - 60000 + 540000)
            # Retrying the paid request and reloading the last response across
            # a process restart must not settle the free queue a second time.
            restarted = GameService(path, create_registry(['roma-x-10000']))
            restored = Adapter(restarted)
            self.assertEqual(restored.handle(token, 0, request, 'free-retrigger'), reply)
            for ack in (36, 4, 36):
                restored.handle(token, ack, [], 'restore')
                self.assertEqual(restarted.wallet(token)['balance_minor'], balance)
            self.assertEqual(len(restarted.history(token)), 1)

    def test_latest_captured_purchases_and_battle_settlement(self):
        fixture = json.loads(Path(__file__).with_name('fixtures').joinpath('roma-x-10000-live-features.json').read_text(encoding='utf-8'))
        game = RomaX10000()
        modes = set()
        for sample in fixture['samples']:
            request, spin = sample['request'], sample['spin']
            amount = round(request['bet'] * 10000)
            self.assertEqual(request['mall']['Bet'], request['bet'] * game.config['buy_multipliers'][request['mall']['Index']])
            total = 0
            for record in spin['RoundQueue']:
                for stage in record['ComboStageData']:
                    awards, _, win = evaluate([col['Col'] for col in stage['ComboStageSymbol']], amount, game.config)
                    self.assertEqual(win, round(stage.get('ComboStageWin', 0) * 10000))
                    total += win
            hp = 3
            for action in spin['BonusInfo']:
                result, symbol = action.get('Result', 0), action['Symbol']
                hp -= int(result in (0, 1))
                self.assertEqual(action.get('HealthPoint', 0), hp)
                self.assertEqual(round(action.get('Win', 0) * 10000), 0 if result == 2 else amount * {10: 3, 11: 10, 12: 20}[symbol])
            self.assertEqual(hp, 0)
            battle = round(sum(a.get('Win', 0) for a in spin['BonusInfo']) * spin['BonusWheelMult'] * 10000)
            self.assertEqual(battle, round(spin['BonusTotalWin'] * 10000))
            self.assertEqual(total + battle, round(spin['TotalWin'] * 10000))
            modes.add((request['mall']['Index'], spin['BonusWheelMult']))
        self.assertEqual(modes, {(0, 1), (0, 2), (1, 10)})

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
