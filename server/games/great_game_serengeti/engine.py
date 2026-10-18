"""Rules-based Serengeti rounds. Captures are evidence, never result selection.

Original strips and payouts are retained; feature and reward weights are local,
explicit parameters and have not been calibrated to the original RTP.
"""
import copy
import hashlib
import json
from pathlib import Path
import random

from server.core.contracts import Outcome, ServiceError


CASH_VALUES = (2, 4, 6, 8, 10, 20, 30, 40, 50, 100, 150, 200, 250, 500, 1000, 1500, 2500, 5000)


def encode_grid(grid):
    if len(grid) != 15:
        raise ValueError('Expected 5 by 3 grid')
    return '-+' + ''.join(chr(v + 40) for v in grid)


def decode_grid(value):
    if not isinstance(value, str) or len(value) != 17 or not value.startswith('-+'):
        raise ValueError('Expected 5 by 3 grid')
    return [ord(v) - 40 for v in value[2:]]


def mask(positions):
    return ''.join('1' if p in positions else '0' for p in range(15))


def action(name, **data):
    return dict(at=name, data=data)


def ordered(positions):
    return sorted(positions, key=lambda p: (p % 5, p // 5))


class GreatGameSerengeti:
    game_id = 'great-game-serengeti'
    title = 'Great Game Serengeti'
    version = '1.0.0'
    minor_unit = 100

    def __init__(self, config=None):
        self.config = json.loads(Path(config or Path(__file__).with_name('config.json')).read_text(encoding='utf-8'))
        self.ruleset_id = hashlib.sha256(json.dumps(dict(engine=self.version, config=self.config), sort_keys=True).encode()).hexdigest()[:20]

    def initial_state(self, seed):
        return dict(sid='0', phase='ready', pending=None, last_round=None,
                    last_bet_minor=self.config['default_bet_minor'])

    def public_state(self, state):
        return copy.deepcopy(state)

    def normalize_bet(self, payload):
        if not isinstance(payload, dict):
            raise ServiceError('BET_INVALID', 'Expected an object.')
        if payload.get('action') == 'confirm':
            if set(payload) != {'action', 'round_id'} or not isinstance(payload['round_id'], str):
                raise ServiceError('BET_INVALID', 'Invalid round confirmation.')
            return dict(action='confirm', round_id=payload['round_id'])
        if set(payload) - {'bet_minor', 'mode'}:
            raise ServiceError('BET_INVALID', 'Unknown bet field.')
        amount, mode = payload.get('bet_minor'), payload.get('mode', 'base')
        if type(amount) is not int or amount not in self.config['bets_minor'] or not isinstance(mode, str) or mode not in self.config['costs']:
            raise ServiceError('BET_INVALID', 'Invalid bet amount or feature.')
        return dict(bet_minor=amount, mode=mode)

    def evaluate(self, grid, amount):
        wins = []
        for line in self.config['lines']:
            positions = [row * 5 + col for col, row in enumerate(line)]
            natural = next((grid[p] for p in positions if grid[p] != 0), 0)
            best = None
            for symbol in dict.fromkeys((0, natural)):
                count = 0
                for p in positions:
                    if grid[p] not in (0, symbol):
                        break
                    count += 1
                tier = '_5_inf' if count == 5 else '_' + str(count)
                payout = int(self.config['payouts'].get(str(symbol), {}).get(tier, 0))
                if payout:
                    candidate = action('gridwin', winAmount=str(amount * payout // self.config['base_bet_level']),
                                       symbol=str(symbol), mask=mask(positions[:count]), count=str(count))
                    if best is None or int(candidate['data']['winAmount']) > int(best['data']['winAmount']):
                        best = candidate
            if best:
                wins.append(best)
        return wins

    def hunt(self, grid, rng, amount):
        """Transform, collect in column order, then multiply the updated values."""
        origin = grid.index(13)
        shots = [rng.random() < self.config['shot_hit_probability'] for _ in range(5)]
        transformed, values, collectors, wilds = list(grid), {}, [], []
        for p in ordered(range(15)):
            if not shots[p % 5]:
                continue
            symbol = grid[p]
            if symbol == 0:
                transformed[p] = 14
                wilds.append(p)
            elif symbol == 9:
                transformed[p] = 15
                values[p] = rng.choices(self.config['collector_values'], self.config['collector_weights'])[0]
                collectors.append(p)
            elif symbol in (5, 6, 7, 8):
                start = 0 if symbol in (5, 6) else 5 if symbol == 7 else 9
                index = rng.choices(list(range(start, len(CASH_VALUES))), self.config['coin_weights'][start:])[0]
                transformed[p], values[p] = 19 + index, CASH_VALUES[index]
        actions = [action('hunt', p=str(origin), c=shots, g=encode_grid(transformed))]
        if collectors:
            actions.append(action('collectorValues', p=list(map(str, collectors)), v=[str(values[p]) for p in collectors]))
        for p in collectors:
            hits = set(values) - {p}
            if hits:
                values[p] += sum(values[h] for h in hits)
                actions.append(action('collect', p=str(p), h=mask(hits), v=str(values[p])))
        for p in wilds:
            if not values:
                continue
            multiplier = rng.choices(self.config['multiplier_values'], self.config['multiplier_weights'])[0]
            hits = rng.sample(sorted(values), rng.randint(1, min(5, len(values))))
            for h in hits:
                values[h] *= multiplier
            actions.append(action('mult', p=str(p), m=str(multiplier), hits=list(map(str, hits)),
                                  results=[str(values[h]) for h in hits]))
        win = sum(values.values()) * amount // self.config['base_bet_level']
        actions.append(action('cashWin', w=str(win), h=mask(values)))
        lows = {p for p, symbol in enumerate(grid) if shots[p % 5] and symbol in (1, 2, 3, 4)}
        return actions, win, lows

    def generate(self, rng, amount, mode):
        events, total, granted_total, free_mode, bar = [], 0, 0, None, 0
        cap = amount * self.config['maximum_win_multiplier']

        def emit(kind, data, win=0):
            nonlocal total
            win = min(win, cap - total)
            total += win
            events.append(dict(et=2, etn=kind, en='0', ba='0', bc='0', wa=str(win), wc='0', awa=str(total), awc='0', c=data))

        def play(game_mode, forced=None, respin=False):
            nonlocal bar
            stampede = respin or forced == 'mod_stampede' or (
                game_mode in ('base', 'fs') and forced not in ('fs', 'fs_2') and rng.random() < self.config['stampede_probability'])
            reel_set = 'stampede' if stampede else {'base': 'default', 'fs': 'fs', 'fs_2': 'fs2', 'epic': 'epic'}[game_mode]
            if game_mode == 'base' and forced in ('mod_hunt', 'mod_stampede'):
                reel_set = 'hunt_stampede' if stampede else 'hunt'
            reels = self.config['reel_sets'][reel_set]
            stops = [rng.randrange(len(reel)) for reel in reels]
            grid = [reels[col][(stops[col] + row) % len(reels[col])] for row in range(3) for col in range(5)]
            # Specials are generated separately by explicit local parameters.
            grid = [rng.randint(5 if stampede else 1, 9) if v in (12, 13) else v for v in grid]
            # The published default/free strips contain no Wilds, whereas the
            # captured ordinary/free reveals do. Preserve that overlay mechanic
            # with an explicit local weight instead of excluding those Wilds.
            wild_chance = self.config['wild_probability' if game_mode == 'base' else 'free_wild_probability']
            if not stampede:
                grid = [0 if v in range(1, 10) and rng.random() < wild_chance else v for v in grid]
            scatter_count = 0
            if forced in ('fs', 'fs_2'):
                scatter_count = 3 if forced == 'fs' else 4
            elif game_mode == 'base' and not stampede and mode not in ('mod_hunt', 'mod_stampede') and rng.random() < self.config['free_trigger_probability'] * (3 if mode == 'mod_bonus' else 1):
                scatter_count = rng.choices([3, 4, 5], self.config['free_scatter_weights'])[0]
            elif game_mode in ('fs', 'fs_2') and not stampede and rng.random() < self.config['retrigger_probability']:
                scatter_count = rng.choices([2, 3], [9, 1])[0]
            if scatter_count:
                for col in rng.sample(range(5), scatter_count):
                    grid[rng.randrange(3) * 5 + col] = 12
            elif stampede or forced == 'mod_hunt' or game_mode == 'epic' or rng.random() < self.config['hunt_probability' if game_mode == 'base' else 'free_hunt_probability']:
                grid[rng.randrange(15)] = 13
            actions = [action('stampede')] if stampede else []
            wins = self.evaluate(grid, amount)
            remaining = cap - total
            for item in wins:
                paid = min(int(item['data']['winAmount']), remaining)
                item['data']['winAmount'] = str(paid)
                remaining -= paid
            actions.extend(wins)
            win = sum(int(w['data']['winAmount']) for w in wins)
            if 13 in grid:
                hunt_actions, cash, lows = self.hunt(grid, rng, amount)
                cash = min(cash, remaining)
                hunt_actions[-1]['data']['w'] = str(cash)
                actions.extend(hunt_actions)
                win += cash
                if game_mode in ('fs_2', 'epic') and lows:
                    bar += len(lows)
                    actions.append(action('ProgressBar', bar=str(bar), threshold='10', h=mask(lows)))
            extra, feature = 0, None
            if game_mode == 'base' and scatter_count >= 3:
                feature = {3: 'fs', 4: 'fs_2', 5: 'epic'}[scatter_count]
                extra = 8 if feature == 'fs' else 10
                actions.extend([action('gridwin', winAmount='0', symbol='12', mask=mask({p for p, v in enumerate(grid) if v == 12}), count=str(scatter_count)),
                                action('bonusfeaturewon', bfw=feature, bfc=str(extra))])
            elif game_mode in ('fs', 'fs_2') and scatter_count >= 2:
                extra = 2 if scatter_count == 2 else 4
                actions.append(action('retrigger', s=str(extra), h=mask({p for p, v in enumerate(grid) if v == 12})))
            data = dict(reelSet=reel_set, stops=list(map(str, stops)), grid=encode_grid(grid))
            if actions:
                data['actions'] = actions
            emit(('reveal' if game_mode == 'base' else game_mode + ('_respin' if respin else '_reveal')), data, win)
            return extra, feature

        free_count, free_mode = play('base', mode)
        granted_total = free_count
        if free_count and total < cap:
            emit('feature_enter', dict(bonusFeatureWon=free_mode, bonusFeatureCount=str(free_count)))
            remaining, played = free_count, 0
            while remaining and total < cap:
                remaining -= 1
                extra, _ = play(free_mode)
                remaining += extra
                granted_total += extra
                played += 1
                # A full Lion Bar awards an extra spin, including on the last
                # regular free spin. Overflow remains after subtracting ten.
                while bar >= 10 and total < cap:
                    bar -= 10
                    play(free_mode, respin=True)
                if played > 1000:
                    raise RuntimeError('Generated bonus exceeds sanity limit')
            if total < cap:
                emit('feature_exit', {})
        if total >= cap:
            emit('max_win_reached', {})
        return events, total, granted_total, free_mode

    def step(self, state, bet, seed, sid):
        state = copy.deepcopy(state)
        if bet.get('action') == 'confirm':
            pending = state['pending']
            if not pending or pending['round_id'] != bet['round_id']:
                raise ServiceError('ROUND_INVALID', 'No matching pending round.', 409)
            state.update(sid=sid, phase='ready', pending=None)
            return Outcome(state, dict(round_id=pending['round_id'], next_phase='ready', confirm=True,
                                       round=dict(roundId=pending['round_id'], status='completed', possibleActions=[], events=[])),
                           0, pending['win_minor'])
        if state['pending']:
            raise ServiceError('ROUND_PENDING', 'Complete the previous round presentation first.', 409)
        amount, mode = bet['bet_minor'], bet['mode']
        events, total, free_count, free_mode = self.generate(random.Random(str(seed)), amount, mode)
        round_data = dict(roundId=sid, status='wfwpc' if total else 'completed', possibleActions=[], events=events)
        state.update(sid=sid, last_bet_minor=amount, last_round=round_data, phase='pending' if total else 'ready',
                     pending=dict(round_id=sid, win_minor=total, bet_minor=amount, mode=mode) if total else None)
        event = dict(round_id=sid, next_phase=state['phase'], round=round_data, bet_minor=amount,
                     mode=mode, total_minor=total, free_spins=free_count, free_mode=free_mode)
        return Outcome(state, event, amount * self.config['costs'][mode], 0)
