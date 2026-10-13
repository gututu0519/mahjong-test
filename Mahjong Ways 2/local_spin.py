"""Stateful local replay of complete captured rounds, with a synthetic wallet.

This is a deterministic sample player, not the production outcome generator.
The original client still sends and decodes the binary Spin protocol.
"""
import base64
import copy
import json
import os
import re
import threading
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from local_auth import SESSION_TOKEN
from spin_protocol import (decode_request, double_field, field, fields, pack,
                           patch, text_field, unpack)

ROOT = Path(__file__).resolve().parent
MONEY_FIELDS = {'aw': 6, 'tb': 15, 'tbb': 16, 'tw': 17, 'np': 18,
                'ctw': 54, 'ssaw': 109}


def amount(value):
    return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class SpinError(ValueError):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.status = code, status


class LocalSpin:
    def __init__(self, state_path=None):
        self.rounds = json.loads((ROOT / 'fixtures/spin-rounds.json').read_text(encoding='utf-8'))['rounds']
        self.path = Path(state_path) if state_path else ROOT / 'diagnostics/local-spin-state.json'
        self.lock = threading.RLock()
        self.state = {'version': 1, 'balance': 2000, 'round': 0, 'step': 0,
                      'serial': 0, 'sid': '0', 'round_sid': '0', 'cs': 0.01, 'ml': 5}
        if self.path.exists():
            saved = json.loads(self.path.read_text(encoding='utf-8'))
            if saved.get('version') != 1:
                raise ValueError('Unsupported local wallet state version')
            self.state = saved

    def _save(self, state):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
        os.replace(temporary, self.path)
        self.state = state

    def game_info(self, data):
        with self.lock:
            data = copy.deepcopy(data)
            data['dt']['bl'] = self.state['balance']
            if 'last_wire' in self.state:
                data['localSpin'] = self.state['last_wire']
            return data

    def wallet(self):
        with self.lock:
            balance = self.state['balance']
            return {'dt': {'cc': 'AUD', 'tb': balance, 'pb': 0, 'cb': balance,
                           'tbb': 0, 'tfgb': 0, 'rfgc': 0, 'inbe': False,
                           'infge': False, 'iebe': False, 'iefge': False,
                           'ch': {'k': '0_C', 'cid': 0, 'cb': balance},
                           'p': None, 'ocr': None, 'bwc': 0, 'fgwc': 0}, 'err': None}

    def spin(self, body):
        raw, seed = unpack(body)
        request = decode_request(raw)
        if request.get('atk') != SESSION_TOKEN or request.get('btt') != 1:
            raise SpinError('LOCAL_SESSION_INVALID', 'Only the local demo session is supported.')
        if request.get('pf') != 1 or request.get('wk') != '0_C':
            raise SpinError('LOCAL_WALLET_INVALID', 'Unsupported local wallet.')
        if request.get('cs') not in (0.01, 0.06, 0.3) or request.get('ml') not in range(1, 11):
            raise SpinError('LOCAL_BET_INVALID', 'Unsupported bet size or level.')
        if request.get('fb', 0) or request.get('ab', 0):
            raise SpinError('LOCAL_FEATURE_UNAVAILABLE', 'This captured sample does not support feature buys.')
        if not isinstance(request.get('id'), str):
            raise SpinError('LOCAL_SPIN_ID_INVALID', 'Missing previous spin ID.')
        key = json.dumps(request, sort_keys=True)
        with self.lock:
            # A transport retry receives the same settlement, reshuffled with
            # its new request seed. It must never debit the wallet a second time.
            if key == self.state.get('last_request'):
                return pack(base64.b64decode(self.state['last_wire']), seed)
            if request['id'] != self.state['sid']:
                raise SpinError('LOCAL_SPIN_STALE', 'Refresh to load the current local round.', 409)
            state = copy.deepcopy(self.state)
            if state['step'] and (request['cs'], request['ml']) != (state['cs'], state['ml']):
                raise SpinError('LOCAL_BET_LOCKED', 'Finish the current cascade before changing the bet.')
            if not state['step']:
                state['cs'], state['ml'] = request['cs'], request['ml']
            template = self.rounds[state['round']][state['step']]
            tx = copy.deepcopy(template['transaction'])
            scale = Decimal(str(state['cs'])) * state['ml'] / (Decimal(str(tx['cs'])) * tx['ml'])
            for name in MONEY_FIELDS:
                tx[name] = float(amount(Decimal(str(tx[name])) * scale))
            if tx.get('lw'):
                tx['lw'] = {k: float(amount(Decimal(str(v)) * scale)) for k, v in tx['lw'].items()}
            if tx.get('fs'):
                tx['fs']['aw'] = float(amount(Decimal(str(tx['fs']['aw'])) * scale))
            balance = amount(state['balance'])
            bet, win = amount(tx['tb']), amount(tx['tw'])
            if balance < bet:
                raise SpinError('LOCAL_BALANCE_LOW', 'Insufficient local demo balance.')
            state['serial'] += 1
            state['sid'] = str(state['serial'])
            if not state['step']:
                state['round_sid'] = state['sid']
            tx.update(sid=state['sid'], psid=state['round_sid'], cs=state['cs'], ml=state['ml'],
                      blb=float(balance), blab=float(balance - bet), bl=float(balance - bet + win))
            # Keep the captured grid/check string consistent with the scaled bet
            # and award. Symbol positions and cascade transitions are untouched.
            if tx.get('hashr'):
                for label, value in [('MV', tx['tb']), ('MG', tx['tw'])]:
                    tx['hashr'] = re.sub(r'(#' + label + r'#)[^#]*',
                                        lambda m: m[1] + str(value), tx['hashr'])
            wire = self._response(template, tx)
            state['balance'] = tx['bl']
            state['last_request'] = key
            state['last_wire'] = base64.b64encode(wire).decode()
            state['step'] += 1
            if state['step'] == len(self.rounds[state['round']]):
                state['step'] = 0
                state['round'] = (state['round'] + 1) % len(self.rounds)
            self._save(state)
            return pack(wire, seed)

    @staticmethod
    def _response(template, tx):
        raw = base64.b64decode(template['wire'])
        replacements = {number: double_field(number, tx[name]) for name, number in MONEY_FIELDS.items()}
        replacements.update({1: text_field(1, tx['sid']), 2: text_field(2, tx['psid']),
                             12: double_field(12, tx['blb']), 13: double_field(13, tx['blab']),
                             14: double_field(14, tx['bl']), 51: field(51, 0, tx['ml']),
                             52: double_field(52, tx['cs'])})
        if tx.get('hashr'):
            replacements[59] = text_field(59, tx['hashr'])
        if tx.get('lw'):
            replacements[102] = b''.join(field(102, 2, field(1, 0, int(k)) + double_field(2, v))
                                         for k, v in tx['lw'].items())
        if tx.get('fs'):
            original = next(v for n, w, v in fields(raw) if n == 107 and w == 2)
            replacements[107] = field(107, 2, patch(original, {1: double_field(1, tx['fs']['aw'])}))
        return patch(raw, replacements)
