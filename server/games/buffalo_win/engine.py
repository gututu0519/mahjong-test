"""Generated Buffalo Win demo. Integer-credit settlement; no captured outcome replay.

Captured rules: see docs/buffalo-win-rules-analysis.txt. Probability parameters are
local configuration, not the original provider RNG.
"""
import copy
import hashlib
import json
import random
from decimal import Decimal, InvalidOperation
from pathlib import Path

from server.core.contracts import Outcome, ServiceError

PAYTABLE = {3: 5, 4: 4, 5: 3, 6: 3, 7: 2, 8: 2, 9: 2, 10: 1, 11: 1, 12: 1}


def evaluate(board, expanded, block_counts, coin_minor, level):
    if len(board) < 12 or len(board) % 4 or any(type(v) is not int or v not in range(13) for v in board):
        raise ValueError('Expected columns of four symbols in 0..12')
    positions, counts, awards = {}, {}, {}
    for symbol, rate in PAYTABLE.items():
        hits = []
        for offset in range(0, len(board), 4):
            column = [offset + i for i, v in enumerate(board[offset:offset + 4]) if v in (0, symbol)]
            if not column:
                break
            hits.extend(column)
        if len({p // 4 for p in hits}) < 3:
            continue
        key = str(symbol)
        positions[key] = hits
        count = len(hits)
        for block_id, cells in expanded.items():
            if set(cells).issubset(hits):
                count += block_counts[block_id] - len(cells)
        counts[key] = count
        awards[key] = coin_minor * level * rate * count
    extend = 1 in board[-4:] or any(p >= len(board) - 4 for hits in positions.values() for p in hits)
    return {'positions': positions, 'counts': counts, 'awards_minor': awards,
            'base_minor': sum(awards.values()), 'extend': extend}


class BuffaloWin:
    game_id = 'buffalo-win'
    title = '美洲野牛'
    version = '1.2.0'

    def __init__(self, config_path=None):
        self.config = json.loads(Path(config_path or Path(__file__).with_name('config.json')).read_text(encoding='utf-8'))
        c = self.config
        if (c['coin_sizes_minor'] != [2, 3, 10, 20, 30, 90, 200] or c['bet_levels'] != list(range(1, 11))
                or c['base_bet_factor'] != 10 or c['free_trigger'] != 3 or c['free_spins'] != 10
                or c['free_extra_spins'] != 2 or c['free_retrigger'] is not True
                or c['feature_buy'] != {'t': 0.5, 'bms': None, 'is': True, 'bm': 75}
                or c['feature_buy_game_config'] != {'t': 40.0, 'bms': None, 'is': True, 'bm': 75}):
            raise ValueError('Unsupported documented rule constants')
        if (set(c['symbol_weights']) != set(map(str, range(13)))
                or any(type(v) is not int or not 0 <= v <= 10000 for v in c['symbol_weights'].values())
                or c['symbol_weights']['2'] <= 0
                or any(type(c[k]) not in (int, float) or not 0 <= c[k] <= 1
                       for k in ('stack_probability', 'expanded_probability'))
                or c['win_thresholds'] != {'mw': 3, 'bw': 5, 'mgw': 15, 'smgw': 35}):
            raise ValueError('Invalid local generation configuration')
        digest = hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()[:16]
        self.ruleset_id = f'{self.version}:{digest}'
        # The 1.1 rules for natural rounds are unchanged. Recognize that exact
        # configuration so a pre-upgrade feature can finish without losing progress.
        legacy = copy.deepcopy(c)
        legacy['coin_sizes_minor'] = [3, 10, 30, 90]
        for key in ('feature_buy', 'feature_buy_game_config'):
            legacy.pop(key)
        self.compatible_ruleset_id = '1.1.0:' + hashlib.sha256(
            json.dumps(legacy, sort_keys=True).encode()).hexdigest()[:16]

    def normalize_bet(self, payload):
        if not isinstance(payload, dict) or set(payload) - {'coin_minor', 'level', 'cs', 'ml', 'buy_free'}:
            raise ServiceError('BET_INVALID', 'Unsupported bet fields.')
        buy = payload.get('buy_free', False)
        if type(buy) is not bool:
            raise ServiceError('BET_INVALID', 'buy_free must be a boolean.')
        try:
            coin = payload.get('coin_minor')
            if coin is None:
                value = Decimal(str(payload.get('cs', '0.3'))) * 100
                if not value.is_finite() or value != value.to_integral_value():
                    raise ValueError()
                coin = int(value)
            level = payload.get('level', payload.get('ml', 2))
            if (type(coin) is not int or type(level) is not int
                    or coin not in self.config['coin_sizes_minor'] or level not in self.config['bet_levels']):
                raise ValueError()
        except (ValueError, InvalidOperation, TypeError, OverflowError):
            raise ServiceError('BET_INVALID', 'Unsupported coin size or bet level.') from None
        return {'coin_minor': coin, 'level': level, **({'buy_free': True} if buy else {})}

    def _buy_board(self, rng):
        """Generate a purchase trigger, rather than replaying the captured board.

        Local distribution: two scatters initially (one on the last reel), then
        a third on the first extension. The ordinary extension rules still apply.
        """
        board = [symbol for col in range(3) for symbol in self._column(rng, first=col == 0)]
        board = [2 if symbol == 1 else symbol for symbol in board]
        for position in (rng.randrange(8), rng.randrange(8, 12)):
            board[position] = 1
        special = rng.randint(3, 12)
        expanded, counts = self._new_blocks(board, rng)
        return board, special, expanded, counts

    def _buy_column(self, rng, needs_scatter):
        column = [2 if symbol == 1 else symbol for symbol in self._column(rng)]
        if needs_scatter:
            column[rng.randrange(4)] = 1
        return column

    def _column(self, rng, first=False):
        result = []
        symbols = range(1 if first else 0, 13)
        while len(result) < 4:
            symbol = rng.choices(symbols, weights=[self.config['symbol_weights'][str(s)] for s in symbols])[0]
            size = rng.randint(2, 4) if symbol >= 3 and rng.random() < self.config['stack_probability'] else 1
            result.extend([symbol] * min(size, 4 - len(result)))
        return result

    def _start_board(self, rng, free):
        board = [symbol for col in range(3) for symbol in self._column(rng, first=col == 0)]
        special = rng.randint(3, 12)
        # The original help excludes Wild from reel 1, including free-spin stacks.
        expanded, counts = self._new_blocks(board[4:] if free else board, rng, 4 if free else 0)
        return board, special, expanded, counts

    def _new_blocks(self, board, rng, offset=0, first_id=1):
        """Mark stacked symbols; their larger count is used only in winning combinations."""
        expanded, counts = {}, {}
        for col in range(len(board) // 4):
            start = col * 4
            while start < col * 4 + 4:
                end = start + 1
                while end < col * 4 + 4 and board[end] == board[start]:
                    end += 1
                if (end - start >= 2 and board[start] >= 3
                        and rng.random() < self.config['expanded_probability']):
                    key = str(first_id + len(expanded))
                    expanded[key] = list(range(offset + start, offset + end))
                    counts[key] = end - start + rng.randint(1, end - start)
                start = end
        return expanded, counts

    def _free_award(self, scatter_count):
        if scatter_count < self.config['free_trigger']:
            return 0
        return self.config['free_spins'] + (scatter_count - self.config['free_trigger']) * self.config['free_extra_spins']

    def initial_state(self, seed):
        return {'sid': '0', 'round_id': '0', 'phase': 'ready', 'ruleset_id': self.ruleset_id,
                'bet': {'coin_minor': 30, 'level': 2}, 'board': [3, 2, 4, 2, 5, 2, 6, 2, 7, 2, 8, 2],
                'expanded': {}, 'block_counts': {}, 'special': 10, 'multiplier': 1,
                'free': None, 'counts': {}, 'round_award_minor': 0, 'base_minor': 0,
                'extension_index': 0, 'last_event': None}

    def public_state(self, state):
        return copy.deepcopy(state)

    def step(self, state, bet, seed, sid):
        state = copy.deepcopy(state)
        phase = state['phase']
        start = phase == 'ready'
        buy = bet.get('buy_free', False)
        if buy and not start:
            raise ServiceError('FEATURE_LOCKED', 'Finish this round before buying free spins.', 409)
        bet = {key: bet[key] for key in ('coin_minor', 'level')}
        free_mode = phase in ('free_start', 'free_extension')
        extension = phase in ('paid_extension', 'free_extension')
        if not start and state['ruleset_id'] not in (self.ruleset_id, self.compatible_ruleset_id):
            raise ServiceError('RULESET_CHANGED', 'Finish this round with its original ruleset.', 409)
        if not start and bet != state['bet']:
            raise ServiceError('BET_LOCKED', 'Finish this round before changing your bet.', 409)
        if start:
            state.update(round_id=sid, bet=bet, ruleset_id=self.ruleset_id, multiplier=1,
                         free=None, counts={}, round_award_minor=0, base_minor=0,
                         bought_feature=buy)
        rng = random.Random(seed)
        prior_base = state['base_minor']
        previous_board = state['board'][:]
        previous_positions = evaluate(previous_board, state['expanded'], state['block_counts'],
                                      bet['coin_minor'], bet['level'])['positions'] if extension else {}
        new_blocks, original_column = {}, None
        if free_mode:
            state['free']['added'] = 0
        if extension:
            column = (self._buy_column(rng, previous_board.count(1) < self.config['free_trigger'])
                      if not free_mode and state.get('bought_feature') else self._column(rng))
            original_column = column[:]
            new_blocks, new_counts = self._new_blocks(column, rng, len(previous_board),
                                                      max(map(int, state['expanded']), default=0) + 1)
            state['expanded'].update(new_blocks)
            state['block_counts'].update(new_counts)
            state['board'].extend(column)
            original = previous_board
            state['multiplier'] += 1
            state['extension_index'] += 1
            if free_mode:
                state['free']['rc'] += 1
        else:
            original, special, state['expanded'], state['block_counts'] = (
                self._buy_board(rng) if buy else self._start_board(rng, free_mode))
            if not free_mode:
                state['special'] = special
            state['board'] = original[:]
            state['extension_index'] = 0
            if free_mode:
                state['free']['remaining'] -= 1
                state['free']['rc'] = 0
        # Captured orl/oecrl preserve symbols before the stack transformation.
        for cells in state['expanded'].values():
            for p in cells:
                state['board'][p] = 0 if free_mode else state['special']
        if phase != 'ready':
            state['counts'][phase] = state['counts'].get(phase, 0) + 1
        board = state['board']
        result = evaluate(board, state['expanded'], state['block_counts'], bet['coin_minor'], bet['level'])
        multiplier = state['multiplier']
        base = result['base_minor']
        debit = bet['coin_minor'] * bet['level'] * 10 if start else 0
        if buy:
            debit *= self.config['feature_buy']['bm']
        credit = 0 if result['extend'] else base * multiplier
        state['round_award_minor'] += credit
        if free_mode:
            state['free']['award_minor'] += credit
        if result['extend']:
            next_phase = 'free_extension' if free_mode else 'paid_extension'
        elif free_mode:
            # Award once when this spin's entire extension chain settles, including
            # on the final free spin; extending itself never consumes another spin.
            added = self._free_award(board.count(1))
            state['free']['remaining'] += added
            state['free']['total'] += added
            state['free']['added'] = added
            next_phase = 'free_start' if state['free']['remaining'] > 0 else 'ready'
        elif (awarded := self._free_award(board.count(1))):
            state['free'] = {'remaining': awarded, 'total': awarded,
                             'award_minor': 0, 'added': 0, 'rc': 0}
            state['multiplier'] = 1
            next_phase = 'free_start'
        else:
            next_phase = 'ready'
        free_event = copy.deepcopy(state['free'])
        accumulated = base if result['positions'] else (prior_base if free_mode else 0)
        display_delta = base - prior_base if result['extend'] or not base else base * (multiplier - 1)
        state['base_minor'] = accumulated
        event = {'sid': sid, 'round_id': state['round_id'], 'phase': phase, 'next_phase': next_phase,
                 'bet': bet, 'base_bet_minor': bet['coin_minor'] * bet['level'] * 10,
                 'bought_feature': state.get('bought_feature', False),
                 'debit_minor': debit, 'win_minor': credit, 'round_award_minor': state['round_award_minor'],
                 'board': board[:], 'original': original, 'expanded': copy.deepcopy(state['expanded']),
                 'block_counts': dict(state['block_counts']), 'special': state['special'],
                 'multiplier': multiplier, 'extension_index': state['extension_index'],
                 'extension': extension, 'extend': result['extend'], 'previous_positions': previous_positions,
                 'new_blocks': new_blocks, 'original_column': original_column,
                 'free': free_event, 'phase_counts': dict(state['counts']), 'counts_eval': result['counts'] or None,
                 'scatter_count': board.count(1),
                 'accumulated_minor': accumulated, 'display_delta_minor': display_delta, **result}
        state.update(sid=sid, phase=next_phase, last_event=event)
        return Outcome(state, event, debit, credit)
