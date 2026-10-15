"""Save credential-free Olympus evidence and check count wins/cascade gravity."""
import argparse
import collections
import json
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]


def snapshot(session):
    if len(session) != 32 or any(c not in '0123456789abcdef' for c in session):
        raise ValueError('Invalid capture ID')
    folder = ROOT / 'response-capture/captures' / session
    manifest = folder / 'manifest.json'
    if manifest.exists():
        data = json.loads(manifest.read_text(encoding='utf-8'))
    else:
        with urlopen('http://127.0.0.1:8090/api/sessions/' + session, timeout=10) as response:
            data = json.load(response)
    rows = []
    for row in data['rows']:
        if '/gameService' not in row['url'] or row.get('status') != 200 or row.get('state') != 'complete':
            continue
        def read(key):
            path = (folder / row[key]).resolve()
            if not path.is_relative_to(folder.resolve()):
                raise ValueError('Invalid capture path')
            return {k: v[0] for k, v in parse_qs(path.read_text(encoding='utf-8')).items()}
        if not row.get('request_body') or not row.get('body'):
            continue
        request, response = read('request_body'), read('body')
        if request.get('symbol') != 'vs20olympgate' or request.get('action') not in ('doSpin', 'doCollect'):
            continue
        request = {k: v for k, v in request.items() if k in ('action', 'c', 'l', 'bl', 'pur', 'index', 'counter')}
        allowed = set('puri purtr s sa sb c l bl w tw na tmb tmb_win tmb_res rs rs_p rs_c rs_m rs_t rmul accv apwa apt apv fs fsmax fswin fsres fsmul fs_total fswin_total fsres_total fsmul_total fsend_total psym reel_set index counter balance'.split())
        response = {k: v for k, v in response.items() if k in allowed or (k.startswith('l') and k[1:].isdigit())}
        rows.append({'id': row['id'], 'request': request, 'response': response})
    return {'capture': session, 'capture_state': data['state'], 'rows': rows}


def audit(data):
    from server.games.gates_of_olympus.engine import evaluate
    errors, wins, gravity, multipliers = [], 0, 0, 0
    previous = None
    for row in data['rows']:
        d = row['response']
        if row['request']['action'] != 'doSpin':
            previous = None
            continue
        board = list(map(int, d['s'].split(',')))
        coin = int(Decimal(d['c']) * 100)
        result = evaluate(board, coin)
        actual = sum(int(Decimal(v.split('~')[1]) * 100) for k, v in d.items() if k.startswith('l') and k[1:].isdigit())
        if result['base_minor'] != actual:
            errors.append([row['id'], 'count award', result['base_minor'], actual])
        wins += bool(actual)
        if 'apwa' in d:
            expected = Decimal(d['tmb_win']) * (int(d['apv']) - 1)
            if expected != Decimal(d['apwa']):
                errors.append([row['id'], 'multiplier award'])
            multipliers += 1
        if previous and 'tmb' in previous:
            old = list(map(int, previous['s'].split(',')))
            removed = {int(p.split(',')[0]) for p in previous['tmb'].split('~')}
            for col in range(6):
                survivors = [old[p] for p in range(col, 30, 6) if p not in removed]
                after = board[col::6]
                if survivors and after[-len(survivors):] != survivors:
                    errors.append([row['id'], 'gravity', col])
            gravity += 1
        previous = d
    return {'actions': dict(collections.Counter(r['request']['action'] for r in data['rows'])),
            'winning_steps': wins, 'cascade_transitions': gravity, 'multiplier_settlements': multipliers,
            'errors': errors}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session')
    args = parser.parse_args()
    data = snapshot(args.session)
    out = ROOT / 'server/tests/fixtures/olympus-spins.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=True, separators=(',', ':')) + '\n', encoding='utf-8', newline='\n')
    # Permit direct invocation without installing the repository as a package.
    import sys
    sys.path.insert(0, str(ROOT))
    print(json.dumps(audit(data)))
