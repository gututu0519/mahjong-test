"""Generated local Olympus rules. No HTTP, wallet writes or recorded outcomes."""
import copy
import hashlib
import json
import random
from pathlib import Path
from server.core.contracts import Outcome, ServiceError

# Coin-unit awards for 8–9, 10–11, 12+ symbols. Evidence: doInit paytable.
PAYTABLE = {3: (200, 500, 1000), 4: (50, 200, 500), 5: (40, 100, 300),
            6: (30, 40, 240), 7: (20, 30, 200), 8: (16, 24, 160),
            9: (10, 20, 100), 10: (8, 18, 80), 11: (5, 15, 40)}
MULTIPLIERS = [2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 50, 100, 250, 500]
COINS = [1, 2, 3, 4, 5, 10, 20, 30, 40, 50, 75, 100, 200, 300, 400,
         500, 600, 700, 800, 900, 1000, 1100, 1200]


def evaluate(board, coin):
    if len(board) != 30 or any(type(s) is not int or s not in (1, *range(3, 13)) for s in board):
        raise ValueError('Expected a row-major 6 by 5 board')
    positions, awards = {}, {}
    for symbol, rates in PAYTABLE.items():
        hits = [p for p, value in enumerate(board) if value == symbol]
        if len(hits) >= 8:
            positions[str(symbol)] = hits
            awards[str(symbol)] = coin * rates[2 if len(hits) >= 12 else 1 if len(hits) >= 10 else 0]
    return {'positions': positions, 'awards_minor': awards, 'base_minor': sum(awards.values())}


def scatter_award(count, coin):
    return coin * (2000 if count >= 6 else 100 if count == 5 else 60 if count == 4 else 0)


