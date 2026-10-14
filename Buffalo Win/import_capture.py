"""Import captured Buffalo assets without touching accounts, entry HTML or existing bytes."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session')
    args = parser.parse_args()
    if len(args.session) != 32 or any(c not in '0123456789abcdef' for c in args.session):
        parser.error('Expected a capture session ID')
    root = Path(__file__).resolve().parent
    capture = root.parent / 'response-capture/captures' / args.session
    with urlopen('http://127.0.0.1:8090/api/sessions/' + args.session, timeout=10) as response:
        snapshot = json.load(response)
    manifest_path = root / 'fixtures/asset-sources.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    known = {item['path'] for item in manifest}
    pending = {}
    for row in snapshot['rows']:
        url = urlsplit(row['url'])
        if (row.get('status') != 200 or not row.get('body')
                or url.hostname not in ('static.pg-demo.com', 'static.eajzzxhro.com')):
            continue
        relative = (url.path[5:] if url.path.startswith('/108/') else
                    url.path.lstrip('/') if url.path.startswith('/shared/') else '')
        if not relative or Path(relative).suffix.lower() not in ('.json', '.js', '.css', '.png', '.jpg', '.jpeg', '.webp', '.mp3', '.ogg', '.woff', '.woff2'):
            continue
        target, body = (root / relative).resolve(), (capture / row['body']).resolve()
        if not target.is_relative_to(root) or not body.is_relative_to(capture.resolve()):
            raise ValueError('Capture path outside asset directories')
        data = body.read_bytes()
        if target.exists():
            if target.read_bytes() != data:
                raise ValueError('Version conflict; preserving existing asset: ' + relative)
            continue
        if relative in pending and pending[relative][1] != data:
            raise ValueError('Conflicting capture bodies: ' + relative)
        pending[relative] = (target, data, {
            'path': relative, 'source': url._replace(query='', fragment='').geturl(),
            'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
            'session': args.session, 'requestId': row['id'],
        })
    for relative, (target, data, item) in pending.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        if relative not in known:
            manifest.append(item)
    manifest_path.write_bytes((json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(json.dumps({'session': args.session, 'state': snapshot['state'],
                      'rows': len(snapshot['rows']), 'imported': list(pending)}))


if __name__ == '__main__':
    main()
