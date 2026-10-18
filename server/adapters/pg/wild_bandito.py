"""Wild Bandito v4 binary protocol, with the client's game-specific salt 5."""
import hashlib
import json
import struct
from pathlib import Path

from server.core.contracts import ServiceError
from .protocol import decode_request, unpack, pack, field, double_field, text_field
from .wire import encode

SCHEMA = json.loads(Path(__file__).with_name('wild_bandito_schema.json').read_text(encoding='utf-8'))
PHASES = {'ready': 1, 'paid_cascade': 4, 'free_start': 21, 'free_cascade': 22}


def encode_response(tx):
    return encode(tx, SCHEMA['transaction']['nested']) + encode(tx, SCHEMA['wallet']['nested'])


def transaction(e, wallet, thresholds):
    amount = lambda value: value / 100
    free = e['free']
    fs = (dict(aw=amount(free['award_minor']), s=free['remaining'], ts=free['total'],
               nosa=free['added'], gm=free['multiplier']) if free else None)
    rs = (dict(rns=e['refills'], rnss=e['new_gold'], bsb=e['broken_gold'])
          if e['refills'] is not None else None)
    ratio = e['win_minor'] / e['base_bet_minor'] if e['base_bet_minor'] else 0
    gwt = -1
    for i, key in enumerate(('mw', 'bw', 'mgw', 'smgw'), 1):
        if ratio >= thresholds[key]:
            gwt = i
    grid = '#'.join(';'.join(str(e['board_before'][c * 5 + r]) for c in range(5)) for r in range(1, 5))
    hash_text = f"{e['multiplier'] - 1}:{grid}"
    for symbol in sorted(e['winning_positions'], key=int):
        positions = e['winning_positions'][symbol]
        hash_text += '#R#' + symbol + '#' + ''.join(f'{p // 5}{p % 5 - 1}' for p in positions)
    hash_text += f"#MV#{amount(e['debit_minor'])}#MT#1#MG#{amount(e['win_minor'])}#"
    return dict(sid=e['sid'], psid=e['round_id'], st=PHASES[e['phase']], nst=PHASES[e['next_phase']],
                pf=1, ml=e['bet']['level'], cs=amount(e['bet']['coin_minor']),
                rl=e['board_after'], orl=e['board_before'], gm=e['multiplier'],
                wp=e['winning_positions'] or None, lw={k: amount(v) for k, v in e['base_awards_minor'].items()} or None,
                ssb=e['gold_before'] or None, ss=e['gold_after'] or None,
                ptbr=e['removed'] or None, snww=e['ways'] or None, sc=e['scatter_count'], rs=rs, fs=fs,
                ssaw=amount(e['spin_award_minor']), aw=amount(e['round_award_minor']),
                ctw=amount(e['win_minor']), tw=amount(e['win_minor']), tb=amount(e['debit_minor']),
                tbb=amount(e['base_bet_minor']), np=amount(e['win_minor'] - e['debit_minor']),
                cwc=e['combo'], pcwc=int(e['phase'] == 'ready' and e['win_minor'] > 0),
                fstc={str(PHASES[k]): v for k, v in e['counts'].items()} or None,
                rwsp=json.dumps(e['rates'], sort_keys=True, separators=(',', ':')) if e['rates'] else None,
                hashr=hash_text, gwt=gwt, ge=[1, 11], wid=0, wt='C', wk='0_C',
                blb=amount(wallet['before_minor']), blab=amount(wallet['before_minor'] - wallet['debit_minor']),
                bl=amount(wallet['after_minor']))


def idle_event(state):
    return dict(sid=state['sid'], round_id='0', phase='ready', next_phase='ready', bet=state['bet'],
                board_before=state['board'], board_after=state['board'], gold_before={}, gold_after={},
                removed=[], refills=None, new_gold=None, broken_gold=[], free=None, scatter_count=0,
                winning_positions={}, ways={}, rates={}, base_awards_minor={}, multiplier=1,
                base_bet_minor=0, debit_minor=0, win_minor=0, round_award_minor=0, spin_award_minor=0,
                combo=0, counts={})


def request(body):
    try:
        raw, seed = unpack(body, salt=5)
        return decode_request(raw), seed
    except (ValueError, UnicodeError, OverflowError):
        raise ServiceError('SPIN_INVALID', 'Invalid binary request.') from None


