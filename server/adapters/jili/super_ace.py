"""Plain local transport for the original JILI client protobuf payloads."""
import copy
import json
import time
from decimal import Decimal
from pathlib import Path
from server.core.contracts import ServiceError
from .wire import encode, decode

SCHEMAS = json.loads(Path(__file__).with_name('super_ace_schema.json').read_text(encoding='utf-8'))
ROOT = Path(__file__).resolve().parents[3]
CLIENT = ROOT / 'clients/super-ace'


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
        state = self.service.state(token, 'super-ace')
        data = copy.deepcopy(self.info_template)
        data['WalletInfo'][0]['coin'] = state['balance_minor'] / 10000
        data['lastBet'] = state['state']['last_bet_minor'] / 10000
        return pack('GameInfoAck', data)

    def handle(self, token, ack, payload, key):
        if type(ack) is not int or not isinstance(payload, list) or len(payload) > 16384 or any(type(v) is not int or not 0 <= v <= 255 for v in payload):
            raise ServiceError('INVALID_REQUEST', 'Invalid JILI request.')
        data = []
        if ack == 1:
            data = self.info(token)
        elif ack == 2:
            # NoticeResponse -> NoticeInfo(balance=4, money, currencyNumber=3).
            from .wire import varint
            import struct
            money = self.service.wallet(token)['balance_minor'] / 10000
            notice = b'\x08\x04\x11' + struct.pack('<d', money) + b'\x28\x03'
            data = list(b'\x0a' + varint(len(notice)) + notice)
        elif ack in (0, 4, 36):
            state = self.service.state(token, 'super-ace')
            if ack == 0:
                req = unpack('SpinReq', payload)
                amount = Decimal(str(req.get('bet', 0))) * 10000
                if not amount.is_finite() or amount != amount.to_integral_value():
                    raise ServiceError('BET_INVALID', 'Invalid bet precision.')
                buy = 'mall' in req
                if buy:
                    mall = req['mall']
                    if mall.get('Type', 0) != 0 or mall.get('Index', 0) != 0 or Decimal(str(mall.get('Bet', 0))) * 10000 != amount * Decimal('40.5'):
                        raise ServiceError('BET_INVALID', 'Purchase price does not match the bet.')
                if req.get('extraSpin') or req.get('freeSpin'):
                    raise ServiceError('BET_INVALID', 'Free games are included in the original round response.')
                previous_sid = state['state']['sid']
                with self.service.connection() as db:
                    player = self.service.sessions._player(db, token)
                    cached = db.execute('SELECT request_json FROM spins WHERE player_id=? AND game_id=? AND request_key=?',
                                        (player['id'], 'super-ace', key)).fetchone()
                    if cached:
                        previous_sid = json.loads(cached['request_json'])['previous_sid']
                result = self.service.spin(token, 'super-ace', key, previous_sid,
                                           dict(bet_minor=int(amount), buy_bonus=buy))
                event, money, sid = result['outcome'], result['wallet']['after_minor'], result['sid']
            else:
                self.service.wallet(token)
                event, money, sid = state['state']['last_event'], state['balance_minor'], state['state']['sid']
                if not event:
                    return dict(type=ack, ret=0, error_msg='', data=[])
                req = {'bet': event['bet_minor']/10000}
            data = pack('SpinResponse', dict(data=pack('AllPlate', {'plate': event['plates']}),
                        service={}, totalWin=event['total_minor']/10000, postMoney=money/10000,
                        roundIndexV2=int(sid), spinReq=req))
        else:
            self.service.wallet(token)
            raise ServiceError('ACK_UNSUPPORTED', 'Unrecognized JILI command: ' + str(ack))
        return dict(type=ack, ret=0, error_msg='', data=data)
