"""Import original TaDa static assets; never copy session URLs or API responses."""
import argparse
import json
import shutil
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
HOSTS = {'casino-wbgame.tadagaming.com', 'uat-web-cdn.tadagaming.com'}


def import_capture(session):
    capture = ROOT / 'response-capture/captures' / session
    manifest = capture / 'manifest.json'
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding='utf-8'))
    else:
        with urlopen('http://127.0.0.1:8090/api/sessions/' + session, timeout=10) as response:
            data = json.load(response)
    destination = ROOT / 'clients/fortune-gems2'
    sources = {}
    for row in data['rows']:
        url = urlsplit(row['url'])
        if url.hostname not in HOSTS or row.get('status') != 200 or not row.get('body'):
            continue
        relative = url.path.lstrip('/')
        if not relative.startswith(('fgp/', 'astarte2/', 'smallicon/', 'static/', 'api-documents/')):
            continue
        if relative.endswith('/'):
            relative += 'index.html'
        target = (destination / relative).resolve()
        if not target.is_relative_to(destination.resolve()):
            raise ValueError('Asset path escapes client directory')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(capture / row['body'], target)
        sources[relative] = {'request_id': row['id'], 'source': url._replace(query='', fragment='').geturl(), 'bytes': target.stat().st_size}
    fixtures = destination / 'fixtures'
    fixtures.mkdir(parents=True, exist_ok=True)
    (fixtures / 'asset-sources.json').write_text(json.dumps({'capture': session, 'assets': sources}, indent=2) + '\n', encoding='utf-8')
    print(f'Imported {len(sources)} assets')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session')
    import_capture(parser.parse_args().session)
