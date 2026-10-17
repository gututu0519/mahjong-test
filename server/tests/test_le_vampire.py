import json
from pathlib import Path
import random
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from server.games.le_vampire.engine import LeVampire, COINS, encode_grid, decode_grid, mask, adjacent
from server.adapters.hacksaw.le_vampire import Adapter, CLIENT
from server.core.contracts import ServiceError
from server.core.service import GameService
from server.games.catalog import create_registry
from server.services.le_vampire_demo import build_server


class LeVampireTests(unittest.TestCase):
    def test_captured_cluster_payouts_and_super_cascade_removal(self):
        game=LeVampire();checked=0
        for sample in json.loads((CLIENT/'fixtures/rounds.json').read_text(encoding='utf-8')):
            bets=sample['request'].get('bets')
            if not bets:continue
            amount=int(bets[0]['betAmount'])
            for event in sample['response'].get('round',{}).get('events',[]):
                c=event['c']
                if 'grid' not in c:continue
                grid=decode_grid(c['grid']);calculated=game.evaluate(grid,amount)
                self.assertEqual(encode_grid(grid),c['grid'])
                wins=[a['data'] for a in c.get('actions',[]) if a['at']=='gridwin' and a['data']['symbol']!='12']
                for win in wins:
                    self.assertTrue(any(a['data']['mask']==win['mask'] for a in calculated))
                    self.assertEqual(int(win['winAmount']),game.payout(int(win['symbol']),int(win['count']),amount))
                    checked+=1
                remove=next((a['data']['mask'] for a in c.get('actions',[]) if a['at']=='remove'),None)
                if remove:
                    symbols={int(a['symbol']) for a in wins}
                    expected={p for p,v in enumerate(grid) if v in symbols}
                    expected.update(p for win in wins for p,v in enumerate(win['mask']) if v=='1' and grid[p]==0)
                    self.assertEqual(remove,mask(expected))
        self.assertGreater(checked,100)

    def test_captured_special_value_arithmetic(self):
        coverage=set()
        for sample in json.loads((CLIENT/'fixtures/rounds.json').read_text(encoding='utf-8')):
            bets=sample['request'].get('bets')
            if not bets:continue
            amount=int(bets[0]['betAmount'])
            for event in sample['response'].get('round',{}).get('events',[]):
                grid=[];values={}
                for a in event['c'].get('actions',[]):
                    k,d=a['at'],a['data'];coverage.add(k)
                    if k in ('replace','localReplace'):
                        grid=decode_grid(d['g'])
                        cells={p for p,v in enumerate(d['goldMask']) if v=='1'}|{p for p,v in enumerate(d['bloodMask']) if v=='1'}
                        for p in cells:
                            values.pop(p,None)
                            if 19<=grid[p]<=38:values[p]=COINS[grid[p]-19]
                    elif k in ('mult','globalMult'):
                        p,m=int(d['p']),int(d['m'])
                        for q,value in zip(d['hits'],d['results']):
                            q=int(q)
                            self.assertTrue(k=='globalMult' or adjacent(p,q))
                            values[q]*=m
                            self.assertEqual(values[q],int(value))
                    elif k in ('collect','localCollect'):
                        hits={p for p,v in enumerate(d['h']) if v=='1'}
                        self.assertEqual(sum(values[p] for p in hits),int(d['w']))
                        p=int(d['p']);values[p]=int(d['w'])
                    elif k=='cashWin':
                        hits={p for p,v in enumerate(d['h']) if v=='1'}
                        self.assertEqual(sum(values[p] for p in hits)*amount//10,int(d['w']))
        self.assertTrue({'mult','collect','localCollect','allHighsUpgraded'}<=coverage)

    def test_generated_special_values_and_rare_mode_witnesses(self):
        game=LeVampire()
        for mode,seed,expected in [('fs',2,79880),('fs_2',0,70200),('mod_epic',353,549720)]:
            events,total,_,_=game.generate(random.Random(str(seed)),200,mode)
            self.assertEqual(total,expected)
            for event in events:
                values={}
                for a in event['c'].get('actions',[]):
                    k,d=a['at'],a['data']
                    if k in ('replace','localReplace'):
                        grid=decode_grid(d['g'])
                        cells={p for p in range(30) if d['goldMask'][p]=='1' or d['bloodMask'][p]=='1'}
                        for p in cells:
                            values.pop(p,None)
                            if 19<=grid[p]<=38:values[p]=COINS[grid[p]-19]
                    elif k in ('mult','globalMult'):
                        for p,v in zip(d['hits'],d['results']):
                            p=int(p);values[p]*=int(d['m'])
                            self.assertEqual(values[p],int(v))
                    elif k in ('collect','localCollect'):
                        hits={p for p,v in enumerate(d['h']) if v=='1'}
                        self.assertEqual(sum(values[p] for p in hits),int(d['w']))
                        values[int(d['p'])]=int(d['w'])
                    elif k=='cashWin':
                        hits={p for p,v in enumerate(d['h']) if v=='1'}
                        self.assertEqual(sum(values[p] for p in hits)*20,int(d['w']))
        game.config.update(bonus_probability=1,bonus_weights=[0,0,1])
        events,_,count,feature=game.generate(random.Random('0'),200,'base')
        self.assertEqual(feature,'epic')
        self.assertEqual(count,12)
        for e in events:
            if e['etn']=='epic_reveal':
                self.assertTrue(any(v in (13,14) for v in decode_grid(e['c']['grid'])))
            for a in e['c'].get('actions',[]):
                if a['at'] in ('replace','localReplace'):
                    g=decode_grid(a['data']['g'])
                    for p in range(30):
                        if a['data']['goldMask'][p]=='1' or a['data']['bloodMask'][p]=='1':self.assertNotIn(g[p],(19,20))

    def test_connected_clusters_and_wilds(self):
        game=LeVampire();grid=[1+(p%8) for p in range(30)]
        for p in (0,1,2,6,7):grid[p]=1
        grid[1]=0;grid[29]=1
        cluster=next(c for s,c in game.clusters(grid) if s==1)
        self.assertTrue({0,1,2,6,7}<=cluster)
        self.assertNotIn(29,cluster)
        self.assertFalse(adjacent(5,6))
        self.assertTrue(adjacent(0,7))

    def test_generated_all_modes_and_features(self):
        game=LeVampire();seen=set()
        for mode in game.config['costs']:
            for seed in range(80):
                events,total,count,feature=game.generate(random.Random(str(seed)),200,mode)
                self.assertEqual(sum(int(e['wa']) for e in events),total)
                self.assertEqual(int(events[-1]['awa']),total)
                self.assertLessEqual(total,3_000_000)
                self.assertLessEqual(count,18)
                if feature:
                    self.assertIn(count,(10,12,14,16,18))
                    played=sum(e['etn']==feature+'_reveal' for e in events)
                    if events[-1]['etn']!='max_win_reached':self.assertEqual(played,count)
                for e in events:
                    for a in e['c'].get('actions',[]):
                        seen.add(a['at'])
                        if a['at'] in ('replace','localReplace'):
                            d=a['data'];g=decode_grid(d['g'])
                            for p,v in enumerate(d['bloodMask']):
                                if v=='1':self.assertNotIn(g[p],range(19,25))
        self.assertTrue({'globalMult','highUpgrade','allHighsUpgraded','collect','localCollect','highlightReset'}<=seen)

    def test_pending_round_persists_and_settles_once(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'games.sqlite3';service=GameService(path,create_registry(['le-vampire']))
            token=service.create_session()['token'];adapter=Adapter(service)
            request={'sessionUuid':token,'seq':1,'bets':[{'betAmount':'200','buyBonus':'fs_2'}]}
            result=adapter.bet(request);auth=adapter.authenticate(token)
            self.assertEqual(result['accountBalance']['balance'],'150000')
            self.assertEqual(auth['roundStatus'],'wfwpc')
            service=GameService(path,create_registry(['le-vampire']));adapter=Adapter(service)
            self.assertEqual(adapter.authenticate(token)['events'],auth['events'])
            confirm={'sessionUuid':token,'seq':2,'roundId':auth['roundId'],'continueInstructions':{'action':'win_presentation_complete'}}
            done=adapter.bet(confirm)
            self.assertEqual(int(done['accountBalance']['balance']),150000+int(auth['pendingWin']))
            self.assertEqual(adapter.bet(confirm)['accountBalance'],done['accountBalance'])
            self.assertIsNone(adapter.authenticate(token)['roundStatus'])
            with self.assertRaises(ServiceError):adapter.bet({**request,'bets':[{'betAmount':'100'}]})

    def test_cap_and_input_validation(self):
        game=LeVampire()
        for payload in ({'bet_minor':True},{'bet_minor':201},{'bet_minor':200,'mode':'epic'},{'bet_minor':200,'override':1}):
            with self.assertRaises(ServiceError):game.normalize_bet(payload)
        game.config['maximum_win_multiplier']=1
        events,total,_,_=game.generate(random.Random('1'),200,'mod_epic')
        self.assertEqual(total,200)
        self.assertEqual(events[-1]['etn'],'max_win_reached')

    def test_max_win_discards_remaining_free_spins(self):
        game=LeVampire();game.config.update(coin_weights=[0]*19+[1],special_probabilities=[0]*4)
        events,total,awarded,feature=game.generate(random.Random('0'),200,'fs_2')
        self.assertEqual(total,3_000_000)
        self.assertEqual(events[-1]['etn'],'max_win_reached')
        self.assertLess(sum(e['etn']=='fs_2_reveal' for e in events),awarded)
        self.assertFalse(any(e['etn']=='feature_exit' for e in events))
        self.assertEqual(sum(int(e['wa']) for e in events),total)

    def test_http_original_assets_language_and_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            with build_server(0,Path(directory)/'test.sqlite3') as http:
                thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
                base='http://127.0.0.1:'+str(http.server_port)
                try:
                    health=json.load(urlopen(base+'/health'))
                    self.assertEqual(health['service_id'],'le-vampire')
                    req=Request(base+'/api/v1/games/le-vampire/launch',data=b'{"language":"zh"}',headers={'Content-Type':'application/json'})
                    launch=json.load(urlopen(req));self.assertEqual(launch['client_language'],'zh-cn')
                    self.assertEqual(launch['balance_minor'],200000)
                    self.assertEqual(urlopen(base+'/2582/1.36.0/main.js').read(),(CLIENT/'2582/1.36.0/main.js').read_bytes())
                    with self.assertRaises(HTTPError):urlopen(base+'/fixtures/authenticate.json')
                    with self.assertRaises(HTTPError):urlopen(Request(base+'/api/v1/sessions',data=b'{}',headers={'Origin':'https://example.com'}))
                finally:http.shutdown();thread.join()


if __name__=='__main__':unittest.main()
