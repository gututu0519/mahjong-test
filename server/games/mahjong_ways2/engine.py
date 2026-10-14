"""Pure Mahjong Ways 2 rules. Boards and refills are generated, never replayed.

Paytable/visible cells/cascades are based on the repository's rule audit.
Weights, golden frequency and 5-scatter awards are explicitly local choices.
All settlement amounts are integer hundredths of a virtual credit.
"""
import copy
import hashlib
import json
import math
import random
from decimal import Decimal, InvalidOperation
from pathlib import Path

from server.core.contracts import Outcome, ServiceError

PAYTABLE = {
    2: {3: 10, 4: 25, 5: 50}, 3: {3: 8, 4: 20, 5: 40},
    4: {3: 6, 4: 15, 5: 30}, 5: {3: 5, 4: 10, 5: 15},
    6: {3: 3, 4: 5, 5: 12}, 7: {3: 3, 4: 5, 5: 12},
    8: {3: 2, 4: 4, 5: 10}, 9: {3: 1, 4: 3, 5: 6},
    10: {3: 1, 4: 3, 5: 6},
}
VISIBLE = [list(range(1, 5)), list(range(8, 13)), list(range(15, 20)),
           list(range(22, 27)), list(range(29, 33))]


def evaluate(board, coin_minor, level, multiplier):
    if len(board) != 35 or any(type(x) is not int or not 0 <= x <= 10 for x in board):
        raise ValueError('Expected 35 symbol IDs in 0..10')
    positions, ways, rates, awards = {}, {}, {}, {}
    for symbol, table in PAYTABLE.items():
        hits = []
        for column in VISIBLE:
            matches = [p for p in column if board[p] in (0, symbol)]
            if not matches:
                break
            hits.append(matches)
        if len(hits) >= 3:
            key = str(symbol)
            positions[key] = [p for group in hits for p in group]
            ways[key] = math.prod(map(len, hits))
            rates[key] = table[len(hits)]
            awards[key] = coin_minor * level * ways[key] * rates[key]
    return {'winning_positions': positions, 'ways': ways, 'rates': rates,
            'base_awards_minor': awards, 'win_minor': sum(awards.values()) * multiplier}


