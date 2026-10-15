import json
import threading
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs
from server.core.contracts import ServiceError


def money(value):
    return f'{value // 100}.{value % 100:02d}'


def transaction(e):
    d = {'s': ','.join(map(str,e['board'])), 'sa': ','.join(map(str,e['sa'])),
         'sb': ','.join(map(str,e['sb'])), 'sh': '3', 'c': money(e['bet']['coin_minor']),
         'l': '10', 'reel_set': str(e['reel_set']), 'w': money(e['delta_minor']),
         'tw': money(e['total_minor']), 'na': 'c' if e['next_phase'] == 'collect' else 's'}
    for i, win in enumerate(e['wins']):
        d['l'+str(i)] = '~'.join([str(win['line']), money(win['amount']), *map(str,win['positions'])])
    if any(e['values']) or e['free_spin']:
        d['mo'] = ','.join(str(e['multiplier'] if e['free_spin'] and s == 2 else v) for s,v in zip(e['board'],e['values']))
        d['mo_t'] = ','.join('mma' if e['free_spin'] and s == 2 else 'v' if s == 7 else 'r' for s in e['board'])
    if e['fish_win']:
        d['mo_tw'] = money(e['fish_win'])
        d['mo_tv'] = str(e['fish_win'] // e['bet']['coin_minor'])
        d['mo_c'] = '1'
    f = e['free']
    if f:
        if e['free_spin']:
            d.update(accv=str(f['collectors'])+';'+str(f['stage']+1)+'~4', accm='cp;cp~mp', acci='0;1')
        if e['free_spin'] and e['next_phase'] == 'collect':
            d.update(fs_total=str(f['played']), fswin_total=money(f['win_minor']),
                     fsres_total=money(f['win_minor']), fsmul_total='1', fsend_total='1')
        else:
            d.update(fs=str(f['played']+1), fsmax=str(f['total']),
                     fswin=money(f['win_minor']), fsres=money(f['win_minor']), fsmul='1')
        if e['free_spin'] and e['free_awarded']:
            d['fsmore'] = str(e['free_awarded'])
    return d


class PPAdapter:
    game_id = 'big-bass-bonanza'

    def __init__(self, service, initial):
        self.service, self.initial = service, initial
        # Serializes read-current-state + service CAS within this HTTP process.
        # SQLite uniqueness and the settlement CAS still protect other writers.
        self.lock = threading.RLock()

    def handle(self, form):
        if any(len(v) != 1 for v in form.values()):
            raise ServiceError('REQUEST_INVALID', 'Duplicate form fields.')
        q = {k: v[0] for k, v in form.items()}
        if q.get('symbol') != 'vs10bbbonanza':
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
                d['gameInfo'] = '{props:{max_rnd_win:"2100"}}'
                d.update(s=','.join(map(str,s['board'])), c=money(s['bet']['coin_minor']),
                         sa=','.join(map(str,s['sa'])), sb=','.join(map(str,s['sb'])), reel_set=str(s['reel_set']),
                         na='s', w='0.00', tw='0.00')
                if s['phase'] != 'ready' and s['last_event']:
                    d.update(transaction(s['last_event']))
                index = max(index, s['protocol_index'])
                counter = max(counter + 1, index * 2)
            elif action in ('doSpin', 'doCollect'):
                if (q.get('pur', '') not in ('', '-1')
                        or any(q.get(k, '') not in ('', '-1') for k in ('buy', 'fsbuy'))
                        or (action == 'doCollect' and q.get('pur') == '0')):
                    raise ServiceError('PURCHASE_INVALID', 'Invalid purchase option.', 400)
                command = {'action': 'collect' if action == 'doCollect' else 'spin', 'request_index': index}
                if action == 'doSpin':
                    try:
                        coin = Decimal(q.get('c', '')) * 100
                        if not coin.is_finite() or coin != coin.to_integral_value() or q.get('l') != '10' or q.get('bl', '0') != '0':
                            raise ValueError()
                        command.update(coin_minor=int(coin))
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
