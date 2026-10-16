"""Import Roma X 10000 static assets from an ongoing capture."""
import argparse
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
HOSTS = {'casino-wbgame.jiligames.com', 'uat-web-cdn.jiligames.com', 'uat-history.jiligames.com'}
PREFIXES = ('rx10000/', 'astarte2/', 'smallicon/', 'api-documents/', 'static/images/intro/')
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
    destination = ROOT / 'clients/roma-x-10000'
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
        if Path(relative).suffix.lower() in EXTENSIONS or relative.startswith(('rx10000/', 'astarte2/')):
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
        if target.suffix in ('.bin', '.zip', '.wasm', '.cconb') or target.suffix.lower() not in EXTENSIONS:
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
    # The original bundles periodically request native integrity assets with
    # generated extensions. Recover their exact names from captured Cocos packs.
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
    def uuid(value):
        if len(value) != 22:
            return value
        raw = value[:2]
        for i in range(2, 22, 2):
            raw += f'{alphabet.index(value[i]) * 64 + alphabet.index(value[i + 1]):03x}'
        return '-'.join((raw[:8], raw[8:12], raw[12:16], raw[16:20], raw[20:]))
    def extensions(value):
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and re.fullmatch(r'\.[a-zA-Z0-9]{3,20}', item) and item.lower() not in EXTENSIONS:
                    yield item
                elif isinstance(item, (list, dict)):
                    yield from extensions(item)
        elif isinstance(value, dict):
            yield from extensions(list(value.values()))
    guards = {}
    for config_file in destination.glob('**/config*.json'):
        if 'diagnostics' in config_file.parts:
            continue
        config = json.loads(config_file.read_text(encoding='utf-8'))
        versions = config.get('versions', {}).get('native', [])
        native = {str(versions[i]): versions[i + 1] for i in range(0, len(versions), 2)}
        for pack_id, indices in config.get('packs', {}).items():
            packs = list(config_file.parent.glob(f'import/{pack_id[:2]}/{pack_id}.*.json'))
            if not packs:
                continue
            data = json.loads(packs[0].read_text(encoding='utf-8'))
            if not isinstance(data, list) or len(data) != 6 or len(data[5]) != len(indices):
                continue
            for entry, index in zip(data[5], indices):
                if str(index) not in native:
                    continue
                for extension in extensions(entry):
                    name = uuid(config['uuids'][int(index)])
                    relative = (config_file.parent / f'native/{name[:2]}/{name}.{native[str(index)]}{extension}').relative_to(destination).as_posix()
                    guards[relative] = ({'id': None, 'body': None}, 'https://casino-wbgame.jiligames.com/' + relative)
    for relative, (row, source) in guards.items():
        target = destination / relative
        if not target.is_file():
            with urlopen(source, timeout=45) as response:
                if urlsplit(response.url).hostname not in HOSTS:
                    raise ValueError('Unexpected integrity asset redirect')
                content = response.read()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        content = target.read_bytes()
        sources[relative] = dict(source=source, bytes=len(content), sha256=hashlib.sha256(content).hexdigest(),
                                 evidence='Native reference in captured Cocos configuration and import pack')
    sources = {**previous, **sources}
    fixtures = destination / 'fixtures'
    fixtures.mkdir(parents=True, exist_ok=True)
    (fixtures / 'asset-sources.json').write_text(json.dumps(
        {'capture': session, 'assets': sources}, indent=2) + '\n', encoding='utf-8')
    print(f"Imported {len(sources)} static assets; capture state: {snapshot['state']}.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session')
    import_capture(parser.parse_args().session)
