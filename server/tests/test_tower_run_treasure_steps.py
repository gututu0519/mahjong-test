import copy
from collections import deque
import json
from pathlib import Path
import random
import socket
import tempfile
import threading
import unittest
from http.cookiejar import CookieJar
from urllib.parse import urlencode
from urllib.request import build_opener, HTTPCookieProcessor, Request

from server.adapters.playngo.tower_run import Adapter, CLIENT
from server.core.contracts import ServiceError
from server.core.service import GameService
from server.games.catalog import create_registry
from server.games.tower_run_treasure_steps.engine import TowerRunTreasureSteps
from server.services.tower_run_treasure_steps_demo import build_server


class TreasureScript:
    """Specify landings by cell; preserve normal countdown and life handling."""
    def __init__(self, spins):
        self.draws, self.symbols, locked = deque(), deque(), set()
        for spin in spins:
            for p in range(25):
                if p not in locked:
                    self.draws.append(0 if p in spin else 1)
                    if p in spin:
                        self.symbols.append(spin[p])
            locked.update(p for p,s in spin.items() if s in (11,13))

    def random(self):
        return self.draws.popleft() if self.draws else 1

    def choices(self, values, weights, k=1):
        return [self.symbols.popleft() if list(values)==[11,12,13] else values[0]]

    def choice(self, values):
        return values[0]


def treasure_reveals(packets):
    rows=[]
    row=summary=group=None
    for packet in packets:
        for line in packet:
            d=list(map(int,line.split()))
            if d[:2]==[3,0]:summary=d
            elif d[0]==1:
                row=dict(grid=d[4:29],flag=d[29],summary=summary,values={},events=[])
                rows.append(row)
            elif d[:2]==[2,0]:group=d
            elif d[:3]==[2,2,25]:
                row['values']={d[i]:(d[i+1],d[i+2]) for i in range(4,len(d),3)}
            elif d[:3] in ([2,2,26],[2,2,27]):
                row['events'].append((d,group))
    return rows