class PGAdapter:
    game_id = 'wild-bandito'

    def __init__(self, service):
        self.service = service
        self.game = service.registry.get(self.game_id)

    def spin(self, body, token):
        req, seed = request(body)
        if req.get('atk') != token or req.get('btt') != 2 or req.get('pf') != 1 or req.get('wk') != '0_C':
            raise ServiceError('SPIN_INVALID', 'Invalid wallet or session.')
        if req.get('fb', 0) or req.get('ab', 0):
            raise ServiceError('FEATURE_INVALID', 'This captured operator configuration has no feature buy or ante.')
        identity = {k: v for k, v in req.items() if k != 'atk'}
        key = 'pg:' + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        result = self.service.spin(token, self.game_id, key, req.get('id'), {'cs': req.get('cs'), 'ml': req.get('ml')})
        tx = transaction(result['outcome'], result['wallet'], self.game.config['win_thresholds'])
        return pack(encode_response(tx), seed, salt=5)

    def game_info(self, body, token):
        req, seed = request(body)
        if req.get('atk') != token:
            raise ServiceError('SESSION_INVALID', 'Invalid session.', 401)
        snapshot = self.service.state(token, self.game_id)
        state, balance = snapshot['state'], snapshot['balance_minor']
        event = state['last_event'] or idle_event(state)
        wallet = dict(before_minor=balance + event['debit_minor'] - event['win_minor'],
                      after_minor=balance, debit_minor=event['debit_minor'])
        c = self.game.config
        info = double_field(1, balance / 100) + text_field(4, 'PGC')
        info += field(11, 2, b''.join(struct.pack('<d', v / 100) for v in c['coin_sizes_minor']))
        info += field(12, 2, bytes(c['bet_levels'])) + field(13, 0, 20)
        info += field(22, 2, b''.join(double_field(i, c['win_thresholds'][k]) for i, k in enumerate(('mw', 'bw', 'mgw', 'smgw'), 1)))
        raw = encode_response(transaction(event, wallet, c['win_thresholds'])) + field(900, 2, info)
        return pack(raw, seed, salt=5)

    def wallet(self, token):
        balance = self.service.wallet(token)['balance_minor'] / 100
        return {'dt': dict(cc='PGC', tb=balance, pb=0, cb=balance, tbb=0, tfgb=0, rfgc=0,
                           inbe=False, infge=False, iebe=False, iefge=False,
                           ch=dict(k='0_C', cid=0, cb=balance), p=None, ocr=None, bwc=0, fgwc=0), 'err': None}

    def history(self, token, form, summary=False):
        """Native history models from shared/4528468aab, grouped by paid round."""
        with self.service.connection() as db:
            player = self.service.sessions._player(db, token)
            rows = db.execute('SELECT response_json,created_at FROM spins WHERE player_id=? AND game_id=? ORDER BY id',
                              (player['id'], self.game_id)).fetchall()
        def timestamp(name, default):
            raw = form.get(name, [str(default)])[0]
            return int(raw) if raw else default
        start, end = timestamp('dtf', 0), timestamp('dtt', 253402300799000)
        groups = {}
        for row in rows:
            response = json.loads(row['response_json'])
            e = response['outcome']
            bt = row['created_at'] * 1000
            group = groups.setdefault(e['round_id'], dict(bt=bt, tid=e['round_id'], gtba=0, gtwla=0,
                gtwa=0, cc='PGC', ge=[1, 11], bd=[], mgcc=0, fscc=0, wm=1))
            tx = transaction(e, response['wallet'], self.game.config['win_thresholds'])
            tx['tst'] = group['bt']
            group['bd'].append(dict(bl=tx['bl'], bt=bt, gd=tx, ib=False, tba=tx['tb'], tid=e['sid'], twla=tx['np']))
            group['gtba'] += e['debit_minor']
            group['gtwa'] += e['win_minor']
            group['mgcc'] += int(e['phase'] == 'paid_cascade')
            group['fscc'] += int(e['phase'] == 'free_cascade')
            group['wm'] = max(group['wm'], e['multiplier'])
        records = [v for v in reversed(list(groups.values())) if start <= v['bt'] <= end]
        for r in records:
            r['gtwla'] = (r['gtwa'] - r['gtba']) / 100
            r['gtba'] /= 100
            r['gtwa'] /= 100
        if summary:
            return {'dt': {'lut': records[0]['bt'] if records else 0,
                           'bs': dict(bc=len(records), btba=round(sum(r['gtba'] for r in records), 2),
                                      btwla=round(sum(r['gtwla'] for r in records), 2),
                                      btwa=round(sum(r['gtwa'] for r in records), 2), gid=104,
                                      lbid=records[0]['tid'] if records else '0') if records else None}, 'err': None}
        page = max(1, timestamp('bn', 1))
        count = min(100, max(1, timestamp('rc', 20)))
        return {'dt': {'bh': records[(page - 1) * count:page * count]}, 'err': None}
