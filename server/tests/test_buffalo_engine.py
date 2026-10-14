import concurrent.futures
import copy
import json
import random
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlencode

from server.core.contracts import Registry, ServiceError
from server.core.service import GameService
from server.games.buffalo_win.engine import BuffaloWin, evaluate
from server.adapters.pg.buffalo_win import PGAdapter, transaction


BLANK = [3, 2, 3, 2, 4, 2, 4, 2, 5, 2, 5, 2]


class Scripted(BuffaloWin):
    def __init__(self, boards=(), columns=()):
        super().__init__()
        self.boards, self.columns = list(boards), list(columns)

    def _start_board(self, rng, free):
        return copy.deepcopy(self.boards.pop(0)) if self.boards else (BLANK[:], 10, {}, {})

    def _column(self, rng, first=False):
        return self.columns.pop(0)[:] if self.columns else [2] * 4

    def _new_blocks(self, board, rng, offset=0, first_id=1):
        return {}, {}


class BuffaloRulesTests(unittest.TestCase):
    def test_offline_capture_oracle(self):
        cases = json.loads((Path(__file__).parents[2] / 'Buffalo Win/fixtures/rule-cases.json').read_bytes())
        english = json.loads((Path(__file__).parents[2] / 'Buffalo Win/fixtures/rule-cases-en.json').read_bytes())
        self.assertEqual(len(english), 386)
        cases.extend(english)
        self.assertGreaterEqual(len(cases), 789)
        for case in cases:
            with self.subTest(row=case['row']):
                result = evaluate(case['rl'], case['es'] or {}, case['bsc'] or {}, round(case['cs'] * 100), case['ml'])
                self.assertEqual(result['positions'], case['wp'] or {})
                self.assertEqual(result['counts'], case['scs'] or {})
                self.assertEqual(result['extend'], case['ix'])
                self.assertEqual(0 if result['extend'] else result['base_minor'] * case['gm'], round(case['tw'] * 100))

    def test_expanded_count_and_204_credit_example(self):
        game = Scripted([([3,3,3,3,2,0,2,3,0,0,2,7], 3, {'1': [0,1,2,3]}, {'1': 8})],
                        [[3,3,2,5], [0,0,2,3], [2,8,8,2]])
        state = game.initial_state('test')
        results = []
        for i in range(4):
            outcome = game.step(state, state['bet'], str(i), str(i+1))
            results.append(outcome)
            state = outcome.state
        self.assertEqual([x.debit_minor for x in results], [600,0,0,0])
        self.assertEqual([x.credit_minor for x in results], [0,0,0,20400])
        self.assertEqual(results[-1].event['counts_eval'], {'3': 17})
        self.assertEqual(state['phase'], 'ready')
        tx = transaction(results[-1].event, {'before_minor': 100000, 'after_minor': 120400, 'debit_minor': 0}, game.config['win_thresholds'])
        self.assertEqual(tx['sw'], {'3': [5.0,51.0]})
        self.assertEqual(tx['gm'], 4)
        self.assertEqual(tx['lrs'], {'0': [3]*8})

    def test_free_feature_carry_and_restore(self):
        trigger = ([1,1,2,3,1,2,4,2,1,2,5,2],10,{}, {})
        win = ([12,12,2,8,4,4,4,4,10,10,10,10],10,{'1':[4,5,6,7],'2':[8,9,10,11]}, {'1':5,'2':6})
        game = Scripted([trigger,win])
        state = game.initial_state('test')
        state = game.step(state,state['bet'],'one','1').state
        state = game.step(state,state['bet'],'two','2').state
        self.assertEqual(state['phase'], 'free_start')
        self.assertEqual(state['free']['remaining'],12)
        self.assertEqual(state['multiplier'],1)
        state = game.step(state,state['bet'],'three','3').state
        self.assertEqual(state['board'][4:], [0]*8)
        self.assertEqual(state['phase'],'free_extension')
        self.assertEqual(state['free']['remaining'],11)
        with self.assertRaises(ServiceError) as locked:
            game.step(state,{'coin_minor':3,'level':1},'bad','4')
        self.assertEqual(locked.exception.code,'BET_LOCKED')
        # Serialization matches a process restart mid-feature.
        state = json.loads(json.dumps(state))
        result = game.step(state,state['bet'],'four','4')
        self.assertEqual(result.credit_minor,4440)
        self.assertEqual(result.state['free']['remaining'],11)
        state = result.state
        for i in range(11):
            result = game.step(state,state['bet'],str(i),str(i+5))
            self.assertEqual(result.debit_minor,0)
            self.assertEqual(result.event['multiplier'],2)
            state = result.state
        self.assertEqual(state['phase'],'ready')
        result = game.step(state,{'coin_minor':3,'level':1},'new','20')
        self.assertEqual(result.event['multiplier'],1)
        self.assertEqual(result.debit_minor,30)

    def test_generation_is_seeded_and_follows_symbol_constraints(self):
        game = BuffaloWin()
        state = game.initial_state('test')
        old = copy.deepcopy(state)
        first = game.step(state,state['bet'],'same-seed','1')
        self.assertEqual(first,game.step(state,state['bet'],'same-seed','1'))
        self.assertEqual(state,old)
        states, boards = set(), set()
        for i in range(1500):
            outcome = game.step(state,state['bet'],f'seed-{i}',str(i+1))
            state = outcome.state
            states.add(outcome.event['phase'])
            boards.add(tuple(outcome.event['board']))
            self.assertNotIn(0, state['board'][:4])
            for key, cells in state['expanded'].items():
                self.assertIn(state['block_counts'][key], range(len(cells) + 1, len(cells) * 2 + 1))
            self.assertEqual(type(outcome.credit_minor),int)
            self.assertGreaterEqual(outcome.credit_minor,0)
        self.assertEqual(states, {'ready','paid_extension','free_start','free_extension'})
        self.assertGreater(len(boards),100)

    def test_documented_scatter_awards_and_no_early_trigger(self):
        for scatters, award in ((2, 0), (3, 10), (4, 12), (5, 14)):
            with self.subTest(scatters=scatters):
                board = [1] * scatters + [2] * (12 - scatters)
                game = Scripted([(board, 10, {}, {})])
                state = game.initial_state('test')
                outcome = game.step(state, state['bet'], 'trigger', '1')
                self.assertEqual(outcome.state['phase'], 'free_start' if award else 'ready')
                self.assertEqual(outcome.event['free']['remaining'] if award else 0, award)
                self.assertEqual(outcome.debit_minor, 600)
        # Count a third scatter arriving on an added reel, but award only once
        # the final scatter reel has been followed by a terminating reel.
        game = Scripted([([1,2,2,2,2,2,2,2,1,2,2,2],10,{}, {})], [[1,2,2,2], [2]*4])
        state = game.initial_state('test')
        for sid in ('1', '2'):
            state = game.step(state, state['bet'], sid, sid).state
            self.assertIsNone(state['free'])
        outcome = game.step(state, state['bet'], '3', '3')
        self.assertEqual(outcome.event['free']['total'], 10)
        self.assertEqual(outcome.state['multiplier'], 1)

    def test_retrigger_on_last_free_spin_with_extensions_and_restore(self):
        game = Scripted([([1,2,2,2,1,2,2,2,1,2,2,2],10,{}, {})], [[1,2,2,2], [2]*4])
        state = game.initial_state('test')
        state.update(phase='free_start', multiplier=5,
                     free={'remaining':1,'total':10,'added':0,'rc':0,'award_minor':1234})
        for sid in ('1', '2'):
            outcome = game.step(state, state['bet'], sid, sid)
            self.assertEqual(outcome.event['free']['added'], 0)
            self.assertEqual(outcome.event['free']['remaining'], 0)
            self.assertEqual(outcome.state['phase'], 'free_extension')
            state = json.loads(json.dumps(outcome.state))
        outcome = game.step(state, state['bet'], '3', '3')
        self.assertEqual(outcome.debit_minor, 0)
        self.assertEqual(outcome.state['phase'], 'free_start')
        self.assertEqual(outcome.state['multiplier'], 7)
        tx = transaction(outcome.event, {'before_minor':10000,'after_minor':10000,'debit_minor':0}, game.config['win_thresholds'])
        self.assertEqual(tx['fs'], {'s':12,'ts':22,'as':12,'aw':12.34,'rc':2})
        next_spin = game.step(outcome.state, state['bet'], '4', '4')
        self.assertEqual(next_spin.event['free']['added'], 0)
        self.assertEqual(next_spin.event['free']['remaining'], 11)
        self.assertEqual(next_spin.event['free']['total'], 22)
        self.assertEqual(next_spin.event['multiplier'], 7)

    def test_extensions_continue_beyond_eight_reels(self):
        game = Scripted([([3,2,2,2]*3,3,{}, {})], [[3,2,2,2]]*8 + [[2]*4])
        state = game.initial_state('test')
        for i in range(10):
            outcome = game.step(state, state['bet'], str(i), str(i+1))
            state = outcome.state
            self.assertEqual(outcome.debit_minor, 600 if i == 0 else 0)
            self.assertEqual(outcome.credit_minor, 33000 if i == 9 else 0)
        self.assertEqual(len(state['board']) // 4, 12)
        self.assertEqual(state['phase'], 'ready')

    def test_new_reel_stack_conversion_and_protocol(self):
        game = Scripted([([10,2,2,2]*3,10,{}, {})], [[2,8,8,2], [2]*4])
        game.config['expanded_probability'] = 1
        game._new_blocks = BuffaloWin._new_blocks.__get__(game)
        state = game.initial_state('test')
        state = game.step(state, state['bet'], '1', '1').state
        outcome = game.step(state, state['bet'], '2', '2')
        tx = transaction(outcome.event, {'before_minor':10000,'after_minor':10000,'debit_minor':0}, game.config['win_thresholds'])
        self.assertEqual(tx['rs']['ecrl'], [2,10,10,2])
        self.assertEqual(tx['rs']['oecrl'], [2,8,8,2])
        self.assertEqual(tx['rs']['nes'], {'1':[13,14]})
        self.assertEqual(tx['rs']['ebwp'], {'1':[13,14]})
        self.assertIn(tx['rs']['ebwsc']['1'], (3,4))
        self.assertEqual(tx['scs']['10'], 3 + tx['bsc']['1'])

    def test_all_stack_expansion_sizes_are_documented(self):
        game = BuffaloWin()
        game.config['expanded_probability'] = 1
        for size in (2,3,4):
            observed = set()
            for seed in range(100):
                blocks, counts = game._new_blocks([3]*size + [2]*(4-size), random.Random(seed))
                self.assertEqual(blocks, {'1':list(range(size))})
                observed.add(counts['1'])
            self.assertEqual(observed, set(range(size+1, size*2+1)))

    def test_completed_old_round_upgrades_without_resetting_history(self):
        game = Scripted()
        state = game.initial_state('test')
        state.update(sid='123', ruleset_id='1.0.0:old')
        outcome = game.step(state, state['bet'], 'upgrade', '124')
        self.assertEqual(outcome.state['ruleset_id'], game.ruleset_id)
        self.assertEqual(outcome.event['sid'], '124')

    def test_invalid_bets_and_changed_ruleset(self):
        game=BuffaloWin()
        for payload in ({'cs':'nan'},{'cs':'0.031'},{'coin_minor':True},{'ml':True},{'cs':0.2},{'level':11}):
            with self.assertRaises(ServiceError):game.normalize_bet(payload)
        state=game.initial_state('x');state.update(phase='paid_extension',ruleset_id='old')
        with self.assertRaises(ServiceError) as error:game.step(state,state['bet'],'x','1')
        self.assertEqual(error.exception.code,'RULESET_CHANGED')


class BuffaloSettlementTests(unittest.TestCase):
    def test_retrigger_retry_and_persistence_do_not_award_twice(self):
        trigger = ([1,1,1,2,2,2,2,2,2,2,2,2], 11, {}, {})
        retrigger = ([1,1,1,2,2,2,2,2,2,2,2,2], 7, {}, {})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'retrigger.sqlite3'
            game = Scripted([trigger, retrigger])
            service = GameService(path, Registry([game]))
            token = service.create_session()['token']
            first = service.spin(token, game.game_id, 'trigger', '0', {})
            second = service.spin(token, game.game_id, 'retrigger', first['sid'], {})
            self.assertEqual(second['outcome']['free']['remaining'], 19)
            self.assertEqual(second['outcome']['free']['added'], 10)
            self.assertEqual(second['outcome']['special'], 11)
            restarted = GameService(path, Registry([Scripted()]))
            self.assertEqual(restarted.spin(token, game.game_id, 'retrigger', first['sid'], {}), second)
            info = PGAdapter(restarted).game_info(token)['dt']['ls']['si']
            self.assertEqual(info['fs']['s'], 19)
            self.assertEqual(info['fs']['as'], 10)
            third = restarted.spin(token, game.game_id, 'next', second['sid'], {})
            self.assertEqual(third['outcome']['free']['remaining'], 18)
            self.assertEqual(third['outcome']['free']['added'], 0)
            self.assertEqual(third['outcome']['free']['total'], 20)
            self.assertEqual(restarted.wallet(token)['balance_minor'], 199400)
            with restarted.connection() as db:
                self.assertEqual(db.execute('SELECT COUNT(*), SUM(debit_minor) FROM spins JOIN ledger ON ledger.spin_id=spins.id').fetchone()[:], (3, 600))

    def test_concurrent_retry_restart_and_service_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'buffalo.sqlite3'
            registry=Registry([Scripted()])
            service=GameService(path,registry)
            token=service.create_session()['token']
            adapter=PGAdapter(service)
            body=urlencode({'id':'0','cs':'0.3','ml':2,'wk':'0_C','btt':2,'pf':1}).encode()
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
                results=list(pool.map(lambda _:adapter.spin(body,token),range(12)))
            self.assertTrue(all(x==results[0] for x in results))
            self.assertEqual(service.wallet(token)['balance_minor'],199400)
            restarted=GameService(path,registry)
            self.assertEqual(PGAdapter(restarted).spin(body,token),results[0])
            self.assertEqual(PGAdapter(restarted).game_info(token)['dt']['ls']['si'],results[0]['dt']['si'])
            other=GameService(Path(directory)/'other.sqlite3',registry)
            with self.assertRaises(ServiceError):other.wallet(token)
            with service.connection() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM ledger WHERE kind='spin'").fetchone()[0],1)
                self.assertEqual(db.execute('SELECT SUM(credit_minor-debit_minor) FROM ledger').fetchone()[0],199400)
            with service.connection(True) as db:db.execute('UPDATE players SET balance_minor=0')
            previous=results[0]['dt']['si']['sid']
            before=service.state(token,'buffalo-win')
            with self.assertRaises(ServiceError) as error:
                service.spin(token,'buffalo-win','next',previous,{'cs':0.3,'ml':2})
            self.assertEqual(error.exception.code,'INSUFFICIENT_BALANCE')
            self.assertEqual(before,service.state(token,'buffalo-win'))
