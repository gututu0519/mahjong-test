"""Import public Le Vampire resources and sanitized evidence from a live capture.

The recorder is read only. Raw sessions, credentials and request headers stay local.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
from urllib.parse import urlsplit, unquote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / 'clients/le-vampire'
BASE = 'https://static-live.hacksawgaming.com'
PREFIX = '2582/1.36.0/'


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
        print(json.dumps({'resources': len(index), 'errors': errors}))
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
    endpoints = {'authenticate': 'authenticate.json', 'partnerSettings': 'partner-settings.json',
                 'gameInfo': 'game-info.json'}
    rounds = []
    for row in snapshot['rows']:
        url = urlsplit(row['url'])
        source = capture / row['body'] if row.get('body') else None
        if not source or row.get('status') != 200 or not source.is_file():
            continue
        name = unquote(url.path).lstrip('/')
        if url.hostname == 'www-live.hacksawgaming.com' and name == 'casino_thumbnails/2582.jpg':
            cover = ROOT/'demo/le-vampire-cover.jpg'
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
            (fixtures/endpoints[endpoint]).write_text(json.dumps(public(read_json(source)), indent=2), encoding='utf-8')
        if url.hostname == 'rgs-demo.hacksawgaming.com' and endpoint == 'bet':
            request = read_json(capture/row['request_body'])
            response = read_json(source)
            rounds.append({'request_id': row['id'], 'request': public(request), 'response': public(response)})
    (fixtures/'rounds.json').write_text(json.dumps(rounds, indent=2), encoding='utf-8')
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
                         for weight in ('regular', 'bold'))
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
            path = CLIENT/name
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
        with ThreadPoolExecutor(max_workers=8) as pool:
            for result in pool.map(fetch, sorted(files)):
                if result:
                    name, meta = result
                    if 'error' in meta:
                        print('MISSING', name, meta['error'], flush=True)
                    else:
                        index[name] = meta
    index_file.write_text(json.dumps(dict(sorted(index.items())), indent=2), encoding='utf-8')
    print(json.dumps({'resources': len(index), 'round_responses': len(rounds), 'state': snapshot['state']}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
