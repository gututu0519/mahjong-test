"""Translate canonical game events into the existing client's wire protocol.

Only protocol metadata is loaded here; no recorded spin/outcome templates.
"""
import base64
import hashlib
import json
from pathlib import Path

from server.core.contracts import ServiceError
from .protocol import decode_request, double_field, field, pack, text_field, unpack

SCHEMA = json.loads(Path(__file__).with_name('mahjong_ways2_schema.json').read_text(encoding='utf-8'))
PHASES = {'ready': 1, 'paid_cascade': 4, 'free_start': 21, 'free_cascade': 22}


def _value(number, kind, value, types):
    if kind in ('int32', 'int64', 'uint32', 'uint64', 'bool'):
        return field(number, 0, int(value))
    if kind == 'double':
        return double_field(number, value)
    if kind == 'string':
        return text_field(number, value)
    if kind == 'bytes':
        return field(number, 2, bytes(value))
    return field(number, 2, encode_message(value, kind, types))


def encode_message(data, name, types):
    pieces = []
    for key, spec in types[name]['fields'].items():
        value = data.get(key)
        if value is None:
            continue
        number, kind = spec['id'], spec['type']
        if 'keyType' in spec:
            # Storage sorts JSON object keys; use a stable wire order for fresh
            # results and cached retries, including multi-digit map keys.
            for map_key in sorted(value, key=int):
                item = value[map_key]
                if kind == 'Int32List':
                    item = {'__value': item}
                entry = _value(1, spec['keyType'], int(map_key), types) + _value(2, kind, item, types)
                pieces.append(field(number, 2, entry))
        elif spec.get('rule') == 'repeated':
            for item in value:
                if kind == 'Int32List':
                    item = {'__value': item}
                pieces.append(_value(number, kind, item, types))
        else:
            pieces.append(_value(number, kind, value, types))
    return b''.join(pieces)


def encode_response(tx):
    return (encode_message(tx, '__root__', SCHEMA['transaction']['nested'])
            + encode_message(tx, '__root__', SCHEMA['wallet']['nested']))


def transaction(event, wallet, thresholds):
    e = event
    amount = lambda value: value / 100
    free = e['free']
    fs = ({'aw': amount(free['award_minor']), 's': free['remaining'],
           'ts': free['total'], 'nosa': free['added']} if free else None)
    rs = None
    if e['refills'] is not None:
        rs = {'rns': e['refills'], 'rnss': e['new_gold'], 'bsb': [],
              'sspt': {k: field(1, 0, old) + field(2, 0, new)
                       for k, (old, new) in e['gold_moves'].items()}}
    ratio = e['win_minor'] / e['base_bet_minor'] if e['base_bet_minor'] else 0
    gwt = -1
    for index, key in enumerate(('mw', 'bw', 'mgw', 'smgw'), 1):
        if ratio >= thresholds[key]:
            gwt = index
    grid = '#'.join(';'.join(str(e['board_before'][col * 7 + row]) for col in range(5)) for row in range(7))
    hash_text = f"{e['multiplier_index']}:{grid}"
    for symbol in sorted(e['winning_positions'], key=int):
        positions = e['winning_positions'][symbol]
        hash_text += '#R#' + symbol + '#' + ''.join(f'{p // 7}{p % 7}' for p in positions)
    hash_text += f"#MV#{amount(e['debit_minor'])}#MT#1#MG#{amount(e['win_minor'])}#"
    return {
        'sid': e['sid'], 'psid': e['round_id'], 'st': PHASES[e['phase']], 'nst': PHASES[e['next_phase']],
        'pf': 1, 'aw': amount(e['round_award_minor']), 'tb': amount(e['debit_minor']),
        'tbb': amount(e['base_bet_minor']), 'tw': amount(e['win_minor']),
        'np': amount(e['win_minor'] - e['debit_minor']), 'ocr': None, 'mr': None,
        'ge': [1, 11], 'pmt': b'', 'wp': e['winning_positions'] or None,
        'lw': {k: amount(v) for k, v in e['base_awards_minor'].items()} or None,
        'ml': e['bet']['level'], 'cs': amount(e['bet']['coin_minor']),
        'rl': e['board_after'], 'orl': e['board_before'], 'ctw': amount(e['win_minor']),
        'cwc': e['combo'], 'fstc': {str(PHASES[k]): v for k, v in e['counts'].items()} or None,
        'pcwc': int(e['phase'] == 'ready' and e['win_minor'] > 0),
        'rwsp': json.dumps(e['rates'], sort_keys=True, separators=(',', ':')) if e['rates'] else None,
        'hashr': hash_text, 'fb': None, 'gwt': gwt, 'snww': e['ways'] or None,
        'ssb': e['gold_before'] or None, 'ss': e['gold_after'] or None, 'fs': fs, 'rs': rs,
        'ssaw': amount(e['spin_award_minor']), 'ptbr': e['removed'] or None,
        'sc': e['scatter_count'], 'mi': e['multiplier_index'], 'wm': e['multiplier'],
        'wid': 0, 'wt': 'C', 'wk': '0_C', 'wbn': None, 'wfg': None,
        'blb': amount(wallet['before_minor']), 'blab': amount(wallet['before_minor'] - wallet['debit_minor']),
        'bl': amount(wallet['after_minor']),
    }


