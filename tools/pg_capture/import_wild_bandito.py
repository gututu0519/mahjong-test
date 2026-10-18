"""Import public client resources; never publish capture credentials or wallets."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

from server.adapters.pg.protocol import unpack
from server.adapters.pg.wire import decode
from server.adapters.pg.wild_bandito import SCHEMA
from server.games.wild_bandito.engine import evaluate

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / 'clients/wild-bandito'


def run(session):
    with urlopen('http://127.0.0.1:8090/api/sessions/' + session) as response:
        snapshot = json.load(response)
    source = ROOT / 'response-capture/captures' / session
    index = []
    for row in snapshot['rows']:
        url = urlsplit(row['url'])
        if (row['status'] != 200 or not row.get('body') or row['method'] != 'GET'
                or url.hostname not in ('static.rhzzzvqpd.com', 'm.rhzzzvqpd.com')
                or not url.path.startswith(('/104/', '/shared/', '/favicon/', '/loader/'))):
            continue
        relative = url.path.lstrip('/')
        path = (CLIENT / relative).resolve()
        if not path.is_relative_to(CLIENT.resolve()):
            raise ValueError('Invalid resource path')
        data = (source / row['body']).read_bytes()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        index.append({'request': row['id'], 'path': relative,
                      'source': url._replace(query='', fragment='').geturl(),
                      'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)})
    fixtures = CLIENT / 'fixtures'
    fixtures.mkdir(parents=True, exist_ok=True)
    # Public rule metadata contains no player information.
    rule = next(r for r in snapshot['rows'] if '/GameRule/Get' in r['url'])
    (fixtures / 'game-rule.json').write_bytes((source / rule['body']).read_bytes())
    auth = json.loads((source / 'bodies/000158.json').read_text(encoding='utf-8'))['dt']
    allowed = ('oj', 'st', 'geu', 'lau', 'bau', 'cc', 'cs', 'gm', 'uiogc', 'ec', 'occ', 'gcv', 'sdn', 'jc')
    public = {k: auth[k] for k in allowed if k in auth}
    public.update(geu='game-api/wild-bandito/', bau='web-api/game-proxy/', lau='game-api/lobby/',
                  pid='local-player', pcd='local-player', nkn='Player', tk='local-session', ioph='local', cc='PGC', cs='')
    # Captured operator links and identity have no purpose in the local client.
    public['occ'] = dict(tcm='', tlb='', trb='', tsc=0, ttp=0, rurl='')
    (fixtures / 'auth-metadata.json').write_text(json.dumps(public, indent=2), encoding='utf-8')
    unique = {r['path']: r for r in index}
    cover = next(r for r in snapshot['rows'] if '/slots/wild-bandito-hero.webp' in r['url'] and r.get('body'))
    cover_data = (source / cover['body']).read_bytes()
    (ROOT / 'demo/wild-bandito-cover.webp').write_bytes(cover_data)
    (fixtures / 'resource-index.json').write_text(json.dumps({'session': session, 'last_request': len(snapshot['rows']),
        'resources': list(unique.values()), 'lobby_cover': {'path': 'demo/wild-bandito-cover.webp',
        'source': cover['url'].split('?')[0], 'sha256': hashlib.sha256(cover_data).hexdigest()}}, indent=2), encoding='utf-8')
    spins, failures = [], []
    counts = {}
    for row in snapshot['rows']:
        if '/game-api/wild-bandito/v4/Spin' not in row['url'] or not row.get('body'):
            continue
        _, seed = unpack((source / row['request_body']).read_bytes(), salt=5)
        raw, _ = unpack((source / row['body']).read_bytes(), seed, salt=5)
        tx = decode(raw, SCHEMA['transaction']['nested'])
        outcome = evaluate(tx['orl'], round(tx['cs'] * 100), tx['ml'], tx.get('gm', 0))
        checks = (outcome['winning_positions'] == tx.get('wp', {}), outcome['ways'] == tx.get('snww', {}),
                  outcome['win_minor'] == round(tx.get('tw', 0) * 100))
        if not all(checks):
            failures.append(row['id'])
        pair = f"{tx.get('st')}->{tx.get('nst')}"
        counts[pair] = counts.get(pair, 0) + 1
        # Outcome evidence only: no server round IDs, player information or funds.
        public_tx = {k: v for k, v in tx.items() if k not in ('sid', 'psid', 'hashr', 'pmt', 'ocr', 'mr')}
        spins.append({'request': row['id'], 'transaction': public_tx})
    (fixtures / 'spin-evidence.json').write_text(json.dumps({'session': session, 'counts': counts,
        'checked': len(spins), 'failures': failures, 'spins': spins}, indent=2), encoding='utf-8')
    if failures:
        raise ValueError(f'Paytable audit failed at {failures}')
    print(json.dumps({'resources': len(unique), 'bytes': sum(r['size'] for r in unique.values()),
                      'requests': len(snapshot['rows']), 'spins': len(spins), 'states': counts, 'failures': failures}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--session', default='b1f3bdd49e9945e29b7e6cc64de1ca23')
    run(parser.parse_args().session)
