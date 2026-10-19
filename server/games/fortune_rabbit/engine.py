"""Fortune Rabbit rules, generated outcomes, and integer wallet settlement.

Paylines/paytable/prize rules are audited against the original client/capture.
Weights and feature frequency are local configuration, not the original math.
Feature timing and blank cells are audited against the complete original round.
"""
import copy
import hashlib
import json
import random
from pathlib import Path

from server.core.contracts import Outcome, ServiceError
from server.games.mahjong_ways2.engine import MahjongWays2

PAYTABLE = {0: 200, 2: 100, 3: 50, 4: 10, 5: 5, 6: 3, 7: 2}
LINES = [(0, 4, 8), (0, 5, 8), (0, 5, 9), (1, 5, 8), (1, 5, 9),
         (1, 6, 9), (1, 6, 10), (2, 6, 9), (2, 6, 10), (2, 7, 10)]
VISIBLE = (0, 1, 2, 4, 5, 6, 7, 8, 9, 10)


def evaluate(board, coin_minor, level, prizes=None):
    if (len(board) != 12 or board[3] != 99 or board[11] != 99
            or any(type(board[p]) is not int or board[p] not in range(9) for p in VISIBLE)):
        raise ValueError('Expected a padded 3/4/3 Fortune Rabbit board')
    positions, rates, awards = {}, {}, {}
    for i, line in enumerate(LINES, 1):
        symbols = [board[p] for p in line]
        candidates = [s for s in PAYTABLE if all(v in (0, s) for v in symbols)]
        if candidates:
            symbol = max(candidates, key=PAYTABLE.get)
            key = str(i)
            positions[key], rates[key] = list(line), PAYTABLE[symbol]
            awards[key] = coin_minor * level * rates[key]
    cash_positions = {p for p in VISIBLE if board[p] == 8}
    cash = 0
    if prizes is not None:
        recorded = {item.get('p', 0) for item in prizes.values()}
        if recorded != cash_positions or len(prizes) != len(cash_positions):
            raise ValueError('Every prize symbol needs exactly one prize value')
        if len(cash_positions) >= 5:
            cash = sum(round(item['bv'] * 100) for item in prizes.values())
    return dict(winning_positions=positions, rates=rates, line_awards_minor=awards,
                line_win_minor=sum(awards.values()), cash_win_minor=cash,
                win_minor=sum(awards.values()) + cash)


class FortuneRabbit(MahjongWays2):
    game_id = 'fortune-rabbit'
    title = 'Fortune Rabbit'
    version = '1.0.1'

    def __init__(self, config_path=None):
        self.config = json.loads(Path(config_path or Path(__file__).with_name('config.json')).read_text(encoding='utf-8'))
        c = self.config
        if (c['coin_sizes_minor'] != [3, 10, 30, 90] or c['bet_levels'] != list(range(1, 11))
                or c['base_bet_factor'] != 10 or c['free_spins'] != 8 or c['max_win_multiplier'] != 5000
                or set(c['symbol_weights']) != set(map(str, PAYTABLE.keys() | {8}))
                or any(type(v) is not int or v <= 0 for v in c['symbol_weights'].values())
                or c['prize_multipliers'] != [.5, 1, 2, 5, 10, 20, 30, 50, 100, 500]
                or len(c['prize_weights']) != 10
                or any(type(v) is not int or v <= 0 for v in c['prize_weights'])
                or not 0 <= c['feature_probability'] <= 1
                or not 0 <= c['feature_prize_probability'] <= 1
                or not 0 <= c['feature_teaser_probability'] <= 1
                or c['win_thresholds'] != {'mw': 3, 'bw': 5, 'mgw': 15, 'smgw': 35}):
            raise ValueError('Invalid Fortune Rabbit configuration')
        self.ruleset_id = self.version + ':' + hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()[:16]

    def normalize_bet(self, payload):
        if isinstance(payload, dict) and not {'cs', 'coin_minor'} & payload.keys():
            payload = {**payload, 'coin_minor': 30}
        return super().normalize_bet(payload)

    def _new_board(self, rng, feature=False):
        symbols = list(map(int, self.config['symbol_weights']))
        board = rng.choices(symbols, weights=list(self.config['symbol_weights'].values()), k=12)
        if feature:
            board = [8 if rng.random() < self.config['feature_prize_probability'] else 1 for _ in range(12)]
        board[3] = board[11] = 99
        return board

    def _trigger_feature(self, rng):
        return rng.random() < self.config['feature_probability']

    def _prizes(self, rng, board, total_bet):
        values = rng.choices(self.config['prize_multipliers'], weights=self.config['prize_weights'], k=10)
        return {str(i): dict(p=p, bv=total_bet * value / 100, m=value)
                for i, (p, value) in enumerate(zip((p for p in VISIBLE if board[p] == 8), values), 1)}

    def initial_state(self, seed):
        return dict(phase='ready', sid='0', round_id='0', ruleset_id=self.ruleset_id,
                    step=0, board=self._new_board(random.Random(seed)), bet=dict(coin_minor=30, level=2),
                    free=None, round_award_minor=0, combo=0, paid_combo=0, last_event=None)

    def step(self, state, bet, seed, sid):
        state = copy.deepcopy(state)
        start = state['phase'] == 'ready'
        if not start and state['ruleset_id'] != self.ruleset_id:
            raise ServiceError('RULESET_CHANGED', 'Finish the current round first.', 409)
        if not start and state['bet'] != bet:
            raise ServiceError('BET_LOCKED', 'Finish the current round before changing bet.', 409)
        if start:
            state.update(seed=seed, step=0, round_id=sid, bet=bet, free=None,
                         round_award_minor=0, ruleset_id=self.ruleset_id)
        rng = random.Random(f"{state['seed']}:{state['step']}:{self.ruleset_id}")
        trigger = start and self._trigger_feature(rng)
        feature = not start or trigger
        teaser = start and not trigger and rng.random() < self.config['feature_teaser_probability']
        total_bet = bet['coin_minor'] * bet['level'] * 10
        board = self._new_board(rng, feature)
        prizes = self._prizes(rng, board, total_bet)
        result = evaluate(board, bet['coin_minor'], bet['level'], prizes)
        available = total_bet * self.config['max_win_multiplier'] - state['round_award_minor']
        win = min(result['win_minor'], max(0, available))
        max_win = win >= available
        free = copy.deepcopy(state['free'])
        if trigger:
            free = dict(remaining=7, total=8, award_minor=win)
        elif feature:
            free['remaining'] -= 1
            free['award_minor'] += win
        if max_win and free:
            free['remaining'] = 0
        next_phase = 'free' if free and free['remaining'] else 'ready'
        round_award = state['round_award_minor'] + win
        combo = (state.get('paid_combo', 0) if start else state.get('combo', 0)) + 1 if win else 0
        paid_combo = combo if start else 0
        event = dict(result, sid=sid, round_id=state['round_id'], phase=state['phase'], next_phase=next_phase,
                     bet=bet, board=board, prizes=prizes, debit_minor=total_bet if start else 0,
                     base_bet_minor=total_bet, win_minor=win, round_award_minor=round_award,
                     free=free, feature=feature, feature_trigger=trigger, feature_teaser=teaser,
                     step=state['step'], combo=combo, paid_combo=paid_combo, max_win=max_win,
                     ruleset_id=self.ruleset_id)
        state.update(sid=sid, phase=next_phase, board=board, free=free,
                     round_award_minor=round_award, step=state['step'] + 1,
                     combo=combo, paid_combo=paid_combo, last_event=event)
        return Outcome(state, event, event['debit_minor'], win)
