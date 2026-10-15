"""Import a captured PP client and initialization, without remote credentials."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / 'clients/gates-of-olympus'
HOST = 'demogamesfree.pragmaticplay.net'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session')
    parser.add_argument('--game', choices=['gates-of-olympus', 'sweet-bonanza-pop', 'big-bass-bonanza'], default='gates-of-olympus')
    parser.add_argument('--language-pack', choices=['zh', 'en'], help='Import only locale packages, including the Asia /gs2c host')
    args = parser.parse_args()
    global CLIENT
    CLIENT = ROOT / 'clients' / args.game
    symbol = {'sweet-bonanza-pop': 'vs10swtbnz', 'gates-of-olympus': 'vs20olympgate', 'big-bass-bonanza': 'vs10bbbonanza'}[args.game]
    if not re.fullmatch('[0-9a-f]{32}', args.session):
        parser.error('Expected a capture session ID')
    capture = ROOT / 'response-capture/captures' / args.session
    manifest = capture / 'manifest.json'
    try:
        with urlopen('http://127.0.0.1:8090/api/sessions/' + args.session, timeout=10) as response:
            snapshot = json.load(response)
    except OSError:
        snapshot = json.loads(manifest.read_text(encoding='utf-8'))
    fixtures = CLIENT / 'fixtures'
    fixtures.mkdir(parents=True, exist_ok=True)
    sources_path = fixtures / 'asset-sources.json'
    sources = {r['path']: r for r in json.loads(sources_path.read_text())} if sources_path.exists() else {}
    imported = 0
    for row in snapshot['rows']:
        url = urlsplit(row['url'])
        source_url = url._replace(query='', fragment='').geturl()
        if args.language_pack:
            if url.hostname not in (HOST, 'demogamesfree-asia.pragmaticplay.net'):
                continue
            path = re.sub(r'^/gs2c/common/', '/hub-demo/common/', url.path)
            if not re.fullmatch(r'/hub-demo/common/v3/games-html5/games/vs/' + re.escape(symbol) +
                                r'/(desktop|mobile)/packages/' + args.language_pack + r'_(GUI_)?(desktop|mobile)\.json', path):
                continue
            url = url._replace(netloc=HOST, path=path)
        if url.hostname != HOST or row.get('status') != 200 or row.get('state') != 'complete' or not row.get('body'):
            continue
        source = (capture / row['body']).resolve()
        if not source.is_relative_to(capture.resolve()):
            raise ValueError('Invalid capture body path')
        data = source.read_bytes()
        relative = url.path.lstrip('/')
        if url.path == '/hub-demo/html5Game.do':
            html = data.decode('utf-8')
            config = json.loads(re.search(r"gameConfig: '(.*?)',", html)[1])
            if '/' + symbol + '/' not in config['datapath']:
                continue
            # Keep the original loader and document, replace its session configuration.
            def script(match):
                attrs, content = match[1], match[2]
                if 'Html5GameManager.init' in content:
                    return '<script src="/local-preview.js"></script><script>Html5GameManager.init({contextPath:"/hub-demo",gameConfig:JSON.stringify(__LOCAL_CONFIG__)});</script>'
                if any(x in content for x in ('JsApiHelper.init', 'var noga =')) or 'demo-js-api-script.js' in attrs:
                    return ''
                return match[0]
            html = re.sub(r'<script\b([^>]*)>(.*?)</script>', script, html, flags=re.S | re.I)
            html = html.replace('https://' + HOST, '')
            data, relative = html.encode('utf-8'), 'index.html'
        elif url.path.endswith('/gameService'):
            req_path = (capture / row.get('request_body', '')).resolve()
            if not req_path.is_relative_to(capture.resolve()) or not req_path.is_file():
                continue
            req = parse_qs(req_path.read_text())
            if req.get('action') != ['doInit'] or req.get('symbol') != [symbol]:
                continue
            # Only static initialization; spin responses are never imported by this tool.
            relative = 'fixtures/init.txt'
        elif not url.path.startswith('/hub-demo/common/'):
            continue
        elif '/games/vs/' in url.path and '/games/vs/' + symbol + '/' not in url.path:
            continue
        target = (CLIENT / relative).resolve()
        if not target.is_relative_to(CLIENT.resolve()):
            raise ValueError('Invalid asset path')
        if target.exists() and target.read_bytes() == data:
            continue
        if target.exists() and relative not in ('index.html', 'fixtures/init.txt'):
            raise ValueError('Asset version conflict: ' + relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        sources[relative] = {'path': relative, 'source': source_url,
                             'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
                             'session': args.session, 'request_id': row['id']}
        imported += 1
    sources_path.write_text(json.dumps(list(sources.values()), indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'imported': imported, 'assets': len(sources), 'capture_state': snapshot['state']}))


if __name__ == '__main__':
    main()
