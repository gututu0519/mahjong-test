"""Captured Hacksaw JSON protocol over the shared transactional wallet."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
from server.core.contracts import ServiceError

CLIENT = Path(__file__).resolve().parents[3] / 'clients/great-game-serengeti'


class Adapter:
    def __init__(self, service):
        self.service = service
        self.auth = json.loads((CLIENT/'fixtures/authenticate.json').read_text(encoding='utf-8'))
        self.partner = json.loads((CLIENT/'fixtures/partner-settings.json').read_text(encoding='utf-8'))
        self.info = json.loads((CLIENT/'fixtures/game-info.json').read_text(encoding='utf-8'))

    def response(self, token=None, **fields):
        balance = None if token is None else {'currencyCode': 'EUR',
                  'balance': str(self.service.wallet(token)['balance_minor']), 'realBalance': None, 'bonusBalance': None}
        return dict(statusCode=0, statusMessage='', accountBalance=balance, statusData=None, dialog=None,
                    customData=None, serverTime=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), **fields)

    def authenticate(self, token):
        current = self.service.state(token, 'great-game-serengeti')
        state = current['state']
        data = copy.deepcopy(self.auth)
        data.update(self.response(token))
        data.update(playerId=self.service.wallet(token)['player_id'], name='Player', sessionUuid=token,
                    languageCode='en-us', roundId='0', roundStatus=None, pendingWin='0', events=None,
                    defaultBetLevel=str(state['last_bet_minor']), gameState=None)
        if state['pending']:
            pending = state['pending']
            data.update(roundId=pending['round_id'], roundStatus='wfwpc', pendingWin=str(pending['win_minor']),
                        events=state['last_round']['events'],
                        gameState={'bet': {'betAmount': str(pending['bet_minor']),
                                           **({'buyBonus':pending['mode'], 'buyBonusBetMultiplier':str(self.service.registry.get('great-game-serengeti').config['costs'][pending['mode']])} if pending['mode'] != 'base' else {})},
                                   'possibleActions': []})
        return data

    def bet(self, request):
        token = request.get('sessionUuid')
        if not isinstance(token, str) or type(request.get('seq')) is not int or request['seq'] < 1:
            raise ServiceError('REQUEST_INVALID', 'A session and sequence are required.')
        continuation = request.get('continueInstructions')
        if continuation is not None:
            if continuation != {'action': 'win_presentation_complete'} or not isinstance(request.get('roundId'), str):
                raise ServiceError('REQUEST_INVALID', 'Unknown continuation.')
            payload = dict(action='confirm', round_id=request['roundId'])
        else:
            bets = request.get('bets')
            if not isinstance(bets, list) or len(bets) != 1 or not isinstance(bets[0], dict):
                raise ServiceError('BET_INVALID', 'Expected one bet.')
            item = bets[0]
            if set(item) - {'betAmount', 'buyBonus'}:
                raise ServiceError('BET_INVALID', 'Unknown bet field.')
            amount = item.get('betAmount')
            if not isinstance(amount, str) or not amount.isdecimal():
                raise ServiceError('BET_INVALID', 'Bet amount must be an integer string.')
            if request.get('offerId') or request.get('promotionId'):
                raise ServiceError('BET_INVALID', 'No promotion is attached to this account.')
            payload = dict(bet_minor=int(amount), mode=item.get('buyBonus') or 'base')
        key = 'hacksaw:' + str(request['seq'])
        current = self.service.state(token, 'great-game-serengeti')['state']
        previous = current['sid']
        # Retries use the original state boundary; conflicts remain the core's responsibility.
        with self.service.connection() as db:
            player = self.service.sessions._player(db, token)
            cached = db.execute('SELECT request_json FROM spins WHERE player_id=? AND game_id=? AND request_key=?',
                                (player['id'], 'great-game-serengeti', key)).fetchone()
            if cached:
                previous = json.loads(cached['request_json'])['previous_sid']
        result = self.service.spin(token, 'great-game-serengeti', key, previous, payload)
        data = self.response(token, round=result['outcome']['round'], promotionNoLongerAvailable=False,
                             promotionWin=None, offer=None, freeRoundOffer=None)
        # An idempotent retry must report the wallet at that operation, not today's balance.
        data['accountBalance']['balance'] = str(result['wallet']['after_minor'])
        return data
