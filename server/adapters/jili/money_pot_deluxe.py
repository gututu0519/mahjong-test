"""Local JILI transport using the captured Money Pot DELUXE protobuf definitions."""
import copy
import json
import time
from decimal import Decimal
from pathlib import Path
from server.adapters.jili.wire import encode, decode, varint
from server.core.contracts import ServiceError

SCHEMAS = json.loads((Path(__file__).parents[1] / 'jili/super_ace_schema.json').read_text(encoding='utf-8'))
SCHEMAS.update(json.loads(Path(__file__).with_name('money_pot_deluxe_schema.json').read_text(encoding='utf-8')))
CLIENT = Path(__file__).resolve().parents[3] / 'clients/money-pot-deluxe'


def pack(name, value):
    return list(encode(SCHEMAS[name], value, SCHEMAS))


def unpack(name, value):
    return decode(SCHEMAS[name], value, SCHEMAS)


class Adapter:
    def __init__(self, service):
        self.service = service
        self.login_template = json.loads((CLIENT / 'fixtures/login.json').read_text(encoding='utf-8'))
        self.info_template = json.loads((CLIENT / 'fixtures/info.json').read_text(encoding='utf-8'))

    def login(self, token):
        wallet = self.service.wallet(token)
        data = copy.deepcopy(self.login_template)
        data['token'] = token
        data['profile']['coin'] = wallet['balance_minor'] / 10000
        data['response']['time'] = int(time.time())
        return data

    def info(self, token):
        state = self.service.state(token, 'money-pot-deluxe')
        data = copy.deepcopy(self.info_template)
        data['WalletInfo'][0]['coin'] = state['balance_minor'] / 10000
        data['WalletInfo'][0]['bet'] = [b / 10000 for b in self.service.registry.get('money-pot-deluxe').config['bets_minor']]
        data['lastBet'] = state['state']['last_bet_minor'] / 10000
        data['extraInfo'] = pack('GameInfoData', {'Mul': [1, 1.5, 3, 6]})
        return pack('GameInfoAck', data)

    def handle(self, token, ack, payload, key):
        if type(ack) is not int or not isinstance(payload, list) or len(payload) > 16384 or any(type(v) is not int or not 0 <= v <= 255 for v in payload):
            raise ServiceError('INVALID_REQUEST', 'Invalid JILI request.')
        if ack == 1:
            data = self.info(token)
        elif ack == 2:
            import struct
            money = self.service.wallet(token)['balance_minor'] / 10000
            notice = b'\x08\x04\x11' + struct.pack('<d', money) + b'\x28\x03'
            data = list(b'\x0a' + varint(len(notice)) + notice)
        elif ack in (0, 4, 36):
            state = self.service.state(token, 'money-pot-deluxe')
            if ack == 0:
                req = unpack('SpinReq', payload)
                if set(req) - {'bet', 'special', 'extraSpin', 'clientRecord'}:
                    raise ServiceError('BET_INVALID', "Unsupported Money Pot DELUXE spin request.")
                if any(req.get('special', {}).values()):
                    # Turbo changes presentation only; tournament/cheat are unsupported.
                    if set(k for k, v in req['special'].items() if v) - {'turbo'}:
                        raise ServiceError('BET_INVALID', 'Unsupported spin option.')
                if 'extraSpin' in req and req['extraSpin'].get('Index', 0) not in range(3):
                    raise ServiceError('BET_INVALID', 'Invalid Extra Bet selection.')
                amount = Decimal(str(req.get('bet', 0))) * 10000
                if not amount.is_finite() or amount != amount.to_integral_value():
                    raise ServiceError('BET_INVALID', 'Invalid bet precision.')
                previous_sid = state['state']['sid']
                with self.service.connection() as db:
                    player = self.service.sessions._player(db, token)
                    cached = db.execute('SELECT request_json FROM spins WHERE player_id=? AND game_id=? AND request_key=?',
                                        (player['id'], 'money-pot-deluxe', key)).fetchone()
                    if cached:
                        previous_sid = json.loads(cached['request_json'])['previous_sid']
                result = self.service.spin(token, 'money-pot-deluxe', key, previous_sid,
                                           dict(bet_minor=int(amount), extra=req.get('extraSpin', {}).get('Index', 0) + 1 if 'extraSpin' in req else 0))
                event, money, sid = result['outcome'], result['wallet']['after_minor'], result['sid']
            else:
                event, money, sid = state['state']['last_event'], state['balance_minor'], state['state']['sid']
                if not event:
                    return dict(type=ack, ret=0, error_msg='', data=[])
                req = {'bet': event['bet_minor'] / 10000}
                if event['extra']:
                    req['extraSpin'] = {'Index': event['extra'] - 1}
            data = pack('SpinResponse', dict(data=pack('SpinAck', event['spin']), service={},
                        totalWin=event['total_minor'] / 10000, postMoney=money / 10000,
                        roundIndexV2=int(sid), spinReq=req))
        else:
            self.service.wallet(token)
            raise ServiceError('ACK_UNSUPPORTED', 'Unrecognized JILI command: ' + str(ack))
        return dict(type=ack, ret=0, error_msg='', data=data)
