"""Build a secret-free release including the original Buffalo Win client assets."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def package(output, root=ROOT):
    root, output = Path(root), Path(output)
    selected = []
    for folder in ('server', 'clients/buffalo-win', 'services/gtt-gateway/config', 'deploy/gttgames'):
        for path in (root / folder).rglob('*'):
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            if any(part in ('__pycache__', 'tests', 'data', 'logs', 'node_modules') for part in relative.parts):
                continue
            if path.suffix.lower() in ('.pyc', '.har', '.log', '.sqlite3', '.zip'):
                continue
            if 'fixtures' in relative.parts and path.name not in ('auth-metadata.json', 'game-rule.json'):
                continue
            selected.append((relative.as_posix(), path))
    for name in ('gtt-rtp.md', 'gtt-admin.md', 'gtt-merchant-wallet-v1.md', 'gtt-prebet.md'):
        path = root / 'docs' / name
        if path.is_file():
            selected.append((path.relative_to(root).as_posix(), path))
    required = ('server/merchant/sandbox.py', 'clients/buffalo-win/index.html',
                'clients/buffalo-win/fixtures/auth-metadata.json', 'clients/buffalo-win/fixtures/game-rule.json',
                'deploy/gttgames/production.json', 'services/gtt-gateway/config/buffalo-win.json')
    if set(required) - {name for name, _ in selected}:
        raise ValueError('The release is missing required source/assets.')
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {'format': 1, 'files': {}}
    with output.open('xb') as stream, zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        def write(name, body):
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, body)
        for name, path in sorted(selected):
            body = path.read_bytes()
            manifest['files'][name] = hashlib.sha256(body).hexdigest()
            write(name, body)
        write('release-manifest.json', (json.dumps(manifest, indent=2) + '\n').encode())
    return {'status': 'passed', 'package': str(output.resolve()), 'files': len(selected),
            'bytes': output.stat().st_size, 'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(package(args.output)))
