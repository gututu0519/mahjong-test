"""Sweet Bonanza POP: generated outcomes, no captured-spin replay or wallet writes."""
import copy
import hashlib
import json
import random
from pathlib import Path
from server.core.contracts import Outcome, ServiceError

PAYTABLE = {'1': (100, 250, 500), '2': (20, 80, 200), '3': (10, 20, 100),
            '4': (6, 15, 60), '5': (4, 10, 40), '6': (2, 8, 20)}
MULTIPLIERS = [2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 50, 100, 250, 500, 1000]


def evaluate(board, coin):
    if len(board) != 15 or any(s not in '123456SMJ' for s in board):
        raise ValueError('Expected a row-major 3 by 5 screen')
    positions, awards = {}, {}
    for symbol, rates in PAYTABLE.items():
        hits = [p for p, value in enumerate(board) if value == symbol]
        if len(hits) >= 5:
            positions[symbol] = hits
            awards[symbol] = coin * rates[2 if len(hits) >= 9 else 1 if len(hits) >= 7 else 0]
    return {'positions': positions, 'awards_minor': awards, 'base_minor': sum(awards.values())}


class SweetBonanzaPop:
    game_id = 'sweet-bonanza-pop'
    title = 'Sweet Bonanza POP'
    version = '1.0.0'

    def __init__(self, config_path=None):
        self.config = json.loads(Path(config_path or Path(__file__).with_name('config.json')).read_text(encoding='utf-8'))
        c = self.config
        for reels in c['reel_sets']:
            if len(reels) != 3 or any(len(r) < 5 or any(s not in '123456SMJ' for s in r) for r in reels):
                raise ValueError('Invalid reels')
        for name in ('base', 'free'):
            weights = c['reel_weights'][name]
            if len(weights) != len(c['reel_sets']) or not sum(weights) or any(type(w) is not int or w < 0 for w in weights):
                raise ValueError('Invalid reel weights')
        weights = c['multiplier_weights']
        if len(weights) != len(MULTIPLIERS) or not sum(weights) or any(type(w) is not int or w < 0 for w in weights):
            raise ValueError('Invalid multiplier weights')
        self.ruleset_id = self.version + ':' + hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()[:16]

    def normalize_bet(self, payload):
        if not isinstance(payload, dict) or set(payload) - {'coin_minor', 'action', 'request_index'}:
            raise ServiceError('BET_INVALID', 'Unsupported bet fields.')
        coin, action, index = payload.get('coin_minor', 20), payload.get('action', 'spin'), payload.get('request_index', 0)
        if type(coin) is not int or coin not in self.config['coins'] or action not in ('spin', 'collect') or type(index) is not int or not 0 <= index <= 1_000_000_000:
            raise ServiceError('BET_INVALID', 'Invalid coin, action or index.')
        return {'coin_minor': coin, 'action': action, 'request_index': index}

    def initial_state(self, seed):
        return {'sid': '0', 'round_id': '0', 'phase': 'ready', 'ruleset_id': self.ruleset_id,
                'bet': {'coin_minor': 20}, 'board': list('342611522344521'), 'orbs': {},
                'sa': list('123'), 'sb': list('456'), 'reel_set': 0, 'sequence_minor': 0,
                'initial_win_minor': 0, 'total_minor': 0, 'tumble': 0, 'free': None,
                'protocol_index': 0, 'last_event': None}

    def public_state(self, state):
        return copy.deepcopy(state)

    def _draw(self, rng, reel_set, col, count):
        reel = self.config['reel_sets'][reel_set][col]
        start = rng.randrange(len(reel))
        values = [reel[(start + i) % len(reel)] for i in range(count)]
        mults = {i: rng.choices(MULTIPLIERS, self.config['multiplier_weights'])[0]
                 for i, value in enumerate(values) if value == 'M'}
        return values, mults, reel[(start - 1) % len(reel)], reel[(start + count) % len(reel)]

    def _new_board(self, rng, reel_set):
        board, orbs, sa, sb = [''] * 15, {}, [], []
        for col in range(3):
            values, mults, above, below = self._draw(rng, reel_set, col, 5)
            sa.append(above); sb.append(below)
            for row, symbol in enumerate(values):
                p = row * 3 + col
                board[p] = symbol
                if row in mults:
                    orbs[str(p)] = mults[row]
        return board, orbs, sa, sb

    def _cascade(self, rng, state):
        removed = {p for ps in evaluate(state['board'], state['bet']['coin_minor'])['positions'].values() for p in ps}
        board, orbs, sa = [''] * 15, {}, []
        for col in range(3):
            survivors = [(state['board'][p], state['orbs'].get(str(p))) for p in range(col, 15, 3) if p not in removed]
            values, mults, above, _ = self._draw(rng, state['reel_set'], col, 5 - len(survivors))
            sa.append(above)
            for row, (symbol, mult) in enumerate([(v, mults.get(i)) for i, v in enumerate(values)] + survivors):
                p = row * 3 + col
                board[p] = symbol
                if mult is not None:
                    orbs[str(p)] = mult
        return board, orbs, sa, state['sb'][:]

    def step(self, state, command, seed, sid):
        s = copy.deepcopy(state)
        index = command['request_index']
        if index and index <= s['protocol_index']:
            raise ServiceError('STALE_INDEX', 'Reload the current state.', 409)
        if s['phase'] != 'ready' and s['ruleset_id'] != self.ruleset_id:
            raise ServiceError('RULESET_CHANGED', 'Finish the round with its original rules.', 409)
        if command['action'] == 'collect':
            if s['phase'] != 'collect':
                raise ServiceError('COLLECT_INVALID', 'No completed round.', 409)
            credit = s['total_minor']
            s.update(sid=sid, phase='ready', last_event=None, free=None, protocol_index=index or s['protocol_index'])
            return Outcome(s, {'action': 'collect', 'sid': sid, 'round_id': s['round_id']}, 0, credit)
        if s['phase'] == 'collect':
            raise ServiceError('COLLECT_REQUIRED', 'Collect the completed round first.', 409)
        bet = {'coin_minor': command['coin_minor']}
        if s['phase'] != 'ready' and bet != s['bet']:
            raise ServiceError('BET_LOCKED', 'Bet is locked during a round.', 409)
        rng = random.Random(seed)
        phase, debit = s['phase'], 0
        free_spin, cascade = phase in ('free', 'free_cascade'), phase in ('cascade', 'free_cascade')
        if phase == 'ready':
            s.update(round_id=sid, ruleset_id=self.ruleset_id, bet=bet, free=None, total_minor=0)
            debit = bet['coin_minor'] * 10
        if not cascade:
            s.update(sequence_minor=0, initial_win_minor=0, tumble=0)
            if free_spin:
                s['free']['played'] += 1
            s['reel_set'] = rng.choices(range(len(self.config['reel_sets'])), self.config['reel_weights']['free' if free_spin else 'base'])[0]
            draw = self._new_board(rng, s['reel_set'])
        else:
            draw = self._cascade(rng, s)
            s['tumble'] += 1
        s['board'], s['orbs'], s['sa'], s['sb'] = draw
        result = evaluate(s['board'], bet['coin_minor'])
        current, prior = result['base_minor'], s['total_minor']
        if not cascade:
            s['initial_win_minor'] = current
        s['sequence_minor'] += current
        s['total_minor'] += current
        ended = not result['positions']
        multiplier = max(1, sum(s['orbs'].values())) if free_spin else 1
        extra, jackpot, awarded = 0, 0, 0
        if ended:
            extra = s['sequence_minor'] * (multiplier - 1)
            s['total_minor'] += extra
            scatters, pops = s['board'].count('S'), s['board'].count('J')
            if free_spin:
                awarded = 10 if scatters >= 3 else 5 if scatters == 2 else 0
                s['free']['total'] += awarded
                s['phase'] = 'free' if s['free']['played'] < s['free']['total'] else 'collect'
            elif scatters + pops >= 3:
                # Award values are in doInit; exact POP response mapping awaits a capture.
                jackpot = (25000 if pops >= 3 else 500 if pops == 2 else 50 if pops == 1 else 0) * bet['coin_minor'] * 10
                s['total_minor'] += jackpot
                s['free'] = {'total': 10, 'played': 0, 'win_minor': 0}
                s['phase'], awarded = 'free', 10
            else:
                s['phase'] = 'collect' if s['total_minor'] else 'ready'
        else:
            s['phase'] = 'free_cascade' if free_spin else 'cascade'
        cap = bet['coin_minor'] * 10 * 25000
        capped = s['total_minor'] >= cap
        if capped:
            s['total_minor'], s['phase'] = cap, 'collect'
        delta = s['total_minor'] - prior
        if free_spin:
            s['free']['win_minor'] += delta
        e = {'action': 'spin', 'sid': sid, 'round_id': s['round_id'], 'index': index,
             'bet': bet, 'board': s['board'][:], 'orbs': dict(s['orbs']), 'sa': s['sa'][:], 'sb': s['sb'][:],
             'reel_set': s['reel_set'], **result, 'cascade': cascade, 'tumble': s['tumble'],
             'sequence_minor': s['sequence_minor'], 'initial_win_minor': s['initial_win_minor'],
             'total_minor': s['total_minor'], 'delta_minor': delta, 'extra_minor': extra,
             'jackpot_minor': jackpot, 'multiplier': multiplier, 'free_spin': free_spin,
             'free': copy.deepcopy(s['free']), 'free_awarded': awarded, 'ended': ended,
             'capped': capped, 'next_phase': s['phase']}
        s.update(sid=sid, last_event=e, protocol_index=index or s['protocol_index'])
        return Outcome(s, e, debit, 0)
