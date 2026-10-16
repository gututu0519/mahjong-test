"""Money Pot DELUXE rules with configurable local symbol frequencies."""
import copy
import hashlib
import json
import random
from decimal import Decimal
from pathlib import Path
from server.core.contracts import Outcome, ServiceError


def money(amount, multiplier):
    return int(Decimal(amount) * Decimal(str(multiplier)))


def evaluate(symbols, multipliers, bet):
    """Six horizontal lines, sum values, and count a full row once."""
    awards, total = [], 0
    for row in range(3):
        for direction, columns in ((0, range(5)), (1, range(4, -1, -1))):
            positions = []
            for col in columns:
                if not symbols[col][row]:
                    break
                positions.append((col, row))
            count = len(positions)
            if count < 3 or direction and count == 5:
                continue
            values = [multipliers[col][r] for col, r in positions]
            multiplier = sum(Decimal(str(v)) for v in values)
            win = money(bet, multiplier)
            total += win
            awards.append(dict(Atype=2 if count == 5 else direction, Index=row, Count=count,
                Symbol=[symbols[col][r] for col, r in positions], Mul=values,
                AllMul=float(multiplier), Win=win / 10000))
    return awards, total


def columns(values):
    return [dict(Col=list(col)) for col in values]


class MoneyPotDeluxe:
    game_id, title, version, minor_unit = 'money-pot-deluxe', 'Money Pot DELUXE', '1.0.0', 10000

    def __init__(self, config_path=None):
        self.config = json.loads(Path(config_path or Path(__file__).with_name('config.json')).read_text(encoding='utf-8'))
        c = self.config
        if (len(c['symbol_weights']) != 8 or any(type(v) is not int or v < 0 for v in c['symbol_weights'])
                or not sum(c['symbol_weights']) or len(c['coin_weights']) != len(c['coin_multipliers'])
                or any(type(v) is not int or v <= 0 for v in c['coin_weights'])):
            raise ValueError('Invalid symbol configuration')
        if (not c['bets_minor'] or any(type(v) is not int or v <= 0 or v % 100 for v in c['bets_minor'])
                or len(set(c['bets_minor'])) != len(c['bets_minor'])):
            raise ValueError('Invalid bet levels')
        if c['extra_costs'] != [1, 1.5, 3, 6] or c['jackpots'] != [15, 25, 100, 5000] or c['max_win_multiple'] != 5000:
            raise ValueError('Invalid rule constants')
        if any(not 0 <= c[k] <= 1 for k in ('bonus_chance', 'bonus_add_chance', 'pot_chance')):
            raise ValueError('Invalid generation frequency')
        if any(not Decimal(str(v)).is_finite() or v <= 0 for v in c['coin_multipliers']):
            raise ValueError('Invalid coin multipliers')
        self.ruleset_id = self.version + ':' + hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()[:16]

    def initial_state(self, seed):
        return dict(sid='0', round_id='0', phase='ready', ruleset_id=self.ruleset_id,
                    last_event=None, last_bet_minor=30000, extra=0)

    def public_state(self, state):
        return copy.deepcopy(state)

    def normalize_bet(self, payload):
        if not isinstance(payload, dict) or set(payload) - {'bet_minor', 'extra'}:
            raise ServiceError('BET_INVALID', 'Unsupported play fields.')
        amount, extra = payload.get('bet_minor', 30000), payload.get('extra', 0)
        if type(amount) is not int or amount not in self.config['bets_minor'] or type(extra) is not int or extra not in range(4):
            raise ServiceError('BET_INVALID', 'Invalid play selection.')
        return dict(bet_minor=amount, extra=extra)

    def step(self, state, bet, seed, sid, _attempt=0):
        rng, c = random.Random(seed), self.config
        amount, extra = bet['bet_minor'], bet['extra']
        symbols = [[rng.choices(range(8), c['symbol_weights'])[0] for _ in range(3)] for _ in range(5)]
        # The center Caishen is the trigger; its local frequency is explicit.
        bonus = rng.random() < min(1, c['bonus_chance'] * (1, 2, 4, 8)[extra])
        if not bonus and symbols[2][1] in (5, 6, 7):
            symbols[2][1] = 0
        if bonus:
            symbols[2][1] = 6 if extra >= 2 else 5
        if extra >= 2:
            symbols = [[6 if value == 5 else value for value in col] for col in symbols]
        mul = [[self._value(rng, value) for value in col] for col in symbols]
        first = self._round(rng, symbols, mul, amount, extra, bonus=bonus)
        if bonus and rng.random() < 0.35:
            # Captured PotType=3 places the trigger in an empty center slot.
            first['Symbol'][2]['Col'][1] = 0
            first['Mul'][2]['Col'][1] = 0
            first['PotList'] = [dict(Pos=7, Symbol=symbols[2][1], Mul=2 if extra >= 2 else 1)]
            first['PotType'] = 3
        rounds = [first]
        if bonus:
            rounds.extend(self._bonus(rng, first, amount))
        total = sum(money(10000, r.get('RoundWin', 0)) for r in rounds)
        if total > amount * c['max_win_multiple']:
            if _attempt >= 99:
                raise ServiceError('GENERATION_LIMIT', 'Configured maximum exceeded.', 503)
            return self.step(state, bet, str(seed) + ':retry', sid, _attempt + 1)
        spin = dict(RoundQueue=rounds, GameType=extra, Extra=0, TotalWin=total / 10000)
        event = dict(round_id=sid, bet_minor=amount, extra=extra, spin=spin, total_minor=total)
        new_state = dict(sid=sid, round_id=sid, phase='ready', ruleset_id=self.ruleset_id,
                         last_event=event, last_bet_minor=amount, extra=extra)
        return Outcome(new_state, event, money(amount, c['extra_costs'][extra]), total)

    def _value(self, rng, symbol):
        if symbol == 1:
            return rng.choices(self.config['coin_multipliers'], self.config['coin_weights'])[0]
        if symbol == 2:
            return rng.choices(self.config['jackpots'][:3], [85, 13, 2])[0]
        return 0

    def _round(self, rng, symbols, mul, amount, extra, bonus=False):
        original, initial = copy.deepcopy(symbols), copy.deepcopy(mul)
        pot, mystery, collect = [], [], []
        if not bonus and rng.random() < self.config['pot_chance']:
            empty = [(col, row) for col in range(5) for row in range(3) if not symbols[col][row]]
            rng.shuffle(empty)
            for col, row in empty[:rng.randint(1, 4)]:
                symbols[col][row], mul[col][row] = 1, self._value(rng, 1)
                pot.append(dict(Pos=col * 3 + row, Symbol=1, Mul=mul[col][row]))
        coin_positions = [col * 3 + row for col in range(5) for row in range(3) if symbols[col][row] == 1]
        coin_sum = sum(Decimal(str(mul[p // 3][p % 3])) for p in coin_positions)
        for col in range(5):
            for row in range(3):
                if symbols[col][row] in (5, 6, 7):
                    factor = 2 if symbols[col][row] == 6 else 1
                    mul[col][row] = float(coin_sum * factor)
        if not bonus:
            for col in range(5):
                for row in range(3):
                    if symbols[col][row] in (3, 4):
                        is_jp = symbols[col][row] == 4
                        symbols[col][row] = 2 if is_jp or rng.random() < 0.05 else 1
                        mul[col][row] = self._value(rng, symbols[col][row])
                        mystery.append(dict(IsJP=is_jp, Pos=col * 3 + row, Symbol=symbols[col][row], Mul=mul[col][row]))
        awards, total = evaluate(symbols, mul, amount) if not bonus else ([], 0)
        winning = set()
        for award in awards:
            order = range(4, 4 - award['Count'], -1) if award['Atype'] == 1 else range(award['Count'])
            for index, col in enumerate(order):
                winning.add(col * 3 + award['Index'])
                award['Symbol'][index] = original[col][award['Index']]
        for col in range(5):
            for row in range(3):
                pos = col * 3 + row
                if symbols[col][row] in (5, 6, 7) and (pos in winning or bonus):
                    collect.append(dict(Pos=pos, CPos=coin_positions, Mul=float(coin_sum), SymbolMul=2 if symbols[col][row] == 6 else 1))
        return dict(Symbol=columns(original), Mul=columns(initial), FinalSymbol=columns(symbols), FinalMul=columns(mul),
                    CollectList=collect, MysteryList=mystery, AwardDataVec=awards, PotList=pot,
                    PotType=1 if pot else 0, RoundWin=total / 10000, AwardTypeFlag=2 if bonus else 1 if total else 0,
                    GetReSpin=bonus, ReSpinRemainRound=3 if bonus else 0)

    def _bonus(self, rng, first, amount):
        # Filled positions lock. New symbols reset the remaining count to three.
        symbols = [list(col['Col']) for col in first['FinalSymbol']]
        mul = [list(col['Col']) for col in first['FinalMul']]
        symbols = [[7 if value in (5, 6) else value for value in col] for col in symbols]
        remain, records, count = 3, [], 0
        while remain and count < 100:
            count += 1
            added, collectors = False, []
            for col in range(5):
                for row in range(3):
                    if not symbols[col][row] and rng.random() < self.config['bonus_add_chance']:
                        symbols[col][row] = rng.choices([1, 2, 3, 4, 7], [75, 5, 12, 3, 5])[0]
                        mul[col][row] = self._value(rng, symbols[col][row])
                        if symbols[col][row] == 7:
                            collectors.append(col * 3 + row)
                        added = True
            remain = 3 if added else remain - 1
            full = all(value for col in symbols for value in col)
            if full:
                remain = 0
            record = dict(Symbol=columns(symbols), Mul=columns(mul), FinalSymbol=columns(symbols), FinalMul=columns(mul),
                CollectList=[], MysteryList=[], AwardDataVec=[], PotList=[], PotType=0,
                ReSpinRemainRound=remain, ReSpinTotalRound=count, GetReSpin=False, GetAdd=added,
                RoundWin=0, AwardTypeFlag=4, MaxFlag=False)
            coin_positions = [col * 3 + row for col in range(5) for row in range(3) if symbols[col][row] == 1]
            coin_sum = sum(Decimal(str(mul[p // 3][p % 3])) for p in coin_positions)
            for pos in collectors:
                factor = rng.randint(2, 20)
                mul[pos // 3][pos % 3] = float(coin_sum * factor)
                record['CollectList'].append(dict(Pos=pos, CPos=coin_positions, Mul=float(coin_sum), SymbolMul=factor))
            record['FinalMul'] = columns(mul)
            if not remain:
                for col in range(5):
                    for row in range(3):
                        if symbols[col][row] in (3, 4):
                            is_jp = symbols[col][row] == 4
                            symbols[col][row] = 2 if is_jp or rng.random() < 0.1 else 1
                            mul[col][row] = self._value(rng, symbols[col][row])
                            record['MysteryList'].append(dict(IsJP=is_jp, Pos=col * 3 + row, Symbol=symbols[col][row], Mul=mul[col][row]))
                total = amount * 5000 if full else sum(money(amount, v) for col in mul for v in col)
                awards = [dict(Atype=3, Pos=col * 3 + row, AllMul=mul[col][row],
                               Win=money(amount, mul[col][row]) / 10000, Symbol=[], Mul=[])
                          for col in range(5) for row in range(3) if symbols[col][row]]
                if full:
                    # The original client detects the Grand branch by Index=99.
                    awards = [dict(Atype=3, Index=99, AllMul=5000, Win=total / 10000, Symbol=[], Mul=[])]
                record.update(FinalSymbol=columns(symbols), FinalMul=columns(mul), RoundWin=total / 10000,
                              AwardDataVec=awards)
            records.append(record)
        return records
