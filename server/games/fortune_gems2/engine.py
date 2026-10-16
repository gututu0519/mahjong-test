"""Fortune Gems 2 local generated rounds. Weights are not the original math model."""
import copy
import hashlib
import json
import random
from pathlib import Path
from server.core.contracts import Outcome, ServiceError

LINES = ((1, 1, 1), (0, 0, 0), (2, 2, 2), (0, 1, 2), (2, 1, 0))
MULTIPLIERS = (1, 2, 3, 5, 10, 15)


def evaluate(columns, bet, multiplier, paytable):
    awards = []
    for line, rows in enumerate(LINES):
        symbols = [columns[c][r] for c, r in enumerate(rows)]
        regular = set(symbols) - {7}
        if len(regular) > 1:
            continue
        symbol = next(iter(regular), 7)
        amount = bet * paytable[symbol] * multiplier // 5
        awards.append(dict(Symbol=symbol, Line=line, Win=amount / 10000))
    return awards


class FortuneGems2:
    game_id, title, version, minor_unit = 'fortune-gems2', 'Fortune Gems 2', '1.0.1', 10000

    def __init__(self, config_path=None):
        self.config = json.loads(Path(config_path or Path(__file__).with_name('config.json')).read_text(encoding='utf-8'))
        c = self.config
        for key, size in [('symbol_weights', 8), ('paytable_fifths', 8), ('multiplier_weights', 6), ('wheel_multiplier_weights', 6), ('wheel_weights', 12)]:
            if len(c[key]) != size or any(type(x) is not int or x <= 0 for x in c[key]):
                raise ValueError('Invalid Fortune Gems 2 configuration: ' + key)
        if any(not 0 <= c[k] <= 1 for k in ['stack_chance', 'wheel_chance', 'extra_wheel_chance']):
            raise ValueError('Invalid Fortune Gems 2 probabilities')
        self.ruleset_id = self.version + ':' + hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()[:16]

    def initial_state(self, seed):
        return dict(sid='0', round_id='0', phase='ready', ruleset_id=self.ruleset_id,
                    last_event=None, last_bet_minor=2000, extra=False)

    def public_state(self, state):
        return copy.deepcopy(state)

    def normalize_bet(self, payload):
        if not isinstance(payload, dict) or set(payload) - {'bet_minor', 'extra'}:
            raise ServiceError('BET_INVALID', 'Unsupported Fortune Gems 2 bet fields.')
        amount, extra = payload.get('bet_minor', 2000), payload.get('extra', False)
        if type(amount) is not int or amount not in self.config['bets_minor'] or type(extra) is not bool:
            raise ServiceError('BET_INVALID', 'Invalid Fortune Gems 2 bet.')
        return dict(bet_minor=amount, extra=extra)

    def step(self, state, bet, seed, sid):
        rng, c = random.Random(seed), self.config
        amount, extra = bet['bet_minor'], bet['extra']
        columns = []
        for _ in range(3):
            col = rng.choices(range(8), c['symbol_weights'], k=3)
            if rng.random() < c['stack_chance']:
                col = [col[0]] * 3
            columns.append(col)
        wheel = rng.random() < c['extra_wheel_chance' if extra else 'wheel_chance']
        index = rng.choices(range(1 if extra else 0, 6), c['multiplier_weights'][1 if extra else 0:])[0]
        multiplier = 1 if wheel else MULTIPLIERS[index]
        special = 15 if extra and wheel else 14 if wheel else 8 + index
        columns.append([rng.randrange(9 if extra else 8, 14), special, rng.randrange(9 if extra else 8, 14)])
        awards = evaluate(columns, amount, multiplier, c['paytable_fifths'])
        line_minor = sum(round(a['Win'] * 10000) for a in awards)
        wheel_odd = rng.choices(c['wheel_odds'], c['wheel_weights'])[0] if wheel else 0
        # The client indexes all twelve sectors when showing Extra Bet upgrades.
        # These weights are local configuration, not inferred original frequencies.
        mult_show = rng.choices(MULTIPLIERS, c['wheel_multiplier_weights'], k=12) if wheel and extra else [1] * 12
        wheel_mult = mult_show[c['wheel_odds'].index(wheel_odd)] if wheel else 1
        wheel_minor = amount * wheel_odd * wheel_mult
        total = line_minor + wheel_minor
        # All-wild lines (25x) + maximum wheel (15000x) define the natural ceiling.
        if total > amount * c['max_win_multiple']:
            raise ServiceError('GENERATION_LIMIT', 'Configured maximum win exceeded.', 503)
        spin = dict(PlateSymbol=[{'Col': col} for col in columns], AwardDataVec=awards,
                    AwardTypeFlag=(1 if awards else 0) | (2 if wheel else 0), LineMult=multiplier,
                    LineWin=line_minor / 10000, WheelOdd=wheel_odd, WheelMult=wheel_mult,
                    WheelWin=wheel_minor / 10000, TotalWin=total / 10000, Bet=amount / 10000,
                    Extra=extra, IsBonus=wheel, MultShowArray=mult_show, LightOnPos=[])
        event = dict(round_id=sid, bet_minor=amount, extra=extra, spin=spin, total_minor=total)
        new_state = dict(sid=sid, round_id=sid, phase='ready', ruleset_id=self.ruleset_id,
                         last_event=event, last_bet_minor=amount, extra=extra)
        return Outcome(new_state, event, amount * 3 // 2 if extra else amount, total)
