"""Buffalo Win v2 JSON protocol adapter. Never loads recorded spin fixtures."""
import hashlib
import json
from urllib.parse import parse_qs

from server.core.contracts import ServiceError
from server.games.buffalo_win.engine import PAYTABLE

PHASES = {'ready': 1, 'paid_extension': 4, 'free_start': 21, 'free_extension': 22}


def transaction(e, wallet, thresholds):
    amount = lambda value: value / 100
    wp = e['positions']
    winning_cells = set(p for cells in wp.values() for p in cells)
    blocks = {k: cells for k, cells in e['expanded'].items() if set(cells).issubset(winning_cells)}
    long_reels = {}
    for col in {cells[0] // 4 for cells in blocks.values()}:
        reel, position = [], col * 4
        while position < (col + 1) * 4:
            block = next((k for k, cells in blocks.items() if cells[0] == position), None)
            if block:
                reel.extend([e['board'][position]] * e['block_counts'][block])
                position += len(blocks[block])
            else:
                reel.append(e['board'][position])
                position += 1
        long_reels[str(col)] = reel
    rs = None
    if e['extension']:
        offset = len(e['board']) - 4
        new_wins = {k: [p for p in cells if p >= offset] for k, cells in wp.items()}
        new_wins = {k: cells for k, cells in new_wins.items() if cells}
        new_blocks = e.get('new_blocks') or {}
        winning_new_blocks = {k: cells for k, cells in blocks.items() if k in new_blocks}
        rs = {'ecrl': e['board'][-4:], 'oecrl': e.get('original_column') or e['board'][-4:], 'pr': None,
              'sr': int(next(iter(sorted(e['previous_positions'])), '3')), 'ewp': new_wins or None,
              'ebwp': winning_new_blocks or None,
              'ebwsc': {k: e['block_counts'][k] for k in winning_new_blocks} or None,
              'nes': new_blocks or None}
    free = e['free']
    fs = {'s': free['remaining'], 'ts': free['total'], 'as': free['added'],
          'aw': amount(free['award_minor']), 'rc': free['rc']} if free else None
    settled = not e['extend']
    ratio = e['win_minor'] / e['base_bet_minor'] if e['base_bet_minor'] else 0
    gwt = -1
    for index, key in enumerate(('mw', 'bw', 'mgw', 'smgw'), 1):
        if ratio >= thresholds[key]:
            gwt = index
    grid = '#'.join(';'.join(str(e['board'][col * 4 + row]) for col in range(3)) for row in range(4))
    hash_text = f"{e['extension_index']}:{grid}"
    for symbol in sorted(wp):
        cells = wp[symbol]
        hash_text += '#R#' + symbol + '#' + ''.join(f'{p // 4}{p % 4}' for p in cells)
    hash_text += f"#MV#{amount(e['debit_minor'])}#MT#1#MG#{amount(e['win_minor'])}#"
    return {
        'sid': e['sid'], 'psid': e['round_id'], 'st': PHASES[e['phase']], 'nst': PHASES[e['next_phase']],
        'pf': 1, 'ml': e['bet']['level'], 'cs': amount(e['bet']['coin_minor']),
        'rl': e['board'], 'orl': e['original'], 's': e['special'], 'ix': e['extend'],
        'sc': e['scatter_count'], 'gm': e['multiplier'], 'wp': wp or None,
        'lw': None, 'sw': {k: [float(PAYTABLE[int(k)]), amount(v)] for k, v in e['awards_minor'].items()} if settled and wp else None,
        'scs': e['counts_eval'],
        'wpl': sorted(winning_cells) or None, 'bwp': blocks or None,
        'bwsc': {k: e['block_counts'][k] for k in blocks} or None,
        'es': e['expanded'] or None, 'bsc': e['block_counts'] or None,
        'lrs': long_reels or None, 'rs': rs, 'fs': fs,
        'twbm': amount(e['base_minor']) if settled else 0.0,
        'acw': amount(e['accumulated_minor']), 'ctw': amount(e['display_delta_minor']),
        'tw': amount(e['win_minor']), 'aw': amount(e['round_award_minor']),
        'tb': amount(e['debit_minor']), 'tbb': amount(e['debit_minor']),
        'np': amount(e['win_minor'] - e['debit_minor']), 'gwt': gwt,
        'cwc': int(e['win_minor'] > 0), 'pcwc': 0,
        'fstc': {str(PHASES[k]): v for k, v in e['phase_counts'].items()} or None,
        'rwsp': None, 'hashr': hash_text, 'fb': None, 'pmt': None, 'ab': None,
        'wid': 0, 'wt': 'C', 'wk': '0_C', 'wbn': None, 'wfg': None, 'ocr': None, 'mr': None,
        'ge': [3 if e['extend'] and wp else (2 if free and free['remaining'] > 0 else
               (3 if e['base_bet_minor'] and e['win_minor'] >= e['base_bet_minor'] * 3 else 1)), 11],
        'blb': amount(wallet['before_minor']), 'blab': amount(wallet['before_minor'] - wallet['debit_minor']),
        'bl': amount(wallet['after_minor']),
    }


def idle_event(state):
    return {'sid': state['sid'], 'round_id': '0', 'phase': 'ready', 'next_phase': 'ready',
            'bet': state['bet'], 'board': state['board'], 'original': None,
            'expanded': {}, 'block_counts': {}, 'positions': {}, 'counts_eval': None, 'phase_counts': {},
            'special': 10, 'multiplier': 1, 'extension_index': 0, 'extension': False, 'extend': False,
            'previous_positions': {}, 'free': None, 'scatter_count': 0, 'base_bet_minor': 0,
            'debit_minor': 0, 'win_minor': 0, 'round_award_minor': 0, 'accumulated_minor': 0,
            'display_delta_minor': 0, 'base_minor': 0, 'awards_minor': {}}


class PGAdapter:
    game_id = 'buffalo-win'

    def __init__(self, service):
        self.service = service
        self.game = service.registry.get(self.game_id)

    def spin(self, body, token):
        form = parse_qs(body.decode('utf-8'), keep_blank_values=True)
        if any(len(v) != 1 for v in form.values()):
            raise ServiceError('SPIN_INVALID', 'Duplicate request fields.')
        request = {k: v[0] for k, v in form.items()}
        if request.get('wk') != '0_C' or request.get('btt') != '2' or request.get('pf') != '1':
            raise ServiceError('SPIN_INVALID', 'Only the local virtual wallet is supported.')
        feature = request.get('fb', '0')
        if feature not in ('', '0', 'false', '2'):
            raise ServiceError('BET_INVALID', 'Unsupported feature-buy option.')
        if request.get('ab', '0') not in ('', '0', 'false'):
            raise ServiceError('BET_INVALID', 'Ante bet is not supported by this game.')
        try:
            level = int(request.get('ml', ''))
        except ValueError:
            raise ServiceError('BET_INVALID', 'Invalid level.') from None
        bet = self.game.normalize_bet({'cs': request.get('cs'), 'ml': level, 'buy_free': feature == '2'})
        previous = request.get('id')
        # Identity excludes rotating trace IDs and transport authentication.
        identity = json.dumps({'previous': previous, 'bet': bet}, sort_keys=True)
        key = 'pg:' + hashlib.sha256(identity.encode()).hexdigest()
        response = self.service.spin(token, self.game_id, key, previous, bet)
        return {'dt': {'si': transaction(response['outcome'], response['wallet'], self.game.config['win_thresholds'])}, 'err': None}

    def game_info(self, token):
        snapshot = self.service.state(token, self.game_id)
        state, balance = snapshot['state'], snapshot['balance_minor']
        event = state['last_event'] or idle_event(state)
        wallet = {'before_minor': balance + event['debit_minor'] - event['win_minor'],
                  'after_minor': balance, 'debit_minor': event['debit_minor']}
        tx = transaction(event, wallet, self.game.config['win_thresholds'])
        c = self.game.config
        return {'dt': {'cs': [v / 100 for v in c['coin_sizes_minor']], 'ml': c['bet_levels'],
                       'mxl': 10, 'maxwm': None, 'wt': c['win_thresholds'],
                       'fb': dict(c['feature_buy']), 'gcs': {'bf': dict(c['feature_buy_game_config'])},
                       'bl': balance / 100, 'inwe': False, 'iuwe': False, 'ls': {'si': tx}, 'cc': 'PGC'},
                'err': None}

    def wallet(self, token):
        balance = self.service.wallet(token)['balance_minor'] / 100
        return {'dt': {'cc': 'PGC', 'tb': balance, 'pb': 0, 'cb': balance, 'tbb': 0,
                       'tfgb': 0, 'rfgc': 0, 'inbe': False, 'infge': False, 'iebe': False,
                       'iefge': False, 'ch': {'k': '0_C', 'cid': 0, 'cb': balance},
                       'p': None, 'ocr': None, 'bwc': 0, 'fgwc': 0}, 'err': None}