def idle_event(state):
    return dict(sid=state['sid'], round_id='0', phase='ready', next_phase='ready',
                bet=state['bet'], base_bet_minor=0, debit_minor=0, win_minor=0,
                round_award_minor=0, spin_award_minor=0, board_before=state['board'],
                board_after=state['board'], gold_before={}, gold_after={}, refills=None,
                new_gold=None, gold_moves={}, winning_positions={}, ways={}, rates={},
                base_awards_minor={}, removed=[], multiplier=1, multiplier_index=0,
                combo=0, counts={}, free=None, scatter_count=0)


class PGAdapter:
    game_id = 'mahjong-ways2'

    def __init__(self, service):
        self.service = service
        self.game = service.registry.get(self.game_id)

    def spin(self, body):
        try:
            raw, seed = unpack(body)
            request = decode_request(raw)
        except (ValueError, UnicodeError, OverflowError):
            raise ServiceError('SPIN_INVALID', 'Invalid binary Spin request.') from None
        if request.get('btt') != 1 or request.get('pf') != 1 or request.get('wk') != '0_C':
            raise ServiceError('SPIN_INVALID', 'Only the local virtual wallet is supported.')
        if request.get('fb', 0) or request.get('ab', 0):
            raise ServiceError('FEATURE_UNAVAILABLE', 'Feature buys are not implemented.')
        # The legacy client has no explicit idempotency header. Its previous spin
        # id plus normalized request content identifies a single state transition.
        key = 'pg:' + hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        response = self.service.spin(request.get('atk'), self.game_id, key, request.get('id'),
                                     {'cs': request.get('cs'), 'ml': request.get('ml')})
        tx = transaction(response['outcome'], response['wallet'], self.game.config['win_thresholds'])
        return pack(encode_response(tx), seed)

    def game_info(self, token):
        snapshot = self.service.state(token, self.game_id)
        state, balance = snapshot['state'], snapshot['balance_minor']
        event = state['last_event'] or idle_event(state)
        debit, win = event['debit_minor'], event['win_minor']
        wallet = {'before_minor': balance + debit - win, 'after_minor': balance, 'debit_minor': debit}
        tx = transaction(event, wallet, self.game.config['win_thresholds'])
        wire = encode_response(tx)
        # JSON ls is just the startup envelope. The original client reads the
        # fully generated binary transaction through localSpin below.
        json_tx = {k: v for k, v in tx.items() if k not in ('rs', 'pmt')}
        json_tx.update(rs=None, pmt=None)
        c = self.game.config
        return {'dt': {'bl': balance / 100, 'cc': 'AUD', 'cs': [v / 100 for v in c['coin_sizes_minor']],
                       'ml': c['bet_levels'], 'mxl': 20, 'fb': None, 'ls': {'si': json_tx},
                       'wt': c['win_thresholds'], 'inwe': False, 'iuwe': False, 'maxwm': None},
                'err': None, 'localSpin': base64.b64encode(wire).decode(), 'engineMode': 'generated'}

    def wallet(self, token):
        balance = self.service.wallet(token)['balance_minor'] / 100
        return {'dt': {'cc': 'AUD', 'tb': balance, 'pb': 0, 'cb': balance, 'tbb': 0,
                       'tfgb': 0, 'rfgc': 0, 'inbe': False, 'infge': False, 'iebe': False,
                       'iefge': False, 'ch': {'k': '0_C', 'cid': 0, 'cb': balance},
                       'p': None, 'ocr': None, 'bwc': 0, 'fgwc': 0}, 'err': None}
