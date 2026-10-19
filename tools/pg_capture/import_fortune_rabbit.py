"""Import public Fortune Rabbit client assets from a live or saved capture.

The live capture remains untouched. Credentials and player data stay in captures/.
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import urlopen

from server.adapters.pg.protocol import unpack
from server.adapters.pg.wire import decode

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / 'clients/fortune-rabbit'
GAME_INDEX = '1543462'


def snapshot(session):
    with urlopen('http://127.0.0.1:8090/api/sessions/' + session, timeout=20) as response:
        return json.load(response)


def run(session):
    data = snapshot(session)
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
    cover = None
    for row in data['rows']:
        if row.get('status') != 200 or not row.get('body'):
            continue
        if '/GameRule/Get' in row['url']:
            (fixtures / 'game-rule.json').write_bytes((source / row['body']).read_bytes())
        if '/verifySession' in row['url']:
            auth = json.loads((source / row['body']).read_text(encoding='utf-8'))['dt']
            allowed = ('oj', 'st', 'cc', 'cs', 'gm', 'uiogc', 'ec', 'gcv', 'sdn', 'jc')
            public = {k: auth[k] for k in allowed if k in auth}
            public.update(geu='game-api/fortune-rabbit/', bau='web-api/game-proxy/', lau='game-api/lobby/',
                          pid='local-player', pcd='local-player', nkn='Player', tk='local-session',
                          ioph='local', cc='PGC', cs='',
                          occ=dict(tcm='', tlb='', trb='', tsc=0, ttp=0, rurl=''))
            (fixtures / 'auth-metadata.json').write_text(json.dumps(public, indent=2), encoding='utf-8')
        if row['method'] == 'GET' and urlsplit(row['url']).path.endswith('/fortune-rabbit.webp'):
            content = (source / row['body']).read_bytes()
            (ROOT / 'demo/fortune-rabbit-cover.webp').write_bytes(content)
            cover = dict(path='demo/fortune-rabbit-cover.webp', source=row['url'].split('?')[0],
                         request=row['id'], size=len(content), sha256=hashlib.sha256(content).hexdigest())
    (fixtures / 'resource-index.json').write_text(json.dumps(dict(session=session,
        last_request=len(data['rows']), resources=list(index.values()), lobby_cover=cover), indent=2), encoding='utf-8')
    schema = json.loads((ROOT / 'server/adapters/pg/fortune_rabbit_schema.json').read_text(encoding='utf-8'))
    spins = []
    for row in data['rows']:
        if '/fortune-rabbit/v4/Spin' not in row['url'] or not row.get('body') or row.get('status') != 200:
            continue
        _, seed = unpack((source / row['request_body']).read_bytes(), salt=25)
        raw, _ = unpack((source / row['body']).read_bytes(), seed, salt=25)
        tx = decode(raw, schema['transaction']['nested'])
        # Public outcome evidence only; omit server round IDs and player metadata.
        tx = {k: v for k, v in tx.items() if k not in ('sid', 'psid', 'ocr', 'mr', 'pmt')}
        spins.append(dict(request=row['id'], transaction=tx))
    (fixtures / 'spin-evidence.json').write_text(json.dumps(dict(session=session, spins=spins), indent=2), encoding='utf-8')
    states = Counter(f"{r['transaction']['st']}->{r['transaction']['nst']}" for r in spins)
    endings = [dict(request=r['request'], win=r['transaction'].get('tw', 0),
                    total=r['transaction'].get('aw', 0),
                    fs_aw=r['transaction'].get('fs', {}).get('aw', 0))
               for r in spins if r['transaction']['st'] == 2 and r['transaction']['nst'] == 1]
    endpoints = {'game_info': '/fortune-rabbit/v4/GameInfo/Get',
                 'history_summary': '/BetSummary/Get', 'history_list': '/BetHistory/Get'}
    summary = dict(session=session, state=data['state'], total_requests=len(data['rows']),
                   spin_responses=len(spins), states=dict(states), feature_endings=endings,
                   endpoint_requests={name: [r['id'] for r in data['rows'] if path in r['url']
                       and r.get('status') == 200 and r.get('body')] for name, path in endpoints.items()})
    (fixtures / 'capture-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(dict(resources=len(index), bytes=sum(r['size'] for r in index.values()),
        spins=sum('/fortune-rabbit/v4/Spin' in r['url'] and bool(r.get('body')) for r in data['rows']),
        states=data['state'], rules=(fixtures / 'game-rule.json').exists())))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--session', required=True)
    run(parser.parse_args().session)
