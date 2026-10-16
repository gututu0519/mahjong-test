import json
import tempfile
import unittest
from pathlib import Path
from server.adapters.jili.three_billion_vaults import Adapter, pack, unpack
from server.adapters.jili.wire import decode
from server.core.contracts import ServiceError
from server.core.service import GameService
from server.games.catalog import create_registry
from server.games.three_billion_vaults.engine import ThreeBillionVaults, evaluate

class VaultsTests(unittest.TestCase):
    def test_captured_ways_and_feature_accounting(self):
        g=ThreeBillionVaults()
        samples=json.loads(Path(__file__).with_name('fixtures').joinpath('three-billion-vaults-spins.json').read_text())
        self.assertEqual({s['request']['mall']['Index'] for s in samples if s['spin'].get('IsBuy')},{0,1,2})
        for s in samples:
            total=0
            for r in s['spin']['RoundQueue']:
                actual,line=evaluate([col['Column'] for col in r['PlateSymbol']],r['NowWildPos'],round(s['request']['bet']*10000),g.config['paytable_tenths'])
                norm=lambda rows:[tuple(a.get(k,0) for k in ('Symbol','Count','LineNum','Win')) for a in rows]
                self.assertEqual(norm(actual),norm([a for a in r['AwardDataVec'] if a.get('Symbol',0)>=0]))
                cash=sum(round(x.get('Win',0)*10000) for x in r['FGRedCoins'])
                self.assertEqual(line+cash+round(r.get('RedEnvelopeWin',0)*10000)+round(r.get('JPPlate',{}).get('Win',0)*10000),round(r.get('RoundWin',0)*10000))
                total+=round(r.get('RoundWin',0)*10000)
            self.assertEqual(total,round(s['totalWin']*10000))
            self.assertEqual(unpack('SpinAck',pack('SpinAck',s['spin'])),s['spin'])

    def test_signed_packed_and_unpacked(self):
        self.assertEqual(unpack('AwardData',pack('AwardData',{'Symbol':-98}))['Symbol'],-98)
        self.assertEqual(unpack('GameInfoAck',pack('GameInfoAck',{'freeSpinType':-1}))['freeSpinType'],-1)
        self.assertEqual(decode({'x':[1,'int32',True]},bytes([10,5,255,255,255,255,15]),{})['x'],[-1])

    def test_generation_and_persistent_wilds(self):
        g=ThreeBillionVaults();state=g.initial_state('x')
        for seed in range(150):
            bet=dict(bet_minor=1000,extra=False,buy=seed%3 if seed<30 else None)
            outcome=g.step(state,bet,str(seed),str(seed+1));spin=outcome.event['spin']
            self.assertEqual(outcome.credit_minor,sum(round(r['RoundWin']*10000) for r in spin['RoundQueue']))
            self.assertEqual(outcome.debit_minor,round(1000*(g.config['buy_multipliers'][seed%3] if seed<30 else 1)))
            for r in spin['RoundQueue']:
                _,line=evaluate([col['Column'] for col in r['PlateSymbol']],r['NowWildPos'],1000,g.config['paytable_tenths'])
                cash=sum(round(v.get('Win',0)*10000) for v in r['FGRedCoins'])
                self.assertEqual(round(r['RoundWin']*10000),line+cash+round(r.get('RedEnvelopeWin',0)*10000)+round(r.get('JPPlate',{}).get('Win',0)*10000))
            state=outcome.state
        g.config.update(wild_chance=0,feature_chance=0,heist_chance=0)
        state['wilds']={'1000':[6,7,8,11],'2000':[14]}
        outcome=g.step(state,dict(bet_minor=1000,extra=False,buy=None),'moved','200')
        self.assertEqual(outcome.state['wilds'],{'1000':[6,7,10],'2000':[14]})

    def test_transaction_and_reconnect(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'wallet.sqlite3';service=GameService(path,create_registry(['3-billion-vaults']))
            token=service.create_session()['token'];adapter=Adapter(service)
            req=pack('SpinReq',dict(bet=.1,mall=dict(Type=1,Index=1,Bet=4.65)))
            result=adapter.handle(token,0,req,'purchase');money=service.wallet(token)['balance_minor']
            response=unpack('SpinResponse',result['data'])
            self.assertEqual(money,20000000-46500+round(response['totalWin']*10000))
            self.assertEqual(adapter.handle(token,0,req,'purchase'),result)
            adapter.handle(token,4,[],'end');self.assertEqual(service.wallet(token)['balance_minor'],money)
            service=GameService(path,create_registry(['3-billion-vaults']));adapter=Adapter(service)
            self.assertEqual(adapter.handle(token,0,req,'purchase'),result)
            self.assertIn('State',unpack('GameInfoData',unpack('GameInfoAck',adapter.info(token))['extraInfo']))
            for invalid in [dict(bet=.15),dict(bet=.1,mall=dict(Type=1,Index=0,Bet=.1)),dict(bet=.1,extraSpin={},mall=dict(Type=1,Index=0,Bet=2.3))]:
                with self.assertRaises(ServiceError):adapter.handle(token,0,pack('SpinReq',invalid),'bad')
            self.assertEqual(service.wallet(token)['balance_minor'],money)

if __name__=='__main__':unittest.main()