class TowerRunTests(unittest.TestCase):
    def test_captured_payouts_wild_sharing_and_thresholds(self):
        game = TowerRunTreasureSteps()
        packets = json.loads((CLIENT/'fixtures/commands.json').read_text(encoding='utf-8'))
        grid, count, shared, tiers = None, 0, False, set()
        for packet in packets:
            if packet['direction'] != 'received':
                continue
            for line in packet['lines']:
                data = list(map(int, line.split()))
                if data[0] == 1 and len(data) == 31:
                    grid = data[4:29]
                elif data[:3] == [2,2,10]:
                    grid = data[5:30]
                elif data[:3] == [2,2,8]:
                    self.assertIsNotNone(grid)
                    n, cursor, awards = data[4], 5, []
                    for _ in range(n):
                        symbol, size = data[cursor:cursor+2]
                        cells = data[cursor+2:cursor+2+size]
                        value, multiplier = data[cursor+2+size:cursor+4+size]
                        cursor += 4+size
                        expected = next(w for w in game.evaluate(grid,multiplier) if w['symbol']==symbol)
                        self.assertEqual(expected['cells'],cells)
                        self.assertEqual(expected['coins'],value)
                        awards.append(set(cells))
                        count += 1
                    shared |= any(a&b for i,a in enumerate(awards) for b in awards[i+1:])
                elif data[:3] == [2,2,22]:
                    tiers.add(data[4])
        self.assertGreater(count,10)
        self.assertTrue(shared)
        self.assertIn(9,tiers)

    def test_new_rounds_modes_progress_and_accounting(self):
        game = TowerRunTreasureSteps()
        for ultra in (False,True):
            for seed in range(100):
                result = game.generate(random.Random(str(seed)),10,ultra,17)
                self.assertTrue(0 <= result['progress'] < 18)
                self.assertTrue(0 <= result['total_minor'] <= 30000*100)
                total = 0
                for packet in [result['lines'],*result['queue']]:
                    for line in packet:
                        d = list(map(int,line.split()))
                        if d[:3] == [2,2,0]:
                            total += d[3]
                        if d[:3] == [2,2,8]:
                            n,cursor=d[4],5
                            for _ in range(n):
                                size=d[cursor+1]
                                total += d[cursor+2+size]
                                cursor += 4+size
                self.assertEqual(total,result['total_coins'])
                self.assertEqual(result['total_minor'],total*10)
                bob=list(map(int,result['lines'][2].split()))
                self.assertTrue(1 <= bob[4] <= 6)
                self.assertEqual(bob[5],(17+bob[4])%18)
                self.assertEqual(bob[7],1)

    def test_treasure_sticky_keys_chests_and_lives(self):
        game=TowerRunTreasureSteps()
        game.config['symbol_weights']=[45,30,20,15,10,5,5,5,5,5,1]
        game.config['treasure_land_probability']=0.12
        game.config['treasure_symbol_weights']=[30,30,40]
        modes=set(); opened=False; keyed=False
        for ultra in (False,True):
            result=next(r for seed in range(2000) if (r:=game.generate(random.Random(str(seed)),10,ultra,0))['bonus'])
            self.assertIn('2 0 3 14 0 0',result['queue'][-1])
            self.assertTrue(any(line.startswith('1 1 ') for packet in result['queue'] for line in packet))
            locked={};lives=4 if ultra else 3
            for packet in result['queue']:
                for line in packet:
                    d=list(map(int,line.split()))
                    if d[0]==1:
                        grid=d[4:29]
                        for p,s in locked.items():
                            self.assertIn(grid[p],(13,14) if s==13 else (s,))
                        locked.update({p:s for p,s in enumerate(grid) if s in (11,13,14)})
                        modes.update(grid)
                    elif d[:3]==[2,2,1]:
                        self.assertTrue(0 <= d[3] <= lives)
                    elif d[:3]==[2,2,26]:keyed=True
                    elif d[:3]==[2,2,27]:opened=True
                    elif d[:2]==[3,0]:
                        self.assertEqual(d[2:4],[result['base_coins'],result['base_coins']*10])
                        self.assertGreater(d[4],0)
            self.assertLessEqual(result['total_coins'],300000)
        self.assertIn(11,modes)
        self.assertIn(13,modes)
        self.assertTrue(opened or keyed)

    def test_latest_captured_opening_groups_and_opened_chest_symbol(self):
        packets=json.loads((CLIENT/'fixtures/commands.json').read_text(encoding='utf-8'))
        rows=treasure_reveals([r['lines'] for r in packets if r['direction']=='received'])
        events=[]
        for i,row in enumerate(rows):
            for data,group in row['events']:
                target=data[4] if data[2]==26 else data[3]
                self.assertEqual(group,[2,0,0,12 if data[2]==26 else 13,1,0])
                self.assertEqual(row['flag'],3)
                self.assertEqual(row['grid'][target],13)
                self.assertEqual(row['values'][target][0],13)
                if data[2]==27:self.assertEqual(row['values'][target][1],0)
                self.assertEqual(rows[i+1]['grid'][target],14)
                self.assertEqual(rows[i+1]['values'][target],(14,data[-1]))
                events.append(data[2])
        self.assertIn(26,events)
        self.assertIn(27,events)

    def scripted_treasure(self, spins, ultra=False, base=0, coin=10, timer=4):
        game=TowerRunTreasureSteps()
        game.config.update(treasure_land_probability=1,coin_coins=[coin],coin_weights=[1],
                           chest_timers=[timer],chest_coins=[100],chest_weights=[1])
        packets,paid=game.generate_treasure(TreasureScript(spins),10,ultra,base,300000)
        return packets,treasure_reveals(packets),paid

    def test_multiple_keys_open_new_chests_once_and_keep_opened_cells(self):
        packets,rows,paid=self.scripted_treasure([{0:12,1:13,2:13,3:12}])
        self.assertEqual(paid,200)
        self.assertEqual([d for d,g in rows[0]['events']],[[2,2,26,0,1,100],[2,2,26,3,2,100]])
        self.assertEqual(rows[0]['values'],{1:(13,4),2:(13,4)})
        self.assertEqual(rows[0]['flag'],3)
        self.assertEqual(rows[1]['grid'][1:3],[14,14])
        self.assertEqual(rows[1]['grid'][0],-1)
        self.assertEqual(rows[1]['grid'][3],-1)
        self.assertEqual(rows[1]['summary'][4],3)
        self.assertEqual(packets[2],['2 0 3 11 0 0','2 2 1 1','2 5 1'])
        self.assertTrue(all(row['values'][1]==(14,100) for row in rows[1:]))

    def test_timer_and_key_openings_together_and_ultra_life_reset(self):
        for ultra in (False,True):
            packets,rows,paid=self.scripted_treasure([{0:13},{},{1:11},{},{2:13,3:12}],ultra)
            opened=rows[4]
            self.assertEqual([d[2] for d,g in opened['events']],[27,26])
            self.assertEqual(opened['values'][0],(13,0))
            self.assertEqual(opened['values'][2],(13,4))
            self.assertEqual(rows[5]['values'][0],(14,100))
            self.assertEqual(rows[5]['values'][2],(14,100))
            self.assertEqual(rows[5]['summary'][4],4 if ultra else 3)
            self.assertEqual(paid,210)
            self.assertEqual([g for d,g in opened['events']],[[2,0,0,13,1,0],[2,0,0,12,1,0]])

    def test_no_target_key_disappears_and_unopened_chest_pays_nothing(self):
        for spin,timer in (({0:12},4),({0:13},12)):
            packets,rows,paid=self.scripted_treasure([spin],timer=timer)
            self.assertEqual(len(rows),4)
            self.assertEqual(paid,0)
            self.assertFalse(any(row['events'] for row in rows))
            if spin[0]==12:self.assertTrue(all(r['grid'][0]==-1 for r in rows[1:]))
            else:self.assertTrue(all(r['grid'][0]==13 for r in rows))
            self.assertIn('2 2 0 0',packets[-1])

    def test_full_board_and_simultaneous_prizes_stop_at_base_bet_cap(self):
        packets,rows,paid=self.scripted_treasure([{p:11 for p in range(25)}])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['grid'],[11]*25)
        self.assertEqual(paid,250)
        for ultra in (False,True):
            packets,rows,paid=self.scripted_treasure([{p:11 for p in range(25)}],ultra,base=299875,coin=50)
            self.assertEqual(paid,125)
            self.assertEqual(rows[0]['values'],{0:(11,50),1:(11,50),2:(11,25)})
            self.assertEqual(rows[0]['grid'][3:],[-1]*22)
            packets,rows,paid=self.scripted_treasure([{0:12,1:13,2:12,3:13}],ultra,base=299850)
            self.assertEqual(paid,150)
            self.assertEqual([d[-1] for d,g in rows[0]['events']],[100,50])
            self.assertIn('2 2 0 150',packets[-1])

    def test_skipped_wild_stage_and_multiplier_returns_after_one_cascade(self):
        class SkipStage(random.Random):
            first=True
            def choices(self, values, weights=None, *, cum_weights=None, k=1):
                if list(values)==list(range(11)):
                    if self.first:
                        self.first=False
                        return [10]*5+[s for s in range(5) for _ in range(2)]+[5]*10
                    return [self.randrange(10) for _ in range(k)]
                return [values[-1]]*k
            def randint(self,a,b):return a
            def sample(self,population,k):return list(population)[:k]
        game=TowerRunTreasureSteps()
        result=game.generate(SkipStage(2),10,False,0)
        self.assertIn('2 2 22 1 6 9',result['lines'])
        self.assertTrue(any(l.startswith('2 2 23 1 2 ') for l in result['lines']))
        self.assertIn('2 2 24 1 5',result['lines'])
        game.config['maximum_win_multiplier']=1
        capped=game.generate(SkipStage(2),10,False,0)
        awards=next(list(map(int,line.split())) for line in capped['lines'] if line.startswith('2 2 8 '))
        self.assertEqual(awards[4],3)
        self.assertEqual(capped['total_coins'],10)
        self.assertFalse(any(l.startswith(('2 2 23 ','2 2 24 ')) for l in capped['lines']))
        game.config['maximum_win_multiplier']=30000
        game.config['symbol_weights']=[45,30,20,15,10,5,5,5,5,5,1]
        for ultra in (False,True):
            result=game.generate(random.Random('7'),10,ultra,0)
            trigger=None;following=[]
            for line in result['lines']:
                d=list(map(int,line.split()))
                if d[:3]==[2,2,24]:trigger=d[3]
                elif trigger is not None and d[:3]==[2,2,8] and d[3]>trigger:
                    cursor=5; multipliers=[]
                    for _ in range(d[4]):
                        size=d[cursor+1]
                        multipliers.append(d[cursor+3+size]);cursor+=size+4
                    following.append(multipliers)
            self.assertGreaterEqual(len(following),2)
            self.assertEqual(set(following[0]),{5 if ultra else 2})
            self.assertTrue(all(set(values)=={2 if ultra else 1} for values in following[1:]))

    def test_restart_after_opening_replays_same_bonus_and_pays_once(self):
        for ultra,seed in ((False,'247'),(True,'2155')):
            with tempfile.TemporaryDirectory() as folder:
                config=copy.deepcopy(TowerRunTreasureSteps().config)
                config.update(symbol_weights=[45,30,20,15,10,5,5,5,5,5,1],
                              treasure_land_probability=.05,treasure_symbol_weights=[30,30,40],chest_timers=[4])
                path=Path(folder)/'config.json';path.write_text(json.dumps(config),encoding='utf-8')
                database=Path(folder)/'games.sqlite3'
                registry=create_registry(['tower-run-treasure-steps'],{'tower-run-treasure-steps':path})
                game=registry.get('tower-run-treasure-steps');step=game.step
                game.step=lambda state,bet,entropy,sid:step(state,bet,seed,sid)
                service=GameService(database,registry);token=service.create_session()['token'];a=Adapter(service)
                a.call(token,1,'1 1 '+('15' if ultra else '10')+' 10 1')
                balance=service.wallet(token)['balance_minor'];seq=2
                while True:
                    response=a.call(token,seq,'2 6');seq+=1
                    if any(line.startswith(('2 2 26 ','2 2 27 ')) for line in response):break
                pending=copy.deepcopy(a.current(token)['pending']);progress=copy.deepcopy(a.current(token)['progress'])
                service=GameService(database,create_registry(['tower-run-treasure-steps'],{'tower-run-treasure-steps':path}));a=Adapter(service)
                response=a.call(token,seq,'104 1098 0');seq+=1
                self.assertIn(pending['initial_lines'][0],response)
                self.assertEqual(a.current(token)['progress'],progress)
                self.assertEqual(service.wallet(token)['balance_minor'],balance)
                while a.current(token)['phase']=='pending':
                    response=a.call(token,seq,'2 6')
                    self.assertEqual(a.call(token,seq,'2 6'),response)
                    seq+=1
                self.assertEqual(service.wallet(token)['balance_minor'],balance)
                response=a.call(token,seq,'4 0')
                self.assertEqual(a.call(token,seq,'4 0'),response)
                self.assertEqual(service.wallet(token)['balance_minor'],balance+pending['total_minor'])

    def test_persistence_retry_replay_and_no_duplicate_debit_or_credit(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'games.sqlite3'
            service=GameService(path,create_registry(['tower-run-treasure-steps']))
            token=service.create_session()['token'];a=Adapter(service)
            response=a.call(token,1,'1 1 15 10 1')
            self.assertEqual(a.call(token,1,'1 1 15 10 1'),response)
            self.assertEqual(service.wallet(token)['balance_minor'],199850)
            pending=copy.deepcopy(a.current(token)['pending'])
            progress=copy.deepcopy(a.current(token)['progress'])
            service=GameService(path,create_registry(['tower-run-treasure-steps']));a=Adapter(service)
            replay=a.call(token,2,'104 1098 0')
            self.assertEqual(a.call(token,2,'104 1098 0'), replay)
            self.assertFalse(any(line.startswith('113') for line in replay))
            self.assertEqual(replay[-1],'109')
            self.assertIn('56 1 10 '+str(progress['10'])+' 18',replay)
            self.assertIn('52 200000 0 0',replay)
            self.assertTrue(any(l==pending['initial_lines'][0] for l in replay))
            self.assertEqual(a.current(token)['progress'],progress)
            with self.assertRaises(ServiceError):a.call(token,3,'1 1 10 10 1')
            seq=4
            while a.current(token)['phase']=='pending':
                a.call(token,seq,'2 6');seq+=1
            if pending['total_minor']:
                summary=a.call(token,seq,'2 6');seq+=1
                self.assertIn('3 0 '+str(pending['total_coins'])+' '+str(pending['total_minor'])+' 0 1',summary)
                paid=a.call(token,seq,'4 0')
                self.assertEqual(a.call(token,seq,'4 0'),paid)
                with self.assertRaises(ServiceError):a.call(token,seq+1,'4 0')
            self.assertEqual(service.wallet(token)['balance_minor'],199850+pending['total_minor'])

    def test_cap_and_progress_per_denomination(self):
        game=TowerRunTreasureSteps()
        game.config['symbol_weights']=[0]*9+[1,0]
        for ultra in (False, True):
            result=game.generate(random.Random('cap'),10,ultra,0)
            self.assertEqual(result['total_coins'],300000)
            self.assertEqual(result['total_minor'],3000000)
            self.assertEqual(result['queue'],[])
        state=game.initial_state('seed')
        for i,(denom,ultra) in enumerate(((10,False),(20,False),(10,True),(20,True))):
            old=copy.deepcopy(state['progress'])
            outcome=game.step(state,dict(denom=denom,ultra=ultra),'cap',str(i)+'spin')
            state=outcome.state
            bob=list(map(int,outcome.event['lines'][2].split()))
            self.assertEqual(bob[3],old.get(str(denom),0))
            self.assertEqual(bob[8],denom)
            for other,progress in old.items():
                if other != str(denom):self.assertEqual(state['progress'][other],progress)
            state=game.step(state,dict(action='continue'),'cap',str(i)+'continue').state
            state=game.step(state,dict(action='collect'),'cap',str(i)+'collect').state

    def test_http_original_bootstrap_native_http_and_private_assets(self):
        with tempfile.TemporaryDirectory() as folder:
            with build_server(0,Path(folder)/'games.sqlite3') as server:
                thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                origin='http://127.0.0.1:'+str(server.server_port)
                opener=build_opener(HTTPCookieProcessor(CookieJar()))
                try:
                    page=opener.open(origin+'/').read().decode('utf-8')
                    self.assertIn('/local-adapter.js',page)
                    config=json.load(opener.open(origin+'/configuration/v2'))
                    self.assertEqual(config['defaultProtocol'],'http')
                    self.assertIn('游戏规则',opener.open(origin+'/casino/gamehelp?lang=zh_CN').read().decode('utf-8'))
                    first=server.service.create_session()['token'];second=server.service.create_session()['token']
                    # The last cookie can belong to another tab. The original
                    # packet session must select the correct isolated wallet.
                    opener.open(origin+'/?ops='+second).read()
                    data=urlencode({'d':'20\r\n'+first+'\r\n1 1 10 10 1\r\n'}).encode()
                    text=opener.open(Request(origin+'/',data=data,headers={'Content-Type':'application/x-www-form-urlencoded','Origin':origin})).read().decode()
                    self.assertTrue(text.startswith('d=1 1 10 10 '))
                    self.assertEqual(server.service.wallet(first)['balance_minor'],199900)
                    self.assertEqual(server.service.wallet(second)['balance_minor'],200000)
                    config=json.load(opener.open(origin+'/configuration/v2?ops='+first))
                    self.assertIn(first,config['desktopGameHistoryUrl'])
                    history=opener.open(origin+config['desktopGameHistoryUrl']).read().decode()
                    self.assertIn('<table>',history)
                    with socket.create_connection(('127.0.0.1',server.server_port),timeout=5) as ws:
                        key=__import__('base64').b64encode(b'0123456789abcdef').decode()
                        request=f'GET /platform/player-events HTTP/1.1\r\nHost: 127.0.0.1:{server.server_port}\r\nOrigin: {origin}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\nCookie: tower-session={first}\r\n\r\n'
                        ws.sendall(request.encode())
                        stream=ws.makefile('rb')
                        self.assertIn(b'101',stream.readline())
                        while stream.readline()!=b'\r\n':pass
                        def exchange(data):
                            mask=b'test'
                            ws.sendall(bytes([0x81,0x80|len(data)])+mask+bytes(v^mask[i%4] for i,v in enumerate(data)))
                            header=stream.read(2)
                            return stream.read(header[1]&127)
                        self.assertEqual(exchange(b'{"protocol":"json","version":1}\x1e'),b'{}\x1e')
                        result=json.loads(exchange(b'{"type":1,"invocationId":"1","target":"RefreshFeatureStates","arguments":[]}\x1e').rstrip(b'\x1e'))
                        self.assertEqual(result,dict(type=3,invocationId='1'))
                        stream.close()
                    for p in ('/fixtures/commands.json','/../fixtures/configuration.json','/cdn/%2e%2e/fixtures/commands.json','/cdn/..%5cfixtures/commands.json','/services/tower-run-treasure-steps/data/games.sqlite3'):
                        with self.assertRaises(__import__('urllib.error',fromlist=['HTTPError']).HTTPError):opener.open(origin+p)
                finally:
                    server.shutdown();thread.join(timeout=5)


if __name__=='__main__':
    unittest.main()
