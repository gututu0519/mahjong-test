"""Fortune Rabbit v4 transport (game index 1543462, digit sum/salt 25)."""
import hashlib
import json
import random
import struct
from pathlib import Path

from server.core.contracts import ServiceError
from .protocol import decode_request, unpack, pack, field, double_field, text_field
from .wire import encode

SCHEMA = json.loads(Path(__file__).with_name('fortune_rabbit_schema.json').read_text(encoding='utf-8'))
SALT = 25
PHASES = {'ready': 1, 'free': 2}


def encode_response(tx):
    return encode(tx, SCHEMA['transaction']['nested']) + encode(tx, SCHEMA['wallet']['nested'])


def transaction(e, wallet, thresholds):
    amount = lambda value: value / 100
    free = e['free']
    # Original final-spin response keeps fs.aw at the amount before the last
    # prize (capture 1256: fs.aw=174, tw=21, aw=195). The durable state and
    # wallet still contain the full award; this is a wire-format distinction.
    free_award = free['award_minor'] if free else 0
    if (free and e['phase'] == 'free' and e['next_phase'] == 'ready'
            and e.get('step', 0) == free['total'] - 1):
        free_award -= e['win_minor']
    ratio = e['win_minor'] / e['base_bet_minor'] if e['base_bet_minor'] else 0
    gwt = -1
    for i, key in enumerate(('mw', 'bw', 'mgw', 'smgw'), 1):
        if ratio >= thresholds[key]:
            gwt = i
    board = e['board']
    grid = '#'.join(';'.join(str(board[c * 4 + r]) for c in range(3)) for r in range(4))
    hash_text = str(e.get('step', 0)) + ':' + grid
    for line in e['winning_positions'].values():
        symbol = next((board[p] for p in line if board[p]), 0)
        hash_text += '#R#' + str(symbol) + '#' + ''.join(f'{p // 4}{p % 4}' for p in line)
        hash_text += f"#MV#{amount(e['base_bet_minor'])}#MT#1"
    hash_text += f"#MV#{amount(e['debit_minor'])}#MT#1#MG#{amount(e['win_minor'])}#"
    cash_paid = e['cash_win_minor'] > 0
    return dict(sid=e['sid'], psid=e['round_id'], st=PHASES[e['phase']], nst=PHASES[e['next_phase']],
                pf=1, ml=e['bet']['level'], cs=amount(e['bet']['coin_minor']),
                rl=board, orl=board, wp=e['winning_positions'] or None,
                lw={k: amount(v) for k, v in e['line_awards_minor'].items()} or None,
                cpf=e['prizes'] or None, cptw=amount(e['cash_win_minor']),
                crtw=0, iff=e['next_phase'] == 'free',
                ift=e.get('feature_teaser', False), imw=e['max_win'],
                fs=dict(aw=amount(free_award), s=free['remaining'], ts=free['total']) if free else None,
                aw=amount(e['round_award_minor']), ctw=amount(e['win_minor']),
                tw=amount(e['win_minor']), tb=amount(e['debit_minor']), tbb=amount(e['base_bet_minor']),
                np=amount(e['win_minor'] - e['debit_minor']),
                cwc=e.get('combo', int(e['win_minor'] > 0)), pcwc=e.get('paid_combo', int(e['win_minor'] > 0)),
                fstc={'2': e.get('step', 0)} if free and e.get('step', 0) else None,
                rwsp=json.dumps(e['rates'], sort_keys=True, separators=(',', ':')) if e['rates'] else None,
                hashr=hash_text, gwt=gwt, ge=[3 if cash_paid else 2 if e['next_phase'] == 'free' else 1, 11], wid=0, wt='C', wk='0_C',
                blb=amount(wallet['before_minor']), blab=amount(wallet['before_minor'] - wallet['debit_minor']),
                bl=amount(wallet['after_minor']))


def request(body):
    try:
        raw, seed = unpack(body, salt=SALT)
        return decode_request(raw), seed
    except (ValueError, UnicodeError, OverflowError):
        raise ServiceError('SPIN_INVALID', 'Invalid binary request.') from None


