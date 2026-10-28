from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile

from deploy.gttgames import backup, package

ROOT = Path(__file__).resolve().parents[2]


class DeploymentToolsTests(unittest.TestCase):
    def test_release_contains_required_assets_and_excludes_private_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'source'
            files = {
                'server/merchant/sandbox.py': b'code',
                'clients/buffalo-win/index.html': b'original-client-bytes',
                'clients/buffalo-win/fixtures/auth-metadata.json': b'{}',
                'clients/buffalo-win/fixtures/game-rule.json': b'{}',
                'deploy/gttgames/production.json': b'{}',
                'services/gtt-gateway/config/buffalo-win.json': b'{}',
                'server/data/private.json': b'PRIVATE_SECRET',
                'server/tests/private-fixture.json': b'PRIVATE_SECRET',
                'services/gtt-gateway/data/sandbox.json': b'PRIVATE_SECRET',
                'clients/buffalo-win/fixtures/captured-player.json': b'PRIVATE_SECRET',
                'server/merchant/__pycache__/cache.pyc': b'PRIVATE_SECRET',
            }
            for name, body in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
            output = Path(temporary) / 'release.zip'
            result = package.package(output, root)
            self.assertEqual(result['status'], 'passed')
            with zipfile.ZipFile(output) as archive:
                self.assertIsNone(archive.testzip())
                manifest = json.loads(archive.read('release-manifest.json'))
                self.assertEqual(len(manifest['files']), 6)
                for name, expected in manifest['files'].items():
                    body = archive.read(name)
                    self.assertEqual(hashlib.sha256(body).hexdigest(), expected)
                    self.assertNotIn(b'PRIVATE_SECRET', body)
                    self.assertEqual(archive.getinfo(name).external_attr >> 16, 0o100644)
            with self.assertRaises(FileExistsError):
                package.package(output, root)

    def test_backup_pair_is_readable_and_does_not_overwrite_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sources = [root / 'merchants.sqlite3', root / 'gtt.sqlite3']
            for number, path in enumerate(sources):
                with closing(sqlite3.connect(path)) as db:
                    db.execute('CREATE TABLE sample(value INTEGER)')
                    db.execute('INSERT INTO sample VALUES (?)', (number,))
                    db.commit()
            config = json.loads((ROOT / 'deploy/gttgames/production.json').read_bytes())
            config.update(merchant_database=str(sources[0]), game_database=str(sources[1]))
            config_path = root / 'production.json'
            config_path.write_text(json.dumps(config))
            result = backup.backup(config_path, root / 'backups')
            for number, path in enumerate(sources):
                with closing(sqlite3.connect(Path(result['backup']) / path.name)) as db:
                    self.assertEqual(db.execute('SELECT value FROM sample').fetchone()[0], number)
                with closing(sqlite3.connect(path)) as db:
                    self.assertEqual(db.execute('SELECT value FROM sample').fetchone()[0], number)


if __name__ == '__main__':
    unittest.main()
