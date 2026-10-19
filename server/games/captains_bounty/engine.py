"""Captain's Bounty rules and generated cascades, independent of capture files.

Paylines, paytable, multipliers and free awards come from the original client.
Symbol weights and the generation policy are local choices, not original RTP.
"""
import copy
import hashlib
import json
import random
from pathlib import Path

from server.core.contracts import Outcome, ServiceError
from server.games.mahjong_ways2.engine import MahjongWays2

PAYTABLE = {2: {3: 50, 4: 250, 5: 2500}, 3: {3: 20, 4: 100, 5: 1000},
            4: {3: 15, 4: 50, 5: 500}, 5: {3: 10, 4: 25, 5: 200},
            6: {3: 5, 4: 20, 5: 100}, 7: {3: 4, 4: 15, 5: 75},
            8: {3: 3, 4: 10, 5: 50}}
LINES = [(1, 4, 7, 10, 13), (0, 3, 6, 9, 12), (2, 5, 8, 11, 14),
         (0, 4, 8, 10, 12), (2, 4, 6, 10, 14), (0, 3, 7, 9, 12),
         (2, 5, 7, 11, 14), (1, 5, 8, 11, 13), (1, 3, 6, 9, 13),
         (0, 4, 7, 10, 12), (2, 4, 7, 10, 14), (1, 4, 6, 10, 13),
         (1, 4, 8, 10, 13), (1, 3, 7, 9, 13), (1, 5, 7, 11, 13),
         (0, 4, 6, 10, 12), (2, 4, 8, 10, 14), (0, 3, 7, 11, 14),
         (2, 5, 7, 9, 12), (0, 5, 6, 11, 12)]


def evaluate(board, coin_minor, level, multiplier):
    if len(board) != 15 or any(type(s) is not int or not 0 <= s <= 8 for s in board):
        raise ValueError('Expected 15 Captain\'s Bounty symbols')
    positions, rates, awards = {}, {}, {}
    for number, line in enumerate(LINES, 1):
        candidates = []
        for symbol, table in PAYTABLE.items():
            cells = []
            for p in line:
                if board[p] not in (0, symbol):
                    break
                cells.append(p)
            if len(cells) >= 3:
                candidates.append((table[len(cells)], cells))
        if candidates:
            rate, cells = max(candidates, key=lambda item: item[0])
            key = str(number)
            positions[key], rates[key] = cells, rate
            awards[key] = coin_minor * level * rate
    return dict(winning_positions=positions, rates=rates, base_awards_minor=awards,
                base_win_minor=sum(awards.values()), win_minor=sum(awards.values()) * multiplier)