class PGAdapter:
    game_id = 'fortune-rabbit'

    def __init__(self, service):
        self.service = service
        self.game = service.registry.get(self.game_id)

    def wallet(self, token):
        balance = self.service.wallet(token)['balance_minor'] / 100
        return {'dt': dict(cc='PGC', tb=balance, pb=0, cb=balance, tbb=0, tfgb=0, rfgc=0,
                           inbe=False, infge=False, iebe=False, iefge=False,
                           ch=dict(k='0_C', cid=0, cb=balance), p=None, ocr=None, bwc=0, fgwc=0), 'err': None}

    def spin(self, body, token):
        req, seed = request(body)
        if req.get('atk') != token or req.get('btt') != 2 or req.get('pf') != 1 or req.get('wk') != '0_C':
            raise ServiceError('SPIN_INVALID', 'Invalid wallet or session.')
        if req.get('fb', 0) or req.get('ab', 0):
            raise ServiceError('FEATURE_INVALID', 'The captured operator does not enable feature buy or ante.')
        identity = {k: v for k, v in req.items() if k != 'atk'}
        key = 'pg:' + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        result = self.service.spin(token, self.game_id, key, req.get('id'), {'cs': req.get('cs'), 'ml': req.get('ml')})
        tx = transaction(result['outcome'], result['wallet'], self.game.config['win_thresholds'])
        return pack(encode_response(tx), seed, salt=SALT)

    def game_info(self, body, token):
        req, seed = request(body)
        if req.get('atk') != token:
            raise ServiceError('SESSION_INVALID', 'Invalid session.', 401)
        snapshot = self.service.state(token, self.game_id)
        state, balance = snapshot['state'], snapshot['balance_minor']
        event = state['last_event']
        if event is None:
            event = dict(sid=state['sid'], round_id='0', phase='ready', next_phase='ready', bet=state['bet'],
                         board=state['board'], winning_positions={}, rates={}, line_awards_minor={},
                         line_win_minor=0, cash_win_minor=0, win_minor=0, debit_minor=0,
                         base_bet_minor=state['bet']['coin_minor'] * state['bet']['level'] * 10,
                         prizes=self.game._prizes(random.Random('idle'), state['board'],
                             state['bet']['coin_minor'] * state['bet']['level'] * 10),
                         round_award_minor=0, feature=False, feature_trigger=False, max_win=False, free=None)
        wallet = dict(before_minor=balance + event['debit_minor'] - event['win_minor'],
                      after_minor=balance, debit_minor=event['debit_minor'])
        c = self.game.config
        info = double_field(1, balance / 100) + text_field(4, 'PGC')
        info += field(11, 2, b''.join(struct.pack('<d', v / 100) for v in c['coin_sizes_minor']))
        info += field(12, 2, bytes(c['bet_levels'])) + field(13, 0, 10)
        info += field(22, 2, b''.join(double_field(i, c['win_thresholds'][k]) for i, k in enumerate(('mw', 'bw', 'mgw', 'smgw'), 1)))
        info += field(23, 2, field(1, 0, 5000))
        raw = encode_response(transaction(event, wallet, c['win_thresholds'])) + field(900, 2, info)
        return pack(raw, seed, salt=SALT)

    def history(self, token, form, summary=False):
        with self.service.connection() as db:
            player = self.service.sessions._player(db, token)
            rows = db.execute('SELECT response_json,created_at FROM spins WHERE player_id=? AND game_id=? ORDER BY id',
                              (player['id'], self.game_id)).fetchall()

        def number(name, default):
            return int(form.get(name, [str(default)])[0] or default)

        groups = {}
        for row in rows:
            response = json.loads(row['response_json'])
            e, wallet = response['outcome'], response['wallet']
            bt = row['created_at'] * 1000
            group = groups.setdefault(e['round_id'], dict(bt=bt, tid=e['round_id'], gid=1543462, gtba=0, gtwa=0,
                gtwla=0, cc='PGC', ge=[1, 11], bd=[], fscc=0, mgcc=0))
            tx = transaction(e, wallet, self.game.config['win_thresholds'])
            if e['phase'] == 'ready':
                group['ge'] = tx['ge']
            tx['tst'] = group['bt']
            group['bd'].append(dict(bl=tx['bl'], bt=bt, gd=tx, ib=False, tba=tx['tb'], tid=e['sid'], twla=tx['np']))
            group['gtba'] += e['debit_minor']
            group['gtwa'] += e['win_minor']
            group['fscc'] += int(e['feature'])
            if e['free']:
                group['ge'] = [2, 11]
        start, end = number('dtf', 0), number('dtt', 253402300799000)
        records = [v for v in reversed(list(groups.values())) if start <= v['bt'] <= end]
        for record in records:
            record['gtwla'] = (record['gtwa'] - record['gtba']) / 100
            record['gtba'] /= 100
            record['gtwa'] /= 100
        if summary:
            return {'dt': dict(lut=records[0]['bt'] if records else 0,
                bs=dict(bc=len(records), btba=round(sum(r['gtba'] for r in records), 2),
                        btwla=round(sum(r['gtwla'] for r in records), 2), btwa=round(sum(r['gtwa'] for r in records), 2),
                        gid=1543462, lbid=records[0]['tid']) if records else None), 'err': None}
        page, count = max(1, number('bn', 1)), min(100, max(1, number('rc', 20)))
        return {'dt': {'bh': records[(page - 1) * count:page * count]}, 'err': None}
