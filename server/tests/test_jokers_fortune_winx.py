import json
import tempfile
import unittest
from pathlib import Path
from server.adapters.jili.jokers_fortune_winx import Adapter, pack, unpack
from server.core.contracts import ServiceError
from server.core.service import GameService
from server.games.catalog import create_registry
from server.games.jokers_fortune_winx.engine import JokersFortuneWinX, evaluate


class JokersFortuneWinXTests(unittest.TestCase):
    def test_real_regular_and_extra_rounds(self):
        samples = json.loads(Path(__file__).with_name('fixtures').joinpath('jokers-fortune-winx-spins.json').read_text())
        game = JokersFortuneWinX()
        self.assertEqual(len(samples), 60)
        self.assertEqual(sum('extraSpin' in s['request'] for s in samples), 30)
        for sample in samples:
            spin, request = sample['spin'], sample['request']
            total = 0
            for r in spin['RoundQueue']:
                actual, base, line, scatter = evaluate([c['Col'] for c in r['Symbol']], round(request['bet']*10000),
                    [int(v) for v in r['MulVec']], 'extraSpin' in request, game.config['paytable'])
                keys = ('Atype','Index','Symbol','Count','Win')
                self.assertEqual([tuple(a.get(k,0) for k in keys) for a in actual],
                                 [tuple(a.get(k,0) for k in keys) for a in r['AwardDataVec']])
                self.assertEqual(base, round(r.get('BaseWin',0)*10000))
                self.assertEqual(line+scatter, round(r.get('RoundWin',0)*10000))
                total += line+scatter
            self.assertEqual(total, round(sample['totalWin']*10000))
            self.assertEqual(unpack('SpinAck', pack('SpinAck', spin)), spin)

    def test_scatter_is_separate_and_does_not_use_reel_multiplier(self):
        g = JokersFortuneWinX()
        cols = [[7,0,1],[7,0,2],[7,0,3],[4,1,4],[5,2,5]]
        for extra in (False, True):
            awards, base, line, scatter = evaluate(cols,1000,[2,10,3],extra,g.config['paytable'])
            self.assertEqual(scatter,10000)
            self.assertEqual(line,30000)
            self.assertEqual(base,13000)
            self.assertEqual(awards[-1]['Pos'],[0,3,6])

    def test_generated_round_accounting(self):
        g = JokersFortuneWinX()
        for seed in range(200):
            extra = bool(seed%2)
            result = g.step(g.initial_state('x'),{'bet_minor':1000,'extra':extra},str(seed),str(seed+1))
            spin = result.event['spin']
            r = spin['RoundQueue'][0]
            self.assertEqual(result.debit_minor,2000 if extra else 1000)
            self.assertEqual(result.credit_minor,round(sum(a['Win'] for a in r['AwardDataVec'])*10000))
            self.assertEqual(len(r['MulVec']),3)
            self.assertLessEqual(sum(c['Col'].count(7) for c in r['Symbol']),5)
            self.assertLessEqual(result.credit_minor,1000*g.config['max_win_multiple'])

    def test_idempotency_and_round_end(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'wallet.sqlite3'
            service = GameService(path,create_registry(['jokers-fortune-winx']))
            token = service.create_session()['token']
            adapter = Adapter(service)
            req = pack('SpinReq',{'bet':.1,'extraSpin':{}})
            result = adapter.handle(token,0,req,'one')
            money = service.wallet(token)['balance_minor']
            response = unpack('SpinResponse',result['data'])
            self.assertEqual(money,20000000-2000+round(response['totalWin']*10000))
            self.assertEqual(adapter.handle(token,0,req,'one'),result)
            for ack in (4,36):
                adapter.handle(token,ack,[],'end')
                self.assertEqual(service.wallet(token)['balance_minor'],money)
            restarted = GameService(path,create_registry(['jokers-fortune-winx']))
            self.assertEqual(Adapter(restarted).handle(token,0,req,'one'),result)
            for request in ({'bet':.15},{'bet':.1,'extraSpin':{'Index':1}}):
                with self.assertRaises(ServiceError):
                    adapter.handle(token,0,pack('SpinReq',request),'invalid')
            self.assertEqual(service.wallet(token)['balance_minor'],money)


if __name__ == '__main__':
    unittest.main()
