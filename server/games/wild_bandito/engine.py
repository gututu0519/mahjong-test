"""Wild Bandito: published rules and generated boards, never recorded outcomes."""
import copy
import hashlib
import json
import math
import random
from pathlib import Path

from server.core.contracts import Outcome, ServiceError
from server.games.mahjong_ways2.engine import MahjongWays2

PAYTABLE = {
    2: {3: 10, 4: 25, 5: 50}, 3: {3: 8, 4: 20, 5: 40},
    4: {3: 6, 4: 15, 5: 30}, 5: {3: 5, 4: 10, 5: 15},
    6: {3: 3, 4: 5, 5: 12}, 7: {3: 3, 4: 5, 5: 12},
    8: {3: 2, 4: 4, 5: 10}, 9: {3: 1, 4: 3, 5: 6}, 10: {3: 1, 4: 3, 5: 6},
}
VISIBLE = [list(range(c * 5 + 1, c * 5 + 5)) for c in range(5)]


def evaluate(board, coin_minor, level, multiplier):
    if len(board) != 25 or any(type(v) is not int or not 0 <= v <= 10 for v in board):
        raise ValueError('Expected 25 symbols')
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
            positions[key] = [p for cells in hits for p in cells]
            ways[key] = math.prod(map(len, hits))
            rates[key] = table[len(hits)]
            awards[key] = coin_minor * level * ways[key] * rates[key]
    return dict(winning_positions=positions, ways=ways, rates=rates,
                base_awards_minor=awards, win_minor=sum(awards.values()) * multiplier)


