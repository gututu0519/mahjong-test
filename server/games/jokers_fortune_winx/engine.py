"""Joker's Fortune WinX local math; frequencies are configurable, not original RTP."""
import copy
import hashlib
import json
import random
from pathlib import Path
from server.core.contracts import Outcome, ServiceError

LINES = ((1,1,1,1,1), (0,0,0,0,0), (2,2,2,2,2), (0,1,2,1,0), (2,1,0,1,2))
LINE_ROWS = (1,0,2,0,2)


def evaluate(columns, bet, multipliers, extra, paytable):
    awards, base, lines = [], 0, 0
    for index, rows in enumerate(LINES):
        symbol = columns[0][rows[0]]
        if symbol == 7:
            continue
        count = 0
        for col, row in enumerate(rows):
            if columns[col][row] != symbol:
                break
            count += 1
        win = bet * paytable[symbol][count]
        if not win:
            continue
        base += win
        if extra or index == 0:
            win *= multipliers[LINE_ROWS[index]]
        lines += win
        awards.append(dict(Atype=1, Index=index, Symbol=symbol, Count=count, Win=win/10000, Pos=[]))
    positions = [col*3+row for col in range(5) for row in range(3) if columns[col][row] == 7]
    scatter = bet * {3:10,4:50,5:250}.get(len(positions), 0)
    if scatter:
        awards.append(dict(Atype=2, Symbol=7, Count=len(positions), Win=scatter/10000, Pos=positions))
    return awards, base + scatter, lines, scatter


class JokersFortuneWinX:
    game_id, title, version, minor_unit = 'jokers-fortune-winx', "Joker's Fortune WinX", '1.0.0', 10000

    def __init__(self, config_path=None):
        self.config = json.loads(Path(config_path or Path(__file__).with_name('config.json')).read_text())
        c = self.config
        if len(c['symbol_weights']) != 8 or len(c['multiplier_weights']) != 6 or any(type(v) is not int or v <= 0 for v in c['symbol_weights']+c['multiplier_weights']):
            raise ValueError('Invalid Joker weights')
        if len(c['paytable']) != 7 or any(len(row) != 6 or any(type(v) is not int or v < 0 for v in row) for row in c['paytable']):
            raise ValueError('Invalid Joker paytable')
        if not c['bets_minor'] or any(type(v) is not int or v <= 0 for v in c['bets_minor']) or len(set(c['bets_minor'])) != len(c['bets_minor']):
            raise ValueError('Invalid Joker play amounts')
        if not 0 <= c['stack_chance'] <= 1 or type(c['max_win_multiple']) is not int or c['max_win_multiple'] <= 0:
            raise ValueError('Invalid Joker generation limits')
        self.ruleset_id = self.version + ':' + hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()[:16]

    def initial_state(self, seed):
        return dict(sid='0', round_id='0', phase='ready', ruleset_id=self.ruleset_id, last_event=None, last_bet_minor=1000, extra=False)

    def public_state(self, state):
        return copy.deepcopy(state)

    def normalize_bet(self, payload):
        if not isinstance(payload, dict) or set(payload)-{'bet_minor','extra'}:
            raise ServiceError('BET_INVALID', 'Unsupported play fields.')
        bet, extra = payload.get('bet_minor',1000), payload.get('extra',False)
        if type(bet) is not int or bet not in self.config['bets_minor'] or type(extra) is not bool:
            raise ServiceError('BET_INVALID', 'Invalid play amount.')
        return dict(bet_minor=bet, extra=extra)

    def step(self, state, bet, seed, sid):
        rng, c = random.Random(seed), self.config
        amount, extra = bet['bet_minor'], bet['extra']
        for attempt in range(100):
            columns = []
            for _ in range(5):
                col = rng.choices(range(8), c['symbol_weights'], k=3)
                # At most one scatter on each physical reel.
                found = False
                for row in range(3):
                    if col[row] == 7:
                        if found:
                            col[row] = rng.choices(range(7), c['symbol_weights'][:7])[0]
                        found = True
                if 7 not in col and rng.random() < c['stack_chance']:
                    col = [col[0]] * 3
                columns.append(col)
            multipliers = rng.choices([1,2,3,4,5,10], c['multiplier_weights'], k=3)
            awards, base, lines, scatter = evaluate(columns, amount, multipliers, extra, c['paytable'])
            total = lines + scatter
            if total <= amount*c['max_win_multiple']:
                break
        else:
            raise ServiceError('GENERATION_LIMIT', 'Configured maximum exceeded.', 503)
        round_info = dict(Symbol=[dict(Col=col) for col in columns], AwardDataVec=awards, MulVec=multipliers,
                          LineWin=lines/10000, ScatterWin=scatter/10000, BaseWin=base/10000,
                          RoundWin=total/10000, AwardTypeFlag=(1 if lines else 0)|(2 if scatter else 0))
        spin = dict(RoundQueue=[round_info], TotalBaseWin=base/10000, TotalWin=total/10000, Extra=int(extra))
        event = dict(round_id=sid, bet_minor=amount, extra=extra, spin=spin, total_minor=total)
        new_state = dict(sid=sid, round_id=sid, phase='ready', ruleset_id=self.ruleset_id,
                         last_event=event, last_bet_minor=amount, extra=extra)
        return Outcome(new_state, event, amount*(2 if extra else 1), total)
