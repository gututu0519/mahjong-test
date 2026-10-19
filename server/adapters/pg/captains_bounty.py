"""Captain's Bounty v4 binary protocol; game 54 uses digit sum/salt 9."""
import hashlib
import json
import struct
from pathlib import Path

from server.core.contracts import ServiceError
from .protocol import decode_request, unpack, pack, field, double_field, text_field
from .wire import encode

SCHEMA = json.loads(Path(__file__).with_name('captains_bounty_schema.json').read_text(encoding='utf-8'))
SALT = 9
PHASES = {'ready': 1, 'paid_cascade': 4, 'free_start': 21, 'free_cascade': 22}


def encode_response(tx):
    return encode(tx, SCHEMA['transaction']['nested']) + encode(tx, SCHEMA['wallet']['nested'])


def transaction(e, wallet, thresholds=None):
    amount = lambda value: value / 100
    free = e['free']
    cascade = e['phase'] in ('paid_cascade', 'free_cascade')
    rs = (dict(bw=amount(e['base_win_minor']) if e['phase'] != 'ready' else 0,
               aw=amount(e['spin_award_minor'])) if e['win_minor'] or cascade else None)
    return dict(sid=e['sid'], psid=e['round_id'], st=PHASES[e['phase']], nst=PHASES[e['next_phase']],
                pf=1, ml=e['bet']['level'], cs=amount(e['bet']['coin_minor']), rl=e['board'],
                wp=e['winning_positions'] or None,
                lw={k: amount(v) for k, v in e['base_awards_minor'].items()} or None,
                lwm={k: amount(v * e['multiplier']) for k, v in e['base_awards_minor'].items()} or None,
                wm=e['multiplier'], rns=e['refills'], rs=rs,
                fs=dict(s=free['remaining'], ts=free['total'],
                        **{'as': {'__value': free['added']} if free['added'] else {}},
                        aw=amount(free['award_minor'])) if free else None,
                aw=amount(e['round_award_minor']), tw=amount(e['win_minor']), tb=amount(e['debit_minor']),
                tbb=amount(e['base_bet_minor']), np=amount(e['win_minor'] - e['debit_minor']),
                ge=[2 if free else 1, 11], wid=0, wt='C', wk='0_C',
                blb=amount(wallet['before_minor']), blab=amount(wallet['before_minor'] - wallet['debit_minor']),
                bl=amount(wallet['after_minor']))


def request(body):
    try:
        raw, seed = unpack(body, salt=SALT)
        return decode_request(raw), seed
    except (ValueError, UnicodeError, OverflowError):
        raise ServiceError('SPIN_INVALID', 'Invalid binary request.') from None


class PGAdapter:
    game_id = 'captains-bounty'

    def __init__(self, service):
        self.service = service
        self.game = service.registry.get(self.game_id)

    def spin(self, body, token):
        req, seed = request(body)
        if req.get('atk') != token or req.get('btt') != 2 or req.get('pf') != 1 or req.get('wk') != '0_C':
            raise ServiceError('SPIN_INVALID', 'Invalid wallet or session.')
        if req.get('fb', 0) or req.get('ab', 0):
            raise ServiceError('FEATURE_INVALID', 'Captured operator does not enable buy or ante.')
        identity = {k: v for k, v in req.items() if k != 'atk'}
        key = 'pg:' + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        result = self.service.spin(token, self.game_id, key, req.get('id'), {'cs': req.get('cs'), 'ml': req.get('ml')})
        return pack(encode_response(transaction(result['outcome'], result['wallet'])), seed, salt=SALT)

    def game_info(self, body, token):
        req, seed = request(body)
        if req.get('atk') != token:
            raise ServiceError('SESSION_INVALID', 'Invalid session.', 401)
        snapshot = self.service.state(token, self.game_id)
        state, balance = snapshot['state'], snapshot['balance_minor']
        event = state['last_event']
        if event is None:
            event = dict(sid='0', round_id='0', phase='ready', next_phase='ready', bet=state['bet'],
                         board=state['board'], winning_positions={}, base_awards_minor={}, base_win_minor=0,
                         multiplier=1, refills=None, free=None, win_minor=0, debit_minor=0,
                         base_bet_minor=0, round_award_minor=0, spin_award_minor=0)
        wallet = dict(before_minor=balance + event['debit_minor'] - event['win_minor'],
                      after_minor=balance, debit_minor=event['debit_minor'])
        c = self.game.config
        info = double_field(1, balance / 100) + text_field(4, 'PGC')
        info += field(11, 2, b''.join(struct.pack('<d', v / 100) for v in c['coin_sizes_minor']))
        info += field(12, 2, bytes(c['bet_levels'])) + field(13, 0, 20)
        info += field(22, 2, b''.join(double_field(i, c['win_thresholds'][k]) for i, k in enumerate(('mw', 'bw', 'mgw', 'smgw'), 1)))
        info += field(23, 2, field(1, 0, 30000))
        return pack(encode_response(transaction(event, wallet)) + field(900, 2, info), seed, salt=SALT)

    def wallet(self, token):
        balance = self.service.wallet(token)['balance_minor'] / 100
        return {'dt': dict(cc='PGC', tb=balance, pb=0, cb=balance, tbb=0, tfgb=0, rfgc=0,
                           inbe=False, infge=False, iebe=False, iefge=False,
                           ch=dict(k='0_C', cid=0, cb=balance), p=None, ocr=None, bwc=0, fgwc=0), 'err': None}


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
            group = groups.setdefault(e['round_id'], dict(bt=bt, tid=e['round_id'], gid=54, gtba=0, gtwa=0,
                gtwla=0, cc='PGC', ge=[1, 11], bd=[], fscc=0, mgcc=0))
            tx = transaction(e, wallet, self.game.config['win_thresholds'])
            if e['phase'] == 'ready':
                group['ge'] = tx['ge']
            tx['tst'] = group['bt']
            group['bd'].append(dict(bl=tx['bl'], bt=bt, gd=tx, ib=False, tba=tx['tb'], tid=e['sid'], twla=tx['np']))
            group['gtba'] += e['debit_minor']
            group['gtwa'] += e['win_minor']
            group['fscc'] += int(e['phase'] == 'free_start')
            group['mgcc'] += int(e['phase'] in ('paid_cascade', 'free_cascade'))
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
                        gid=54, lbid=records[0]['tid']) if records else None), 'err': None}
        page, count = max(1, number('bn', 1)), min(100, max(1, number('rc', 20)))
        return {'dt': {'bh': records[(page - 1) * count:page * count]}, 'err': None}
