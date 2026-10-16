"""Local TaDa transport using the captured Roma X 10000 protobuf definitions."""
import copy
import json
import time
from decimal import Decimal
from pathlib import Path
from server.adapters.jili.wire import encode, decode, varint
from server.core.contracts import ServiceError

SCHEMAS = json.loads((Path(__file__).parents[1] / 'jili/super_ace_schema.json').read_text(encoding='utf-8'))
SCHEMAS.update(json.loads(Path(__file__).with_name('roma_x_10000_schema.json').read_text(encoding='utf-8')))
CLIENT = Path(__file__).resolve().parents[3] / 'clients/roma-x-10000'


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
        state = self.service.state(token, 'roma-x-10000')
        data = copy.deepcopy(self.info_template)
        data['WalletInfo'][0]['coin'] = state['balance_minor'] / 10000
        data['WalletInfo'][0]['bet'] = [b / 10000 for b in self.service.registry.get('roma-x-10000').config['bets_minor']]
        data['extraInfo'] = pack('GameInfoData', {'Mul': []})
        data['lastBet'] = state['state']['last_bet_minor'] / 10000
        return pack('GameInfoAck', data)

    def handle(self, token, ack, payload, key):
        if type(ack) is not int or not isinstance(payload, list) or len(payload) > 16384 or any(type(v) is not int or not 0 <= v <= 255 for v in payload):
            raise ServiceError('INVALID_REQUEST', 'Invalid TaDa request.')
        if ack in (19,21,25,27,33,51,60):
            self.service.wallet(token)
            if ack == 19 and payload != [8,3]:
                raise ServiceError('CURRENCY_INVALID', 'Only the captured SC wallet is available.')
            # Captured read-only initialization metadata; no platform rewards.
            replies = {19:[24,1],21:[],25:[],27:[],33:[10,2,8,1,10,2,8,2,10,2,8,3],51:[],60:[]}
            return dict(type=ack, ret=801 if ack == 60 else 0, error_msg='', data=replies[ack])
        if ack == 1:
            data = self.info(token)
        elif ack == 2:
            import struct
            money = self.service.wallet(token)['balance_minor'] / 10000
            notice = b'\x08\x04\x11' + struct.pack('<d', money) + b'\x28\x03'
            data = list(b'\x0a' + varint(len(notice)) + notice)
        elif ack in (0, 4, 36):
            state = self.service.state(token, 'roma-x-10000')
            if ack == 0:
                req = unpack('SpinReq', payload)
                if set(req) - {'bet', 'special', 'extraSpin', 'clientRecord', 'mall', 'customReq', 'specialBonus'}:
                    raise ServiceError('BET_INVALID', "Unsupported Roma X 10000 spin request.")
                if any(req.get('special', {}).values()):
                    # Turbo changes presentation only; tournament/cheat are unsupported.
                    if set(k for k, v in req['special'].items() if v) - {'turbo'}:
                        raise ServiceError('BET_INVALID', 'Unsupported spin option.')
                if 'extraSpin' in req:
                    raise ServiceError('BET_INVALID', 'Invalid Extra Bet selection.')
                amount = Decimal(str(req.get('bet', 0))) * 10000
                if not amount.is_finite() or amount != amount.to_integral_value():
                    raise ServiceError('BET_INVALID', 'Invalid bet precision.')
                buy = None
                if req.get('specialBonus', {}).get('used') or req.get('customReq'):
                    raise ServiceError('BET_INVALID', 'Unsupported custom play.')
                if 'mall' in req:
                    mall = req['mall']
                    buy = mall.get('Index', 0)
                    prices = self.service.registry.get('roma-x-10000').config['buy_multipliers']
                    if mall.get('Type', 0) != 1 or buy not in range(2) or 'extraSpin' in req or Decimal(str(mall.get('Bet', 0)))*10000 != amount*Decimal(str(prices[buy])):
                        raise ServiceError('BET_INVALID', 'Invalid feature purchase.')
                previous_sid = state['state']['sid']
                with self.service.connection() as db:
                    player = self.service.sessions._player(db, token)
                    cached = db.execute('SELECT request_json FROM spins WHERE player_id=? AND game_id=? AND request_key=?',
                                        (player['id'], 'roma-x-10000', key)).fetchone()
                    if cached:
                        previous_sid = json.loads(cached['request_json'])['previous_sid']
                result = self.service.spin(token, 'roma-x-10000', key, previous_sid,
                                           dict(bet_minor=int(amount), buy=buy))
                event, money, sid = result['outcome'], result['wallet']['after_minor'], result['sid']
            else:
                event, money, sid = state['state']['last_event'], state['balance_minor'], state['state']['sid']
                if not event:
                    return dict(type=ack, ret=0, error_msg='', data=[])
                req = {'bet': event['bet_minor'] / 10000}
                if event.get('buy') is not None:
                    index = event['buy']
                    req['mall'] = dict(Type=1, Index=index, Bet=event['bet_minor']/10000*self.service.registry.get('roma-x-10000').config['buy_multipliers'][index])
            data = pack('SpinResponse', dict(data=pack('SpinAck', event['spin']), service={},
                        totalWin=event['total_minor'] / 10000, postMoney=money / 10000,
                        roundIndexV2=int(sid), spinReq=req))
        else:
            self.service.wallet(token)
            raise ServiceError('ACK_UNSUPPORTED', 'Unrecognized TaDa command: ' + str(ack))
        return dict(type=ack, ret=0, error_msg='', data=data)