class WildBandito(MahjongWays2):
    game_id = 'wild-bandito'
    title = 'Wild Bandito'
    version = '1.0.0'

    def __init__(self, config_path=None):
        self.config = json.loads(Path(config_path or Path(__file__).with_name('config.json')).read_text(encoding='utf-8'))
        c = self.config
        if (c['coin_sizes_minor'] != [3, 10, 30, 90] or c['bet_levels'] != list(range(1, 11))
                or c['base_bet_factor'] != 20 or c['free_trigger'] != 3 or c['free_base_spins'] != 12
                or c['free_extra_per_scatter'] != 2 or not 0 <= c['gold_probability'] <= 1
                or set(c['symbol_weights']) != set(map(str, range(1, 11)))
                or any(type(w) is not int or w <= 0 for w in c['symbol_weights'].values())):
            raise ValueError('Invalid Wild Bandito rules')
        self.ruleset_id = self.version + ':' + hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()[:16]

    def normalize_bet(self, payload):
        payload = dict(payload) if isinstance(payload, dict) else payload
        if isinstance(payload, dict) and not {'cs', 'coin_minor'} & payload.keys():
            payload['coin_minor'] = 10
        return super().normalize_bet(payload)

    def _new_board(self, rng):
        return [s for _ in range(5) for s in self._draw_column(rng, 5)]

    def _gold(self, rng, board, candidates, gold, serial, free_mode=False):
        added = [[] for _ in range(5)]
        for pos in candidates:
            col = pos // 5
            if (col in (1, 2, 3) and board[pos] >= 2
                    and (free_mode and col == 2 or rng.random() < self.config['gold_probability'])):
                serial += 1
                gold[str(serial)] = pos
                added[col].append(pos % 5)
        return gold, serial, added

    def initial_state(self, seed):
        return dict(phase='ready', sid='0', round_id='0', step=0, ruleset_id=self.ruleset_id,
                    board=self._new_board(random.Random(seed)), gold={}, removed=[], converted=[], gold_serial=0,
                    bet={'coin_minor': 10, 'level': 2}, free=None, multiplier=1, combo=0,
                    round_award_minor=0, spin_award_minor=0, counts={}, last_event=None)

    def step(self, state, bet, seed, sid):
        state = copy.deepcopy(state)
        phase = state['phase']
        start = phase == 'ready'
        if not start and state['ruleset_id'] != self.ruleset_id:
            raise ServiceError('RULESET_CHANGED', 'Finish the current round first.', 409)
        if not start and bet != state['bet']:
            raise ServiceError('BET_LOCKED', 'Finish the current round before changing bet.', 409)
        if start:
            state.update(seed=seed, step=0, ruleset_id=self.ruleset_id, round_id=sid, bet=bet,
                         round_award_minor=0, spin_award_minor=0, free=None, counts={})
        rng = random.Random(f"{state['seed']}:{state['step']}:{self.ruleset_id}")
        cascade = phase in ('paid_cascade', 'free_cascade')
        free_mode = phase in ('free_start', 'free_cascade')
        refills, new_gold, broken = None, None, []
        if cascade:
            board, gold, candidates, refills = [], {}, [], []
            removed = set(state['removed'])
            for col in range(5):
                survivors = [v for p, v in enumerate(state['board']) if p // 5 == col and p not in removed]
                incoming = self._draw_column(rng, 5 - len(survivors), 1 in survivors)
                refills.append(incoming)
                candidates.extend(range(col * 5, col * 5 + len(incoming)))
                board.extend(incoming + survivors)
            for key, old in state['gold'].items():
                gold[key] = old + sum(p > old and p // 5 == old // 5 for p in removed)
            broken = state['converted']
            gold, serial, new_gold = self._gold(rng, board, candidates, gold, state['gold_serial'], free_mode)
        else:
            board = self._new_board(rng)
            gold, serial, _ = self._gold(rng, board, range(25), {}, 0, free_mode)
        multiplier = (state['multiplier'] + 1 if cascade else
                      state['free']['multiplier'] if free_mode else 1)
        result = evaluate(board, bet['coin_minor'], bet['level'], multiplier)
        win = result['win_minor']
        won = {p for group in result['winning_positions'].values() for p in group}
        converted = [int(k) for k, p in gold.items() if p in won]
        transformed = {gold[str(k)] for k in converted}
        removed = sorted(won - transformed)
        after = [0 if p in transformed else symbol for p, symbol in enumerate(board)]
        remaining_gold = {k: p for k, p in gold.items() if p not in transformed}
        scatter = sum(board[p] == 1 for column in VISIBLE for p in column)
        free = copy.deepcopy(state['free'])
        if free_mode:
            free['remaining'] -= int(phase == 'free_start')
            free['award_minor'] += win
            free['added'] = 0
            free['multiplier'] = multiplier + int(win > 0)
        if not win and scatter >= 3:
            added = 12 + (scatter - 3) * 2
            if free is None:
                free = dict(remaining=0, total=0, award_minor=0, added=0, multiplier=1)
            free['remaining'] += added
            free['total'] += added
            free['added'] = added
        next_phase = (('free_cascade' if free_mode else 'paid_cascade') if win else
                      'free_start' if free and free['remaining'] else 'ready')
        total_bet = bet['coin_minor'] * bet['level'] * 20
        debit = total_bet if start else 0
        round_award = state['round_award_minor'] + win
        spin_award = (state['spin_award_minor'] if cascade else 0) + win
        combo = (state['combo'] if cascade else 0) + 1 if win else 0
        counts = state['counts']
        if not start:
            counts[phase] = counts.get(phase, 0) + 1
        event = dict(result, sid=sid, round_id=state['round_id'], phase=phase, next_phase=next_phase,
                     bet=bet, base_bet_minor=total_bet, debit_minor=debit, board_before=board, board_after=after,
                     gold_before=gold, gold_after=remaining_gold, removed=removed, refills=refills,
                     new_gold=new_gold, broken_gold=broken, scatter_count=scatter, multiplier=multiplier,
                     free=free, round_award_minor=round_award, spin_award_minor=spin_award,
                     combo=combo, counts=copy.deepcopy(counts), ruleset_id=self.ruleset_id)
        state.update(phase=next_phase, sid=sid, step=state['step'] + 1, board=after, gold=remaining_gold,
                     gold_serial=serial, removed=removed, converted=converted, multiplier=multiplier,
                     combo=combo, free=free, round_award_minor=round_award, spin_award_minor=spin_award,
                     last_event=event)
        return Outcome(state, event, debit, win)
