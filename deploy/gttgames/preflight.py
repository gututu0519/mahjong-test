"""Read-only deployment checks. --template also works on a developer machine."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from server.merchant.deployment import Deployment


def check(config_path, root=ROOT, template=False):
    config = json.loads(Path(config_path).read_bytes())
    deployment = Deployment(config)
    if not deployment.production or 'merchants' in config or any(key.startswith('sandbox_') for key in config):
        raise ValueError('Expected a production configuration without simulator data.')
    for key in ('merchant_database', 'game_database', 'bootstrap_directory', 'log_directory'):
        if not isinstance(config.get(key), str) or not PurePosixPath(config[key]).is_absolute():
            raise ValueError('An absolute Linux path is required: ' + key)
    if sys.version_info < (3, 11):
        raise ValueError('Python 3.11 or later is required.')
    node = shutil.which('node')
    if not node:
        raise ValueError('Node.js is required for original client module validation.')
    version = subprocess.run([node, '--version'], check=True, capture_output=True, text=True).stdout.strip()
    if int(version.lstrip('v').split('.')[0]) < 18:
        raise ValueError('Node.js 18 or later is required.')
    client = Path(root) / 'clients/buffalo-win'
    for relative in ('index.html', 'local-auth-bootstrap.js', 'local-frame-clock.js',
                     'fixtures/auth-metadata.json', 'fixtures/game-rule.json'):
        if not (client / relative).is_file():
            raise ValueError('Missing deployment asset: clients/buffalo-win/' + relative)
    if not any((client / 'assets').rglob('*')) or not list((client / 'shared').rglob('index.js')):
        raise ValueError('Complete original game assets and shared modules are required.')
    rules = Path(root) / 'services/gtt-gateway/config/buffalo-win.json'
    json.loads(rules.read_bytes())
    manifest_path = Path(root) / 'release-manifest.json'
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_bytes())
        if manifest.get('format') != 1 or not isinstance(manifest.get('files'), dict):
            raise ValueError('Invalid release manifest.')
        for name, expected in manifest['files'].items():
            target = (Path(root) / name).resolve()
            if not target.is_relative_to(Path(root).resolve()) or not target.is_file():
                raise ValueError('Missing/invalid release file: ' + name)
            if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                raise ValueError('Release checksum mismatch: ' + name)
    if not template:
        for directory in (Path(config['merchant_database']).parent, Path(config['game_database']).parent,
                          Path(config['bootstrap_directory']), Path(config['log_directory'])):
            if not directory.is_dir() or not os.access(directory, os.R_OK | os.W_OK):
                raise ValueError('Run as gtt after provisioning writable directory: ' + str(directory))
        for name in ('nginx', 'systemctl'):
            if not shutil.which(name):
                raise ValueError('Missing server command: ' + name)
    return {'status': 'passed', 'mode': 'template' if template else 'server', 'origins': deployment.origins,
            'python': sys.version.split()[0], 'node': version, 'game_assets': 'present',
            'release_manifest': 'verified' if manifest_path.is_file() else 'source checkout'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('production.json'))
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--template', action='store_true')
    args = parser.parse_args()
    print(json.dumps(check(args.config, args.root, args.template), ensure_ascii=False))
