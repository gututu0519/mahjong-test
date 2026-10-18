import collections
import json
from pathlib import Path
import random
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from server.adapters.hacksaw.great_game_serengeti import Adapter, CLIENT
from server.core.contracts import ServiceError
from server.core.service import GameService
from server.games.catalog import create_registry
from server.games.great_game_serengeti.engine import GreatGameSerengeti, CASH_VALUES, decode_grid, ordered, mask
from server.services.great_game_serengeti_demo import build_server


class SerengetiTests(unittest.TestCase):
    def test_original_line_awards_and_hunt_accounting(self):
        game = GreatGameSerengeti()
        rounds = json.loads((CLIENT/'fixtures/rounds.json').read_text(encoding='utf-8'))
        counts = collections.Counter()
        for sample in rounds:
            if not sample['request'].get('bets'):
                continue
            amount = int(sample['request']['bets'][0]['betAmount'])
            for event in sample['response']['round']['events']:
                if 'grid' not in event['c']:
                    continue
                grid = decode_grid(event['c']['grid'])
                acts = event['c'].get('actions', [])
                captured = [a for a in acts if a['at'] == 'gridwin' and a['data']['symbol'] != '12']
                self.assertEqual(game.evaluate(grid, amount), captured, sample['request_id'])
                counts['line_awards'] += len(captured)
                values, final, shots, collectors, wilds = {}, None, None, [], []
                for a in acts:
                    d, kind = a['data'], a['at']
                    if kind == 'hunt':
                        counts['hunt'] += 1
                        shots, final = d['c'], decode_grid(d['g'])
                        self.assertEqual(grid[int(d['p'])], 13)
                        for p in range(15):
                            before, after = grid[p], final[p]
                            if not shots[p % 5] or before not in (0, 5, 6, 7, 8, 9):
                                self.assertEqual(before, after)
                            elif before == 0:
                                self.assertEqual(after, 14)
                                wilds.append(p)
                            elif before == 9:
                                self.assertEqual(after, 15)
                                collectors.append(p)
                            else:
                                self.assertGreaterEqual(after, 19 if before in (5, 6) else 24 if before == 7 else 28)
                                values[p] = CASH_VALUES[after - 19]
                    elif kind == 'collectorValues':
                        self.assertEqual(list(map(int, d['p'])), ordered(collectors))
                        values.update(zip(map(int, d['p']), map(int, d['v'])))
                    elif kind == 'collect':
                        counts['collect'] += 1
                        p = int(d['p'])
                        self.assertEqual(d['h'], mask(set(values) - {p}))
                        values[p] += sum(v for q, v in values.items() if q != p)
                        self.assertEqual(values[p], int(d['v']))
                    elif kind == 'mult':
                        counts['mult'] += 1
                        self.assertIn(int(d['p']), wilds)
                        self.assertIn(int(d['m']), (2, 3, 4, 5, 10, 20))
                        self.assertEqual(len(set(d['hits'])), len(d['hits']))
                        self.assertTrue(1 <= len(d['hits']) <= 5)
                        for p, result in zip(map(int, d['hits']), map(int, d['results'])):
                            values[p] *= int(d['m'])
                            self.assertEqual(values[p], result)
                    elif kind == 'cashWin':
                        self.assertEqual(d['h'], mask(values))
                        self.assertEqual(int(d['w']), sum(values.values()) * amount // 10)
                    elif kind == 'ProgressBar':
                        lows = {p for p, v in enumerate(grid) if shots[p % 5] and v in (1, 2, 3, 4)}
                        self.assertEqual(d['h'], mask(lows))
                paid = sum(int(a['data']['winAmount']) for a in captured) + sum(int(a['data']['w']) for a in acts if a['at'] == 'cashWin')
                self.assertEqual(paid, int(event['wa']))
                if collectors:
                    self.assertEqual([int(a['data']['p']) for a in acts if a['at'] == 'collect'], ordered(collectors) if len(values) > 1 else [])
                self.assertEqual([int(a['data']['p']) for a in acts if a['at'] == 'mult'], ordered(wilds) if values else [])
        self.assertGreaterEqual(counts['hunt'], 109)
        self.assertGreaterEqual(counts['collect'], 42)
        self.assertGreaterEqual(counts['mult'], 76)

    def test_original_free_retrigger_and_extra_stampede(self):
        samples = json.loads((CLIENT/'fixtures/rounds.json').read_text(encoding='utf-8'))
        indexed = {r['request_id']: r for r in samples}
        evs = indexed[1121]['response']['round']['events']
        self.assertEqual(sum(e['etn'] == 'fs_reveal' for e in evs), 12)
        self.assertEqual([a['data']['s'] for e in evs for a in e['c'].get('actions', []) if a['at'] == 'retrigger'], ['4'])
        evs = indexed[1123]['response']['round']['events']
        self.assertEqual(sum(e['etn'] == 'fs_2_reveal' for e in evs), 10)
        self.assertEqual(sum(e['etn'] == 'fs_2_respin' for e in evs), 1)
        bars = [int(a['data']['bar']) for e in evs for a in e['c'].get('actions', []) if a['at'] == 'ProgressBar']
        self.assertEqual(bars, [4, 10])
        for n in (1119, 1121, 1123):
            round_id = indexed[n]['response']['round']['roundId']
            self.assertEqual(indexed[n+1]['request']['roundId'], round_id)
            self.assertEqual(indexed[n+1]['response']['round']['status'], 'completed')

    def test_generated_modes_free_counts_progress_and_money(self):
        game = GreatGameSerengeti()
        seen_respins = 0
        for mode in game.config['costs']:
            for seed in range(60):
                evs, total, granted, feature = game.generate(random.Random(str(seed)), 200, mode)
                self.assertEqual(sum(int(e['wa']) for e in evs), total)
                self.assertLessEqual(total, 200 * 5000)
                cumulative, bar, regular, extras = 0, 0, 0, 0
                for e in evs:
                    cumulative += int(e['wa'])
                    self.assertEqual(int(e['awa']), cumulative)
                    if 'grid' not in e['c']:
                        continue
                    grid = decode_grid(e['c']['grid'])
                    self.assertFalse(12 in grid and 13 in grid)
                    self.assertLessEqual(grid.count(13), 1)
                    acts = e['c'].get('actions', [])
                    names = [a['at'] for a in acts]
                    self.assertEqual(int(e['wa']), sum(int(a['data']['winAmount']) for a in acts if a['at'] == 'gridwin') + sum(int(a['data']['w']) for a in acts if a['at'] == 'cashWin'))
                    if e['etn'].endswith('_respin'):
                        self.assertGreaterEqual(bar, 10)
                        bar -= 10
                        seen_respins += 1
                    if 'stampede' in names:
                        self.assertIn(13, grid)
                        self.assertFalse(any(v in (1, 2, 3, 4, 12) for v in grid))
                    if e['etn'] == 'reveal' and mode in ('mod_hunt', 'mod_stampede'):
                        self.assertIn(13, grid)
                        self.assertNotIn(12, grid)
                        if mode == 'mod_stampede':
                            self.assertIn('stampede', names)
                    for a in acts:
                        if a['at'] == 'ProgressBar':
                            bar += a['data']['h'].count('1')
                            self.assertEqual(int(a['data']['bar']), bar)
                        elif a['at'] == 'retrigger':
                            extras += int(a['data']['s'])
                    regular += e['etn'] in ('fs_reveal', 'fs_2_reveal', 'epic_reveal')
                if total < 200 * 5000 and feature:
                    self.assertEqual(regular, (8 if feature == 'fs' else 10) + extras)
                    self.assertEqual(regular, granted)
                if mode in ('fs', 'fs_2'):
                    self.assertEqual(feature, mode)
        self.assertGreater(seen_respins, 0)

    def test_hidden_and_true_maximum_at_all_bet_extremes(self):
        game = GreatGameSerengeti()
        game.config.update(free_trigger_probability=1, free_scatter_weights=[0, 0, 1], stampede_probability=0)
        evs, total, _, feature = game.generate(random.Random('hidden'), 200, 'base')
        self.assertEqual(feature, 'epic')
        for e in evs:
            if e['etn'].startswith('epic_'):
                grid = decode_grid(e['c']['grid'])
                self.assertIn(13, grid)
                self.assertNotIn(12, grid)
        game.config.update(free_hunt_probability=1, shot_hit_probability=1)
        game.config['reel_sets']['fs2'] = [[9] * 5 for _ in range(5)]
        for amount in (10, 200, 200000):
            evs, total, _, _ = game.generate(random.Random('cap'), amount, 'fs_2')
            self.assertEqual(total, amount * 5000)
            self.assertEqual(sum(int(e['wa']) for e in evs), total)
            self.assertEqual(evs[-1]['etn'], 'max_win_reached')
            self.assertEqual(sum(e['etn'] == 'fs_2_reveal' for e in evs), 1)
            self.assertNotIn('feature_exit', [e['etn'] for e in evs])

    def test_wild_overlay_is_available_in_ordinary_hunts(self):
        game = GreatGameSerengeti()
        game.config.update(wild_probability=0.3, hunt_probability=1, shot_hit_probability=1,
                           stampede_probability=0, free_trigger_probability=0)
        game.config['reel_sets']['default'] = [[5] * 5 for _ in range(5)]
        evs, _, _, _ = game.generate(random.Random('overlay'), 200, 'base')
        grid = decode_grid(evs[0]['c']['grid'])
        self.assertIn(0, grid)
        self.assertIn(5, grid)
        self.assertIn(13, grid)
        self.assertEqual(evs[0]['c']['reelSet'], 'default')
        self.assertIn('mult', [a['at'] for a in evs[0]['c']['actions']])

    def test_wallet_retry_recovery_and_unique_payment(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory)/'games.sqlite3'
            service = GameService(database, create_registry(['great-game-serengeti']))
            token = service.create_session()['token']
            adapter = Adapter(service)
            req = dict(sessionUuid=token, seq=1, bets=[dict(betAmount='10', buyBonus='fs_2')])
            result = adapter.bet(req)
            self.assertEqual(result, adapter.bet(req) | {'serverTime': result['serverTime']})
            self.assertEqual(int(result['accountBalance']['balance']), 198000)
            win = int(result['round']['events'][-1]['awa'])
            self.assertGreater(win, 0)
            service = GameService(database, create_registry(['great-game-serengeti']))
            adapter = Adapter(service)
            self.assertEqual(adapter.authenticate(token)['events'], result['round']['events'])
            self.assertEqual(adapter.authenticate(token)['pendingWin'], str(win))
            with self.assertRaises(ServiceError):
                adapter.bet(dict(sessionUuid=token, seq=2, bets=[dict(betAmount='10')]))
            confirm = dict(sessionUuid=token, seq=3, roundId=result['round']['roundId'], continueInstructions={'action':'win_presentation_complete'})
            adapter.bet(confirm)
            adapter.bet(confirm)
            with self.assertRaises(ServiceError):
                adapter.bet(confirm | {'seq': 4})
            self.assertEqual(service.wallet(token)['balance_minor'], 198000 + win)
            self.assertIsNone(adapter.authenticate(token)['roundStatus'])

    def test_original_client_http_and_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            with build_server(0, Path(directory)/'games.sqlite3') as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                base = 'http://127.0.0.1:' + str(server.server_port)
                try:
                    self.assertEqual(json.load(urlopen(base+'/health'))['service_id'], 'great-game-serengeti')
                    req = Request(base+'/api/v1/games/great-game-serengeti/launch', data=b'{"language":"zh"}', headers={'Content-Type':'application/json'})
                    launch = json.load(urlopen(req))
                    with urlopen(base+launch['launch_url']) as response:
                        self.assertIn('/2620/1.26.2/index.html?', response.url)
                        self.assertIn('language=zh-cn', response.url)
                        self.assertIn('/local-adapter.js', response.read().decode('utf-8'))
                    req = Request(base+'/api/play/keepAlive', data=b'{"sessionUuid":"00000000-0000-0000-0000-000000000000"}', headers={'Content-Type':'application/json'})
                    self.assertIsNone(json.load(urlopen(req))['accountBalance'])
                    for path in ('/fixtures/rounds.json','/../fixtures/authenticate.json','/services/great-game-serengeti/data/games.sqlite3'):
                        with self.assertRaises(HTTPError):
                            urlopen(base+path)
                finally:
                    server.shutdown()
                    thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
