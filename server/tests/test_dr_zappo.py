import collections
import itertools
import json
from pathlib import Path
import random
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from server.adapters.hacksaw.dr_zappo import Adapter, CLIENT
from server.core.contracts import ServiceError
from server.core.service import GameService
from server.games.catalog import create_registry
from server.games.dr_zappo.engine import DrZappo, decode_grid, encode_grid, laser_path
from server.services.dr_zappo_demo import build_server


class DrZappoTests(unittest.TestCase):
    def test_captured_multiplier_accumulation_and_bonus_counts(self):
        game = DrZappo()
        allowed = {1, *game.config['multiplier_values']}
        repeated, before_activation, dual, bonuses = 0, 0, 0, set()
        samples = json.loads((CLIENT / 'fixtures/rounds.json').read_text(encoding='utf-8'))
        for sample in samples:
            events = sample['response'].get('round', {}).get('events', [])
            free_count, extra, feature = 0, 0, None
            for event in events:
                if event['etn'] == 'feature_enter':
                    feature = event['c']['bonusFeatureWon']
                    bonuses.add(feature)
                    self.assertEqual(event['c']['bonusFeatureCount'], '10')
                if 'grid' not in event['c']:
                    continue
                grid = decode_grid(event['c']['grid'])
                values = [1 if v in (0, 13) else 0 for v in grid]
                activated, origins = set(), []
                for a in event['c'].get('actions', []):
                    d = a['data']
                    if a['at'] == 'laser':
                        origin = int(d['origin'])
                        activated.add(origin)
                        origins.append(origin)
                        for p, value in zip(map(int, d['p']), map(int, d['m'])):
                            self.assertIn(value - values[p], allowed)
                            repeated += values[p] > 0
                            before_activation += grid[p] == 13 and p not in activated
                            values[p] = value
                    elif a['at'] == 'totalMulti':
                        self.assertEqual(values, list(map(int, d['m'])))
                    elif a['at'] == 'retrigger':
                        added = 2 if grid.count(12) == 2 else 4
                        self.assertEqual(int(d['s']), added)
                        extra += added
                self.assertEqual(origins, sorted(origins))
                if event['etn'] in ('fs_reveal', 'fs_2_reveal', 'epic_reveal'):
                    free_count += 1
                if event['etn'] in ('fs_2_reveal', 'epic_reveal'):
                    self.assertTrue(all(v == 2 for v in collections.Counter(origins).values()))
                    dual += bool(origins)
            if feature and any(e['etn'] == 'feature_exit' for e in events):
                self.assertEqual(free_count, 10 + extra)
        self.assertTrue({'fs', 'fs_2'} <= bonuses)
        self.assertGreater(repeated, 10)
        self.assertGreater(before_activation, 0)
        self.assertGreater(dual, 0)

    def test_all_five_eye_double_shot_combinations_against_captured_paths(self):
        samples = json.loads((CLIENT / 'fixtures/rounds.json').read_text(encoding='utf-8'))
        routes = {}
        for sample in samples:
            for event in sample['response'].get('round', {}).get('events', []):
                for a in event['c'].get('actions', []):
                    if a['at'] == 'laser':
                        d = a['data']
                        routes[(int(d['origin']), d['d'])] = list(map(int, d['p']))
        self.assertEqual(len(routes), 13)

        class MinimumMultiplierRng:
            def __init__(self, directions):
                self.directions = iter(directions)

            def sample(self, available, count):
                result = next(self.directions)
                assert len(result) == count and set(result) <= set(available)
                return result

            def random(self):
                return 1.0

        pairs = list(itertools.permutations(('UpLeft', 'Up', 'UpRight'), 2))
        options = [list(itertools.permutations(('Up', 'UpRight'))), pairs, pairs, pairs,
                   list(itertools.permutations(('UpLeft', 'Up')))]
        for directions in itertools.product(*options):
            rng = MinimumMultiplierRng(directions)
            actions, final, values = DrZappo().lasers([1] * 15 + [13] * 5, rng, 'epic')
            self.assertEqual(len(actions), 11)
            self.assertEqual([a['data']['origin'] for a in actions[:-1]],
                             [str(origin) for origin in range(15, 20) for _ in range(2)])
            expected = [0] * 15 + [1] * 5
            for a, (origin, direction) in zip(actions[:-1], ((o, d) for o, ds in zip(range(15, 20), directions) for d in ds)):
                path = routes[(origin, direction)]
                self.assertEqual(a['data']['p'], list(map(str, path)))
                for p, value in zip(path, map(int, a['data']['m'])):
                    expected[p] += 1
                    self.assertEqual(value, expected[p])
            self.assertEqual(values, expected)
            self.assertEqual(final, [0 if v else 1 for v in expected])
            self.assertEqual(actions[-1]['data']['m'], list(map(str, expected)))

    def test_original_anonymous_time_check_and_authenticated_heartbeat(self):
        captured = json.loads((CLIENT / 'fixtures/keep-alive.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as directory:
            with build_server(0, Path(directory) / 'games.sqlite3') as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                base = 'http://127.0.0.1:' + str(server.server_port)
                def post(data):
                    return json.load(urlopen(Request(base + '/api/play/keepAlive', data=json.dumps(data).encode(),
                                                    headers={'Content-Type': 'application/json'})))
                try:
                    clock = post(dict(sessionUuid='00000000-0000-0000-0000-000000000000'))
                    self.assertEqual(set(clock), set(captured))
                    for key in set(captured) - {'serverTime'}:
                        self.assertEqual(clock[key], captured[key])
                    with server.service.connection() as db:
                        self.assertEqual(db.execute('SELECT COUNT(*) FROM players').fetchone()[0], 0)
                    token = server.service.create_session()['token']
                    before = server.service.wallet(token)
                    self.assertIsNone(post(dict(sessionUuid=token))['accountBalance'])
                    self.assertEqual(server.service.wallet(token), before)
                    for data in ({}, dict(sessionUuid='unknown-session')):
                        rejected = post(data)
                        self.assertNotEqual(rejected['statusCode'], 0)
                        self.assertIsNone(rejected['accountBalance'])
                finally:
                    server.shutdown()
                    thread.join(timeout=5)

    def test_captured_laser_paths_and_payline_amounts(self):
        game = DrZappo()
        wins_checked, lasers_checked = 0, 0
        samples = json.loads((CLIENT / 'fixtures/rounds.json').read_text(encoding='utf-8'))
        key = lambda a: (a['data']['symbol'], a['data']['mask'], int(a['data']['winAmount']))
        for sample in samples:
            bets = sample['request'].get('bets')
            if not bets:
                continue
            for event in sample['response'].get('round', {}).get('events', []):
                if 'grid' not in event['c']:
                    continue
                grid = decode_grid(event['c']['grid'])
                self.assertEqual(encode_grid(grid), event['c']['grid'])
                multipliers = [0] * 20
                for a in event['c'].get('actions', []):
                    d = a['data']
                    if a['at'] == 'laser':
                        self.assertEqual(laser_path(int(d['origin']), d['d']), list(map(int, d['p'])))
                        self.assertEqual(len(d['p']), len(d['m']))
                        grid[int(d['origin'])] = 0
                        for p in map(int, d['p']):
                            grid[p] = 0
                        lasers_checked += 1
                    elif a['at'] == 'totalMulti':
                        multipliers = list(map(int, d['m']))
                actual = [a for a in event['c'].get('actions', []) if a['at'] == 'gridwin' and a['data']['symbol'] != '12']
                self.assertEqual(sorted(map(key, actual)), sorted(map(key, game.evaluate(grid, multipliers, int(bets[0]['betAmount'])))))
                self.assertEqual(sum(int(a['data']['winAmount']) for a in actual), int(event['wa']))
                wins_checked += len(actual)
        self.assertGreater(wins_checked, 50)
        self.assertGreater(lasers_checked, 5)

    def test_reflection_exits_and_straight_repeated_top_cell(self):
        self.assertEqual(laser_path(18, 'UpLeft'), [12, 6, 0])
        self.assertEqual(laser_path(18, 'Up'), [13, 8, 3, 3, 8, 13, 18])
        self.assertEqual(laser_path(17, 'UpLeft'), [11, 5, 1, 7, 13, 19])
        for origin in range(15, 20):
            for direction in ('UpLeft', 'Up', 'UpRight'):
                self.assertTrue(all(0 <= p < 20 for p in laser_path(origin, direction)))

    def test_generated_modes_rules_and_accounting(self):
        game = DrZappo()
        for mode in game.config['costs']:
            for seed in range(35):
                with self.subTest(mode=mode, seed=seed):
                    events, total, count, feature = game.generate(random.Random(str(seed)), 200, mode)
                    self.assertEqual(sum(int(e['wa']) for e in events), total)
                    self.assertLessEqual(total, 200 * 10000)
                    cumulative, frees, extras = 0, 0, 0
                    for event in events:
                        cumulative += int(event['wa'])
                        self.assertEqual(int(event['awa']), cumulative)
                        if 'grid' not in event['c']:
                            continue
                        grid = decode_grid(event['c']['grid'])
                        self.assertFalse(12 in grid and 13 in grid)
                        self.assertTrue(all(p >= 15 for p, v in enumerate(grid) if v == 13))
                        if event['etn'] == 'reveal' and mode == 'mod_laser':
                            self.assertGreaterEqual(grid.count(13), 2)
                            self.assertNotIn(12, grid)
                        shots = [a['data'] for a in event['c'].get('actions', []) if a['at'] == 'laser']
                        grouped = collections.Counter(a['origin'] for a in shots)
                        self.assertTrue(all(not (a['origin'] == '15' and a['d'] == 'UpLeft') and
                                            not (a['origin'] == '19' and a['d'] == 'UpRight') for a in shots))
                        if event['etn'] in ('fs_2_reveal', 'epic_reveal'):
                            self.assertTrue(all(n == 2 for n in grouped.values()))
                            self.assertTrue(all(len({a['d'] for a in shots if a['origin'] == origin}) == 2 for origin in grouped))
                        for a in event['c'].get('actions', []):
                            if a['at'] == 'retrigger':
                                self.assertEqual(int(a['data']['s']), 2 if grid.count(12) == 2 else 4)
                                extras += int(a['data']['s'])
                        frees += event['etn'] in ('fs_reveal', 'fs_2_reveal', 'epic_reveal')
                    if mode in ('fs', 'fs_2'):
                        self.assertEqual(feature, mode)
                        if total < 200 * 10000:
                            self.assertEqual(frees, 10 + extras)
                            self.assertEqual(count, frees)

    def test_hidden_bonus_and_cap(self):
        game = DrZappo()
        game.config.update(free_trigger_probability=1, free_scatter_weights=[0, 0, 1])
        events, _, _, feature = game.generate(random.Random('hidden'), 200, 'base')
        self.assertEqual(feature, 'epic')
        hidden = [e for e in events if e['etn'] == 'epic_reveal']
        self.assertEqual(len(hidden), 10)
        for event in hidden:
            grid = decode_grid(event['c']['grid'])
            self.assertIn(13, grid)
            self.assertNotIn(12, grid)
        game.config.update(free_eye_probability=1, additional_eye_probability=1, multiplier_probability=1,
                           multiplier_weights=[0] * 14 + [1])
        for amount in (10, 200, 200000):
            events, total, _, _ = game.generate(random.Random('0'), amount, 'fs_2')
            self.assertEqual(total, amount * 10000)
            self.assertEqual(sum(int(e['wa']) for e in events), total)
            self.assertEqual(events[-1]['etn'], 'max_win_reached')
            self.assertNotIn('feature_exit', [e['etn'] for e in events])
            self.assertEqual(sum(e['etn'] == 'fs_2_reveal' for e in events), 1)

    def test_first_natural_symbol_and_additive_multiplier(self):
        game = DrZappo()
        grid = [0, 0, 0, 0, 6] + [12] * 15
        result = game.evaluate(grid, [1, 2, 1, 3, 0] + [0] * 15, 200)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['data']['symbol'], '6')
        self.assertEqual(int(result[0]['data']['winAmount']), 2000)

    def test_wallet_retry_recovery_and_unique_payout(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'games.sqlite3'
            service = GameService(database, create_registry(['dr-zappo']))
            token = service.create_session()['token']
            adapter = Adapter(service)
            request = dict(sessionUuid=token, seq=1, bets=[dict(betAmount='10', buyBonus='fs_2')])
            result = adapter.bet(request)
            self.assertEqual(result, adapter.bet(request) | {'serverTime': result['serverTime']})
            self.assertEqual(int(result['accountBalance']['balance']), 198000)
            win = int(result['round']['events'][-1]['awa'])
            self.assertGreater(win, 0)
            service = GameService(database, create_registry(['dr-zappo']))
            adapter = Adapter(service)
            auth = adapter.authenticate(token)
            self.assertEqual(auth['pendingWin'], str(win))
            self.assertEqual(auth['events'], result['round']['events'])
            with self.assertRaises(ServiceError):
                adapter.bet(dict(sessionUuid=token, seq=2, bets=[dict(betAmount='10')]))
            confirm = dict(sessionUuid=token, seq=3, roundId=result['round']['roundId'],
                           continueInstructions=dict(action='win_presentation_complete'))
            paid = adapter.bet(confirm)
            self.assertEqual(int(paid['accountBalance']['balance']), 198000 + win)
            adapter.bet(confirm)
            self.assertEqual(service.wallet(token)['balance_minor'], 198000 + win)
            with self.assertRaises(ServiceError):
                adapter.bet(confirm | {'seq': 4})
            self.assertEqual(service.wallet(token)['balance_minor'], 198000 + win)
            self.assertEqual(adapter.authenticate(token)['pendingWin'], '0')

    def test_http_original_client_launch_and_asset_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            with build_server(0, Path(directory) / 'games.sqlite3') as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                base = 'http://127.0.0.1:' + str(server.server_port)
                try:
                    health = json.load(urlopen(base + '/health'))
                    self.assertEqual(health['service_id'], 'dr-zappo')
                    self.assertEqual([g['id'] for g in health['games']], ['dr-zappo'])
                    request = Request(base + '/api/v1/games/dr-zappo/launch', data=b'{"language":"zh"}', headers={'Content-Type': 'application/json'})
                    launch = json.load(urlopen(request))
                    with urlopen(base + launch['launch_url']) as response:
                        page = response.read().decode('utf-8')
                        self.assertIn('/2253/1.49.1/index.html?', response.url)
                        self.assertIn('language=zh-cn', response.url)
                        self.assertIn('/local-adapter.js', page)
                        self.assertIn('Dr Zappo', page)
                    for path in ('/../fixtures/authenticate.json', '/fixtures/rounds.json', '/services/dr-zappo/data/games.sqlite3'):
                        with self.assertRaises(HTTPError):
                            urlopen(base + path)
                finally:
                    server.shutdown()
                    thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
