"""Super Ace: generated 1024-way rounds, flips, Jokers and bundled free games."""
import copy
import hashlib
import json
import math
import random
from pathlib import Path
from server.core.contracts import Outcome, ServiceError


def evaluate(columns, bet_minor, paytable):
    """Awards contain the pre-combo amount; bonus is the number of ways."""
    awards = []
    for symbol in range(2, 10):
        reels = []
        for col, values in enumerate(columns):
            hits = [dict(row=row, column=col) for row, item in enumerate(values['row']) if item in (0, symbol)]
            if not hits:
                break
            reels.append(hits)
        if len(reels) < 3:
            continue
        ways = math.prod(len(hits) for hits in reels)
        # Paytable numerators use twentieths, avoiding binary floating point money.
        amount = bet_minor * paytable[str(symbol)][len(reels)-3] * ways // 20
        awards.append(dict(symbol=symbol, block=[p for hits in reels for p in hits],
                           win_minor=amount, bonus=ways, maxLen=len(reels)))
    return awards


class SuperAce:
    game_id, title, version, minor_unit = 'super-ace', 'Super Ace', '1.0.0', 10000

    def __init__(self, config_path=None):
        self.config = json.loads(Path(config_path or Path(__file__).with_name('config.json')).read_text(encoding='utf-8'))
        c = self.config
        if len(c['symbol_weights']) != 9 or any(type(x) is not int or x <= 0 for x in c['symbol_weights']):
            raise ValueError('Invalid Super Ace symbol weights')
        if not 0 <= c['gold_chance'] <= 1 or not 0 <= c['big_joker_chance'] <= 1:
            raise ValueError('Invalid Joker probabilities')
        if set(c['paytable_twentieths']) != set(map(str, range(2, 10))) or any(len(v) != 3 or any(type(x) is not int or x < 0 for x in v) for v in c['paytable_twentieths'].values()):
            raise ValueError('Invalid Super Ace paytable')
        self.ruleset_id = self.version + ':' + hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()[:16]

    def initial_state(self, seed):
        return dict(sid='0', round_id='0', phase='ready', ruleset_id=self.ruleset_id,
                    last_event=None, last_bet_minor=5000)

    def public_state(self, state):
        return copy.deepcopy(state)

    def normalize_bet(self, payload):
        if not isinstance(payload, dict) or set(payload) - {'bet_minor', 'buy_bonus'}:
            raise ServiceError('BET_INVALID', 'Unsupported Super Ace bet fields.')
        bet, buy = payload.get('bet_minor', 5000), payload.get('buy_bonus', False)
        if type(bet) is not int or bet not in self.config['bets_minor'] or type(buy) is not bool:
            raise ServiceError('BET_INVALID', 'Invalid Super Ace bet.')
        return dict(bet_minor=bet, buy_bonus=buy)

    def draw_cell(self, rng, col):
        symbol = rng.choices(range(1, 10), self.config['symbol_weights'])[0]
        gold = 0
        if symbol > 1 and 1 <= col <= 3 and rng.random() < self.config['gold_chance']:
            gold = 2 if rng.random() < self.config['big_joker_chance'] else 1
        return symbol, gold

    def make_plate(self, rng, bet, free, budget, buy=False):
        board = []
        for col in range(5):
            cells = [self.draw_cell(rng, col) for _ in range(4)]
            board.append(dict(row=[c[0] for c in cells], isGold=[c[1] for c in cells]))
        if buy:
            # The captured purchase begins with a normal multiplier board containing three scatters.
            for col in board:
                col['row'] = [rng.randrange(2, 10) if x == 1 else x for x in col['row']]
            for col in rng.sample(range(5), 3):
                row = rng.randrange(4)
                board[col]['row'][row], board[col]['isGold'][row] = 1, 0
        plate = dict(column=copy.deepcopy(board), combo=[], win=0, totalFreeSpin=10)
        total = 0
        for step in range(1000):
            awards = evaluate(board, bet, self.config['paytable_twentieths'])
            if not awards or total >= budget:
                break
            multiplier = [1, 2, 3, 5][min(step, 3)] * (2 if free else 1)
            win = min(budget-total, sum(a['win_minor'] for a in awards) * multiplier)
            hit = {(p['column'], p['row']) for a in awards for p in a['block']}
            changes, copies = {}, set()
            for col, row in sorted(hit):
                old_gold = board[col]['isGold'][row]
                if old_gold in (1, 2):
                    symbol, gold = 0, old_gold + 100
                    if old_gold == 2:
                        candidates = [(c, r) for c in range(5) for r in range(4)
                                      if (c, r) not in hit and board[c]['row'][r] != 1]
                        copies.update(rng.sample(candidates, min(len(candidates), rng.randint(1, 3))))
                else:
                    symbol, gold = self.draw_cell(rng, col)
                changes[col, row] = dict(symbol=symbol, row=row, column=col, isGold=gold, lastGold=old_gold)
            for col, row in sorted(copies):
                changes[col, row] = dict(symbol=0, row=row, column=col, isGold=102, lastGold=2)
            # Original DemoData places copied Big Jokers in change, including non-winning positions.
            for (col, row), cell in changes.items():
                board[col]['row'][row], board[col]['isGold'][row] = cell['symbol'], cell['isGold']
            wire_awards = [{**{k: v for k, v in a.items() if k != 'win_minor'}, 'win': a['win_minor']/self.minor_unit} for a in awards]
            plate['combo'].append(dict(change=list(changes.values()), award=wire_awards,
                                       win=win/self.minor_unit, comboBonus=multiplier, extraChange=[]))
            total += win
        else:
            raise ServiceError('GENERATION_LIMIT', 'Round generation limit exceeded; no wager was charged.', 503)
        scatter = sum(col['row'].count(1) for col in board)
        triggered = scatter >= 3
        plate.update(win=total/self.minor_unit, isBonus=triggered)
        return plate, total, triggered

    def step(self, state, bet, seed, sid):
        rng = random.Random(seed)
        amount, buy = bet['bet_minor'], bet['buy_bonus']
        debit = amount * 81 // 2 if buy else amount
        cap = amount * 10000
        base, total, trigger = self.make_plate(rng, amount, False, cap, buy)
        plates, remaining, total_free = [base], 10 if trigger else 0, 10
        while remaining and total < cap:
            remaining -= 1
            plate, win, retrigger = self.make_plate(rng, amount, True, cap-total)
            if retrigger:
                remaining += 5
                total_free += 5
            plate['totalFreeSpin'] = total_free
            plates.append(plate)
            total += win
            if len(plates) > 10000:
                raise ServiceError('GENERATION_LIMIT', 'Free game generation limit exceeded; no wager was charged.', 503)
        event = dict(round_id=sid, bet_minor=amount, buy_bonus=buy, plates=plates,
                     total_minor=total, free_spins=len(plates)-1, capped=total == cap)
        s = dict(sid=sid, round_id=sid, phase='ready', ruleset_id=self.ruleset_id,
                 last_event=event, last_bet_minor=amount)
        return Outcome(s, event, debit, total)
