"""Roma X 10000 rules and configurable local outcomes; not the original RTP."""
import copy
import hashlib
import json
import random
from pathlib import Path
from server.core.contracts import Outcome, ServiceError


def columns(values):
    return [dict(Col=list(col)) for col in values]


def evaluate(plate, amount, config):
    awards, removed, total = [], set(), 0
    for line, positions in enumerate(config['line_infos']):
        values = [plate[p // 3][p % 3] for p in positions]
        candidates = []
        for symbol, table in enumerate(config['paytable_fifteenths']):
            count = 0
            for value in values:
                if value not in (symbol, 7):
                    break
                count += 1
            win = amount * table[count] // 15
            if win:
                candidates.append((win, count, symbol))
        if not candidates:
            continue
        win, count, symbol = max(candidates)
        awards.append(dict(Symbol=symbol, Count=count, Line=line, Win=win / 10000))
        removed.update(positions[:count])
        total += win
    if removed:
        removed.update(col * 3 + row for col, values in enumerate(plate) for row, value in enumerate(values) if value == 9)
    return awards, removed, total


class RomaX10000:
    game_id, title, version, minor_unit = 'roma-x-10000', 'Roma X 10000', '1.0.0', 10000

    def __init__(self, config_path=None):
        self.config = json.loads(Path(config_path or Path(__file__).with_name('config.json')).read_text(encoding='utf-8'))
        c = self.config
        if len(c['line_infos']) != 15 or any(len(row) != 5 or any(type(p) is not int or p // 3 != col for col, p in enumerate(row)) for row in c['line_infos']):
            raise ValueError('Invalid paylines')
        if len(c['paytable_fifteenths']) != 7 or any(len(row) != 6 or any(type(v) is not int or v < 0 for v in row) for row in c['paytable_fifteenths']):
            raise ValueError('Invalid paytable')
        if len(c['symbol_weights']) != 8 or any(type(v) is not int or v < 0 for v in c['symbol_weights']) or not sum(c['symbol_weights']):
            raise ValueError('Invalid symbol weights')
        if not c['bets_minor'] or any(type(v) is not int or v <= 0 or v % 15 for v in c['bets_minor']):
            raise ValueError('Invalid bet levels')
        if len(c['buy_multipliers']) != 2 or any(type(v) is not int or v <= 0 for v in c['buy_multipliers']):
            raise ValueError('Invalid buy prices')
        if any(not 0 <= c[k] <= 1 for k in ('feature_chance', 'super_bonus_chance')) or type(c['max_win_multiple']) is not int or c['max_win_multiple'] <= 0:
            raise ValueError('Invalid frequency or win limit')
        self.ruleset_id = self.version + ':' + hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()[:16]

    def initial_state(self, seed):
        return dict(sid='0', round_id='0', phase='ready', ruleset_id=self.ruleset_id, last_event=None, last_bet_minor=60000)

    def public_state(self, state):
        return copy.deepcopy(state)

    def normalize_bet(self, payload):
        if not isinstance(payload, dict) or set(payload) - {'bet_minor', 'buy'}:
            raise ServiceError('BET_INVALID', 'Invalid play fields.')
        amount, buy = payload.get('bet_minor', 60000), payload.get('buy')
        if type(amount) is not int or amount not in self.config['bets_minor'] or buy is not None and (type(buy) is not int or buy not in range(2)):
            raise ServiceError('BET_INVALID', 'Invalid play selection.')
        if buy is not None and amount > self.config['buy_max_bet_minor']:
            raise ServiceError('BET_INVALID', 'The selected bet exceeds the Buy Bonus maximum.')
        return dict(bet_minor=amount, buy=buy)

    def _round(self, rng, amount, feature=None):
        c = self.config
        plate = [rng.choices(range(8), c['symbol_weights'], k=3) for _ in range(5)]
        if feature:
            for col, value in enumerate([8, 8, 9 if feature == 'super' else 8]):
                plate[col][1] = value
        stages, total = [], 0
        for index in range(200):
            awards, removed, win = evaluate(plate, amount, c)
            if feature and index == 0:
                awards.append(dict(Symbol=8, Count=3, Line=0, Win=0))
            stage = dict(ComboStageSymbol=columns(plate), ComboStageWin=win / 10000,
                         AwardDataVec=awards, FillSymbols=columns([[] for _ in range(5)]),
                         BonusHit=feature == 'bonus' and index == 0, BonusWheelHit=feature == 'super' and index == 0)
            stages.append(stage)
            total += win
            if not removed:
                return dict(ComboStageData=stages, RoundWin=total / 10000, AwardTypeFlag=int(bool(total)))
            fill = [rng.choices(range(8), c['symbol_weights'], k=sum(col * 3 + row in removed for row in range(3))) for col in range(5)]
            stage['FillSymbols'] = columns(fill)
            plate = [[value for row, value in enumerate(values) if col * 3 + row not in removed] + fill[col] for col, values in enumerate(plate)]
        raise RuntimeError('Cascade generation limit reached')

    def _battle(self, rng, amount):
        hp, rounds, total = 3, [], 0
        while hp:
            symbol = 10 if len(rounds) >= 30 else rng.choices([10, 11, 12], [40, 40, 20])[0]
            result = 0 if symbol == 10 else rng.choices([1, 2, 3], [20, 25, 55])[0]
            if result in (0, 1):
                hp -= 1
            win = amount * {10: 3, 11: 10, 12: 20}[symbol] if result != 2 else 0
            rounds.append(dict(Symbol=symbol, Result=result, Win=win / 10000, HealthPoint=hp))
            total += win
        return rounds, total

    def step(self, state, bet, seed, sid, _attempt=0):
        rng, c, amount, buy = random.Random(seed), self.config, bet['bet_minor'], bet.get('buy')
        feature = 'super' if buy == 1 else rng.choice(['bonus', 'super']) if buy == 0 else 'super' if rng.random() < c['super_bonus_chance'] else 'bonus' if rng.random() < c['feature_chance'] else None
        first = self._round(rng, amount, feature)
        spin = dict(RoundQueue=[first], BonusInfo=[], FreeTotalWin=0, BonusTotalWin=0, BonusWheelWin=0, BonusWheelMult=0, BonusWheelResult=0)
        total = round(first['RoundWin'] * 10000)
        multiplier = 1
        if feature == 'super':
            result = rng.choices(range(7), [1, 2, 5, 10, 20, 30, 50])[0]
            spin['BonusWheelResult'] = result
            first['AwardTypeFlag'] |= 32
            if result < 3:
                cash = amount * [10000, 5000, 1000][result]
                spin['BonusWheelWin'] = cash / 10000
                total += cash
            else:
                multiplier = [10, 5, 3, 2][result - 3]
                spin['BonusWheelMult'] = multiplier
                first['ComboStageData'][0]['BonusHit'] = True
                feature = 'bonus'
        if feature == 'bonus':
            spin['BonusInfo'], cash = self._battle(rng, amount)
            spin['BonusTotalWin'] = cash * multiplier / 10000
            first['AwardTypeFlag'] |= 16
            total += cash * multiplier
        wins = sum(stage['ComboStageWin'] > 0 for stage in first['ComboStageData'])
        remaining = [3, 5, 10, 20][min(wins - 4, 3)] if wins >= 4 else 0
        if remaining:
            first.update(AwardTypeFlag=first['AwardTypeFlag'] | 2, AddRound=remaining, FreeRemainRound=remaining, FreeTotalRound=remaining)
        free_total, current, free_count = 0, 0, remaining
        while remaining and current < 500:
            current += 1
            remaining -= 1
            record = self._round(rng, amount)
            wins = sum(stage['ComboStageWin'] > 0 for stage in record['ComboStageData'])
            added = [3, 5, 10, 20][min(wins - 4, 3)] if wins >= 4 else 0
            remaining += added
            free_count += added
            record.update(AwardTypeFlag=record['AwardTypeFlag'] | 4 | (8 if not remaining else 0),
                          FreeRemainRound=remaining, FreeNowRound=current, FreeTotalRound=free_count, AddRound=added)
            spin['RoundQueue'].append(record)
            free_total += round(record['RoundWin'] * 10000)
        total += free_total
        if remaining or total > amount * c['max_win_multiple']:
            if _attempt >= 200:
                raise RuntimeError('Unable to generate an outcome within the win limit')
            return self.step(state, bet, str(seed) + ':retry', sid, _attempt + 1)
        spin.update(FreeTotalWin=free_total / 10000, TotalWin=total / 10000, BonusMaxFlag=total == amount * c['max_win_multiple'])
        event = dict(round_id=str(sid), spin=spin, bet_minor=amount, buy=buy, total_minor=total)
        next_state = dict(state, sid=str(sid), round_id=str(sid), last_event=event, last_bet_minor=amount)
        return Outcome(next_state, event, amount * (c['buy_multipliers'][buy] if buy is not None else 1), total)