class MahjongWays2:
    game_id = 'mahjong-ways2'
    title = '麻将胡了2'
    version = '1.0.0'

    def __init__(self, config_path=None):
        path = config_path or Path(__file__).with_name('config.json')
        self.config = json.loads(Path(path).read_text(encoding='utf-8'))
        c = self.config
        if (set(c['symbol_weights']) != set(map(str, range(1, 11)))
                or any(type(v) is not int or v <= 0 for v in c['symbol_weights'].values())
                or not 0 <= c['gold_probability'] <= 1):
            raise ValueError('Invalid generation weights')
        if (c['coin_sizes_minor'] != [1, 6, 30] or c['bet_levels'] != list(range(1, 11))
                or c['base_bet_factor'] != 20
                or c['normal_multipliers'] != [1, 2, 3, 5]
                or c['free_multipliers'] != [2, 4, 6, 10]
                or c['free_trigger'] != 3 or c['free_base_spins'] != 10
                or c['free_extra_per_scatter'] != 2
                or c['win_thresholds'] != {'mw': 3, 'bw': 5, 'mgw': 15, 'smgw': 35}):
            raise ValueError('This engine version only supports the documented rule constants')
        digest = hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()[:16]
        self.ruleset_id = f'{self.version}:{digest}'

    def normalize_bet(self, payload):
        if not isinstance(payload, dict):
            raise ServiceError('BET_INVALID', 'Bet must be an object.')
        if set(payload) - {'coin_minor', 'level', 'cs', 'ml'}:
            raise ServiceError('BET_INVALID', 'Unsupported bet fields.')
        try:
            coin = payload.get('coin_minor')
            if coin is None:
                value = Decimal(str(payload.get('cs', '0.01'))) * 100
                if not value.is_finite() or value != value.to_integral_value():
                    raise ValueError()
                coin = int(value)
            level = payload.get('level', payload.get('ml', 5))
            if (type(coin) is not int or type(level) is not int
                    or coin not in self.config['coin_sizes_minor']
                    or level not in self.config['bet_levels']):
                raise ValueError()
        except (ValueError, TypeError, InvalidOperation, OverflowError):
            raise ServiceError('BET_INVALID', 'Unsupported coin size or bet level.') from None
        return {'coin_minor': coin, 'level': level}

    def _draw_column(self, rng, count, has_scatter=False):
        symbols = list(range(1, 11))
        result = []
        for _ in range(count):
            weights = [0 if s == 1 and has_scatter else self.config['symbol_weights'][str(s)]
                       for s in symbols]
            symbol = rng.choices(symbols, weights=weights, k=1)[0]
            has_scatter |= symbol == 1
            result.append(symbol)
        return result

    def _gold(self, rng, board, candidates, gold, serial):
        added = [[] for _ in range(5)]
        for pos in candidates:
            col = pos // 7
            if (col in (1, 2, 3) and board[pos] >= 2
                    and rng.random() < self.config['gold_probability']):
                serial += 1
                gold[str(serial)] = pos
                added[col].append(pos % 7)
        return gold, serial, added

    def _new_board(self, rng):
        return [s for _ in range(5) for s in self._draw_column(rng, 7)]

    def initial_state(self, seed):
        rng = random.Random(seed)
        board = self._new_board(rng)
        return {'phase': 'ready', 'sid': '0', 'round_id': '0', 'step': 0,
                'ruleset_id': self.ruleset_id, 'board': board, 'gold': {},
                'removed': [], 'gold_serial': 0, 'bet': {'coin_minor': 1, 'level': 5},
                'free': None, 'multiplier_index': 0, 'combo': 0,
                'round_award_minor': 0, 'spin_award_minor': 0, 'counts': {}, 'last_event': None}

    def public_state(self, state):
        return {k: copy.deepcopy(v) for k, v in state.items() if k not in ('seed', 'gold_serial')}

    def step(self, state, bet, seed, sid):
        state = copy.deepcopy(state)
        phase = state['phase']
        start = phase == 'ready'
        if not start and state['ruleset_id'] != self.ruleset_id:
            raise ServiceError('RULESET_CHANGED', 'Finish this round with its original ruleset.', 409)
        if not start and bet != state['bet']:
            raise ServiceError('BET_LOCKED', 'Finish the round before changing the bet.', 409)
        if start:
            state.update(seed=seed, step=0, ruleset_id=self.ruleset_id, round_id=sid,
                         bet=bet, round_award_minor=0, spin_award_minor=0, free=None,
                         counts={}, gold_serial=0)
        rng = random.Random(f"{state['seed']}:{state['step']}:{self.ruleset_id}")
        cascade = phase in ('paid_cascade', 'free_cascade')
        free_mode = phase in ('free_start', 'free_cascade')
        gold_moves, refills, new_gold = {}, None, None
        if cascade:
            board, gold, candidates, refills = [], {}, [], []
            removed = set(state['removed'])
            for col in range(5):
                survivors = [v for p, v in enumerate(state['board']) if p // 7 == col and p not in removed]
                incoming = self._draw_column(rng, 7 - len(survivors), 1 in survivors)
                refills.append(incoming)
                candidates.extend(range(col * 7, col * 7 + len(incoming)))
                board.extend(incoming + survivors)
            for key, old in state['gold'].items():
                new = old + sum(p > old and p // 7 == old // 7 for p in removed)
                gold[key] = new
                if old != new:
                    gold_moves[key] = [old, new]
            gold, serial, new_gold = self._gold(rng, board, candidates, gold, state['gold_serial'])
        else:
            board = self._new_board(rng)
            gold, serial, _ = self._gold(rng, board, range(35), {}, state['gold_serial'])
        index = min(state['multiplier_index'] + 1, 3) if cascade else 0
        multiplier = self.config['free_multipliers' if free_mode else 'normal_multipliers'][index]
        result = evaluate(board, bet['coin_minor'], bet['level'], multiplier)
        win = result['win_minor']
        won_positions = {p for group in result['winning_positions'].values() for p in group}
        converted = won_positions & set(gold.values())
        removed = sorted(won_positions - converted)
        after = [0 if p in converted else s for p, s in enumerate(board)]
        remaining_gold = {k: p for k, p in gold.items() if p not in converted}
        scatter = sum(board[p] == 1 for column in VISIBLE for p in column)
        free = copy.deepcopy(state['free'])
        if free_mode:
            free['remaining'] -= int(phase == 'free_start')
            free['award_minor'] += win
            free['added'] = 0
        # Grant/retrigger only after the current cascade ends. Higher scatter
        # awards follow the documented local extension, not a claimed original RNG.
        if not win and scatter >= self.config['free_trigger']:
            added = self.config['free_base_spins'] + (scatter - 3) * self.config['free_extra_per_scatter']
            if free is None:
                free = {'remaining': 0, 'total': 0, 'award_minor': 0, 'added': 0}
            free['remaining'] += added
            free['total'] += added
            free['added'] = added
        next_phase = (('free_cascade' if free_mode else 'paid_cascade') if win else
                      'free_start' if free and free['remaining'] else 'ready')
        total_bet = bet['coin_minor'] * bet['level'] * self.config['base_bet_factor']
        debit = total_bet if start else 0
        round_award = state['round_award_minor'] + win
        spin_award = (state['spin_award_minor'] if cascade else 0) + win
        combo = (state['combo'] if cascade else 0) + 1 if win else 0
        counts = state['counts']
        if not start:
            counts[phase] = counts.get(phase, 0) + 1
        event = dict(result, sid=sid, round_id=state['round_id'], phase=phase,
                     next_phase=next_phase, bet=bet, base_bet_minor=total_bet,
                     debit_minor=debit, board_before=board, board_after=after,
                     gold_before=gold, gold_after=remaining_gold, removed=removed,
                     refills=refills, new_gold=new_gold, gold_moves=gold_moves,
                     scatter_count=scatter, multiplier=multiplier, multiplier_index=index,
                     free=free, round_award_minor=round_award, spin_award_minor=spin_award,
                     combo=combo, counts=copy.deepcopy(counts), ruleset_id=self.ruleset_id)
        state.update(phase=next_phase, sid=sid, step=state['step'] + 1, board=after,
                     gold=remaining_gold, gold_serial=serial, removed=removed,
                     multiplier_index=index, combo=combo, free=free,
                     round_award_minor=round_award, spin_award_minor=spin_award, last_event=event)
        return Outcome(state, event, debit, win)
