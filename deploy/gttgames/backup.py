"""Back up the two production stores during a coordinated maintenance stop."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from server.merchant.deployment import Deployment


def backup(config_path, output):
    config_path = Path(config_path)
    raw = config_path.read_bytes()
    config = json.loads(raw)
    if not Deployment(config).production:
        raise ValueError('Expected production configuration.')
    sources = [Path(config[key]).resolve() for key in ('merchant_database', 'game_database')]
    if len(set(sources)) != 2 or not all(path.is_file() for path in sources):
        raise ValueError('Both production databases must exist and be distinct.')
    destination = Path(output) / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    destination.mkdir(parents=True, mode=0o700)
    os.chmod(destination, 0o700)
    for source, name in zip(sources, ('merchants.sqlite3', 'gtt.sqlite3')):
        target = destination / name
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as db, closing(sqlite3.connect(target)) as copy:
            db.backup(copy)
            if copy.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise RuntimeError('Backup integrity check failed.')
        os.chmod(target, 0o600)
    config_copy = destination / 'production.json'
    config_copy.write_bytes(raw)
    os.chmod(config_copy, 0o600)
    return {'status': 'passed', 'backup': str(destination), 'databases': 2}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('/etc/gtt/production.json'))
    parser.add_argument('--output', type=Path, default=Path('/var/backups/gtt'))
    parser.add_argument('--services-stopped', action='store_true', required=True,
                        help='Confirm gateway/admin/RTP worker are stopped for a consistent pair of stores.')
    args = parser.parse_args()
    print(json.dumps(backup(args.config, args.output)))
