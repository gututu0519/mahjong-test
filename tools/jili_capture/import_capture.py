"""Import captured JILI assets without retaining launch credentials or request bodies."""
import argparse
import json
import shutil
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
HOSTS = {'casino-wbgame.jiligames.com', 'uat-web-cdn.jiligames.com'}


def import_capture(session):
    capture = ROOT / 'response-capture/captures' / session
    manifest = json.loads((capture / 'manifest.json').read_text(encoding='utf-8'))
    destination = ROOT / 'clients/super-ace'
    sources = {}
    for row in manifest['rows']:
        url = urlsplit(row['url'])
        if url.hostname not in HOSTS or row.get('status') != 200 or not row.get('body'):
            continue
        relative = url.path.lstrip('/')
        if not relative or relative.endswith('/'):
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
    print(f'Imported {len(sources)} assets into {destination}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session')
    import_capture(parser.parse_args().session)