class CaptainsBounty(MahjongWays2):
    game_id = 'captains-bounty'
    title = "Captain's Bounty"
    version = '1.0.0'

    def __init__(self, config_path=None):
        self.config = json.loads(Path(config_path or Path(__file__).with_name('config.json')).read_text(encoding='utf-8'))
        c = self.config
        if (c['coin_sizes_minor'] != [3, 10, 30, 90] or c['bet_levels'] != list(range(1, 11))
                or c['base_bet_factor'] != 20 or c['normal_multipliers'] != [1, 2, 3, 5]
                or c['free_multipliers'] != [3, 6, 9, 15] or c['free_trigger'] != 3
                or c['free_base_spins'] != 10 or c['free_extra_per_scatter'] != 5
                or c['max_win_multiplier'] != 30000
                or set(c['symbol_weights']) != set(map(str, range(9)))
                or any(type(w) is not int or w <= 0 for w in c['symbol_weights'].values())):
            raise ValueError('Invalid Captain\'s Bounty rules')
        self.ruleset_id = self.version + ':' + hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()[:16]

    def normalize_bet(self, payload):
        if isinstance(payload, dict) and not {'coin_minor', 'cs'} & payload.keys():
            payload = {**payload, 'coin_minor': 30}
        if isinstance(payload, dict) and not {'level', 'ml'} & payload.keys():
            payload = {**payload, 'level': 2}
        return super().normalize_bet(payload)

    def _draw_column(self, rng, count, column, has_scatter=False):
        result = []
        for _ in range(count):
            weights = [0 if s == 0 and column in (0, 4) or s == 1 and has_scatter
                       else self.config['symbol_weights'][str(s)] for s in range(9)]
            symbol = rng.choices(range(9), weights=weights, k=1)[0]
            result.append(symbol)
            has_scatter |= symbol == 1
        return result

    def _new_board(self, rng):
        return [s for column in range(5) for s in self._draw_column(rng, 3, column)]

    def initial_state(self, seed):
        return dict(phase='ready', sid='0', round_id='0', ruleset_id=self.ruleset_id, step=0,
                    board=self._new_board(random.Random(seed)), removed=[], bet=dict(coin_minor=30, level=2),
                    free=None, multiplier_index=0, round_award_minor=0, spin_award_minor=0, last_event=None)

    def step(self, state, bet, seed, sid):
        state = copy.deepcopy(state)
        phase = state['phase']
        start = phase == 'ready'
        if not start and state['ruleset_id'] != self.ruleset_id:
            raise ServiceError('RULESET_CHANGED', 'Finish the current round first.', 409)
        if not start and state['bet'] != bet:
            raise ServiceError('BET_LOCKED', 'Finish the current round before changing bet.', 409)
        if start:
            state.update(seed=seed, step=0, round_id=sid, bet=bet, free=None,
                         round_award_minor=0, spin_award_minor=0, ruleset_id=self.ruleset_id)
        rng = random.Random(f"{state['seed']}:{state['step']}:{self.ruleset_id}")
        cascade = phase in ('paid_cascade', 'free_cascade')
        free_mode = phase in ('free_start', 'free_cascade')
        incoming = None
        if cascade:
            board, incoming = [], []
            for column in range(5):
                survivors = [state['board'][p] for p in range(column * 3, column * 3 + 3)
                             if p not in state['removed']]
                refill = self._draw_column(rng, 3 - len(survivors), column, 1 in survivors)
                incoming.append(refill)
                board.extend(refill + survivors)
        else:
            board = self._new_board(rng)
        index = min(state['multiplier_index'] + 1, 3) if cascade else 0
        multiplier = self.config['free_multipliers' if free_mode else 'normal_multipliers'][index]
        result = evaluate(board, bet['coin_minor'], bet['level'], multiplier)
        total_bet = bet['coin_minor'] * bet['level'] * 20
        available = total_bet * self.config['max_win_multiplier'] - state['round_award_minor']
        win = min(result['win_minor'], max(0, available))
        max_win = win >= available
        free = copy.deepcopy(state['free'])
        if free_mode:
            free['remaining'] -= int(phase == 'free_start')
            free['award_minor'] += win
            free['added'] = 0
        scatters = board.count(1)
        if not win and scatters >= 3:
            added = 10 + (scatters - 3) * 5
            retrigger = free is not None
            if free is None:
                free = dict(remaining=0, total=0, added=0, award_minor=0)
            free['remaining'] += added
            free['total'] += added
            free['added'] = added if retrigger else 0
        if max_win and free:
            free['remaining'] = 0
        next_phase = ('ready' if max_win else
                      ('free_cascade' if free_mode else 'paid_cascade') if win else
                      'free_start' if free and free['remaining'] else 'ready')
        removed = sorted({p for cells in result['winning_positions'].values() for p in cells})
        spin_award = (state['spin_award_minor'] if cascade else 0) + win
        round_award = state['round_award_minor'] + win
        event = dict(result, sid=sid, round_id=state['round_id'], phase=phase, next_phase=next_phase,
                     bet=bet, board=board, removed=removed, refills=incoming, multiplier=multiplier,
                     base_bet_minor=total_bet, debit_minor=total_bet if start else 0, win_minor=win,
                     spin_award_minor=spin_award, round_award_minor=round_award, free=free,
                     free_mode=free_mode, scatter_count=scatters, max_win=max_win, ruleset_id=self.ruleset_id)
        state.update(sid=sid, phase=next_phase, board=board, removed=removed, free=free,
                     multiplier_index=index, step=state['step'] + 1, round_award_minor=round_award,
                     spin_award_minor=spin_award, last_event=event)
        return Outcome(state, event, event['debit_minor'], win)
