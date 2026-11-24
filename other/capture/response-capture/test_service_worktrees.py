"""其他合法工作区的试玩发现与确认管理回归；所有进程操作均为替身。"""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from service_runtime import ServiceError, ServiceManager


class WorktreeDiscoveryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='service-worktree-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.other = self.root / 'repo-other'
        self.outside = self.root / 'repo-other-impostor'
        source = Path(__file__).resolve().parents[3]
        for path in ('gateway/src/catalog.ts', 'gateway/src/game-names.ts'):
            target = self.repo / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((source / path).read_bytes())
        for tree in (self.other, self.outside):
            folder = tree / 'games/great-bear/instance'
            folder.mkdir(parents=True)
            (folder / 'service.json').write_text(json.dumps({'id': 'great-bear', 'port': 18106, 'games': ['great-bear']}), encoding='utf-8')
            entry = tree / 'other/runtime/server/dist/cli.js'
            entry.parent.mkdir(parents=True)
            entry.write_text('// fixture entry', encoding='utf-8')
            route = tree / 'other/diagnostics/great-bear/postgres.json'
            route.parent.mkdir(parents=True)
            route.write_text(json.dumps({'driver': 'postgres', 'isolated': True, 'sources': [
                {'kind': 'local', 'schema': 'great_bear', 'path': str(folder / 'data/games.sqlite3')}]}), encoding='utf-8')
        self.data = {'processes': [], 'listeners': []}
        self.catalog = []
        originals = Mock()
        originals.owner = {}
        originals.catalog.side_effect = lambda: {'games': copy.deepcopy(self.catalog)}
        originals.captures = self.repo / 'captures'
        self.spawn, self.terminate = Mock(side_effect=self.fake_spawn), Mock(side_effect=self.fake_terminate)
        self.spawned = []
        self.manager = ServiceManager(self.repo, owner_chat='fixture-chat', start_background=False,
                                      inventory=lambda: copy.deepcopy(self.data), original_games=originals,
                                      spawner=self.spawn, terminator=self.terminate,
                                      creation=lambda p: '2026-11-24T12:00:00+00:00',
                                      worktree_provider=lambda: [self.repo, self.other])
        self.addCleanup(self.manager.close)

    def fake_spawn(self, command, **kwargs):
        self.spawned.append((command, kwargs))
        return type('FixtureProcess', (), {'pid': 900000 + len(self.spawned), 'stdin': io.BytesIO()})()

    def fake_terminate(self, record, actual):
        self.data['processes'] = [p for p in self.data['processes'] if p['pid'] != actual['pid']]
        self.data['listeners'] = [p for p in self.data['listeners'] if p['pid'] != actual['pid']]

    def process(self, pid, port, tree=None, *, action='service', directory=None, source=False):
        tree = tree or self.other
        folder = str(directory or tree / 'games/great-bear/instance')
        command = ['node.exe', str(tree / 'other/tooling/start-source.mjs'), 'great-bear'] if source else [
            'node.exe', 'dist/cli.js', action, '--service-dir', folder, '--port', str(port)]
        item = {'pid': pid, 'parent': 10, 'created': '2026-11-24T07:21:53+00:00',
                'executable': 'node.exe', 'command': command}
        self.data['processes'].append(item)
        if port:
            self.data['listeners'].append({'pid': pid, 'port': port, 'address': '127.0.0.1'})
        return item

    def discovered(self):
        snapshot = self.manager.refresh()
        self.assertEqual(snapshot['error'], '')
        return [row for row in snapshot['services'] if row['id'].startswith('worktree-demo.')]

    def test_two_live_instances_require_explicit_confirmation_without_changing_twenty_game_registry(self):
        self.process(13604, 18106)
        self.process(12256, 64538)
        rows = self.discovered()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['category'], 'game-demos')
        self.assertEqual(row['game_code'], 'great-bear')
        self.assertEqual(row['running_count'], 2)
        self.assertEqual(len([v for v in self.manager.registry if v.startswith('demo.')]), 20)
        self.assertEqual(len([v for v in self.manager.registry if v.startswith('compute.')]), 20)
        self.assertFalse(row['owned'] or row['can_stop'])
        self.assertTrue(row['can_start'])
        self.assertEqual({i['port'] for i in row['instances']}, {18106, 64538})
        self.assertEqual({i['open_url'] for i in row['instances']}, {'http://127.0.0.1:18106/', 'http://127.0.0.1:64538/'})
        for item in row['instances']:
            self.assertTrue(item['can_stop'])
            self.assertFalse(item['can_start'])
            self.assertTrue(item['requires_confirmation'])
            for operation in (self.manager.start, self.manager.stop):
                with self.assertRaises(ServiceError):
                    operation(item['id'])
        self.spawn.assert_not_called()
        self.terminate.assert_not_called()
        chosen = row['instances'][0]['id']
        confirmation = self.manager.prepare(chosen, 'stop')
        self.assertEqual(confirmation['execution_label'], '强制关闭')
        self.assertTrue(confirmation['warnings'])
        self.manager.stop(chosen, confirmation_id=confirmation['confirmation_id'])
        self.assertEqual([p['pid'] for p in self.data['processes']], [12256])

    def test_similar_path_prefix_outside_git_worktrees_is_not_accepted(self):
        self.process(1, 18106, self.outside)
        self.assertEqual(self.discovered(), [])
        # 另一个工作区中的同名已登记源码服务也不能归到当前工作区。
        process = dict(pid=2, executable='node.exe', command=['node.exe', str(self.outside / 'other/tooling/start-source.mjs'), 'cash-mania'])
        self.assertIsNone(self.manager._classify(process))

    def test_wrong_configuration_identity_missing_file_and_escaping_directory_are_rejected(self):
        config = self.other / 'games/great-bear/instance/service.json'
        self.process(1, 18106)
        config.write_text('{"id":"another-game","games":["great-bear"]}', encoding='utf-8')
        self.assertEqual(self.discovered(), [])
        config.unlink()
        self.assertEqual(self.discovered(), [])
        self.data['processes'] = []
        self.process(2, 64538, directory=self.other / '../repo-other-impostor/games/great-bear/instance')
        self.assertEqual(self.discovered(), [])

    def test_configuration_alone_or_compute_action_does_not_claim_running_demo(self):
        self.process(1, None)
        self.process(2, 64538, action='game')
        self.assertEqual(self.discovered(), [])

    def test_exact_source_entry_in_allowed_worktree_is_recognized(self):
        self.process(1, 18106, source=True)
        rows = self.discovered()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['port'], 18106)
        self.assertTrue(rows[0]['can_start'] and rows[0]['can_stop'])
        with self.assertRaises(ServiceError):
            self.manager.start(rows[0]['id'])
        self.spawn.assert_not_called()

    def test_multiple_instances_have_stable_registry_and_stopped_entry_can_reopen_with_verified_configuration(self):
        self.process(1, 18106)
        self.process(2, 64538)
        row = self.discovered()[0]
        registry = self.manager.home / 'external-services.json'
        first = registry.read_bytes()
        self.data['processes'].reverse()
        self.discovered()
        self.assertEqual(first, registry.read_bytes())
        self.data['processes'], self.data['listeners'] = [], []
        row = self.discovered()[0]
        self.assertEqual(row['status'], 'stopped')
        self.assertTrue(row['can_start'])
        self.assertFalse(row['can_stop'])
        confirmation = self.manager.prepare(row['id'], 'start')
        self.assertTrue(confirmation['requires_confirmation'])
        result = self.manager.start(row['id'], confirmation_id=confirmation['confirmation_id'])
        self.manager.jobs[result['run_id']].join(3)
        self.assertEqual(len(self.spawned), 1)
        command, options = self.spawned[0]
        self.assertIn(str(self.other / 'other/runtime/server/dist/cli.js'), command)
        self.assertIn(str(self.other / 'games/great-bear/instance'), command)
        self.assertNotIn(str(self.repo / 'other/tooling/start-source.mjs'), command)
        self.assertEqual(options['env']['GTT_PG_CONFIG'], str(self.other / 'other/diagnostics/great-bear/postgres.json'))
        self.assertEqual(str(options['cwd']), str(self.other))

    def test_missing_isolated_route_prevents_guessing_database_on_restart(self):
        self.process(1, 18106)
        (self.other / 'other/diagnostics/great-bear/postgres.json').unlink()
        row = self.discovered()[0]
        self.assertFalse(row['can_start'])
        self.assertTrue(row['can_stop'])
        with self.assertRaises(ServiceError):
            self.manager.prepare(row['id'], 'start')
        self.spawn.assert_not_called()

    def test_running_original_preview_is_not_duplicated_as_external_demo(self):
        process = self.process(1, 18106)
        artifact, run_id = 'a' * 32, 'b' * 32
        folder = self.repo / 'other/diagnostics/response-capture-previews' / run_id
        folder.mkdir(parents=True)
        record = {'run_id': run_id, 'artifact_id': artifact, 'state': 'ready', 'mode': 'offline',
                  'pid': 1, 'port': 18106, 'created': process['created'], 'command': process['command'],
                  'chat': 'another-chat', 'cwd': str(self.other), 'record': str(folder / 'ownership.json')}
        (folder / 'ownership.json').write_text(json.dumps(record), encoding='utf-8')
        self.catalog.append({'id': artifact, 'title': 'Great Bear', 'directory': str(self.other),
                             'game_ids': [], 'can_preview': False, 'reason': 'fixture'})
        self.assertEqual(self.discovered(), [])
        row = next(r for r in self.manager.snapshot()['services'] if r['id'] == 'original.' + artifact)
        self.assertEqual(row['running_count'], 1)


if __name__ == '__main__':
    unittest.main()
