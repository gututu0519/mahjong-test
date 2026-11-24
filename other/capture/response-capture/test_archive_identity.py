"""历史游戏身份、按游戏归档及旧批次留在原位的回归测试。"""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import archive_identity as archive


CAT = 'https://sdstest.ink/api/v1/games/catalog'
GAMES = [
    {'id': 'one', 'externalId': '12', 'name': 'First', 'nameZh': '甲', 'metadata': {'brand': 'PG'}},
    {'id': 'two', 'externalId': 18, 'name': 'Second', 'metadata': {'brand': 'IGT'}},
]


class ArchiveTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()

    def batch(self, sid, records, target=None, group=None, state='completed'):
        folder = (self.root / group if group else self.root) / (sid * 32)
        bodies = folder / 'bodies'
        bodies.mkdir(parents=True, exist_ok=True)
        rows = []
        for i, item in enumerate(records, 1):
            url, method, mime, content, overrides = item
            raw = json.dumps(content).encode('ascii')
            body = 'bodies/%06d.json' % i
            (folder / body).write_bytes(raw)
            rows.append(dict({'id': i, 'url': url, 'method': method, 'mime': mime, 'body': body,
                              'state': 'complete', 'status': 200, 'size': len(raw)}, **overrides))
        data = {'id': folder.name, 'rows': rows, 'target_game': target, 'state': state,
                'url': 'https://user:secret@example.test/private-path?token=secret#secret'}
        (folder / 'manifest.json').write_text(json.dumps(data), encoding='utf-8')
        return folder

    @staticmethod
    def catalog(games=GAMES):
        return (CAT, 'GET', 'application/json', {'items': games}, {})

    @staticmethod
    def launch(site):
        return ('https://sdstest.ink/api/v1/games/' + site + '/launch?token=private', 'POST',
                'application/vnd.sds.encrypted+json; charset=utf-8', {}, {'status': 201})

    def test_launch_assets_target_and_multigame(self):
        self.batch('a', [self.catalog()])
        self.batch('b', [self.launch('two'), self.launch('one'), self.launch('one')])
        self.batch('c', [('https://s5.mmga1.com/12/assets/a.png', 'GET', 'image/png', {}, {})])
        self.batch('d', [], {'site': 'two'})
        index = archive.archive_index(self.root)
        self.assertEqual(index['a'*32]['summary']['display_name'], archive.UNKNOWN)
        multi = index['b'*32]['summary']
        self.assertEqual(multi['display_name'], '多游戏：IGT-18-Second、PG-12-甲')
        self.assertNotIn('target_game', multi)
        self.assertEqual(len(multi['identity_games']), 2)
        self.assertEqual(index['c'*32]['summary']['target_game']['externalId'], '12')
        self.assertEqual(index['d'*32]['summary']['display_name'], 'IGT-18-Second')
        self.assertNotIn('private', str(index))
        self.assertNotIn('secret', str(index))

    def test_ignore_untrusted_data_or_missing_body(self):
        self.batch('a', [self.catalog()])
        fake = self.launch('one')
        bad_rows = [(fake[0], 'GET', *fake[2:]), (fake[0].replace('sdstest.ink', 'other.site'), *fake[1:]),
                    (*fake[:4], {'size': 0}), (*fake[:4], {'body': 'bodies/000005.request.json'}),
                    (*fake[:4], {'body': 'bodies/000003.json'}), (*fake[:4], {'status': 403})]
        self.batch('b', bad_rows)
        self.batch('c', [(CAT, 'POST', 'application/json', {'items': [{'id': 'fake'}]}, {})])
        self.assertEqual(archive.archive_index(self.root)['b'*32]['summary']['display_name'], archive.UNKNOWN)
        self.assertEqual(archive.enrich_target(self.root, {'site': 'fake'}), {'site': 'fake'})

    def test_new_catalog_updates_old_results_and_skips_old_manifests(self):
        self.batch('a', [self.launch('two')])
        with patch.object(archive, '_read_batch', wraps=archive._read_batch) as reads:
            self.assertEqual(archive.archive_index(self.root)['a'*32]['summary']['display_name'], archive.UNKNOWN)
            self.batch('b', [self.catalog()], group='PG-12-甲')
            self.assertEqual(archive.archive_index(self.root)['a'*32]['summary']['display_name'], 'IGT-18-Second')
            self.assertEqual(archive.enrich_target(self.root, {'site': 'one'})['brand'], 'PG')
            self.assertEqual(archive.enrich_target(self.root, {'site': 'unused'}), {'site': 'unused'})
            self.assertEqual(reads.call_count, 2)
            current = archive.archive_index(self.root)
            current['a'*32]['summary'].clear()
            self.assertEqual(archive.archive_index(self.root)['a'*32]['summary']['display_name'], 'IGT-18-Second')
            self.assertEqual(reads.call_count, 2)

    def test_different_roots_do_not_share_catalogs_and_ambiguous_identity_is_unknown(self):
        self.batch('a', [self.catalog()])
        self.batch('b', [self.catalog([{**GAMES[0], 'externalId': 'other'}])])
        self.assertEqual(archive.enrich_target(self.root, {'site':'one'}), {'site':'one'})
        with tempfile.TemporaryDirectory() as other:
            self.assertEqual(archive.enrich_target(other, {'site':'two'}), {'site':'two'})

    def test_partial_manifest_does_not_drop_prior_history_or_other_games(self):
        known = self.batch('a', [self.catalog(), self.launch('one')])
        self.batch('b', [self.launch('two')])
        archive.archive_index(self.root)
        manifest = known / 'manifest.json'
        original = manifest.stat()
        manifest.write_text('{"id":')
        with patch.object(archive, '_read_batch', wraps=archive._read_batch) as reads:
            for _ in range(2):
                index = archive.archive_index(self.root)
                self.assertEqual(index['a'*32]['summary']['display_name'], 'PG-12-甲')
                self.assertEqual(index['b'*32]['summary']['display_name'], 'IGT-18-Second')
            self.assertEqual(reads.call_count, 2)
        self.batch('a', [self.catalog(), self.launch('two')])
        self.assertEqual(manifest.stat().st_size, original.st_size)
        # 明确复现旧指纹：修复文件与原成功版本同长度、同修改时间。
        os.utime(manifest, ns=(original.st_atime_ns, original.st_mtime_ns))
        self.assertEqual(archive.archive_index(self.root)['a'*32]['summary']['display_name'], 'IGT-18-Second')

    def test_read_failure_also_invalidates_prior_fingerprint(self):
        known = self.batch('a', [self.catalog(), self.launch('one')])
        archive.archive_index(self.root)
        manifest = known / 'manifest.json'
        original = manifest.stat()
        self.batch('a', [self.catalog(), self.launch('two')])
        os.utime(manifest, ns=(original.st_atime_ns, original.st_mtime_ns + 1_000_000_000))
        with patch.object(archive, '_read_batch', side_effect=OSError('测试文件暂时不可读')):
            self.assertEqual(archive.archive_index(self.root)['a'*32]['summary']['display_name'], 'PG-12-甲')
        os.utime(manifest, ns=(original.st_atime_ns, original.st_mtime_ns))
        with patch.object(archive, '_read_batch', wraps=archive._read_batch) as reads:
            for _ in range(2):
                self.assertEqual(archive.archive_index(self.root)['a'*32]['summary']['display_name'], 'IGT-18-Second')
            self.assertEqual(reads.call_count, 1)

    def test_imported_complete_uses_the_standard_history_state(self):
        imported = self.batch('a', [], state='complete')
        original = (imported / 'manifest.json').read_bytes()
        self.assertEqual(archive.archive_index(self.root)['a'*32]['summary']['state'], 'completed')
        self.assertEqual((imported / 'manifest.json').read_bytes(), original)

    def test_duplicate_sid_does_not_hide_other_history(self):
        self.batch('a', [self.catalog(), self.launch('one')])
        self.batch('a', [self.catalog(), self.launch('two')], group='duplicate')
        self.batch('b', [self.catalog(), self.launch('two')])
        index = archive.archive_index(self.root)
        self.assertEqual(list(index), ['b'*32])
        self.assertEqual(index['b'*32]['summary']['display_name'], 'IGT-18-Second')

    def test_label_limits_and_names(self):
        self.assertEqual(archive.game_label({'site': 'one'}), '')
        self.assertEqual(archive.game_label({'brand': 'pg', 'externalId': 14, 'zh': '甲/乙:*?'}), 'PG-14-甲／乙：＊？')
        long = archive.game_label({'brand': 'con', 'externalId': '14', 'name': '😀'*150})
        self.assertTrue(long.startswith('_CON-14-'))
        self.assertLessEqual(len(long.encode('utf-16le')), 232)

    def test_legacy_references_are_idempotent_and_preserve_files(self):
        folder = self.batch('a', [self.catalog(), self.launch('two'), self.launch('one')])
        sid = folder.name
        active = self.batch('b', [self.catalog()], state='running')
        self.batch('c', [self.catalog()], group='X')
        previous = (folder / 'manifest.json').read_bytes()
        index = archive.archive_index(self.root)
        first = archive.sync_legacy_groups(self.root, index)
        self.assertEqual(first['references'], 2)
        self.assertEqual(first['conflicts'], 0)
        self.assertEqual(first['shortcuts'], 2 if os.name == 'nt' else 0)
        for name in ('IGT-18-Second', 'PG-12-甲'):
            ref = self.root / name / (sid + '.capture-ref.json')
            self.assertEqual(json.loads(ref.read_bytes()), {'schema': 1, 'sid': sid})
            self.assertFalse((ref.parent / active.name).exists())
            if os.name == 'nt':
                link = self.root / name / (sid + '.lnk')
                cmd = "$s=New-Object -ComObject WScript.Shell; $p=$s.CreateShortcut($env:CAPTURE_TEST_LINK).TargetPath; if ($p -ne $env:CAPTURE_TEST_EXPECTED) {exit 1}"
                subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',cmd],
                               env={**os.environ, 'CAPTURE_TEST_LINK':str(link),
                                    'CAPTURE_TEST_EXPECTED':str(folder)}, check=True, capture_output=True)
        with patch.object(subprocess, 'run', side_effect=AssertionError('重复创建快捷方式')):
            self.assertEqual(archive.sync_legacy_groups(self.root, index), dict(references=0, shortcuts=0, conflicts=0))
        self.assertFalse((self.root / archive.UNKNOWN).exists())
        self.assertEqual((folder / 'manifest.json').read_bytes(), previous)
        self.assertTrue((active / 'manifest.json').is_file())

    def test_do_not_follow_bad_labels_or_overwrite_conflicts(self):
        folder = self.batch('d', [])
        group = self.root / 'PG-12-甲'
        group.mkdir()
        ref = group / (folder.name + '.capture-ref.json')
        ref.write_text('different')
        result = archive.link_legacy_session(self.root, folder.name, ['../escape', '.', 'CON', group.name])
        self.assertEqual(result, dict(references=0, shortcuts=0, conflicts=1))
        self.assertEqual(ref.read_text(), 'different')
        self.assertFalse((group / (folder.name + '.lnk')).exists())


if __name__ == '__main__':
    unittest.main()
