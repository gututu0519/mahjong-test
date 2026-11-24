"""原版产物发现、目录边界和独立试玩归属回归；不启动实际游戏或桌面窗口。"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import webbrowser
from unittest.mock import Mock, patch

import original_games as original


GAME_A = {'site':'site-a', 'brand':'PG', 'externalId':'83', 'name':'Same Name', 'zh':'甲游戏'}
GAME_B = {'site':'site-b', 'brand':'IGT', 'externalId':'90370029', 'name':'Same Name', 'zh':'乙游戏'}
CREATED = '2026-11-24T00:00:00+00:00'


class OriginalGamesTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='original-games-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repo, self.other, self.outside = (self.root / name for name in ('repo', 'linked-tree', 'unregistered'))
        self.repo.mkdir()
        self.git('init', '-q')
        self.git('-c', 'user.name=测试夹具', '-c', 'user.email=fixture@example.invalid',
                 'commit', '--allow-empty', '-qm', '创建隔离测试基线')
        self.git('worktree', 'add', '--detach', '-q', str(self.other), 'HEAD')
        self.outside.mkdir()
        self.captures = self.root / 'captures'
        self.captures.mkdir()
        self.registry = original.OriginalGames(self.repo, self.captures)
        self.registry.owner['chat'] = 'fixture-current-chat'
        self.addCleanup(self.close_jobs)
        for tree in (self.repo, self.other):
            self.write(tree / original.CONVERTER / 'preview.py', '# 静态预览测试启动器\n')
        self.batch('a', GAME_A)
        self.batch('b', GAME_B)

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True, capture_output=True,
                              creationflags=original.NO_WINDOW)

    def close_jobs(self):
        for job in self.registry.jobs.values():
            job['log_stream'].close()

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def json(self, path, data):
        self.write(path, json.dumps(data, ensure_ascii=False))

    def batch(self, letter, target, *, body=None, url=None):
        folder = self.captures / (letter * 32)
        folder.mkdir(exist_ok=True)
        rows = []
        if body is not None:
            self.write(folder / 'bodies/1.html', body)
            rows.append(dict(id=1, url=url, status=200, state='complete', method='GET',
                             body='bodies/1.html', size=len(body.encode()), mime='text/html'))
        self.json(folder / 'manifest.json', dict(id=folder.name, state='completed',
            created=CREATED, url='https://sdstest.ink/', target_game=target, rows=rows))
        return folder

    def product(self, suffix, target=GAME_A, *, tree=None, status='static_candidate', extra=None):
        tree = tree or self.repo
        folder = tree / original.OUTPUT / ('原版客户端-20261124-' + suffix)
        self.write(folder / 'client/index.html', '<title>原版产物测试夹具</title>')
        self.write(folder / 'preview.py', '# 静态预览测试启动器\n')
        report = dict(schema=1, status=status, title='同名不会作为关联依据', entry_path='index.html',
                      input_batches=[{'target_game': target}] if target else [])
        report.update(extra or {})
        self.json(folder / '转换结果.json', report)
        return folder

    def catalog(self):
        return self.registry.catalog(force=True)['games']

    def junction(self, link, target):
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            if os.name != 'nt':
                raise
            subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                "New-Item -ItemType Junction -Path $env:ORIGINAL_TEST_LINK -Target $env:ORIGINAL_TEST_TARGET -ErrorAction Stop | Out-Null"],
                env={**os.environ, 'ORIGINAL_TEST_LINK':str(link), 'ORIGINAL_TEST_TARGET':str(target)},
                check=True, capture_output=True, creationflags=original.NO_WINDOW)
        self.addCleanup(lambda: link.unlink() if link.is_symlink() else link.rmdir())

    def test_only_registered_worktrees_and_exact_game_identities_are_discovered(self):
        first = self.product('001', GAME_A)
        second = self.product('002', GAME_B, tree=self.other)
        self.product('003', GAME_A, tree=self.outside)
        self.product('004', None, extra={'title':GAME_A['name']})
        self.product('005', extra={'input_batches':[{'target_game':GAME_A}, {'target_game':GAME_B}]})
        games = self.catalog()
        self.assertEqual({str(first), str(second)}, {g['directory'] for g in games})
        self.assertEqual({('site-a',), ('site-b',)}, {tuple(g['game_ids']) for g in games})
        self.assertTrue(all(g['can_preview'] for g in games))
        self.assertEqual({self.repo, self.other}, set(original.worktrees(self.repo)))

    def test_pg_entry_must_agree_with_identity_and_numeric_fallback_is_unique(self):
        self.product('001', GAME_B, status='captured_candidate',
                     extra={'entry':{'origin':'https://static5.mmga1.com', 'path':'/83/index.html'}})
        self.product('002', None, status='captured_candidate',
                     extra={'entry':{'origin':'https://static5.mmga1.com', 'path':'/83/index.html'}})
        games = self.catalog()
        self.assertEqual(1, len(games))
        self.assertEqual(['site-a'], games[0]['game_ids'])
        self.batch('c', {**GAME_A, 'site':'another-site'})
        self.assertEqual([], self.catalog())

    def test_status_and_trusted_launcher_are_required_but_folder_is_retained(self):
        pending = self.product('001', status='needs_adapter', extra={'detail':'该版本尚缺启动适配'})
        changed = self.product('002')
        self.write(changed / 'preview.py', '# 已被其他内容替换\n')
        games = {g['directory']:g for g in self.catalog()}
        self.assertFalse(games[str(pending)]['can_preview'])
        self.assertIn('尚缺启动适配', games[str(pending)]['reason'])
        self.assertFalse(games[str(changed)]['can_preview'])
        with patch.object(original, 'open_directory') as opener, patch.object(original.subprocess, 'Popen') as spawn, \
             patch.object(original, 'worktrees', return_value=[self.repo, self.other]):
            self.registry.open_folder(games[str(pending)]['id'])
            opener.assert_called_once_with(pending)
            with self.assertRaises(ValueError):
                self.registry.preview(games[str(pending)]['id'])
            spawn.assert_not_called()

    def test_folder_endpoint_accepts_only_current_artifact_ids_and_rechecks_report(self):
        folder = self.product('001')
        identifier = self.catalog()[0]['id']
        with patch.object(original, 'open_directory') as opener:
            for value in (str(folder), '../outside', 'f'*32, {'path':str(folder)}, None):
                with self.assertRaises(ValueError):
                    self.registry.open_folder(value)
            opener.assert_not_called()
            self.json(folder / '转换结果.json', {'schema':1, 'status':'static_candidate', 'title':GAME_A['name']})
            with self.assertRaises(ValueError):
                self.registry.open_folder(identifier)
            opener.assert_not_called()

    def test_reparse_artifacts_and_resource_paths_are_not_opened(self):
        external = self.product('outside', tree=self.outside)
        output = self.repo / original.OUTPUT
        output.mkdir(parents=True)
        alias = output / '原版客户端-20261124-linked'
        self.junction(alias, external)
        self.assertEqual([], self.catalog())
        folder = self.product('001')
        resources = folder / 'linked-client'
        self.junction(resources, external / 'client')
        for relative in ('../outside', str(external / 'client/index.html'), 'linked-client/index.html',
                         r'\Windows\system.ini', 'C:relative-file', 'client/index.html:alternate'):
            with self.assertRaises((ValueError, OSError)):
                original.plain_file(folder, relative)

    def test_old_source_identity_requires_matching_capture_body_hash(self):
        entry = '/igt/v0/TEST/index.html'
        body = '<title>原始入口</title>'
        capture = self.batch('b', GAME_B, body=body, url='https://static.funapptoday.com'+entry)
        sha = hashlib.sha256(body.encode()).hexdigest()
        folder = self.product('001', None, status='adapter_ready', extra={'game':'great-bear', 'entry':entry})
        self.json(folder / 'project-launch.json', {'game':'great-bear', 'repo':str(self.other)})
        self.json(folder / '来源索引.json', {'game':'great-bear', 'project_index':'instance/assets.json',
            'resources':[{'source_host':'static.funapptoday.com', 'source_path':entry, 'source_sha256':sha}]})
        self.json(self.other / 'games/great-bear/instance/assets.json', {'resources':[
            {'source':entry.lstrip('/'), 'source_sha256':sha, 'capture':'b'*32, 'request':1}]})
        self.assertEqual(['site-b'], self.catalog()[0]['game_ids'])
        self.write(capture / 'bodies/1.html', '<title>被替换的其他内容</title>')
        self.assertEqual([], self.catalog())

    def start_mock_preview(self):
        folder = self.product('001')
        identifier = self.catalog()[0]['id']
        process = Mock(pid=2222)
        process.poll.return_value = None
        with patch.object(original, 'worktrees', return_value=[self.repo, self.other]), \
             patch.object(original.subprocess, 'Popen', return_value=process) as spawn, \
             patch.object(original.threading, 'Thread'):
            response = self.registry.preview(identifier)
        return folder, identifier, self.registry.jobs[response['run_id']], process, spawn

    def process_info(self, pid=2222, port=49001, parent=None):
        return {'pid':pid, 'parent':parent, 'created':CREATED,
                'listeners':[{'LocalAddress':'127.0.0.1', 'OwningProcess':pid}] if port else []}

    def test_preview_does_not_reuse_another_windows_process_or_persisted_job(self):
        folder, identifier, job, process, spawn = self.start_mock_preview()
        self.json(folder / '预览进程-9999.json', {'pid':9999, 'chat':'another-chat', 'port':49000,
                  'cwd':str(folder), 'url':'http://127.0.0.1:49000/index.html'})
        self.assertEqual(2222, job['pid'])
        spawn.assert_called_once()
        with patch.object(original, 'inspect_process') as inspect, patch.object(webbrowser, 'open') as browser:
            with self.assertRaises(FileNotFoundError):
                self.registry._ready(job)
            inspect.assert_not_called()
            browser.assert_not_called()
        with patch.object(original, 'worktrees', return_value=[self.repo, self.other]), \
             patch.object(original.subprocess, 'Popen') as duplicate:
            self.assertEqual(job['run_id'], self.registry.preview(identifier)['run_id'])
            duplicate.assert_not_called()
        with self.assertRaises(ValueError):
            self.registry.job('e'*32)

    def test_static_preview_checks_chat_creation_and_listener_before_opening(self):
        folder, _, job, _, _ = self.start_mock_preview()
        job['created'] = CREATED
        record = {'pid':job['pid'], 'chat':self.registry.owner['chat'], 'port':49001,
                  'cwd':str(folder), 'url':'http://127.0.0.1:49001/index.html',
                  'started':job['started'], 'command':[str(job['item']['spec']['launcher'])]}
        info = self.process_info()
        with patch.object(original, 'inspect_process', return_value=info), patch.object(webbrowser, 'open') as browser:
            for fields in ({'chat':'another-chat'}, {'pid':9999}, {'cwd':str(self.outside)},
                           {'url':'https://outside.invalid/'}, {'url':'http://127.0.0.1:49002/'}):
                self.json(folder / '预览进程-2222.json', {**record, **fields})
                with self.assertRaises(ValueError):
                    self.registry._ready(job)
            self.json(folder / '预览进程-2222.json', record)
            info['created'] = '2026-11-23T00:00:00+00:00'
            with self.assertRaises(ValueError):
                self.registry._ready(job)
            info['created'] = CREATED
            info['listeners'][0]['OwningProcess'] = 9999
            with self.assertRaises(ValueError):
                self.registry._ready(job)
            browser.assert_not_called()
            info['listeners'][0]['OwningProcess'] = 2222
            ready = self.registry._ready(job)
            self.assertEqual(49001, ready['port'])
            self.assertEqual(record['url'], ready['url'])
            browser.assert_not_called()

    def test_watch_marks_ready_only_after_verification_and_keeps_failure_record(self):
        _, _, job, process, _ = self.start_mock_preview()
        with patch.object(original, 'process_created', return_value=CREATED), \
             patch.object(self.registry, '_ready', return_value={'port':49001, 'message':'已核验就绪'}):
            self.registry._watch(job)
        self.assertEqual('ready', self.registry.job(job['run_id'])['state'])
        saved = json.loads(Path(job['record']).read_bytes())
        self.assertEqual('ready', saved['state'])
        self.assertNotIn('process', saved)
        self.assertTrue(job['log_stream'].closed)
        # 另一独立请求退出后必须保留失败记录，不能借用前一请求已就绪的状态。
        with patch.object(original, 'worktrees', return_value=[self.repo, self.other]), \
             patch.object(original.subprocess, 'Popen', return_value=Mock(pid=3333)), \
             patch.object(original.threading, 'Thread'):
            response = self.registry.preview(job['artifact_id'])
        failed = self.registry.jobs[response['run_id']]
        failed['process'].poll.return_value = 1
        with patch.object(original, 'process_created', return_value=CREATED), \
             patch.object(self.registry, '_ready', side_effect=FileNotFoundError):
            self.registry._watch(failed)
        self.assertEqual('error', self.registry.job(failed['run_id'])['state'])
        self.assertEqual('error', json.loads(Path(failed['record']).read_bytes())['state'])
        self.assertTrue(failed['log_stream'].closed)

    def test_adapter_uses_only_this_run_child_and_checks_game_and_client_fingerprint(self):
        folder = self.product('001')
        probe = b'fixture-exported-client'
        record = self.root / 'current-job/ownership.json'
        record.parent.mkdir()
        job = {'pid':2222, 'mode':'adapter', 'record':str(record), 'item':{'folder':folder,
            'spec':{'spec':{'game':'great-bear', 'probe':'/client-probe.bin',
                           'probe_sha256':hashlib.sha256(probe).hexdigest()}}}}
        ownership = {'pid':4444, 'port':49002, 'created':CREATED, 'chat':self.registry.owner['chat'],
                     'game':'great-bear', 'client':str(folder / 'client')}
        ready = {'pid':4444, 'port':49002, 'origin':'http://127.0.0.1:49002', 'entry':'http://127.0.0.1:49002/'}
        # 其他窗口留下的 ready 文件即使字段齐全，也不进入本次就绪判断。
        self.json(folder / 'run-another-chat/ownership.json', ownership)
        self.json(folder / 'run-another-chat/ready.json', ready)
        with patch.object(original, 'inspect_process') as inspect, patch.object(webbrowser, 'open') as browser:
            with self.assertRaises(FileNotFoundError):
                self.registry._ready(job)
            inspect.assert_not_called()
            browser.assert_not_called()
        self.json(record.parent / 'service/ownership.json', ownership)
        self.json(record.parent / 'service/ready.json', ready)
        info = self.process_info(pid=4444, port=49002, parent=9999)
        with patch.object(original, 'inspect_process', return_value=info), \
             patch.object(webbrowser, 'open') as browser:
            with self.assertRaises(FileNotFoundError):
                self.registry._ready(job)
            browser.assert_not_called()
            info['parent'] = 2222
            for health_game, asset, expected in [('other-game', probe, False),
                                                  ('great-bear', b'wrong-client', False),
                                                  ('great-bear', probe, True)]:
                connection = Mock()
                health = Mock(status=200)
                health.read.return_value = json.dumps({'status':'ok', 'service_id':health_game}).encode()
                resource = Mock(status=200)
                resource.read.return_value = asset
                connection.getresponse.side_effect = [health, resource]
                with patch.object(original, 'HTTPConnection', return_value=connection):
                    if expected:
                        result = self.registry._ready(job)
                        self.assertEqual(4444, result['service_pid'])
                        self.assertEqual(ready['entry'], result['url'])
                        browser.assert_not_called()
                    else:
                        with self.assertRaises(FileNotFoundError):
                            self.registry._ready(job)
                        browser.assert_not_called()
                connection.close.assert_called_once()

    def test_successful_launcher_exit_rechecks_just_written_ready_record(self):
        _, _, job, process, _ = self.start_mock_preview()
        job['mode'] = 'adapter'
        process.poll.return_value = 0
        with patch.object(original, 'process_created', return_value=CREATED), \
             patch.object(self.registry, '_ready', side_effect=[FileNotFoundError,
                 {'port':49003, 'service_pid':4444, 'message':'已核验快速启动结果'}]) as ready:
            self.registry._watch(job)
        self.assertEqual(2, ready.call_count)
        self.assertEqual('ready', self.registry.job(job['run_id'])['state'])
        self.assertTrue(job['log_stream'].closed)


if __name__ == '__main__':
    unittest.main()
