"""Extract a sanitized, complete Buffalo feature-buy oracle from an existing capture."""
import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs
from urllib.parse import urlsplit
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[3]
FIELDS = ('st', 'nst', 'cs', 'ml', 'tb', 'tbb', 'tw', 'aw', 'fs', 'gm', 's', 'sc',
          'rl', 'orl', 'es', 'bsc', 'wp', 'scs', 'ix', 'rs', 'ctw', 'acw', 'twbm',
          'sw', 'ge', 'fstc', 'ssaw', 'imw', 'it')


def read_capture(session):
    if len(session) != 32 or any(c not in '0123456789abcdef' for c in session):
        raise ValueError('Expected a capture session ID')
    folder = ROOT / 'response-capture/captures' / session
    manifest = folder / 'manifest.json'
    if manifest.is_file():
        snapshot = json.loads(manifest.read_bytes())
    else:
        with urlopen('http://127.0.0.1:8090/api/sessions/' + session, timeout=10) as response:
            snapshot = json.load(response)
    return folder, snapshot


def extract(session):
    folder, snapshot = read_capture(session)
    info, spins, purchase = None, [], None
    for row in snapshot['rows']:
        if '/game-api/buffalo-win/' not in row['url'] or row.get('status') != 200 or not row.get('body'):
            continue
        body = (folder / row['body']).read_bytes()
        payload = json.loads(body)
        dt = payload.get('dt') or {}
        if '/GameInfo/Get' in row['url'] and dt.get('fb'):
            info = {'row': row['id'], 'sha256': hashlib.sha256(body).hexdigest(),
                    'data': {key: dt[key] for key in ('cs', 'ml', 'mxl', 'fb', 'gcs')}}
        if not row['url'].split('?')[0].endswith('/Spin') or payload.get('err'):
            continue
        request = parse_qs((folder / row['request_body']).read_text(encoding='utf-8'), keep_blank_values=True)
        si = dt['si']
        if request.get('fb') == ['2'] and purchase is None:
            purchase = si['psid']
        if purchase is None or si['psid'] != purchase:
            continue
        spins.append({'row': row['id'], 'response_sha256': hashlib.sha256(body).hexdigest(),
                      'request': {key: request[key][0] for key in ('cs', 'ml', 'fb', 'ab') if key in request},
                      'wallet_change_minor': int((Decimal(str(si['bl'])) - Decimal(str(si['blb']))) * 100),
                      'si': {key: si[key] for key in FIELDS if key in si}})
    if not info or not spins or spins[-1]['si']['nst'] != 1 or not spins[-1]['si'].get('fs'):
        raise ValueError('Capture does not contain purchase configuration and a completed bought feature')
    if spins[-1]['si']['fs']['s'] != 0:
        raise ValueError('Free spins have not completed')
    return {'session': session, 'snapshot_rows': len(snapshot['rows']), 'game_info': info, 'spins': spins}


def import_assets(session):
    """Import only absent resource versions referenced by the existing client."""
    folder, snapshot = read_capture(session)
    client = ROOT / 'clients/buffalo-win'
    config = json.loads((client / 'assets/resources/config.02a8a.json').read_bytes())
    versions = {version for values in config['versions'].values() for version in values[1::2]}
    sources_path = client / 'fixtures/asset-sources.json'
    sources = json.loads(sources_path.read_bytes())
    pending = {}
    for row in snapshot['rows']:
        url = urlsplit(row['url'])
        if not url.path.startswith('/108/assets/resources/') or row.get('status') != 200 or not row.get('body'):
            continue
        relative = url.path[5:]
        target = (client / relative).resolve()
        if not target.is_relative_to(client.resolve()) or not target.name.split('.')[-2] in versions:
            continue
        data = (folder / row['body']).read_bytes()
        if target.exists():
            if target.read_bytes() != data:
                raise ValueError('Preserving existing asset with different bytes: ' + relative)
            continue
        if relative in pending and pending[relative][0] != data:
            raise ValueError('Conflicting response bodies: ' + relative)
        pending[relative] = (data, {'path': relative, 'source': url._replace(query='', fragment='').geturl(),
                                 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
                                 'session': session, 'requestId': row['id']})
    for relative, (data, source) in pending.items():
        target = client / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        sources.append(source)
    if pending:
        sources_path.write_bytes((json.dumps(sources, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    return list(pending)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session')
    args = parser.parse_args()
    result = extract(args.session)
    target = ROOT / 'clients/buffalo-win/fixtures/feature-buy-capture.json'
    target.write_bytes((json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    imported = import_assets(args.session)
    print(json.dumps({'session': args.session, 'steps': len(result['spins']), 'output': str(target), 'assets': imported}))


if __name__ == '__main__':
    main()
