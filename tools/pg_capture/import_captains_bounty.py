"""Import public Captain's Bounty client assets from a live or saved capture.

The live capture remains untouched. Credentials and player data stay in captures/.
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.request import urlopen

from server.adapters.pg.protocol import unpack
from server.adapters.pg.wire import decode

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / 'clients/captains-bounty'
GAME_INDEX = '54'


def snapshot(session):
    with urlopen('http://127.0.0.1:8090/api/sessions/' + session, timeout=20) as response:
        return json.load(response)


def run(session):
    data = snapshot(session)
    if not any('/captains-bounty/v4/' in row['url'].lower() for row in data['rows']):
        raise ValueError("Capture does not contain Captain's Bounty; verify the actual game first")
    source = ROOT / 'response-capture/captures' / session
    index = {}
    for row in data['rows']:
        url = urlsplit(row['url'])
        if (row.get('status') != 200 or not row.get('body') or row['method'] != 'GET'
                or not url.path.startswith(('/' + GAME_INDEX + '/', '/shared/', '/favicon/', '/loader/'))):
            continue
        relative = unquote(url.path).lstrip('/')
        path = (CLIENT / relative).resolve()
        if not path.is_relative_to(CLIENT.resolve()):
            raise ValueError('Invalid resource path')
        content = (source / row['body']).read_bytes()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        index[relative] = dict(request=row['id'], path=relative,
                               source=url._replace(query='', fragment='').geturl(),
                               sha256=hashlib.sha256(content).hexdigest(), size=len(content))
    fixtures = CLIENT / 'fixtures'
    fixtures.mkdir(parents=True, exist_ok=True)
    supplemental = fixtures / 'resource-supplement.json'
    if supplemental.exists():
        for record in json.loads(supplemental.read_text(encoding='utf-8'))['resources']:
            path = (CLIENT / record['path']).resolve()
            if not path.is_relative_to(CLIENT.resolve()):
                raise ValueError('Invalid supplemental resource path')
            content = path.read_bytes()
            if len(content) != record['size'] or hashlib.sha256(content).hexdigest() != record['sha256']:
                raise ValueError('Supplemental resource checksum mismatch: ' + record['path'])
            index.setdefault(record['path'], record)
    cover = None
    for row in data['rows']:
        if row.get('status') != 200 or not row.get('body'):
            continue
        if '/GameRule/Get' in row['url']:
            request = parse_qs((source / row['request_body']).read_text(encoding='utf-8'))
            if request.get('gid') == [GAME_INDEX]:
                (fixtures / 'game-rule.json').write_bytes((source / row['body']).read_bytes())
        if '/verifySession' in row['url']:
            auth = json.loads((source / row['body']).read_text(encoding='utf-8'))['dt']
            if not any(str(game.get('gid')) == GAME_INDEX for game in auth.get('gm', [])):
                continue
            allowed = ('oj', 'st', 'cc', 'cs', 'gm', 'uiogc', 'ec', 'gcv', 'sdn', 'jc')
            public = {k: auth[k] for k in allowed if k in auth}
            public.update(geu='game-api/captains-bounty/', bau='web-api/game-proxy/', lau='game-api/lobby/',
                          pid='local-player', pcd='local-player', nkn='Player', tk='local-session',
                          ioph='local', cc='PGC', cs='',
                          occ=dict(tcm='', tlb='', trb='', tsc=0, ttp=0, rurl=''))
            (fixtures / 'auth-metadata.json').write_text(json.dumps(public, indent=2), encoding='utf-8')
        if row['method'] == 'GET' and any(urlsplit(row['url']).path.endswith('/' + name + '.webp') for name in ('captains-bounty', 'captain-s-bounty')):
            content = (source / row['body']).read_bytes()
            (ROOT / 'demo/captains-bounty-cover.webp').write_bytes(content)
            cover = dict(path='demo/captains-bounty-cover.webp', source=row['url'].split('?')[0],
                         request=row['id'], size=len(content), sha256=hashlib.sha256(content).hexdigest())
    (fixtures / 'resource-index.json').write_text(json.dumps(dict(session=session,
        last_request=len(data['rows']), resources=list(index.values()), lobby_cover=cover), indent=2), encoding='utf-8')
    schema_path = ROOT / 'server/adapters/pg/captains_bounty_schema.json'
    if not schema_path.exists():
        print(json.dumps(dict(resources=len(index), bytes=sum(r['size'] for r in index.values()), state=data['state'], stage='assets; schema pending')))
        return
    schema = json.loads(schema_path.read_text(encoding='utf-8'))
    spins, response_errors = [], []
    for row in data['rows']:
        if '/captains-bounty/v4/spin' not in row['url'].lower() or not row.get('body'):
            continue
        if row.get('status') != 200:
            error = dict(request=row['id'], status=row.get('status'))
            # Store a classification, never raw authentication error bodies.
            try:
                message = json.loads((source / row['body']).read_text(encoding='utf-8')).get('message')
                if message == 'failed to verify jwt':
                    error['reason'] = 'jwt_verification_failed'
            except (ValueError, UnicodeError, AttributeError):
                pass
            response_errors.append(error)
            continue
        _, seed = unpack((source / row['request_body']).read_bytes(), salt=9)
        raw, _ = unpack((source / row['body']).read_bytes(), seed, salt=9)
        tx = decode(raw, schema['transaction']['nested'])
        # Public outcome evidence only; omit server round IDs and player metadata.
        tx = {k: v for k, v in tx.items() if k not in ('sid', 'psid', 'ocr', 'mr', 'pmt')}
        spins.append(dict(request=row['id'], transaction=tx))
    (fixtures / 'spin-evidence.json').write_text(json.dumps(dict(session=session, spins=spins), indent=2), encoding='utf-8')
    states = Counter(f"{r['transaction']['st']}->{r['transaction']['nst']}" for r in spins)
    endings = [dict(request=r['request'], win=r['transaction'].get('tw', 0),
                    total=r['transaction'].get('aw', 0),
                    fs_aw=r['transaction'].get('fs', {}).get('aw', 0))
               for r in spins if r['transaction']['st'] in (21, 22) and r['transaction']['nst'] == 1]
    endpoints = {'game_info': '/captains-bounty/v4/GameInfo/Get',
                 'history_summary': '/BetSummary/Get', 'history_list': '/BetHistory/Get'}
    summary = dict(session=session, state=data['state'], total_requests=len(data['rows']),
                   spin_responses=len(spins), states=dict(states), feature_endings=endings,
                   response_errors=response_errors,
                   endpoint_requests={name: [r['id'] for r in data['rows'] if path in r['url']
                       and r.get('status') == 200 and r.get('body')] for name, path in endpoints.items()})
    (fixtures / 'capture-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(dict(resources=len(index), bytes=sum(r['size'] for r in index.values()),
        spins=len(spins), response_errors=len(response_errors),
        states=data['state'], rules=(fixtures / 'game-rule.json').exists())))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--session', required=True)
    run(parser.parse_args().session)
