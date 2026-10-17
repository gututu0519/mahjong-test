"""Wicked Grin rules and generated outcomes, separate from the HTTP protocol.

Paytable/mechanics come from captured gameInfo and official client help. Special
symbol frequencies and coin weights are local configuration, not an RTP model.
"""
import copy
import hashlib
import json
from pathlib import Path
import random

from server.core.contracts import Outcome, ServiceError

COINS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30, 40, 50, 100, 150, 250, 500]


def encode_grid(grid):
    return '--' + ''.join(chr(int(value) + 40) for value in grid)


def decode_grid(value):
    if not isinstance(value, str) or len(value) != 27 or value[:2] != '--':
        raise ValueError('Expected a 5 by 5 encoded grid')
    return [ord(char) - 40 for char in value[2:]]


def mask(positions):
    positions = set(positions)
    return ''.join('1' if i in positions else '0' for i in range(25))


def action(name, **data):
    return {'at': name, 'data': data}


class WickedGrin:
    game_id = 'wicked-grin'
    title = 'Wicked Grin'
    version = '1.1.0'
    minor_unit = 100

    def __init__(self, config=None):
        self.config = json.loads(Path(config or Path(__file__).with_name('config.json')).read_text(encoding='utf-8'))
        self.ruleset_id = hashlib.sha256(json.dumps({'engine':self.version,'config':self.config},sort_keys=True).encode()).hexdigest()[:20]

    def initial_state(self, seed):
        return {'sid': '0', 'phase': 'ready', 'pending': None, 'last_round': None,
                'last_bet_minor': self.config['default_bet_minor']}

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
        if type(amount) is not int or amount not in self.config['bets_minor'] or mode not in self.config['costs']:
            raise ServiceError('BET_INVALID', 'Invalid bet amount or feature.')
        return dict(bet_minor=amount, mode=mode)

    def evaluate(self, grid, bet):
        wins = []
        for symbol in range(1, 10):
            positions = [i for i, value in enumerate(grid) if value == symbol]
            count = len(positions)
            if count < 6:
                continue
            tier = 0 if count < 8 else 1 if count < 10 else 2 if count == 10 else 3 if count < 13 else 4 if count < 15 else 5 if count < 17 else 6
            amount = bet * self.config['payouts'][str(symbol)][tier] // 10
            wins.append(action('gridwin', winAmount=str(amount), symbol=str(symbol), mask=mask(positions), count=str(count)))
        return wins

    def free_award(self, grid, rng, game_mode):
        """Only bottom-row scatters expand; every covered cell grants 1..3 spins."""
        scatters = [i for i in range(20,25) if grid[i] in (12,13)]
        if not scatters:
            return [], 0, None
        feature = 'fs_2' if grid[scatters[0]] == 13 else 'fs'
        if game_mode != 'base' and feature != game_mode:
            raise ValueError('A free-spin mode cannot award the other feature')
        positions = [row*5+p%5 for p in scatters for row in range(5)]
        values = rng.choices([1,2,3], weights=[8,2,1], k=len(positions))
        count = sum(values)
        actions = [action('FsExpand',p=list(map(str,positions)),s=list(map(str,values)))]
        actions.append(action('bonusfeaturewon',bfw=feature,bfc=str(count)) if game_mode=='base' else
                       action('retrigger',p=list(map(str,positions)),s=str(count)))
        return actions, count, feature

    def expand_coins(self, grid, rng, amount, game_mode, stash, collectors, win_limit):
        """Resolve an expansion after cascades, keeping non-covered cells unchanged."""
        grins = [i for i,v in enumerate(grid) if v in (14,15)]
        triggers = [i for i in grins if i//5==4]
        if not triggers:
            return [], 0
        epic = next((p for p in triggers if grid[p]==15),None)
        positions = ([epic]+sorted((p for p in grins if p!=epic),key=lambda p:p%5)
                     if epic is not None else triggers)
        converted, values = list(grid), {}
        for p in positions:
            for row in range(p//5+1):
                i = row*5+p%5
                if row and rng.random()<self.config['multiplier_probability']:
                    converted[i] = 16
                else:
                    coin = rng.choices(range(len(COINS)),weights=self.config['coin_weights'])[0]
                    converted[i],values[i] = 21+coin,COINS[coin]
        details = dict(p=list(map(str,positions)),g=encode_grid(converted))
        if epic is not None:
            details['epicPos'] = str(epic)
        actions = [action('epicSpreads' if epic is not None else 'coinSpreads',**details)]
        for p in sorted((i for i,v in enumerate(converted) if v==16),key=lambda i:(i%5,i//5)):
            multiplier = rng.choices([2,3,4,5,10,20],weights=[60,25,10,4,1,1])[0]
            hits = sorted((i for i in values if i//5<p//5 and abs(i%5-p%5)<=1),key=lambda i:(i%5,-(i//5)))
            for i in hits:
                values[i] *= multiplier
            bars = {}
            if game_mode=='fs_2':
                columns = [c for c in range(5) if abs(c-p%5)<=1]
                for col in columns:
                    collectors[col] *= multiplier
                bars = dict(barHits=list(map(str,columns)),barValues=[str(collectors[c]) for c in columns])
            actions.append(action('mult',p=str(p),m=str(multiplier),hits=list(map(str,hits)),
                                  v=[str(values[i]) for i in hits],**bars))
        columns = sorted(set(i%5 for i in values))
        if game_mode=='fs':
            for col in columns:
                hits = sorted((i for i in values if i%5==col))
                for i in hits:
                    values[i] *= stash[col]
                stash[col] += 1
                actions.append(action('columnMult',c=str(col),m=str(stash[col]),hits=list(map(str,hits)),
                                      v=[str(values[i]) for i in hits]))
        if game_mode=='fs_2':
            for col in columns:
                hits = [i for i in values if i%5==col]
                increase = sum(values[i] for i in hits)
                collectors[col] += increase
                actions.append(action('totalBarAdd',c=str(col),h=mask(hits),increase=str(increase),total=str(collectors[col])))
            # The max-win rule also applies to deferred collector winnings: stop
            # immediately when the payable round total reaches the limit.
            if amount*sum(collectors)>=win_limit:
                actions.append(action('finalWin',winAmount=str(win_limit)))
                return actions,win_limit
            return actions,0
        win = min(amount*sum(values.values()),win_limit)
        actions.append(action('cashWin',h=mask(values),w=str(win)))
        return actions,win

    def step(self, state, bet, seed, sid):
        state = copy.deepcopy(state)
        if bet.get('action') == 'confirm':
            pending = state['pending']
            if not pending or bet['round_id'] != pending['round_id']:
                raise ServiceError('ROUND_INVALID', 'No matching pending round.', 409)
            state.update(sid=sid, phase='ready', pending=None)
            event = {'round_id': pending['round_id'], 'next_phase': 'ready', 'confirm': True,
                     'round': dict(roundId=pending['round_id'], status='completed', possibleActions=[], events=[])}
            return Outcome(state, event, 0, pending['win_minor'])
        if state['pending']:
            raise ServiceError('ROUND_PENDING', 'Complete the previous round presentation first.', 409)
        rng = random.Random(str(seed))
        amount, mode = bet['bet_minor'], bet['mode']
        events, total, free_count, free_mode = self.generate(rng, amount, mode)
        round_data = dict(roundId=sid, status='wfwpc' if total else 'completed', possibleActions=[], events=events)
        state.update(sid=sid, last_bet_minor=amount, last_round=round_data,
                     phase='pending' if total else 'ready',
                     pending={'round_id': sid, 'win_minor': total, 'bet_minor': amount, 'mode': mode} if total else None)
        event = {'round_id': sid, 'next_phase': state['phase'], 'round': round_data,
                 'bet_minor': amount, 'mode': mode, 'total_minor': total,
                 'free_spins': free_count, 'free_mode': free_mode}
        return Outcome(state, event, amount*self.config['costs'][mode], 0)

    def generate(self, rng, amount, mode):
        events, total = [], 0
        cap = amount * self.config['maximum_win_multiplier']
        stash, collectors = [1]*5, [1]*5
        def emit(kind, data, win=0):
            nonlocal total
            win = min(win, cap-total)
            total += win
            events.append(dict(et=2, etn=kind, en='0', ba='0', bc='0', wa=str(win), wc='0',
                               awa=str(total), awc='0', c=data))
        def draw(reel):
            return rng.choice(self.config['reels'][reel])
        def play(game_mode, forced=None):
            nonlocal total
            grid = [draw(i % 5) for i in range(25)]
            special = None
            if forced in ('fs', 'fs_2'):
                special = 12 if forced == 'fs' else 13
            elif forced == 'mod_spread':
                special = 15 if rng.random()<self.config['epic_fraction'] else 14
            elif rng.random() < self.config['free_symbol_probability'] * (5 if mode == 'mod_bonus' and game_mode=='base' else 1):
                special = 13 if game_mode == 'fs_2' or (game_mode == 'base' and rng.random() < .25) else 12
            elif rng.random() < self.config['grin_probability']:
                special = 15 if rng.random() < self.config['epic_fraction'] else 14
            if special:
                columns = rng.sample(range(5), 2 if rng.random() < .15 else 1)
                for col in columns:
                    row = 4 if forced else rng.randrange(5)
                    grid[row*5+col] = special
                if special == 15 and rng.random() < .5:
                    other = rng.choice([c for c in range(5) if c not in columns])
                    grid[rng.randrange(5)*5+other] = 14
            prefix = '' if game_mode == 'base' else game_mode+'_'
            for cascade in range(1000):
                wins = self.evaluate(grid, amount)
                win = sum(int(w['data']['winAmount']) for w in wins)
                remaining = cap-total
                # Clip individual winnings consistently with the event and wallet.
                for item in wins:
                    paid = min(int(item['data']['winAmount']), remaining)
                    item['data']['winAmount'] = str(paid)
                    remaining -= paid
                removed = {i for w in wins for i, value in enumerate(w['data']['mask']) if value == '1'}
                data = {'reelSet': 'default', 'grid': encode_grid(grid)}
                if wins:
                    data['actions'] = wins + [action('remove', mask=mask(removed))]
                emit(prefix+('reveal' if cascade == 0 else 'collapse'), data, win)
                if game_mode=='fs_2' and total<cap and total+amount*sum(collectors)>=cap:
                    collected = cap-total
                    data.setdefault('actions',[]).append(action('finalWin',winAmount=str(collected)))
                    events[-1]['wa'] = str(int(events[-1]['wa'])+collected)
                    total = cap
                    events[-1]['awa'] = str(total)
                if total >= cap:
                    return 0, None
                if not wins:
                    break
                for col in range(5):
                    kept = [grid[row*5+col] for row in range(5) if row*5+col not in removed]
                    cells = [draw(col) for _ in range(5-len(kept))] + kept
                    for row, symbol in enumerate(cells):
                        grid[row*5+col] = symbol
            else:
                raise RuntimeError('Generated cascade exceeds sanity limit')
            actions, granted, fs_mode = self.free_award(grid,rng,game_mode)
            if granted:
                data['actions'] = actions
                return granted, fs_mode
            actions,win = self.expand_coins(grid,rng,amount,game_mode,stash,collectors,cap-total)
            if actions:
                data['actions'] = actions
            # Expansion is presented on the final no-win grid, and its amount belongs to that event.
            events[-1]['wa'] = str(win)
            total += win
            events[-1]['awa'] = str(total)
            return 0, None

        free_count, free_mode = play('base', mode if mode in ('fs','fs_2','mod_spread') else None)
        granted_total = free_count
        if free_count and total < cap:
            emit('feature_enter', {'bonusFeatureWon': free_mode, 'bonusFeatureCount': str(free_count)})
            remaining = free_count
            played = 0
            while remaining > 0 and total < cap:
                remaining -= 1
                extra, _ = play(free_mode)
                remaining += extra
                granted_total += extra
                played += 1
                if played > 1000:
                    raise RuntimeError('Generated bonus exceeds sanity limit')
            if free_mode == 'fs_2' and total < cap:
                win = min(amount*sum(collectors), cap-total)
                emit('fs_2_collapse',dict(grid=events[-1]['c']['grid'],reelSet='default',
                     actions=[action('finalWin',winAmount=str(win))]),win)
            if total < cap:
                emit('feature_exit', {})
        if total >= cap:
            emit('max_win_reached', {})
        return events, total, granted_total, free_mode
