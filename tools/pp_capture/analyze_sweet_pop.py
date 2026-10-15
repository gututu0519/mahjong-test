"""Export credential-free POP protocol evidence from the latest capture snapshot."""
import argparse
import json
from pathlib import Path
from urllib.parse import parse_qs
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
FIELDS = set('s sa sb sh sw st c l w tw na rs_iw rs_win rs_p rs_c rs_m rs_more rs_t s_mark pw trail slm_mp slm_mv apwa apt apv fs fsmax fswin fsres fsmul fs_total fswin_total fsres_total fsmul_total fsend_total fsmore reel_set balance index counter'.split())


def snapshot(session):
    if len(session) != 32 or any(c not in '0123456789abcdef' for c in session):
        raise ValueError('Invalid capture ID')
    folder = ROOT / 'response-capture/captures' / session
    try:
        with urlopen('http://127.0.0.1:8090/api/sessions/' + session, timeout=10) as response:
            data = json.load(response)
    except OSError:
        data = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    rows = []
    for row in data['rows']:
        if '/gameService' not in row['url'] or row.get('status') != 200 or row.get('state') != 'complete':
            continue
        if not row.get('body') or not row.get('request_body'):
            continue
        def read(key):
            path = (folder / row[key]).resolve()
            if not path.is_relative_to(folder.resolve()):
                raise ValueError('Invalid capture body path')
            return {k: v[0] for k, v in parse_qs(path.read_text(encoding='utf-8')).items()}
        request, response = read('request_body'), read('body')
        if request.get('symbol') != 'vs10swtbnz' or request.get('action') not in ('doSpin', 'doCollect'):
            continue
        rows.append({'id': row['id'],
                     'request': {k: v for k, v in request.items() if k in ('action', 'c', 'l', 'index', 'counter')},
                     'response': {k: v for k, v in response.items() if k in FIELDS or (k.startswith('l') and k[1:].isdigit())}})
    return {'capture': session, 'capture_state': data['state'], 'rows': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session')
    args = parser.parse_args()
    data = snapshot(args.session)
    path = ROOT / 'server/tests/fixtures/sweet-pop-spins.json'
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'rows': len(data['rows']), 'path': str(path)}))
