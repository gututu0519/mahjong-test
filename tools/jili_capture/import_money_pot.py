"""Import Money Pot DELUXE static assets from an ongoing capture."""
import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
HOSTS = {'casino-wbgame.jiligames.com', 'uat-web-cdn.jiligames.com', 'uat-history.jiligames.com'}
PREFIXES = ('mpt2/', 'astarte2/', 'smallicon/', 'api-documents/', 'static/images/intro/')
EXTENSIONS = {'.html', '.js', '.json', '.css', '.png', '.jpg', '.webp', '.ico', '.plist',
              '.bin', '.wasm', '.mp3', '.ogg', '.wav', '.ttf', '.woff', '.woff2', '.atlas', '.zip', '.cconb', '.ccon'}


def import_capture(session):
    capture = ROOT / 'response-capture/captures' / session
    manifest = capture / 'manifest.json'
    try:
        with urlopen('http://127.0.0.1:8090/api/sessions/' + session, timeout=10) as response:
            snapshot = json.load(response)
    except OSError:
        snapshot = json.loads(manifest.read_text(encoding='utf-8'))
    destination = ROOT / 'clients/money-pot-deluxe'
    destination.mkdir(parents=True, exist_ok=True)
    destination = destination.resolve()
    sources_file = destination / 'fixtures/asset-sources.json'
    previous = json.loads(sources_file.read_text(encoding='utf-8')).get('assets', {}) if sources_file.exists() else {}
    selected = {}
    for row in snapshot['rows']:
        url = urlsplit(row['url'])
        relative = url.path.lstrip('/')
        if url.hostname not in HOSTS or row.get('status') != 200 or not row.get('body'):
            continue
        if not relative.startswith(PREFIXES):
            continue
        if relative.endswith('/'):
            relative += 'index.html'
        if Path(relative).suffix.lower() in EXTENSIONS:
            selected[relative] = (row, url._replace(query='', fragment='').geturl())

    for relative in selected:
        if ".." in Path(relative).parts:
            raise ValueError("Invalid static path")
        (destination / relative).parent.mkdir(parents=True, exist_ok=True)

    def copy(item):
        relative, (row, source) = item
        target = (destination / relative).resolve()
        if not target.is_relative_to(destination):
            raise ValueError('Invalid static path: ' + relative)
        cached = previous.get(relative)
        if cached and cached['source'] == source and target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == cached['sha256']:
            return relative, cached
        content = (capture / row['body']).read_bytes()
        if target.suffix in ('.bin', '.zip', '.wasm', '.cconb'):
            # CDP can transcode text/bin. Always preserve original binary bytes.
            with urlopen(source, timeout=45) as response:
                if urlsplit(response.url).hostname not in HOSTS:
                    raise ValueError('Unexpected asset redirect')
                content = response.read()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return relative, {'request_id': row['id'], 'source': source, 'bytes': len(content),
                          'sha256': hashlib.sha256(content).hexdigest()}

    with ThreadPoolExecutor(max_workers=6) as pool:
        sources = dict(pool.map(copy, selected.items()))
    fixtures = destination / 'fixtures'
    fixtures.mkdir(parents=True, exist_ok=True)
    (fixtures / 'asset-sources.json').write_text(json.dumps(
        {'capture': session, 'assets': sources}, indent=2) + '\n', encoding='utf-8')
    print(f"Imported {len(sources)} static assets; capture state: {snapshot['state']}.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session')
    import_capture(parser.parse_args().session)
