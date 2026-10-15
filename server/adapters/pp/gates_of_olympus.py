import json
import threading
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs
from server.core.contracts import ServiceError


def money(value):
    return f'{value // 100}.{value % 100:02d}'


def transaction(e):
    bet = e['bet']
    d = {'s': ','.join(map(str, e['board'])), 'sa': ','.join(map(str, e['sa'])),
         'sb': ','.join(map(str, e['sb'])), 'sh': '5', 'c': money(bet['coin_minor']),
         'l': '20', 'bl': str(int(bet['ante'])), 'reel_set': str(e['reel_set']),
         'w': money(e['delta_minor']), 'tw': money(e['total_minor']),
         'na': 'c' if e['next_phase'] == 'collect' else 's', 'accm': 'cp', 'acci': '0',
         'accv': str(e['accumulator'])}
    if e.get('purchased'):
        d['puri'] = '0'
    if e.get('purchase_trigger'):
        d['purtr'] = '1'
    if e['orbs']:
        d['rmul'] = ';'.join(f'12~{p}~{v}' for p, v in sorted(e['orbs'].items(), key=lambda x: int(x[0])))
    if e['positions'] and not e['capped']:
        cells = sorted(p for ps in e['positions'].values() for p in ps)
        d.update(tmb='~'.join(f'{p},{e["board"][p]}' for p in cells), rs='mc', rs_p=str(e['tumble']), rs_c='1', rs_m='1')
        for i, (symbol, ps) in enumerate(e['positions'].items()):
            d['l' + str(i)] = '~'.join(['0', money(e['awards_minor'][symbol]), *map(str, ps)])
    if e['sequence_minor']:
        d['tmb_win'] = money(e['sequence_minor'])
        if e['ended'] or e['capped']:
            d.update(tmb_res=money(min(e['sequence_minor'] + e['extra_minor'], e['total_minor'])), rs_t=str(e['tumble']))
    if e['extra_minor']:
        d.update(apwa=money(e['extra_minor']), apt='tumbling_win_mul', apv=str(e['multiplier']))
    if e['scatter_minor']:
        d['psym'] = '1~' + money(e['scatter_minor']) + '~' + ','.join(str(p) for p, s in enumerate(e['board']) if s == 1)
    free = e['free']
    if free:
        final = e['free_spin'] and (free['played'] >= free['total'] or e['capped'])
        if final:
            d.update(fs_total=str(free['total']), fswin_total=money(free['win_minor']), fsres_total=money(free['win_minor']),
                     fsmul_total='1', fsend_total=str(int(e['next_phase'] == 'collect')))
        else:
            d.update(fs=str(free['played'] + 1), fsmax=str(free['total']), fswin=money(free['win_minor']),
                     fsres=money(free['win_minor']), fsmul='1')
    return d


class PPAdapter:
    game_id = 'gates-of-olympus'

    def __init__(self, service, initial):
        self.service, self.initial = service, initial
        # Serializes read-current-state + service CAS within this HTTP process.
        # SQLite uniqueness and the settlement CAS still protect other writers.
        self.lock = threading.RLock()

    def handle(self, form):
        if any(len(v) != 1 for v in form.values()):
            raise ServiceError('REQUEST_INVALID', 'Duplicate form fields.')
        q = {k: v[0] for k, v in form.items()}
        if q.get('symbol') != 'vs20olympgate':
            raise ServiceError('GAME_NOT_FOUND', 'Unknown game.', 404)
        token, action = q.get('mgckey'), q.get('action')
        try:
            index, counter = int(q.get('index', '0')), int(q.get('counter', '0'))
            if not 1 <= index <= 1_000_000_000 or not 1 <= counter <= 2_000_000_000:
                raise ValueError()
        except ValueError:
            raise ServiceError('REQUEST_INVALID', 'Invalid request sequence.') from None
        with self.lock:
            snapshot = self.service.state(token, self.game_id)
            s, balance = snapshot['state'], snapshot['balance_minor']
            if action == 'doInit':
                d = dict(self.initial)
                for key in ('rtp', 'gameInfo'):
                    d.pop(key, None)
                # No claim that the local generation weights reproduce provider RTP.
                d['gameInfo'] = '{props:{max_rnd_win:"5000",max_rnd_win_a:"4000"}}'
                d.update(s=','.join(map(str, s['board'])), c=money(s['bet']['coin_minor']),
                         bl=str(int(s['bet']['ante'])), na='s', w='0.00', tw='0.00')
                if s['phase'] != 'ready' and s['last_event']:
                    d.update(transaction(s['last_event']))
                index = max(index, s['protocol_index'])
                counter = max(counter + 1, index * 2)
            elif action in ('doSpin', 'doCollect'):
                if (q.get('pur', '') not in ('', '-1', '0')
                        or any(q.get(k, '') not in ('', '-1') for k in ('buy', 'fsbuy'))
                        or (action == 'doCollect' and q.get('pur') == '0')):
                    raise ServiceError('PURCHASE_INVALID', 'Invalid purchase option.', 400)
                command = {'action': 'collect' if action == 'doCollect' else 'buy' if q.get('pur') == '0' else 'spin', 'request_index': index}
                if action == 'doSpin':
                    try:
                        coin = Decimal(q.get('c', '')) * 100
                        if not coin.is_finite() or coin != coin.to_integral_value() or q.get('l') != '20' or q.get('bl', '0') not in ('0', '1'):
                            raise ValueError()
                        command.update(coin_minor=int(coin), ante=q.get('bl', '0') == '1')
                    except (ValueError, InvalidOperation, OverflowError):
                        raise ServiceError('BET_INVALID', 'Invalid PP bet.') from None
                key = 'pp:' + str(index)
                previous = s['sid']
                # A transport retry must use its ORIGINAL previous_sid, even after later requests.
                with self.service.connection() as db:
                    player = self.service.sessions._player(db, token)
                    cached = db.execute('SELECT request_json FROM spins WHERE player_id=? AND game_id=? AND request_key=?',
                                        (player['id'], self.game_id, key)).fetchone()
                    if cached:
                        previous = json.loads(cached[0])['previous_sid']
                result = self.service.spin(token, self.game_id, key, previous, command)
                d = transaction(result['outcome']) if action == 'doSpin' else {'na': 's'}
                balance = result['wallet']['after_minor']
                counter += 1
            else:
                raise ServiceError('ACTION_UNSUPPORTED', 'Unsupported game action.', 400)
            d.update(balance=money(balance), balance_cash=money(balance), balance_bonus='0.00',
                     index=str(index), counter=str(counter), sver='5', ntp=money_signed(balance - 200000), stime='0')
            return d


def money_signed(value):
    return ('-' if value < 0 else '') + money(abs(value))