class GatesOfOlympus:
    game_id = 'gates-of-olympus'
    title = 'Gates of Olympus'
    version = '1.0.0'

    def __init__(self, config_path=None):
        self.config = json.loads(Path(config_path or Path(__file__).with_name('config.json')).read_text(encoding='utf-8'))
        c = self.config
        if c['multiplier_values'] != MULTIPLIERS or len(c['multiplier_weights']) != len(MULTIPLIERS):
            raise ValueError('Invalid multiplier distribution')
        for weights in [c['multiplier_weights'], *c['reel_weights'].values()]:
            if not weights or any(type(w) is not int or not 0 <= w <= 10000 for w in weights) or sum(weights) == 0:
                raise ValueError('Invalid local weights')
        if set(c['reel_weights']) != {'base', 'ante', 'free'}:
            raise ValueError('Missing generation mode')
        for weights in c['reel_weights'].values():
            if len(weights) != len(c['reel_sets']):
                raise ValueError('Reel selection mismatch')
        for reels in c['reel_sets']:
            if len(reels) != 6 or any(len(r) < 5 or any(type(s) is not int or s not in (1, *range(3, 13)) for s in r) for r in reels):
                raise ValueError('Invalid reels')
        self.ruleset_id = self.version + ':' + hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()[:16]

    def normalize_bet(self, payload):
        if not isinstance(payload, dict) or set(payload) - {'coin_minor', 'ante', 'action', 'request_index'}:
            raise ServiceError('BET_INVALID', 'Unsupported bet fields.')
        coin, ante = payload.get('coin_minor', 10), payload.get('ante', False)
        action, index = payload.get('action', 'spin'), payload.get('request_index', 0)
        if (type(coin) is not int or coin not in COINS or type(ante) is not bool
                or action not in ('spin', 'collect', 'buy') or type(index) is not int or not 0 <= index <= 1_000_000_000):
            raise ServiceError('BET_INVALID', 'Invalid coin, ante, action or request index.')
        return {'coin_minor': coin, 'ante': ante, 'action': action, 'request_index': index}

    def initial_state(self, seed):
        return {'sid': '0', 'round_id': '0', 'phase': 'ready', 'ruleset_id': self.ruleset_id,
                'bet': {'coin_minor': 10, 'ante': False}, 'board': [3 + p % 9 for p in range(30)],
                'orbs': {}, 'sa': [3, 4, 5, 6, 7, 8], 'sb': [9, 10, 11, 3, 4, 5],
                'reel_set': 0, 'sequence_minor': 0, 'total_minor': 0, 'tumble': 0,
                'free': None, 'protocol_index': 0, 'last_event': None}

    def public_state(self, state):
        return copy.deepcopy(state)

    def _draw(self, rng, reel_set, col, count):
        reel = self.config['reel_sets'][reel_set][col]
        start = rng.randrange(len(reel))
        symbols = [reel[(start + i) % len(reel)] for i in range(count)]
        orbs = {i: rng.choices(MULTIPLIERS, self.config['multiplier_weights'])[0]
                for i, s in enumerate(symbols) if s == 12}
        return symbols, orbs, reel[(start - 1) % len(reel)], reel[(start + count) % len(reel)]

    def _new_board(self, rng, reel_set):
        board, orbs, sa, sb = [0] * 30, {}, [], []
        for col in range(6):
            values, mults, above, below = self._draw(rng, reel_set, col, 5)
            sa.append(above); sb.append(below)
            for row, symbol in enumerate(values):
                p = row * 6 + col
                board[p] = symbol
                if row in mults:
                    orbs[str(p)] = mults[row]
        return board, orbs, sa, sb

    def _purchase_board(self, rng):
        # Captured purchase uses reel 6 and four scatters. Placement weights are local.
        for _ in range(1000):
            board, orbs, sa, sb = self._new_board(rng, 6)
            if 1 in board:
                continue
            for p in rng.sample(range(30), 4):
                board[p] = 1
                orbs.pop(str(p), None)
            if not evaluate(board, 1)['positions']:
                return board, orbs, sa, sb
        raise ServiceError('GENERATION_FAILED', 'Unable to generate purchase trigger.', 503)

    def _cascade(self, rng, state):
        removed = {p for ps in evaluate(state['board'], state['bet']['coin_minor'])['positions'].values() for p in ps}
        board, orbs, sa = [0] * 30, {}, []
        for col in range(6):
            survivors = [(state['board'][p], state['orbs'].get(str(p))) for p in range(col, 30, 6) if p not in removed]
            n = 5 - len(survivors)
            values, mults, above, _ = self._draw(rng, state['reel_set'], col, n)
            sa.append(above)
            cells = [(v, mults.get(i)) for i, v in enumerate(values)] + survivors
            for row, (symbol, multiplier) in enumerate(cells):
                p = row * 6 + col
                board[p] = symbol
                if multiplier is not None:
                    orbs[str(p)] = multiplier
        return board, orbs, sa, state['sb'][:]

    def step(self, state, command, seed, sid):
        s = copy.deepcopy(state)
        action, index = command['action'], command['request_index']
        if index and index <= s['protocol_index']:
            raise ServiceError('STALE_INDEX', 'Request index must advance; reload the current game state.', 409)
        bet = {k: command[k] for k in ('coin_minor', 'ante')}
        if s['phase'] != 'ready' and s['ruleset_id'] != self.ruleset_id:
            raise ServiceError('RULESET_CHANGED', 'Finish the round with its original rules.', 409)
        if action == 'collect':
            if s['phase'] != 'collect':
                raise ServiceError('COLLECT_INVALID', 'No completed round is awaiting collection.', 409)
            credit = s['total_minor']
            event = {'action': 'collect', 'round_id': s['round_id'], 'sid': sid, 'index': index}
            s.update(sid=sid, phase='ready', last_event=None, protocol_index=index or s['protocol_index'], free=None)
            return Outcome(s, event, 0, credit)
        if s['phase'] == 'collect':
            raise ServiceError('COLLECT_REQUIRED', 'Collect the completed round first.', 409)
        if s['phase'] != 'ready' and bet != s['bet']:
            raise ServiceError('BET_LOCKED', 'Bet changes are only allowed between rounds.', 409)
        purchase = action == 'buy'
        if purchase and (s['phase'] != 'ready' or bet['ante']):
            raise ServiceError('PURCHASE_INVALID', 'Purchase requires an idle round with ante disabled.', 409)
        rng = random.Random(seed)
        phase, debit = s['phase'], 0
        free_spin = phase in ('free', 'free_cascade')
        cascade = phase in ('cascade', 'free_cascade')
        if phase == 'ready':
            s.update(round_id=sid, ruleset_id=self.ruleset_id, bet=bet, free=None, total_minor=0, purchased=purchase)
            debit = bet['coin_minor'] * (2000 if purchase else 25 if bet['ante'] else 20)
        if not cascade:
            s.update(sequence_minor=0, tumble=0)
            if free_spin:
                s['free']['played'] += 1
            mode = 'free' if free_spin else 'ante' if bet['ante'] else 'base'
            s['reel_set'] = rng.choices(range(len(self.config['reel_sets'])), self.config['reel_weights'][mode])[0]
            if purchase:
                s['reel_set'] = 6
                draw = self._purchase_board(rng)
            else:
                draw = self._new_board(rng, s['reel_set'])
            s['board'], s['orbs'], s['sa'], s['sb'] = draw
        else:
            s['board'], s['orbs'], s['sa'], s['sb'] = self._cascade(rng, s)
            s['tumble'] += 1
        result = evaluate(s['board'], bet['coin_minor'])
        current = result['base_minor']
        prior_total = s['total_minor']
        s['sequence_minor'] += current
        s['total_minor'] += current
        orb_sum = sum(s['orbs'].values())
        acc = (s['free']['multiplier'] if free_spin else 0) + (orb_sum if not free_spin or s['sequence_minor'] else 0)
        extra, scatter, awarded, multiplier = 0, 0, 0, 1
        ended = not result['positions']
        if ended:
            # Only a winning sequence with a multiplier symbol applies the free accumulator.
            if orb_sum and s['sequence_minor']:
                multiplier = acc
                extra = s['sequence_minor'] * (multiplier - 1)
                s['total_minor'] += extra
                if free_spin:
                    s['free']['multiplier'] = acc
            count = s['board'].count(1)
            scatter = scatter_award(count, bet['coin_minor'])
            s['total_minor'] += scatter
            if free_spin:
                s['free']['win_minor'] += s['sequence_minor'] + extra + scatter
                if count >= 3:
                    s['free']['total'] += 5
                    awarded = 5
                s['phase'] = 'free' if s['free']['played'] < s['free']['total'] else 'collect'
            elif count >= 4:
                awarded = 15
                s['free'] = {'total': 15, 'played': 0, 'win_minor': 0, 'multiplier': 0}
                s['phase'] = 'free'
            else:
                s['phase'] = 'collect' if s['total_minor'] else 'ready'
        else:
            s['phase'] = 'free_cascade' if free_spin else 'cascade'
        # 5000x regular base bet; 4000x ante bet is the same monetary ceiling.
        cap = bet['coin_minor'] * 20 * 5000
        capped = s['total_minor'] >= cap
        if capped:
            overflow = s['total_minor'] - cap
            s['total_minor'] = cap
            if free_spin and ended:
                s['free']['win_minor'] = max(0, s['free']['win_minor'] - overflow)
            elif free_spin:
                s['free']['win_minor'] += max(0, s['sequence_minor'] - overflow)
            s['phase'] = 'collect'
        e = {'action': 'spin', 'sid': sid, 'round_id': s['round_id'], 'index': index,
             'bet': bet, 'board': s['board'][:], 'orbs': dict(s['orbs']), 'sa': s['sa'][:], 'sb': s['sb'][:],
             'reel_set': s['reel_set'], **result, 'cascade': cascade, 'tumble': s['tumble'],
             'sequence_minor': s['sequence_minor'], 'total_minor': s['total_minor'],
             'delta_minor': s['total_minor'] - prior_total, 'extra_minor': extra,
             'scatter_minor': scatter, 'multiplier': multiplier, 'accumulator': acc,
             'free_spin': free_spin, 'free': copy.deepcopy(s['free']), 'free_awarded': awarded,
             'purchased': s.get('purchased', False), 'purchase_trigger': purchase,
             'ended': ended, 'capped': capped, 'next_phase': s['phase']}
        s.update(sid=sid, last_event=e, protocol_index=index or s['protocol_index'])
        return Outcome(s, e, debit, 0)
