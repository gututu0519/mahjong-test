"""共享服务预检回归；所有启停命令均注入替身，绝不操作实际数据库或 Docker。"""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from shared_services import SharedServiceError, SharedServices


class SharedServicesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='shared-services-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.data = self.repo / 'gateway/instance/data/local-postgres/pgdata'
        self.data.mkdir(parents=True)
        self.binary = self.repo / 'fixed-bin'
        self.binary.mkdir()
        self.postgres = self.binary / ('postgres.exe' if os.name == 'nt' else 'postgres')
        self.pg_ctl = self.binary / ('pg_ctl.exe' if os.name == 'nt' else 'pg_ctl')
        self.postgres.write_text('fixture', encoding='utf-8')
        self.pg_ctl.write_text('fixture', encoding='utf-8')
        self.command = [str(self.postgres), '-D', str(self.data)]
        self.process = dict(pid=100, created='2026-11-24T01:00:00+00:00', command=self.command,
                            executable=str(self.postgres), name=self.postgres.name)
        (self.data / 'PG_VERSION').write_text('17\n', encoding='utf-8')
        (self.data / 'postmaster.pid').write_text('100\n' + str(self.data) + '\n1795495026\n15432\n', encoding='utf-8')
        (self.data.parent / 'startup-record.json').write_text(json.dumps({
            'executablePath': str(self.postgres), 'commandLine': self.command, 'ports': [15432]}), encoding='utf-8')
        client = dict(pid=200, created='2026-11-24T01:01:00+00:00', name='node.exe', command=['node.exe', 'gateway'])
        self.inventory = {'processes': [self.process, client], 'listeners': [{'pid': 100, 'port': 15432, 'address': '127.0.0.1'}],
                          'windows_services': [], 'connections': [{'pid': 200, 'remote_port': 15432, 'remote_address': '127.0.0.1'}],
                          'docker': {'available': False, 'reason': 'fixture 未安装 Docker'}}
        self.commands = []
        self.manager = SharedServices(self.repo, inventory=lambda: copy.deepcopy(self.inventory), runner=self.run_command)

    def run_command(self, command, **kwargs):
        self.commands.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, '', '')

    def test_postgres_plan_explains_actual_dependencies_without_executing_or_exposing_internal_identity(self):
        snapshot = self.manager.snapshot()['services'][0]
        self.assertTrue(snapshot['can_stop'])
        self.assertEqual(snapshot['method'], 'pg_ctl')
        self.assertNotIn('identity', snapshot)
        self.assertNotIn('internal', snapshot)
        self.assertNotIn('identity_fingerprint', snapshot)
        plan = self.manager.prepare('advanced.postgres', 'stop')
        self.assertEqual(plan['targets'], [{'id': 'advanced.postgres', 'name': 'PostgreSQL', 'pid': 100,
                                           'created': self.process['created'], 'port': 15432, 'cwd': str(self.data), 'mode': 'pg_ctl'}])
        self.assertIn('200', ' '.join(plan['warnings']))
        self.assertIn('回滚未提交事务', ' '.join(plan['warnings']))
        self.assertEqual(self.commands, [])

    def test_fixed_pg_ctl_stop_and_start_ignore_tampered_client_command(self):
        plan = self.manager.prepare('advanced.postgres', 'stop')
        plan['internal']['program'] = 'untrusted.exe'
        result = self.manager.execute(plan)
        self.assertEqual(result['state'], 'stopping')
        self.assertEqual(self.commands[-1][0], [str(self.pg_ctl), 'stop', '-D', str(self.data), '-w', '-t', '60', '-m', 'fast'])
        self.assertFalse(self.commands[-1][1]['shell'])
        self.inventory['processes'] = []
        self.inventory['listeners'] = []
        self.inventory['connections'] = []
        (self.data / 'postmaster.pid').unlink()
        start = self.manager.prepare('advanced.postgres', 'start')
        self.assertEqual(self.manager.execute(start)['state'], 'starting')
        command = self.commands[-1][0]
        self.assertEqual(command[:7], [str(self.pg_ctl), 'start', '-D', str(self.data), '-w', '-t', '60'])
        self.assertIn('-l', command)
        self.assertFalse(any('initdb' in part or 'kill' in part for part in command))

    def test_pid_reuse_or_new_affected_client_invalidates_confirmed_plan(self):
        plan = self.manager.prepare('advanced.postgres', 'stop')
        self.process['created'] = '2026-11-24T02:00:00+00:00'
        with self.assertRaises(SharedServiceError):
            self.manager.execute(plan)
        self.process['created'] = '2026-11-24T01:00:00+00:00'
        self.inventory['processes'].append(dict(pid=300, created='2026-11-24T02:00:00+00:00', name='node.exe', command=['node.exe', 'mock']))
        self.inventory['connections'].append({'pid': 300, 'remote_port': 15432, 'remote_address': '127.0.0.1'})
        with self.assertRaises(SharedServiceError):
            self.manager.execute(plan)
        self.assertEqual(self.commands, [])

    def test_unknown_client_pid_is_preserved_and_invalidates_existing_confirmation(self):
        plan = self.manager.prepare('advanced.postgres', 'stop')
        self.inventory['connections'].append({'pid': 300, 'remote_port': 15432, 'remote_address': '127.0.0.1'})
        fresh = self.manager.prepare('advanced.postgres', 'stop')
        self.assertNotEqual(plan['identity_fingerprint'], fresh['identity_fingerprint'])
        unknown = next(p for p in fresh['impact']['dependents'] if p['pid'] == 300)
        self.assertEqual(unknown['name'], '未识别客户端')
        self.assertTrue(unknown['identity_unverified'])
        self.assertIn('未识别客户端（PID 300）', ' '.join(fresh['warnings']))
        with self.assertRaises(SharedServiceError):
            self.manager.execute(plan)
        self.assertEqual(self.commands, [])

    def test_mismatched_cluster_lock_unknown_actions_and_missing_docker_are_refused(self):
        (self.data / 'postmaster.pid').write_text('999\n' + str(self.data) + '\n1795495026\n15432\n', encoding='utf-8')
        for identifier, action in [('advanced.postgres', 'stop'), ('advanced.docker', 'start'), ('advanced.docker', 'stop'),
                                   ('all-containers', 'stop'), ('advanced.postgres', 'kill')]:
            with self.subTest(identifier=identifier, action=action):
                with self.assertRaises(SharedServiceError):
                    self.manager.prepare(identifier, action)
        self.assertEqual(self.commands, [])

    def test_stopped_database_does_not_reuse_another_process_port(self):
        self.inventory['processes'] = []
        self.inventory['listeners'] = [{'pid': 999, 'port': 15432, 'address': '127.0.0.1'}]
        (self.data / 'postmaster.pid').unlink()
        with self.assertRaises(SharedServiceError):
            self.manager.prepare('advanced.postgres', 'start')
        self.assertEqual(self.commands, [])

    def test_docker_running_container_set_is_bound_to_confirmation(self):
        container = {'id': 'a' * 64, 'name': 'fixture-one', 'image': 'fixture:1', 'running': True,
                     'started': '2026-11-24T01:00:00Z', 'restart': 'unless-stopped'}
        self.inventory['docker'] = {'available': True, 'desktop_cli': True, 'cli': str(self.binary / 'docker.exe'),
                                    'context': 'desktop-linux', 'endpoint': 'npipe:////./pipe/dockerDesktopLinuxEngine',
                                    'engine_running': True, 'containers_known': True, 'containers': [container]}
        plan = self.manager.prepare('advanced.docker', 'stop')
        self.assertEqual(plan['impact']['running_containers'][0]['name'], 'fixture-one')
        self.inventory['docker']['containers'].append(dict(container, id='b' * 64, name='fixture-two'))
        with self.assertRaises(SharedServiceError):
            self.manager.execute(plan)
        self.assertEqual(self.commands, [])


if __name__ == '__main__':
    unittest.main()
