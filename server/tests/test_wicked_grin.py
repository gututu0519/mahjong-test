import copy
import json
import random
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from server.adapters.hacksaw.wicked_grin import Adapter, CLIENT
from server.core.contracts import ServiceError
from server.core.service import GameService
from server.games.catalog import create_registry
from server.games.wicked_grin.engine import COINS, WickedGrin, decode_grid, mask
from server.services.wicked_grin_demo import build_server


class WickedGrinTests(unittest.TestCase):
    def check_feature_round(self, events, amount):
        stash,collectors = [1]*5,[1]*5
        remaining,feature,total = 0,None,0
        for event in events:
            total += int(event['wa'])
            self.assertEqual(int(event['awa']),total)
            data = event['c']
            if event['etn']=='feature_enter':
                feature = data['bonusFeatureWon']
                remaining = int(data['bonusFeatureCount'])
                self.assertLessEqual(remaining,30)
                self.assertGreaterEqual(remaining,5)
            elif event['etn'] in ('fs_reveal','fs_2_reveal'):
                remaining -= 1
                self.assertGreaterEqual(remaining,0)
            elif event['etn']=='feature_exit':
                self.assertEqual(remaining,0)
            values,awarded = {},0
            for item in data.get('actions',[]):
                kind,detail = item['at'],item['data']
                if kind.lower()=='fsexpand':
                    positions = list(map(int,detail['p']))
                    spins = list(map(int,detail['s']))
                    self.assertEqual(len(spins),len(positions))
                    self.assertTrue(all(v in (1,2,3) for v in spins))
                    grid = decode_grid(data['grid'])
                    columns = {p%5 for p in positions}
                    self.assertIn(len(columns),(1,2))
                    self.assertEqual(set(positions),{r*5+c for c in columns for r in range(5)})
                    self.assertTrue(all(grid[20+c] in (12,13) for c in columns))
                    awarded = sum(spins)
                elif kind=='retrigger':
                    self.assertEqual(int(detail['s']),awarded)
                    self.assertEqual(detail['p'],next(a['data']['p'] for a in data['actions'] if a['at'].lower()=='fsexpand'))
                    remaining += awarded
                elif kind=='bonusfeaturewon':
                    self.assertEqual(int(detail['bfc']),awarded)
                elif kind in ('coinSpreads','epicSpreads'):
                    old,new = decode_grid(data['grid']),decode_grid(detail['g'])
                    triggers = list(map(int,detail['p']))
                    covered = {r*5+p%5 for p in triggers for r in range(p//5+1)}
                    if kind=='epicSpreads':
                        self.assertEqual(int(detail['epicPos']),triggers[0])
                        self.assertEqual(old[triggers[0]],15)
                        self.assertGreaterEqual(triggers[0],20)
                    else:
                        self.assertTrue(all(p>=20 and old[p]==14 for p in triggers))
                    for i in range(25):
                        if i in covered:
                            self.assertTrue(new[i]==16 or 21<=new[i]<=38)
                            if i<5:self.assertNotEqual(new[i],16)
                        else:self.assertEqual(old[i],new[i])
                    values = {i:COINS[v-21] for i,v in enumerate(new) if 21<=v<=38}
                elif kind=='mult':
                    p,m = int(detail['p']),int(detail['m'])
                    self.assertIn(m,(2,3,4,5,10,20))
                    hits = {i for i in values if i//5<p//5 and abs(i%5-p%5)<=1}
                    self.assertEqual(set(map(int,detail['hits'])),hits)
                    for hit,v in zip(detail['hits'],detail['v']):
                        i = int(hit)
                        values[i] *= m
                        self.assertEqual(values[i],int(v))
                    if feature=='fs_2':
                        columns = [c for c in range(5) if abs(c-p%5)<=1]
                        self.assertEqual(list(map(int,detail['barHits'])),columns)
                        for c in columns:collectors[c] *= m
                        self.assertEqual(list(map(int,detail['barValues'])),[collectors[c] for c in columns])
                elif kind=='columnMult':
                    c = int(detail['c'])
                    self.assertEqual(int(detail['m']),stash[c]+1)
                    for hit,v in zip(detail['hits'],detail['v']):
                        i = int(hit)
                        values[i] *= stash[c]
                        self.assertEqual(values[i],int(v))
                    stash[c] += 1
                elif kind=='totalBarAdd':
                    c = int(detail['c'])
                    hits = [i for i in values if i%5==c]
                    increase = sum(values[i] for i in hits)
                    self.assertEqual(detail['h'],mask(hits))
                    self.assertEqual(int(detail['increase']),increase)
                    collectors[c] += increase
                    self.assertEqual(int(detail['total']),collectors[c])
                elif kind=='finalWin':
                    self.assertEqual(int(detail['winAmount']),amount*sum(collectors))
        return total

    def test_latest_original_features_and_complete_buy_settlement(self):
        samples = json.loads((CLIENT/'fixtures/rounds.json').read_text(encoding='utf-8'))
        coverage,modes = set(),set()
        confirmations = {s['request']['roundId']:s['response'] for s in samples if s['request'].get('continueInstructions')}
        for sample in samples:
            bets = sample['request'].get('bets')
            if not bets:continue
            mode = bets[0].get('buyBonus','base')
            modes.add(mode)
            response = sample['response']
            events = response.get('round',{}).get('events',[])
            amount = int(bets[0]['betAmount'])
            self.check_feature_round(events,amount)
            coverage.update(a['at'] for e in events for a in e['c'].get('actions',[]))
            if mode in ('fs','fs_2'):
                rid = response['round']['roundId']
                self.assertIn(rid,confirmations)
                paid = int(confirmations[rid]['accountBalance']['balance'])-int(response['accountBalance']['balance'])
                self.assertEqual(paid,int(events[-1]['awa']))
        self.assertTrue({'base','mod_bonus','mod_spread','fs','fs_2'}<=modes)
        self.assertTrue({'epicSpreads','mult','totalBarAdd','finalWin','retrigger'}<=coverage)

    def test_stash_and_coin_craze_retrigger_rules(self):
        game = WickedGrin()
        # A scatter above the bottom is not an award until it falls to the bottom.
        grid = [1+i%9 for i in range(25)]
        grid[3] = 12
        self.assertEqual(game.free_award(grid,random.Random(1),'fs'),([],0,None))
        for symbol,mode in ((12,'fs'),(13,'fs_2')):
            grid = [1+i%9 for i in range(25)]
            grid[20],grid[24] = symbol,symbol
            acts,count,feature = game.free_award(grid,random.Random(3),mode)
            self.assertEqual(feature,mode)
            self.assertTrue(10<=count<=30)
            self.assertEqual(acts[-1]['at'],'retrigger')
            self.assertEqual(acts[-1]['data']['s'],str(count))
            self.assertEqual(len(acts[-1]['data']['p']),10)

    def test_epic_partial_expansion_and_deferred_win_limit(self):
        game = WickedGrin()
        grid = [1+i%9 for i in range(25)]
        grid[24],grid[11] = 15,14
        stash,collectors = [1]*5,[1]*5
        actions,win = game.expand_coins(grid,random.Random(6),100,'base',stash,collectors,1_000_000)
        self.assertEqual(actions[0]['data']['p'],['24','11'])
        self.check_feature_round([dict(etn='reveal',wa=str(win),awa=str(win),c=dict(grid='--'+''.join(chr(v+40) for v in grid),actions=actions))],100)
        collectors = [1999,1999,1999,1999,1999]
        grid[24] = 14
        actions,win = game.expand_coins(grid,random.Random(6),100,'fs_2',[1]*5,collectors,1_000_000)
        self.assertEqual(win,1_000_000)
        self.assertEqual(actions[-1],{'at':'finalWin','data':{'winAmount':'1000000'}})

    def test_captured_coin_multipliers_stash_and_cash(self):
        samples = json.loads((CLIENT/'fixtures/rounds.json').read_text(encoding='utf-8'))
        checked = 0
        for sample in samples:
            bets = sample['request'].get('bets')
            if not bets:
                continue
            amount = int(bets[0]['betAmount'])
            stash = [1]*5
            for event in sample['response'].get('round',{}).get('events',[]):
                values = {}
                for item in event['c'].get('actions',[]):
                    kind, data = item['at'], item['data']
                    if kind in ('coinSpreads','epicSpreads'):
                        grid = decode_grid(data['g'])
                        values = {i:COINS[v-21] for i,v in enumerate(grid) if 21<=v<=38}
                    elif kind == 'mult':
                        for hit, value in zip(data['hits'],data['v']):
                            i = int(hit)
                            self.assertEqual(values[i]*int(data['m']),int(value))
                            values[i] = int(value)
                    elif kind == 'columnMult':
                        col = int(data['c'])
                        self.assertEqual(int(data['m']),stash[col]+1)
                        for hit,value in zip(data['hits'],data['v']):
                            i = int(hit)
                            self.assertEqual(values[i]*stash[col],int(value))
                            values[i] = int(value)
                        stash[col] += 1
                    elif kind == 'cashWin':
                        self.assertEqual(amount*sum(values.values()),int(data['w']))
                        self.assertEqual(data['h'],''.join('1' if i in values else '0' for i in range(25)))
                        checked += 1
        self.assertGreaterEqual(checked,3)

    def test_captured_grid_paytable_masks_and_cascade_survivors(self):
        game = WickedGrin()
        fixtures = json.loads((CLIENT/'fixtures/rounds.json').read_text(encoding='utf-8'))
        frames = 0
        for sample in fixtures:
            bets = sample['request'].get('bets')
            if not bets:
                continue
            amount = int(bets[0]['betAmount'])
            previous = None
            for event in sample['response'].get('round',{}).get('events',[]):
                data = event['c']
                if 'grid' not in data:
                    previous = None
                    continue
                grid = decode_grid(data['grid'])
                wins = [a for a in data.get('actions',[]) if a['at'] == 'gridwin' and int(a['data']['symbol']) < 10]
                key = lambda a: a['data']['symbol']
                self.assertEqual(sorted(game.evaluate(grid,amount),key=key), sorted(wins,key=key), sample['request_id'])
                if event['etn'].endswith('collapse') and previous:
                    old, removed = previous
                    for col in range(5):
                        kept = [old[r*5+col] for r in range(5) if r*5+col not in removed]
                        self.assertEqual([grid[r*5+col] for r in range(5-len(kept),5)],kept)
                removes = next((a['data']['mask'] for a in data.get('actions',[]) if a['at']=='remove'),None)
                previous = (grid,{i for i,v in enumerate(removes) if v=='1'}) if removes else None
                frames += 1
        self.assertGreater(frames,50)

    def test_generated_rounds_balance_events_and_feature_costs(self):
        game = WickedGrin()
        for mode, cost in game.config['costs'].items():
            for seed in range(75):
                bet = game.normalize_bet({'bet_minor':200,'mode':mode})
                outcome = game.step(game.initial_state('init'),bet,str(seed),'1')
                self.assertEqual(outcome.debit_minor,200*cost)
                self.assertEqual(outcome.credit_minor,0)
                total = 0
                for event in outcome.event['round']['events']:
                    total += int(event['wa'])
                    self.assertEqual(int(event['awa']),total)
                    if 'grid' in event['c']:
                        self.assertEqual(len(decode_grid(event['c']['grid'])),25)
                self.assertEqual(total,outcome.event['total_minor'])
                self.assertLessEqual(total,2_000_000)
                if total<2_000_000:
                    self.check_feature_round(outcome.event['round']['events'],200)
                if mode in ('fs','fs_2'):
                    self.assertGreaterEqual(outcome.event['free_spins'],5)
                    self.assertEqual(outcome.event['free_mode'],mode)
                    self.assertTrue(any(e['etn']=='feature_exit' or e['etn']=='max_win_reached' for e in outcome.event['round']['events']))

    def test_persistent_pending_win_retries_and_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory)/'games.sqlite3'
            service = GameService(database,create_registry(['wicked-grin']))
            token = service.create_session()['token']
            adapter = Adapter(service)
            # FeatureSpins guarantee an expansion and therefore a pending positive win.
            request = dict(seq=2,sessionUuid=token,bets=[dict(betAmount='100',buyBonus='mod_spread')])
            first = adapter.bet(request)
            self.assertEqual(first['round']['status'],'wfwpc')
            self.assertEqual(service.wallet(token)['balance_minor'],195000)
            self.assertEqual(adapter.bet(request)['round'],first['round'])
            with self.assertRaises(ServiceError):
                adapter.bet({**request,'bets':[dict(betAmount='200')]})
            service = GameService(database,create_registry(['wicked-grin']))
            adapter = Adapter(service)
            auth = adapter.authenticate(token)
            self.assertEqual(auth['roundStatus'],'wfwpc')
            self.assertEqual(auth['events'],first['round']['events'])
            self.assertEqual(auth['pendingWin'],first['round']['events'][-1]['awa'])
            confirm = dict(seq=3,sessionUuid=token,roundId=first['round']['roundId'],
                           continueInstructions={'action':'win_presentation_complete'})
            done = adapter.bet(confirm)
            balance = service.wallet(token)['balance_minor']
            self.assertEqual(balance,195000+int(auth['pendingWin']))
            self.assertEqual(adapter.bet(confirm)['accountBalance'],done['accountBalance'])
            self.assertIsNone(adapter.authenticate(token)['roundStatus'])
            with service.connection() as db:
                rows = db.execute("SELECT debit_minor,credit_minor,balance_before,balance_after FROM ledger WHERE kind='spin'").fetchall()
                self.assertEqual(len(rows),2)
                for row in rows:
                    self.assertEqual(row['balance_before']-row['debit_minor']+row['credit_minor'],row['balance_after'])

    def test_input_validation_and_max_win(self):
        game = WickedGrin()
        for data in ({'bet_minor':True},{'bet_minor':201},{'bet_minor':100,'mode':'unknown'},
                     {'bet_minor':100,'cheat':True},{'action':'confirm','round_id':1}):
            with self.assertRaises(ServiceError):
                game.normalize_bet(data)
        cfg = copy.deepcopy(game.config)
        cfg['maximum_win_multiplier'] = 1
        game.config = cfg
        out = game.step(game.initial_state('x'),{'bet_minor':100,'mode':'mod_spread'},'123','1')
        self.assertEqual(out.event['total_minor'],100)
        self.assertEqual(out.event['round']['events'][-1]['etn'],'max_win_reached')

    def test_generated_retriggers_epic_and_early_collector_cap(self):
        game = WickedGrin()
        for mode,seed,expected in [('fs',38,520),('fs_2',38,1520),('mod_spread',2,4000),('mod_spread',13,16260)]:
            result = game.step(game.initial_state('init'),{'bet_minor':200,'mode':mode},str(seed),'1')
            events = result.event['round']['events']
            self.assertEqual(result.event['total_minor'],expected)
            self.check_feature_round(events,200)
            if mode in ('fs','fs_2'):
                self.assertEqual(result.event['free_spins'],14)
                self.assertEqual(sum(e['etn']==mode+'_reveal' for e in events),14)
                self.assertEqual(next(a['data']['s'] for e in events for a in e['c'].get('actions',[]) if a['at']=='retrigger'),'9')
        game.config['coin_weights'] = [0]*17+[1]
        game.config['multiplier_probability'] = .6
        result = game.step(game.initial_state('init'),{'bet_minor':200,'mode':'fs_2'},'18','1')
        events = result.event['round']['events']
        self.assertEqual(result.event['total_minor'],2_000_000)
        initial = int(next(e['c']['bonusFeatureCount'] for e in events if e['etn']=='feature_enter'))
        self.assertLess(sum(e['etn']=='fs_2_reveal' for e in events),initial)
        self.assertEqual(events[-1]['etn'],'max_win_reached')
        self.assertEqual(sum(int(e['wa']) for e in events),2_000_000)
        self.assertEqual(len([a for e in events for a in e['c'].get('actions',[]) if a['at']=='finalWin']),1)

    def test_http_isolation_original_assets_and_language(self):
        with tempfile.TemporaryDirectory() as directory:
            with build_server(0,Path(directory)/'games.sqlite3') as http:
                thread = threading.Thread(target=http.serve_forever,daemon=True)
                thread.start()
                base = f'http://127.0.0.1:{http.server_port}'
                def post(path,data,**headers):
                    return json.load(urlopen(Request(base+path,data=json.dumps(data).encode(),
                        headers={'Content-Type':'application/json',**headers}),timeout=10))
                try:
                    health = json.load(urlopen(base+'/health'))
                    self.assertEqual(health['service_id'],'wicked-grin')
                    self.assertEqual([g['id'] for g in health['games']],['wicked-grin'])
                    launch = post('/api/v1/games/wicked-grin/launch',{'language':'zh'})
                    self.assertEqual(launch['client_language'],'zh-cn')
                    self.assertEqual(launch['balance_minor'],200000)
                    with urlopen(base+'/2347/1.43.1/main.js') as response:
                        self.assertEqual(response.read(),(CLIENT/'2347/1.43.1/main.js').read_bytes())
                    for path in ('/fixtures/authenticate.json','/resource-index.json','/%2e%2e/AGENTS.md'):
                        with self.assertRaises(HTTPError) as error:
                            urlopen(base+path)
                        self.assertEqual(error.exception.code,404)
                    with self.assertRaises(HTTPError) as error:
                        post('/api/v1/sessions',{},Origin='https://example.com')
                    self.assertEqual(error.exception.code,403)
                finally:
                    http.shutdown()
                    thread.join()


if __name__ == '__main__':
    unittest.main()
