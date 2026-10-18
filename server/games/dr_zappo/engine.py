"""Dr Zappo: captured paytable, reflected lasers and locally generated rounds.

Frequencies and multiplier weights are explicit local parameters. Captured rounds
are offline evidence only and never select a generated result.
"""
import copy
import hashlib
import json
from pathlib import Path
import random

from server.core.contracts import Outcome, ServiceError


def encode_grid(grid):
    if len(grid) != 20:
        raise ValueError('Expected 5 by 4 grid')
    return '-,' + ''.join(chr(v + 40) for v in grid)


def decode_grid(value):
    if not isinstance(value, str) or len(value) != 22 or not value.startswith('-,'):
        raise ValueError('Expected 5 by 4 grid')
    return [ord(v) - 40 for v in value[2:]]


def mask(positions):
    return ''.join('1' if p in positions else '0' for p in range(20))


def action(name, **data):
    return dict(at=name, data=data)


def laser_path(origin, direction):
    """Reflect at the energy fields; the two top corners are open exits.

    A vertical top reflection reports that top cell twice (captured protocol).
    """
    if origin not in range(15, 20) or direction not in ('UpLeft', 'Up', 'UpRight'):
        raise ValueError('Invalid eye position or direction')
    dx, dy = {'UpLeft': -1, 'Up': 0, 'UpRight': 1}[direction], -1
    x, y, path = origin % 5, 3, []
    while True:
        if y == 0 and x in (0, 4):
            return path
        if not 0 <= x + dx < 5:
            dx = -dx
        if y + dy < 0:
            dy = -dy
            if dx == 0:
                path.append(x)
        x, y = x + dx, y + dy
        if y > 3:
            return path
        path.append(y * 5 + x)


class DrZappo:
    game_id = 'dr-zappo'
    title = 'Dr Zappo'
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

    def evaluate(self, grid, multipliers, amount):
        """Follow the first natural symbol; plain Wilds do not add multipliers."""
        wins = []
        for line in self.config['lines']:
            positions = [row * 5 + col for col, row in enumerate(line)]
            best = None
            natural = next((grid[p] for p in positions if grid[p] != 0), 0)
            for symbol in dict.fromkeys((0, natural)):
                count = 0
                for p in positions:
                    if grid[p] != symbol and grid[p] != 0:
                        break
                    count += 1
                tier = '_5_inf' if count == 5 else '_' + str(count)
                payout = int(self.config['payouts'].get(str(symbol), {}).get(tier, 0))
                if not payout:
                    continue
                cells = positions[:count]
                mult = sum(multipliers[p] for p in cells if multipliers[p] > 1) or 1
                win = amount * payout * mult // self.config['base_bet_level']
                candidate = action('gridwin', winAmount=str(win), symbol=str(symbol),
                                   mask=mask(cells), count=str(count))
                factors = [multipliers[p] for p in cells if multipliers[p] > 1]
                if factors:
                    candidate['data'].update(baseWinAmount=str(amount * payout // self.config['base_bet_level']),
                                             winMultipliers=list(map(str, factors)))
                if best is None or win > int(best['data']['winAmount']):
                    best = candidate
            if best:
                wins.append(best)
        return wins

    def lasers(self, grid, rng, game_mode):
        transformed = list(grid)
        values = [1 if v in (0, 13) else 0 for v in grid]
        actions = []
        eyes = [p for p in range(15, 20) if grid[p] == 13]
        for origin in eyes:
            available = (['Up', 'UpRight'] if origin == 15 else ['UpLeft', 'Up'] if origin == 19
                         else ['UpLeft', 'Up', 'UpRight'])
            directions = rng.sample(available, 2 if game_mode in ('fs_2', 'epic') else 1)
            # An eye may already have received a multiplier from another eye.
            values[origin] = max(1, values[origin])
            for direction in directions:
                path, results = laser_path(origin, direction), []
                for p in path:
                    if values[p]:
                        increment = (rng.choices(self.config['multiplier_values'], self.config['multiplier_weights'])[0]
                                     if rng.random() < self.config['multiplier_probability'] else 1)
                        values[p] += increment
                    else:
                        values[p] = (rng.choices(self.config['multiplier_values'], self.config['multiplier_weights'])[0]
                                     if rng.random() < self.config['multiplier_probability'] else 1)
                    transformed[p] = 0
                    results.append(str(values[p]))
                actions.append(action('laser', p=list(map(str, path)), m=results, d=direction, origin=str(origin)))
            transformed[origin] = 0
        if eyes:
            actions.append(action('totalMulti', m=list(map(str, values))))
        return actions, transformed, values

    def generate(self, rng, amount, mode):
        events, total, granted_total, free_mode = [], 0, 0, None
        cap = amount * self.config['maximum_win_multiplier']

        def emit(kind, data, win=0):
            nonlocal total
            win = min(win, cap - total)
            total += win
            events.append(dict(et=2, etn=kind, en='0', ba='0', bc='0', wa=str(win), wc='0', awa=str(total), awc='0', c=data))

        def play(game_mode, forced=None):
            reels = self.config['reels' if game_mode == 'base' else 'free_reels']
            grid = [rng.choice(reels[p % 5]) for p in range(20)]
            scatter_count = 0
            if forced in ('fs', 'fs_2'):
                scatter_count = 3 if forced == 'fs' else 4
            elif game_mode == 'base' and mode != 'mod_laser' and rng.random() < self.config['free_trigger_probability'] * (5 if mode == 'mod_bonus' else 1):
                scatter_count = rng.choices([3, 4, 5], self.config['free_scatter_weights'])[0]
            elif game_mode in ('fs', 'fs_2') and rng.random() < self.config['retrigger_probability']:
                scatter_count = rng.choices([2, 3], [9, 1])[0]
            if scatter_count:
                for col in rng.sample(range(5), scatter_count):
                    grid[rng.randrange(4) * 5 + col] = 12
            elif (forced == 'mod_laser' or game_mode == 'epic' or
                  rng.random() < self.config['eye_probability' if game_mode == 'base' else 'free_eye_probability']):
                count = 2 if forced == 'mod_laser' else 1
                while count < 5 and rng.random() < self.config['additional_eye_probability']:
                    count += 1
                for col in rng.sample(range(5), count):
                    grid[15 + col] = 13
            actions, final, multipliers = self.lasers(grid, rng, game_mode)
            wins = self.evaluate(final, multipliers, amount)
            remaining = cap - total
            for item in wins:
                paid = min(int(item['data']['winAmount']), remaining)
                item['data']['winAmount'] = str(paid)
                remaining -= paid
            actions.extend(wins)
            free = 0
            feature = None
            if game_mode == 'base' and scatter_count >= 3:
                free, feature = 10, {3: 'fs', 4: 'fs_2', 5: 'epic'}[scatter_count]
                actions.append(action('gridwin', winAmount='0', symbol='12',
                                      mask=mask({p for p, v in enumerate(grid) if v == 12}), count=str(scatter_count)))
                actions.append(action('bonusfeaturewon', bfw=feature, bfc='10'))
            elif game_mode in ('fs', 'fs_2') and scatter_count >= 2:
                free = 2 if scatter_count == 2 else 4
                actions.append(action('retrigger', s=str(free), h=mask({p for p, v in enumerate(grid) if v == 12})))
            data = dict(reelSet='default', grid=encode_grid(grid))
            if actions:
                data['actions'] = actions
            emit(('' if game_mode == 'base' else game_mode + '_') + 'reveal', data,
                 sum(int(w['data']['winAmount']) for w in wins))
            return free, feature

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
