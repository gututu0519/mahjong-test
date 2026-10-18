"""Import public Dr Zappo resources and sanitized evidence from a live capture.

The recorder is read only. Raw sessions, credentials and request headers stay local.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
from urllib.parse import urlsplit, unquote, parse_qs
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / 'clients/dr-zappo'
BASE = 'https://static-live.hacksawgaming.com'
PREFIX = '2253/1.49.1/'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def public(data):
    if isinstance(data, dict):
        return {k: ('local-session' if k == 'sessionUuid' else 'local-player' if k == 'playerId'
                    else None if k in ('token', 'geo') else public(v)) for k, v in data.items()}
    if isinstance(data, list):
        return [public(v) for v in data]
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('session', nargs='?')
    parser.add_argument('--references', action='store_true')
    parser.add_argument('--audit', action='store_true')
    args = parser.parse_args()
    index_file = CLIENT / 'resource-index.json'
    index = read_json(index_file) if index_file.exists() else {}
    if args.audit:
        errors = [name for name, meta in index.items() if not (CLIENT/name).is_file()
                  or hashlib.sha256((CLIENT/name).read_bytes()).hexdigest() != meta['sha256']]
        declared = []
        def audit_desc(node):
            if node.get('type') == 'file':
                name = PREFIX + node['path']
                path = CLIENT/name
                declared.append(name)
                if not path.is_file() or ('size' in node and path.stat().st_size != int(node['size'])):
                    errors.append(name)
            for child in node.get('children', []):
                audit_desc(child)
        audit_desc(read_json(CLIENT/PREFIX/'assets/desc.json'))
        print(json.dumps({'resources': len(index), 'declared_assets': len(declared), 'errors': sorted(set(errors))}))
        return bool(errors)
    CLIENT.mkdir(parents=True, exist_ok=True)
    fixtures = CLIENT / 'fixtures'
    fixtures.mkdir(exist_ok=True)
    try:
        sessions = json.load(urlopen('http://127.0.0.1:8090/api/sessions', timeout=10))
        sid = args.session or next(s['id'] for s in sessions if 'hacksawgaming.com' in s['url'])
        snapshot = json.load(urlopen('http://127.0.0.1:8090/api/sessions/' + sid, timeout=10))
    except OSError:
        sid = args.session
        snapshot = read_json(ROOT/'response-capture/captures'/sid/'manifest.json')
    capture = ROOT/'response-capture/captures'/sid
    game_sessions = set()
    for row in snapshot['rows']:
        url = urlsplit(row['url'])
        if url.hostname == 'rgs-demo.hacksawgaming.com' and url.path.endswith('/authenticate') and row.get('status') == 200 and row.get('body'):
            auth = read_json(capture/row['body'])
            if str(auth.get('gameId')) == '2253':
                game_sessions.add(auth['sessionUuid'])
    if not game_sessions:
        raise ValueError('This capture has no successful Dr Zappo authentication')
    endpoints = {'authenticate': 'authenticate.json', 'partnerSettings': 'partner-settings.json',
                 'gameInfo': 'game-info.json', 'keepAlive': 'keep-alive.json'}
    rounds = []
    for row in snapshot['rows']:
        url = urlsplit(row['url'])
        source = capture / row['body'] if row.get('body') else None
        if not source or row.get('status') != 200 or not source.is_file():
            continue
        name = unquote(url.path).lstrip('/')
        if url.hostname == 'www-live.hacksawgaming.com' and name == 'casino_thumbnails/2253.jpg':
            cover = ROOT/'demo/dr-zappo-cover.jpg'
            shutil.copyfile(source, cover)
            (CLIENT/'cover-evidence.json').write_text(json.dumps({'url':url.geturl(),
                'sha256':hashlib.sha256(cover.read_bytes()).hexdigest(), 'bytes':cover.stat().st_size,
                'request':row['id']},indent=2),encoding='utf-8')
        if url.hostname == 'static-live.hacksawgaming.com' and name.startswith((PREFIX, 'integrations/')):
            target = (CLIENT/name).resolve()
            if not target.is_relative_to(CLIENT.resolve()):
                raise ValueError('Invalid resource path')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            index[name] = {'url': BASE+'/'+name, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                           'bytes': target.stat().st_size, 'source': 'capture', 'request': row['id']}
        endpoint = url.path.rsplit('/', 1)[-1]
        if url.hostname == 'rgs-demo.hacksawgaming.com' and endpoint in endpoints:
            data = read_json(source)
            if endpoint == 'authenticate' and str(data.get('gameId')) != '2253':
                continue
            if endpoint == 'gameInfo' and parse_qs(url.query).get('gameId') != ['2253']:
                continue
            if endpoint == 'keepAlive' and read_json(capture/row['request_body']).get('sessionUuid') not in game_sessions | {'00000000-0000-0000-0000-000000000000'}:
                continue
            (fixtures/endpoints[endpoint]).write_text(json.dumps(public(data), indent=2), encoding='utf-8')
        if url.hostname == 'rgs-demo.hacksawgaming.com' and endpoint == 'bet':
            request = read_json(capture/row['request_body'])
            if request.get('sessionUuid') not in game_sessions:
                continue
            response = read_json(source)
            rounds.append({'request_id': row['id'], 'request': public(request), 'response': public(response)})
    (fixtures/'rounds.json').write_text(json.dumps(rounds, indent=2), encoding='utf-8')
    events = [event for sample in rounds for event in sample['response'].get('round', {}).get('events', [])]
    summary = dict(session=sid, capture_state=snapshot['state'], responses=len(rounds),
                   last_request=max((sample['request_id'] for sample in rounds), default=None),
                   modes=dict(Counter(bet.get('buyBonus') or 'base' for sample in rounds for bet in sample['request'].get('bets', []))),
                   events=dict(Counter(event['etn'] for event in events)),
                   actions=dict(Counter(a['at'] for event in events for a in event['c'].get('actions', []))))
    (fixtures/'evidence-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    if args.references:
        files = set()
        def walk(node):
            if node.get('type') == 'file':
                files.add(PREFIX+node['path'])
            for child in node.get('children', []):
                walk(child)
        walk(read_json(CLIENT/PREFIX/'assets/desc.json'))
        for lang in ('en-us', 'zh-cn'):
            files.update(PREFIX+p for p in (f'locale/{lang}/{lang}.json', f'casino/locale/{lang}/{lang}.json',
                                           f'gameinfoassets/templates/{lang}/{lang}-gameinfo.html'))
            files.update(PREFIX+f'casino/fonts/localized/{lang}/hacksawui_{weight}.ttf'
                         for weight in ('bold', 'regular'))
        # Original HTML/CSS references, including the icon fonts used by the UI.
        import re
        for path in list(CLIENT.rglob('*.html')) + list(CLIENT.rglob('*.css')):
            text = path.read_text(encoding='utf-8')
            for value in re.findall(r'''(?:src=["']|href=["']|url\(["']?)([^"'\s)>]+)''', text):
                if value.startswith(('http:', 'https:', 'data:', '#', '{')):
                    continue
                target = (path.parent/urlsplit(value).path).resolve()
                if target.is_relative_to(CLIENT.resolve()):
                    files.add(target.relative_to(CLIENT.resolve()).as_posix())
        def fetch(name):
            path = (CLIENT/name).resolve()
            if not path.is_relative_to(CLIENT.resolve()):
                return name, {'error': 'Invalid resource path'}
            if path.is_file():
                return None
            try:
                data = urlopen(Request(BASE+'/'+name, headers={'User-Agent': 'Mozilla/5.0'}), timeout=40).read()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                return name, {'url': BASE+'/'+name, 'sha256': hashlib.sha256(data).hexdigest(),
                              'bytes': len(data), 'source': 'original-reference'}
            except Exception as exc:
                return name, {'error': str(exc)}
        missing = []
        with ThreadPoolExecutor(max_workers=8) as pool:
            for result in pool.map(fetch, sorted(files)):
                if result:
                    name, meta = result
                    if 'error' in meta:
                        print('MISSING', name, meta['error'], flush=True)
                        missing.append({'path': name, **meta})
                    else:
                        index[name] = meta
        (CLIENT/'missing-references.json').write_text(json.dumps(missing, indent=2), encoding='utf-8')
    index_file.write_text(json.dumps(dict(sorted(index.items())), indent=2), encoding='utf-8')
    print(json.dumps({'resources': len(index), 'round_responses': len(rounds), 'state': snapshot['state']}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
