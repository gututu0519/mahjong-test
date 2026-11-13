"""Offline migration oracle only. Node build/start/test never invokes Python.

Run from the repository root: python server/tools/export-reference.py
All inputs are code/config or newly generated synthetic accounts, never user DBs.
"""
import ast
import json
from pathlib import Path
import tempfile
from urllib.parse import urlsplit, parse_qs
from py.games.buffalo_win.engine import BuffaloWin
from py.adapters.pg.buffalo_win import transaction
from py.adapters.pg.client_modules import prepare_module
from py.merchant.control import ControlStore, MerchantDirectory
from py.merchant.provider import MerchantService
from py.merchant import integration_docs

ROOT = Path.cwd()
OUT = ROOT / 'server'
def write(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

game = BuffaloWin(ROOT / 'services/gtt-gateway/config/buffalo-win.json')
cases = []
for number in range(24):
    state = game.initial_state('fixture')
    for step in range(256):
        bet = {'coin_minor': 2, 'level': 1, **({'buy_free': True} if number % 2 and step == 0 else {})}
        seed, sid = f'node-port-{number}-{step}', f'{number}:{step}'
        result = game.step(state, bet, seed, sid)
        wallet = {'before_minor': 200000, 'after_minor': 200000-result.debit_minor+result.credit_minor, 'debit_minor': result.debit_minor}
        cases.append({'state': state, 'bet': bet, 'seed': seed, 'sid': sid,
                      'expected': vars(result), 'wallet': wallet,
                      'transaction': transaction(result.event, wallet, game.config['win_thresholds'])})
        state = result.state
        if state['phase'] == 'ready':
            break
    else:
        raise RuntimeError('Reference round did not complete')
write('fixtures/buffalo-python.json', {'ruleset_id': game.ruleset_id, 'cases': cases})

modules = {}
for path in (ROOT / 'clients/buffalo-win/shared').rglob('index.js'):
    _, digest = prepare_module(path.read_bytes())
    modules[path.relative_to(ROOT / 'clients/buffalo-win').as_posix()] = digest
write('fixtures/module-hashes.json', modules)

class Wallet:
    balance = 200000
    def call(self, mid, action, payload):
        before = self.balance
        change = payload.get('amount_minor', 0)
        self.balance += -change if action == 'debit' else change if action == 'credit' else 0
        return {**payload, 'balance_minor': self.balance, 'balance_before_minor': before,
                'applied_minor': change, 'status': 'applied'}

with tempfile.TemporaryDirectory() as temporary:
    folder = Path(temporary)
    control = ControlStore(folder / 'control.sqlite3')
    control.create_user('fixture', 'admin', 'admin', 'test-only-password-2026')
    created = control.save_merchant('fixture', {'name': 'legacy-merchant', 'enabled': True,
             'wallet_url': 'http://127.0.0.1:1', 'currency': 'USD', 'games': [1]}, [1], create=True)
    mid = created['merchant']['id']
    provider = MerchantService(folder / 'game.sqlite3', MerchantDirectory(control), game=game, wallet=Wallet())
    launch = provider.launch(mid, {'player_id': 'legacy-player', 'game_id': 1})
    tok = parse_qs(urlsplit(launch['launch_url']).query)['ops'][0]
    # Synthetic fixture only: keep the test token valid independently of test date.
    with provider.connection(True) as db:
        db.execute('UPDATE merchant_sessions SET expires_at=4102444800')
    result = provider.spin(tok, 'buffalo-win', 'legacy-buy', '0', {'coin_minor': 2, 'level': 1, 'buy_free': True})
    write('fixtures/legacy-meta.json', {'merchant_id': mid, 'token': tok, 'result': result})
    for name, database in [('legacy-control', control), ('legacy-game', provider)]:
        with database.connection() as db:
            (OUT / 'fixtures' / (name+'.sql')).write_text('\n'.join(db.iterdump()), encoding='utf-8')
print('Exported synthetic Python reference steps, module hashes and legacy database fixture.')
