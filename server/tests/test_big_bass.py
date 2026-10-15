import json
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from server.games.big_bass_bonanza.engine import BigBassBonanza
from server.adapters.pp.big_bass_bonanza import transaction


class BigBassTests(unittest.TestCase):
    def test_captured_rounds(self):
        game = BigBassBonanza()
        state = game.initial_state(0)
        rows = json.loads((Path(__file__).parent/'fixtures/big-bass-spins.json').read_text())['rows']
        free_count = 0
        for row in rows:
            q, d = row['request'], row['response']
            if q['action'] == 'doInit':
                continue
            command = dict(action='collect' if q['action']=='doCollect' else 'spin',
                           coin_minor=int(Decimal(d.get('c', q.get('c','0.16')))*100),
                           request_index=int(q['index']))
            if command['action']=='collect':
                state = game.step(state, command, 1, str(row['id'])).state
                continue
            board = list(map(int,d['s'].split(',')))
            draw = (board,list(map(int,d['sa'].split(','))),list(map(int,d['sb'].split(','))))
            fish = list(map(int,d.get('mo',','.join(['0']*15)).split(',')))
            with patch.object(game,'_draw',return_value=draw), patch('server.games.big_bass_bonanza.engine.random.Random') as random:
                random.return_value.random.return_value = 1
                random.return_value.choices.side_effect = [[fish[p]] for p,s in enumerate(board) if s==7]
                result = game.step(state,command,1,str(row['id']))
            actual = transaction(result.event)
            for k,v in d.items():
                if k not in ('balance','index','counter','reel_set'):
                    self.assertEqual(actual.get(k),v,(row['id'],k,actual.get(k),v))
            state = result.state
            free_count += result.event['free_spin']
        self.assertGreaterEqual(free_count,20)

    def test_delayed_retrigger_and_multiplier(self):
        game = BigBassBonanza()
        s = game.initial_state(0)
        s.update(phase='free', free=dict(total=10,played=6,win_minor=0,collectors=3,stage=0,batch_end=10))
        board=[3,4,5,6,8,9,10,11,12,3,4,5,6,7,2]
        with patch.object(game,'_draw',return_value=(board,[3]*5,[4]*5)), patch('server.games.big_bass_bonanza.engine.random.Random') as random:
            random.return_value.random.return_value=1
            random.return_value.choices.return_value=[20]
            for i in range(5):
                r=game.step(s,dict(action='spin',coin_minor=20,request_index=i+1),1,str(i+1))
                s=r.state
                self.assertEqual(r.event['multiplier'],1 if i<4 else 2)
                self.assertEqual(r.event['free_awarded'],10 if i==3 else 0)
                self.assertEqual(r.debit_minor,0)

    def test_higher_retriggers_and_cap(self):
        game = BigBassBonanza()
        board=[3,4,5,6,8,9,10,11,12,3,4,5,6,7,2]
        for stage, collectors in [(1,7),(2,11),(3,15)]:
            s=game.initial_state(0)
            s.update(phase='free',free=dict(total=10,played=9,win_minor=0,collectors=collectors,stage=stage,batch_end=10))
            with patch.object(game,'_draw',return_value=(board,[3]*5,[4]*5)), patch('server.games.big_bass_bonanza.engine.random.Random') as random:
                random.return_value.random.return_value=1
                random.return_value.choices.return_value=[20]
                r=game.step(s,dict(action='spin',coin_minor=20,request_index=1),1,'1')
            self.assertEqual(r.event['multiplier'],[1,2,3,10][stage])
            self.assertEqual(r.event['free_awarded'],10 if stage<3 else 0)
            self.assertEqual(r.state['phase'],'free' if stage<3 else 'collect')
        s['total_minor']=419999
        with patch.object(game,'_draw',return_value=(board,[3]*5,[4]*5)), patch('server.games.big_bass_bonanza.engine.random.Random') as random:
            random.return_value.random.return_value=1
            random.return_value.choices.return_value=[20000]
            r=game.step(s,dict(action='spin',coin_minor=20,request_index=1),1,'1')
        self.assertEqual(r.event['total_minor'],420000)
        self.assertEqual(r.state['phase'],'collect')
        self.assertEqual(r.event['delta_minor'],1)
