"""Original ASCII commands over the client's native HTTP transport."""
from datetime import datetime, timezone
import json
from pathlib import Path

from server.core.contracts import ServiceError

CLIENT = Path(__file__).resolve().parents[3]/'clients/tower-run-treasure-steps'


class Adapter:
    def __init__(self, service):
        self.service = service

    def current(self, token):
        return self.service.state(token, 'tower-run-treasure-steps')['state']

    def wallet_line(self, token, balance=None):
        amount = self.service.wallet(token)['balance_minor'] if balance is None else balance
        return f'52 {amount} 0 0'

    def transaction(self, token, key, payload):
        previous = self.current(token)['sid']
        with self.service.connection() as db:
            player = self.service.sessions._player(db, token)
            cached = db.execute('SELECT request_json FROM spins WHERE player_id=? AND game_id=? AND request_key=?',
                                (player['id'], 'tower-run-treasure-steps', key)).fetchone()
            if cached:
                previous = json.loads(cached['request_json'])['previous_sid']
        return self.service.spin(token, 'tower-run-treasure-steps', key, previous, payload)

    def call(self, token, sequence, command):
        words = command.split()
        if not words:
            raise ServiceError('REQUEST_INVALID', 'Missing command.')
        kind = words[0]
        if kind == '103':
            return [f'103 "{token}"']
        if kind == '101':
            return [f'103 "{token}!1"', '101 1 "DEMO" "" "ZZ" "Player" ""',
                    '127 "'+datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')+'"']
        if kind == '104':
            if words[1] != '1098':
                raise ServiceError('BET_INVALID', 'Unknown game.')
            state = self.current(token)
            balance = self.service.wallet(token)['balance_minor']
            if state['pending']:
                # The native reconnect animation re-applies its displayed bet.
                balance += (15 if state['ultra'] else 10)*state['last_denom']
            values = self.service.registry.get('tower-run-treasure-steps').config['denominations']
            lines = ['104 1', '54 '+str(len(values))+' '+' '.join(map(str, values))+' 1',
                     '57 "<custom><RTP Value=\\"96\\" /><DisableBetBooster Value=\\"0\\" /></custom>"',
                     '60 96 0 0 0', self.wallet_line(token,balance), '83 0']
            progress = sorted((int(k), v) for k, v in state['progress'].items())
            lines.append('56 '+str(len(progress))+' '+' '.join(str(v) for pair in progress for v in pair)+' 18')
            if state['pending']:
                # Replay the saved pending presentation without another debit.
                replay = self.transaction(token, 'playngo:'+str(sequence)+':replay', {'action':'replay'})
                lines.extend(replay['outcome']['lines'])
            lines.append('109')
            return lines
        if kind == '0':
            return ['0']
        if kind == '7' and len(words) == 2:
            return ['83 '+words[1]]
        if kind == '2' and len(words) == 3 and words[1]=='4':
            return [command]
        if kind == '1' and len(words) == 5:
            if words[1] != '1' or words[4] != '1' or words[2] not in ('10','15'):
                raise ServiceError('BET_INVALID', 'Invalid fixed bet.')
            payload = dict(denom=int(words[3]), ultra=words[2]=='15')
        elif command == '2 6':
            payload = dict(action='continue')
        elif command == '4 0':
            payload = dict(action='collect')
        else:
            raise ServiceError('REQUEST_INVALID', 'Unknown game command.')
        key = 'playngo:'+str(sequence)
        result = self.transaction(token, key, payload)
        outcome = result['outcome']
        lines = ([] if kind == '1' or kind == '4' else [command]) + outcome['lines']
        if outcome['next_phase'] == 'ready':
            lines.append(self.wallet_line(token, result['wallet']['after_minor']))
        return lines
