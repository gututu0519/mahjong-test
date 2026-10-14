import copy
import json
import unittest
from pathlib import Path

from server.games.mahjong_ways2.engine import MahjongWays2, VISIBLE, evaluate


def blank():
    return [symbol for symbol in (2, 3, 4, 5, 6) for _ in range(7)]


class Scripted(MahjongWays2):
    """Inject boards in tests only; production exposes no force-result endpoint."""
    def __init__(self, boards):
        super().__init__()
        self.boards = list(boards)

    def _new_board(self, rng):
        return list(self.boards.pop(0)) if self.boards else blank()

    def _gold(self, rng, board, candidates, gold, serial):
        return gold, serial, [[] for _ in range(5)]


class RuleTests(unittest.TestCase):
    def test_existing_captures_are_only_an_offline_oracle(self):
        source = Path(__file__).parents[2] / 'Mahjong Ways 2/fixtures/spin-rounds.json'
        rounds = json.loads(source.read_text(encoding='utf-8'))['rounds']
        checked = 0
        for captured_round in rounds:
            for entry in captured_round:
                tx = entry['transaction']
                result = evaluate(tx['orl'], round(tx['cs'] * 100), tx['ml'], tx['wm'])
                self.assertEqual(result['winning_positions'], tx['wp'] or {})
                self.assertEqual(result['ways'], tx['snww'] or {})
                self.assertAlmostEqual(result['win_minor'] / 100, tx['tw'])
                checked += 1
        self.assertGreaterEqual(checked, 12)

    def test_paid_cascade_and_golden_conversion(self):
        game = MahjongWays2()
        board = blank()
        board[8] = board[15] = 2
        game._new_board = lambda rng: list(board)
        game._gold = lambda rng, b, candidates, gold, serial: ({'1': 8}, 1, [[], [], [], [], []])
        state = game.initial_state('initial')
        before = copy.deepcopy(state)
        out = game.step(state, {'coin_minor': 1, 'level': 5}, 'seed', '1')
        self.assertEqual(state, before, 'rules must not mutate the input state')
        self.assertEqual(out.debit_minor, 100)
        self.assertEqual(out.event['board_after'][8], 0)
        self.assertNotIn(8, out.event['removed'])
        self.assertEqual(out.state['gold'], {})
        self.assertEqual(out.state['phase'], 'paid_cascade')
        game._gold = lambda rng, b, candidates, gold, serial: (gold, serial, [[], [], [], [], []])
        following = game.step(out.state, out.state['bet'], 'ignored', '2')
        self.assertEqual(following.debit_minor, 0)
        self.assertEqual(following.event['multiplier'], 2)
        rebuilt = []
        for col in range(5):
            rebuilt += following.event['refills'][col]
            rebuilt += [v for p, v in enumerate(out.state['board'])
                        if p // 7 == col and p not in out.state['removed']]
        self.assertEqual(rebuilt, following.event['board_before'])

    def test_free_spins_decrement_and_finish_without_extra_debits(self):
        trigger = blank()
        for pos in (1, 8, 15):
            trigger[pos] = 1
        game = Scripted([blank(), trigger])
        state = game.initial_state('init')
        paid = game.step(state, {'coin_minor': 1, 'level': 5}, 'free-test', '1')
        self.assertEqual(paid.state['phase'], 'free_start')
        self.assertEqual(paid.state['free']['remaining'], 10)
        state = paid.state
        for index in range(10):
            result = game.step(state, state['bet'], 'ignored', str(index + 2))
            self.assertEqual(result.debit_minor, 0)
            self.assertEqual(result.event['multiplier'], 2)
            self.assertEqual(result.state['free']['remaining'], 9 - index)
            state = result.state
        self.assertEqual(state['phase'], 'ready')

    def test_free_retrigger(self):
        trigger = blank()
        for pos in (1, 8, 15):
            trigger[pos] = 1
        game = Scripted([blank(), trigger, trigger])
        state = game.initial_state('init')
        paid = game.step(state, {'coin_minor': 1, 'level': 5}, 'seed', '1')
        free = game.step(paid.state, paid.state['bet'], 'seed', '2')
        self.assertEqual(free.state['free'], {'remaining': 19, 'total': 20, 'added': 10, 'award_minor': 0})

    def test_seed_reproducibility_and_generated_diversity(self):
        game = MahjongWays2()
        state = game.initial_state('initial')
        bet = {'coin_minor': 1, 'level': 5}
        first = game.step(state, bet, 'same-seed', '1')
        self.assertEqual(first, game.step(state, bet, 'same-seed', '1'))
        boards = {tuple(game.step(state, bet, f'seed-{i}', '1').event['board_before']) for i in range(100)}
        self.assertEqual(len(boards), 100)

    def test_generated_chain_invariants(self):
        game = MahjongWays2()
        state = game.initial_state('init')
        starts = 0
        for i in range(600):
            start = state['phase'] == 'ready'
            result = game.step(state, state['bet'], f'round-{i}', str(i + 1))
            event = result.event
            self.assertEqual(result.debit_minor, 100 if start else 0)
            self.assertEqual(len(event['board_before']), 35)
            self.assertTrue(all(type(x) is int and 0 <= x <= 10 for x in event['board_after']))
            self.assertLessEqual(event['scatter_count'], 5)
            self.assertEqual(result.credit_minor, evaluate(event['board_before'], 1, 5, event['multiplier'])['win_minor'])
            self.assertTrue(set(event['removed']).isdisjoint(event['gold_before'].values()))
            self.assertEqual(result.state['round_award_minor'],
                             (0 if start else state['round_award_minor']) + result.credit_minor)
            state = result.state
            starts += start
        self.assertGreater(starts, 30)


if __name__ == '__main__':
    unittest.main()
