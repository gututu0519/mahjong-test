"""Generated Big Bass outcomes; captured reels/rules, explicitly local weights."""
import copy
import hashlib
import json
import random
from pathlib import Path
from server.core.contracts import Outcome, ServiceError


def evaluate(board, coin, config):
    if len(board) != 15 or any(type(v) is not int or not 1 <= v <= 12 for v in board):
        raise ValueError('Expected 5 by 3 row-major symbols')
    wins = []
    for line, cells in enumerate(config['lines']):
        best = (0, [])
        for symbol in range(3, 13):
            hits = []
            for p in cells:
                if board[p] not in (symbol, 2):
                    break
                hits.append(p)
            if hits:
                award = config['paytable'][symbol][5 - len(hits)] * coin
                if award > best[0]:
                    best = (award, hits)
        if best[0]:
            wins.append({'line': line, 'amount': best[0], 'positions': best[1]})
    return wins


class BigBassBonanza:
    game_id, title, version = 'big-bass-bonanza', 'Big Bass Bonanza', '1.0.0'

    def __init__(self, config_path=None):
        self.config = json.loads(Path(config_path or Path(__file__).with_name('config.json')).read_text())
        c = self.config
        if len(c['lines']) != 10 or any(len(line) != 5 or any(p % 5 != i or not 0 <= p < 15 for i, p in enumerate(line)) for line in c['lines']):
            raise ValueError('Invalid paylines')
        if len(c['reel_sets']) != 4 or any(len(rs) != 5 or any(len(r) < 3 or any(v not in range(1, 13) for v in r) for r in rs) for rs in c['reel_sets']):
            raise ValueError('Invalid reel sets')
        if len(c['fish_weights']) != len(c['fish_values']) or any(type(w) is not int or w < 0 for w in c['fish_weights']) or not sum(c['fish_weights']):
            raise ValueError('Invalid fish weights')
        self.ruleset_id = self.version + ':' + hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()[:16]

    def normalize_bet(self, payload):
        if not isinstance(payload, dict) or set(payload) - {'coin_minor', 'action', 'request_index'}:
            raise ServiceError('BET_INVALID', 'Unsupported bet fields.')
        coin, action, index = payload.get('coin_minor', 20), payload.get('action', 'spin'), payload.get('request_index', 0)
        if type(coin) is not int or coin not in self.config['coins'] or action not in ('spin', 'collect') or type(index) is not int or not 0 <= index <= 1000000000:
            raise ServiceError('BET_INVALID', 'Invalid bet or action.')
        return dict(coin_minor=coin, action=action, request_index=index)

    def initial_state(self, seed):
        return dict(sid='0', round_id='0', phase='ready', ruleset_id=self.ruleset_id,
                    bet={'coin_minor': 20}, board=[5,6,9,6,6,8,11,8,9,9,6,9,12,6,6],
                    sa=[11,10,7,10,4], sb=[10,7,7,8,11], reel_set=0,
                    total_minor=0, free=None, protocol_index=0, last_event=None)

    def public_state(self, state):
        return copy.deepcopy(state)

    def _draw(self, rng, reel_set):
        board, sa, sb = [0]*15, [], []
        for col, reel in enumerate(self.config['reel_sets'][reel_set]):
            start = rng.randrange(len(reel))
            sa.append(reel[(start-1) % len(reel)])
            sb.append(reel[(start+3) % len(reel)])
            for row in range(3):
                board[row*5+col] = reel[(start+row) % len(reel)]
        return board, sa, sb

    def step(self, state, command, seed, sid):
        s, index = copy.deepcopy(state), command['request_index']
        if index and index <= s['protocol_index']:
            raise ServiceError('STALE_INDEX', 'Reload current state.', 409)
        if s['phase'] != 'ready' and s['ruleset_id'] != self.ruleset_id:
            raise ServiceError('RULESET_CHANGED', 'Use original round rules.', 409)
        if command['action'] == 'collect':
            if s['phase'] != 'collect':
                raise ServiceError('COLLECT_INVALID', 'No completed round.', 409)
            credit = s['total_minor']
            s.update(sid=sid, phase='ready', last_event=None, free=None, protocol_index=index or s['protocol_index'])
            return Outcome(s, {'action': 'collect', 'sid': sid, 'round_id': s['round_id']}, 0, credit)
        if s['phase'] == 'collect':
            raise ServiceError('COLLECT_REQUIRED', 'Collect first.', 409)
        bet = {'coin_minor': command['coin_minor']}
        if s['phase'] != 'ready' and bet != s['bet']:
            raise ServiceError('BET_LOCKED', 'Bet locked during free spins.', 409)
        rng, free_spin, debit = random.Random(seed), s['phase'] == 'free', 0
        if not free_spin:
            s.update(round_id=sid, ruleset_id=self.ruleset_id, bet=bet, free=None, total_minor=0)
            debit = bet['coin_minor'] * 10
        s['reel_set'] = 3 if free_spin else 0
        board, sa, sb = self._draw(rng, s['reel_set'])
        replacements = []
        # Rule-panel random fish rescue; chance and placement are local configuration.
        if free_spin and board.count(2) == 1 and rng.random() < self.config['rescue_chance']:
            candidates = [i for i,v in enumerate(board) if v not in (2,7)]
            if candidates:
                for p in rng.sample(candidates, rng.randint(1, min(3,len(candidates)))):
                    replacements.append((p, board[p], 7))
                    board[p] = 7
        values = [rng.choices(self.config['fish_values'], self.config['fish_weights'])[0] if v == 7 else 0 for v in board]
        wins = evaluate(board, bet['coin_minor'], self.config)
        delta, awarded, multiplier, fish_win = sum(w['amount'] for w in wins), 0, 1, 0
        if free_spin:
            f = s['free']
            multiplier = [1,2,3,10][f['stage']]
            f['played'] += 1
            fish_win = sum(values) * bet['coin_minor'] * board.count(2) * multiplier
            delta += fish_win
            f['collectors'] += board.count(2)
            if f['played'] == f['batch_end'] and f['stage'] < 3 and f['collectors'] >= (f['stage']+1)*4:
                awarded = 10
                f['total'] += 10
                f['stage'] += 1
                f['batch_end'] += 10
            s['phase'] = 'free' if f['played'] < f['total'] else 'collect'
        elif board.count(1) >= 3:
            awarded = {3:10,4:15,5:20}[min(5,board.count(1))]
            s['free'] = dict(total=awarded, played=0, win_minor=0, collectors=0, stage=0, batch_end=awarded)
            s['phase'] = 'free'
        else:
            s['phase'] = 'collect' if delta else 'ready'
        prior = s['total_minor']
        cap = bet['coin_minor']*10*2100
        s['total_minor'] = min(cap, prior+delta)
        capped = prior+delta >= cap
        if capped:
            s['phase'] = 'collect'
        delta = s['total_minor']-prior
        if free_spin:
            s['free']['win_minor'] += delta
        s.update(board=board, sa=sa, sb=sb)
        e = dict(action='spin', sid=sid, round_id=s['round_id'], bet=bet, board=board, sa=sa, sb=sb,
                 reel_set=s['reel_set'], wins=wins, values=values, fish_win=fish_win, multiplier=multiplier,
                 total_minor=s['total_minor'], delta_minor=delta, free_spin=free_spin,
                 free=copy.deepcopy(s['free']), free_awarded=awarded, replacements=replacements,
                 capped=capped, next_phase=s['phase'])
        s.update(sid=sid, last_event=e, protocol_index=index or s['protocol_index'])
        return Outcome(s, e, debit, 0)
