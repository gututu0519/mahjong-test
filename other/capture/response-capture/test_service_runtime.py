"""服务控制台隔离回归；仅最后一项创建并终止测试自己的临时进程。"""
import copy
from http.client import HTTPConnection
import io
import json
import os
from pathlib import Path
import queue
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from original_games import NO_WINDOW, OriginalGames, inspect_process, process_created
from service_registry import game_catalog
from service_runtime import ServiceError, ServiceManager, command_matches, terminate_checked
from service_control import request_stop


class FixtureOriginals:
    def __init__(self):
        self.games = []

    def catalog(self):
        return {'games': copy.deepcopy(self.games)}


class FixtureSharedServices:
    def __init__(self):
        self.impact = [{'id':'fixture.gateway', 'pid':981001, 'created':'2026-11-24T01:00:00+00:00'}]
        self.executed = []

    def snapshot(self, inventory=None):
        return {'services':[{'id':'advanced.postgres', 'status':'running', 'can_start':True, 'can_stop':True}]}

    def prepare(self, identifier, action, inventory=None):
        return {'id':identifier, 'action':action, 'identity_fingerprint':json.dumps(self.impact, sort_keys=True),
                'targets':[{'id':identifier, 'name':'共享数据库', 'pid':981000, 'port':15432, 'mode':'shared'}],
                'warnings':['停止共享数据库会影响其他聊天的网关和试玩。'], 'impact':copy.deepcopy(self.impact)}

    def execute(self, plan):
        self.executed.append(copy.deepcopy(plan))
        return {'ok':True, 'state':'stopping' if plan['action'] == 'stop' else 'starting'}


class ServiceRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='service-runtime-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        source = Path(__file__).resolve().parents[3]
        for relative in ('gateway/src/catalog.ts', 'gateway/src/game-names.ts'):
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((source / relative).read_bytes())
        for relative in ('other/tooling/run.mjs', 'other/tooling/start-source.mjs', 'other/capture/response-capture/app.py',
                         'other/capture/response-capture/quality_service.py',
                         'other/capture/response-capture/controlled_node.mjs'):
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('// fixture', encoding='utf-8')
        self.current = {'processes': [], 'listeners': []}
        self.spawned = []
        self.terminated = []
        self.originals = FixtureOriginals()
        self.manager = ServiceManager(self.repo, owner_chat='fixture-current-chat',
                                      inventory=lambda: copy.deepcopy(self.current),
                                      spawner=self.spawn, creation=lambda p: '2026-11-24T01:02:03+00:00',
                                      terminator=self.terminate, original_games=self.originals,
                                      health=lambda r: {}, start_background=False)
        self.addCleanup(self.manager.close)

    def spawn(self, command, **kwargs):
        pid = 900001 + len(self.spawned)
        self.spawned.append((copy.deepcopy(command), kwargs, pid))
        return type('FixtureProcess', (), {'pid': pid, 'stdin':io.BytesIO() if kwargs.get('stdin') == subprocess.PIPE else None})()

    def terminate(self, record, actual):
        self.terminated.append(actual['pid'])
        self.current['processes'] = [p for p in self.current['processes'] if p['pid'] != actual['pid']]
        self.current['listeners'] = [p for p in self.current['listeners'] if p['pid'] != actual['pid']]

    def start_live(self, identifier='fixed.gateway'):
        prepared = self.manager.prepare(identifier, 'start')
        result = self.manager.start(identifier, prepared.get('confirmation_id'))
        self.manager.jobs[result['run_id']].join(5)
        self.assertFalse(self.manager.jobs[result['run_id']].is_alive())
        record = self.manager.records[result['run_id']]
        self.assertIsNotNone(record['pid'], record)
        self.current['processes'].append({'pid': record['pid'], 'parent': 42,
                                         'created': record['created'], 'command': record['command'],
                                         'cwd': str(self.repo), 'executable': record['command'][0]})
        if record['port']:
            self.current['listeners'].append({'pid': record['pid'], 'port': record['port'], 'address': '127.0.0.1'})
        self.manager.refresh()
        return record

    def row(self, identifier):
        return next(row for row in self.manager.snapshot()['services'] if row['id'] == identifier)

    def confirm_stop(self, identifier, manager=None):
        manager = manager or self.manager
        prepared = manager.prepare(identifier, 'stop')
        return manager.stop(identifier, prepared.get('confirmation_id'))

    def external_node(self, pid=980001, action='gateway'):
        self.current['processes'].append({'pid':pid, 'parent':42, 'created':'2026-11-24T01:00:00+00:00',
                                         'command':['node', str(self.repo / 'other/tooling/start-source.mjs'), action],
                                         'cwd':str(self.repo), 'executable':'node.exe'})
        self.current['listeners'].append({'pid':pid, 'port':18201 + pid % 10, 'address':'127.0.0.1'})
        self.manager.refresh()
        return 'external.' + str(pid)

    def test_failure_before_listen_keeps_reason_across_polls(self):
        record = self.start_live('fixed.admin')
        record['state'] = 'starting'
        Path(record['log']).write_text('启动流水线失败：依赖安装锁仍被占用', encoding='utf-8')
        self.current['processes'].clear()
        self.current['listeners'].clear()
        for _ in range(2):
            self.manager.refresh()
            self.assertEqual(self.row('fixed.admin')['status'], 'error')
            self.assertIn('依赖安装锁仍被占用', self.row('fixed.admin')['reason'])

    def test_full_catalog_does_not_claim_missing_games_are_deployed(self):
        snapshot = self.manager.refresh()
        expected = {code for code, _, _ in game_catalog(self.repo)}
        self.assertEqual(len(expected), 20)
        for category in ('game-demos', 'game-compute'):
            rows = [row for row in snapshot['services'] if row['category'] == category]
            self.assertEqual({row['game_code'] for row in rows}, expected)
            self.assertTrue(all(row['status'] == 'stopped' and not row['can_start'] for row in rows))
        self.assertEqual(len([row for row in snapshot['services'] if row['category'] == 'fixed']), 6)
        self.assertFalse(self.spawned)

    def test_whitelist_and_shared_dependencies_cannot_start_or_stop(self):
        self.current = {
            'processes': [dict(pid=920001, name='postgres.exe', executable='postgres.exe', command=['postgres.exe']),
                          dict(pid=920002, name='com.docker.backend.exe', executable='com.docker.backend.exe',
                               command=['com.docker.backend.exe'])],
            'listeners': [dict(pid=920001, port=15432, address='127.0.0.1')],
        }
        self.manager.refresh()
        for identifier in ('advanced.postgres', 'advanced.docker'):
            row = self.row(identifier)
            self.assertEqual(row['status'], 'running')
            self.assertFalse(row['can_start'])
            self.assertFalse(row['can_stop'])
        for identifier in ('unknown', 'node --eval danger', '../app.py', 'advanced.postgres', 'advanced.docker'):
            with self.subTest(identifier=identifier):
                with self.assertRaises(ServiceError):
                    self.manager.start(identifier)
                with self.assertRaises(ServiceError):
                    self.manager.stop(identifier)
        self.assertFalse(self.spawned)
        self.assertFalse(self.terminated)

    def test_conflicting_port_chooses_new_port_and_records_fixed_command(self):
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0))
            occupied.listen()
            port = occupied.getsockname()[1]
            self.manager.registry['fixed.gateway']['default_port'] = port
            record = self.start_live()
            self.assertNotEqual(record['port'], port)
            self.assertEqual(occupied.getsockname()[1], port)
            self.assertFalse(self.terminated)
        argv, kwargs, _ = self.spawned[0]
        self.assertEqual(argv[1:], [str(self.repo / 'other/capture/response-capture/controlled_node.mjs'), 'source', 'gateway'])
        self.assertFalse(kwargs['shell'])
        self.assertEqual(kwargs['env']['CODEX_THREAD_ID'], 'fixture-current-chat')
        self.assertEqual(kwargs['env']['GATEWAY_PORT'], str(record['port']))
        saved = json.loads(Path(record['ownership_file']).read_text(encoding='utf-8'))
        self.assertEqual(saved['created'], record['created'])
        self.assertEqual(saved['cwd'], str(self.repo))
        self.assertEqual(self.row('fixed.gateway')['status'], 'running')

    def test_pid_reuse_wrong_chat_command_and_directory_refuse_stop(self):
        record = self.start_live('advanced.quality')
        self.assertTrue(self.row('advanced.quality')['can_stop'])
        baseline = copy.deepcopy(record)
        actual = copy.deepcopy(self.current['processes'][0])
        cases = [('created', '2026-11-24T02:02:03+00:00'), ('command', ['node', 'other-window.js']),
                 ('cwd', str(self.repo.parent / 'other-window'))]
        for field, value in cases:
            with self.subTest(field=field):
                self.current['processes'][0] = dict(actual, **{field: value})
                with self.assertRaises(ServiceError):
                    self.manager.stop('run.' + record['id'])
                self.assertFalse(self.terminated)
        self.current['processes'][0] = actual
        record.update(baseline, chat='another-chat')
        with self.assertRaises(ServiceError):
            self.manager.stop('run.' + record['id'])
        self.assertFalse(self.terminated)

    def test_multiple_instances_stop_only_chosen_and_show_actual_exit(self):
        first, second = self.start_live('advanced.quality'), self.start_live('advanced.quality')
        self.assertEqual(self.row('advanced.quality')['running_count'], 2)
        with self.assertRaises(ServiceError):
            self.manager.stop('advanced.quality')
        self.assertFalse(self.terminated)
        self.confirm_stop('run.' + first['id'])
        self.manager.refresh()
        row = self.row('advanced.quality')
        self.assertEqual(self.terminated, [first['pid']])
        self.assertEqual(row['running_count'], 1)
        self.assertEqual({v['id']: v['status'] for v in row['instances']},
                         {'run.' + first['id']: 'stopped', 'run.' + second['id']: 'running'})
        self.current = {'processes': [], 'listeners': []}
        self.manager.refresh()
        self.assertEqual(self.row('advanced.quality')['status'], 'stopped')
        self.assertEqual(self.row('advanced.quality')['running_count'], 0)

    def test_inventory_failure_disables_cached_stop(self):
        record = self.start_live('advanced.quality')
        self.assertTrue(self.row('advanced.quality')['can_stop'])
        def failing_inventory():
            raise OSError('fixture inventory failed')
        self.manager.inventory = failing_inventory
        with self.assertRaises(ServiceError):
            self.manager.stop('run.' + record['id'])
        self.assertFalse(self.row('advanced.quality')['can_stop'])
        self.assertTrue(self.manager.snapshot()['error'])
        self.assertFalse(self.terminated)

    def test_node_stop_uses_private_pipe_and_never_force_terminates(self):
        record = self.start_live()
        self.assertTrue(self.row('fixed.gateway')['can_stop'])
        handle = self.manager._handles[record['id']]
        self.assertEqual(self.spawned[0][1]['stdin'], subprocess.PIPE)
        prepared = self.manager.prepare('run.' + record['id'], 'stop')
        self.assertEqual(prepared['targets'][0]['mode'], 'pipe')
        result = self.manager.stop('run.' + record['id'], prepared.get('confirmation_id'))
        self.assertEqual(result['state'], 'stopping')
        self.assertEqual(handle.stdin.getvalue(), b'stop\n')
        self.assertFalse(self.terminated)

    def test_legacy_node_or_lost_private_pipe_cannot_stop(self):
        record = self.start_live()
        original_command = copy.deepcopy(record['command'])
        legacy = [record['command'][0], str(self.repo / 'other/tooling/start-source.mjs'), 'gateway']
        record['command'] = legacy
        self.current['processes'][0]['command'] = legacy
        self.manager._handles.pop(record['id'])
        self.manager.refresh()
        self.assertTrue(self.row('fixed.gateway')['can_stop'])
        self.assertEqual(self.manager.prepare('run.' + record['id'], 'stop')['targets'][0]['mode'], 'force')
        with self.assertRaises(ServiceError):
            self.manager.stop('run.' + record['id'])
        record['command'] = original_command
        self.current['processes'][0]['command'] = original_command
        self.manager.refresh()
        self.assertTrue(self.row('fixed.gateway')['can_stop'])
        with self.assertRaises(ServiceError):
            self.manager.stop('run.' + record['id'])
        self.assertFalse(self.terminated)

    def control_owner(self, record):
        owner = {'pid':record['pid'], 'chat':record['chat'], 'nonce':record['control_nonce'],
                 'cwd':record['cwd'], 'command':record['command'], 'started':'2026-11-24T03:00:00+00:00', 'state':'ready'}
        path = Path(record['control_directory']) / 'control-owner.json'
        path.write_text(json.dumps(owner), encoding='utf-8')
        return owner, path

    def test_reopened_console_stops_owned_node_through_persistent_channel(self):
        record = self.start_live()
        self.control_owner(record)
        reopened = ServiceManager(self.repo, owner_chat='fixture-current-chat',
                                  inventory=lambda: copy.deepcopy(self.current), spawner=self.spawn,
                                  terminator=self.terminate, original_games=self.originals, start_background=False)
        self.addCleanup(reopened.close)
        reopened.refresh()
        row = next(r for r in reopened.snapshot()['services'] if r['id'] == 'fixed.gateway')
        self.assertTrue(row['can_stop'])
        self.assertFalse(reopened._handles)
        result = self.confirm_stop('run.' + record['id'], reopened)
        self.assertEqual(result['state'], 'stopping')
        written = json.loads((Path(record['control_directory']) / 'stop-request.json').read_text(encoding='utf-8'))
        self.assertEqual(written, {'pid':record['pid'], 'chat':record['chat'],
                                   'created':record['created'], 'nonce':record['control_nonce']})
        self.assertEqual(self.manager._handles[record['id']].stdin.getvalue(), b'')
        self.assertFalse(self.terminated)

    def test_persistent_channel_rejects_wrong_record_and_current_process_identity(self):
        record = self.start_live()
        owner, owner_path = self.control_owner(record)
        stop_file = Path(record['control_directory']) / 'stop-request.json'
        actual = copy.deepcopy(self.current['processes'][0])
        for field, value in [('nonce','0'*32), ('pid',record['pid']+1), ('chat','another-chat'),
                              ('command',['node','other-server.mjs']), ('cwd',str(self.repo.parent))]:
            with self.subTest(owner_field=field), self.assertRaises(ValueError):
                owner_path.write_text(json.dumps(dict(owner, **{field:value})), encoding='utf-8')
                request_stop(record, self.manager.home, record['chat'], inspector=lambda pid: actual)
            self.assertFalse(stop_file.exists())
        owner_path.write_text(json.dumps(owner), encoding='utf-8')
        for field, value in [('pid',record['pid']+1), ('created','2026-11-24T04:00:00+00:00'),
                              ('command',['node','other-server.mjs'])]:
            with self.subTest(actual_field=field), self.assertRaises(ValueError):
                request_stop(record, self.manager.home, record['chat'],
                             inspector=lambda pid:dict(actual, **{field:value}))
            self.assertFalse(stop_file.exists())
        unsafe = dict(record, control_directory=str(self.repo))
        with self.assertRaises(ValueError):
            request_stop(unsafe, self.manager.home, record['chat'], inspector=lambda pid:actual)
        self.assertFalse(stop_file.exists())

    def test_old_or_unidentified_child_cannot_be_claimed_by_reused_parent_pid(self):
        record = self.start_live('advanced.quality')
        child = {'pid':939001, 'parent':record['pid'], 'command':['python', 'fixture-child.py']}
        self.current['processes'].append(child)
        for created in ('2026-11-23T01:02:03+00:00', None):
            child['created'] = created
            with self.subTest(created=created), self.assertRaises(ServiceError):
                self.manager.stop('run.' + record['id'])
            self.assertFalse(self.terminated)
        child['created'] = '2026-11-24T01:02:04+00:00'
        self.confirm_stop('run.' + record['id'])
        self.assertEqual(self.terminated, [child['pid'], record['pid']])

    def test_capture_requires_current_identity_shutdown_and_no_active_capture(self):
        record = self.start_live('fixed.capture')
        identifier = 'run.' + record['id']
        force = self.manager.prepare(identifier, 'stop')
        self.assertTrue(force['requires_confirmation'])
        self.assertEqual(force['targets'][0]['mode'], 'force')
        for has_shutdown in (False, True):
            self.manager.health = lambda r: {'pid':record['pid'], 'chat':'fixture-current-chat',
                                             'capabilities':{'shutdown':has_shutdown}, 'active_sessions':1}
            with self.subTest(shutdown=has_shutdown):
                self.manager.refresh()
                self.assertFalse(self.row('fixed.capture')['can_stop'])
                with self.assertRaises(ServiceError):
                    self.manager.prepare(identifier, 'stop')
        self.manager.health = lambda r: {'pid': record['pid'], 'chat': 'fixture-current-chat',
                                         'capabilities': {'shutdown': True}, 'active_sessions': 0}
        self.manager.refresh()
        self.assertTrue(self.row('fixed.capture')['can_stop'])
        prepared = self.manager.prepare(identifier, 'stop')
        self.assertFalse(prepared['requires_confirmation'])
        self.assertEqual(prepared['targets'][0]['mode'], 'capture')
        with patch.object(self.manager, '_shutdown_capture') as shutdown:
            self.manager.stop(identifier)
            shutdown.assert_called_once()
        self.assertFalse(self.terminated)

    def test_ready_preview_record_does_not_mean_exited_process_is_running(self):
        directory = self.repo / 'generated-original'
        directory.mkdir()
        self.originals.games = [{'id': 'fixture-product', 'title': '测试原版', 'directory': str(directory),
                                'can_preview': True}]
        folder = self.repo / 'other/diagnostics/response-capture-previews/fixture-preview'
        folder.mkdir(parents=True)
        preview = {'run_id': 'fixture-preview', 'artifact_id': 'fixture-product', 'state': 'ready',
                   'pid': 910001, 'created': '2026-11-24T01:02:03+00:00', 'chat': 'another-chat',
                   'command': ['python', 'fixture-preview.py'], 'cwd': str(directory), 'port': 49201,
                   'url': 'http://127.0.0.1:49201/', 'record': str(folder / 'ownership.json')}
        (folder / 'ownership.json').write_text(json.dumps(preview), encoding='utf-8')
        self.manager.refresh()
        child = self.row('original.fixture-product')['instances'][0]
        self.assertEqual(child['status'], 'stopped')
        self.assertFalse(child['open_url'])
        self.assertFalse(child['can_stop'])
        preview.update(state='error', message='原版启动失败 password=fixture-private-password')
        (folder / 'ownership.json').write_text(json.dumps(preview), encoding='utf-8')
        self.manager.refresh()
        failed = self.row('original.fixture-product')['instances'][0]
        self.assertEqual(failed['status'], 'error')
        self.assertIn('原版启动失败', failed['reason'])
        self.assertNotIn('fixture-private-password', failed['reason'])
        preview.update(state='ready', message='')
        (folder / 'ownership.json').write_text(json.dumps(preview), encoding='utf-8')
        self.current['processes'] = [dict(pid=preview['pid'], created=preview['created'], command=preview['command'], parent=42)]
        self.current['listeners'] = [dict(pid=preview['pid'], port=preview['port'], address='127.0.0.1')]
        self.manager.refresh()
        child = self.row('original.fixture-product')['instances'][0]
        self.assertEqual(child['status'], 'running')
        self.assertTrue(child['can_stop'])
        self.assertTrue(self.manager.prepare(child['id'], 'stop')['requires_confirmation'])
        with self.assertRaises(ServiceError):
            self.manager.stop(child['id'])
        self.assertFalse(self.terminated)

    def test_external_force_prepare_has_no_side_effect_and_receipt_is_single_use(self):
        identifier = self.external_node()
        prepared = self.manager.prepare(identifier, 'stop')
        self.assertTrue(prepared['requires_confirmation'])
        self.assertEqual(prepared['targets'][0]['pid'], 980001)
        self.assertEqual(prepared['targets'][0]['mode'], 'force')
        self.assertIn('强制', prepared['execution_label'])
        self.assertTrue(any('其他聊天' in value for value in prepared['warnings']))
        self.assertTrue(any('未完成' in value for value in prepared['warnings']))
        self.assertFalse(self.spawned)
        self.assertFalse(self.terminated)
        with self.assertRaises(ServiceError):
            self.manager.stop(identifier)
        token = prepared['confirmation_id']
        self.manager.stop(identifier, token)
        self.assertEqual(self.terminated, [980001])
        self.assertNotIn(token, self.manager._confirmations)
        with self.assertRaises(ServiceError):
            self.manager.stop(identifier, token)
        self.assertEqual(self.terminated, [980001])

    def test_confirmation_is_bound_to_action_target_expiry_and_current_process_tree(self):
        first, second = self.external_node(), self.external_node(980002, 'admin')
        token = self.manager.prepare(first, 'stop')['confirmation_id']
        with self.assertRaises(ServiceError):
            self.manager.stop(second, token)
        token = self.manager.prepare('fixed.gateway', 'stop')['confirmation_id']
        with self.assertRaises(ServiceError):
            self.manager.start('fixed.gateway', token)
        token = self.manager.prepare(first, 'stop')['confirmation_id']
        self.manager._confirmations[token]['expires'] = time.monotonic() - 1
        with self.assertRaises(ServiceError):
            self.manager.stop(first, token)
        baseline = copy.deepcopy(self.current)
        for field, value in [('created','2026-11-24T04:00:00+00:00'),
                             ('command',['node',str(self.repo / 'other/tooling/start-source.mjs'),'gateway','--changed']),
                             ('parent',888888)]:
            self.current = copy.deepcopy(baseline)
            token = self.manager.prepare(first, 'stop')['confirmation_id']
            self.current['processes'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ServiceError):
                self.manager.stop(first, token)
        self.current = copy.deepcopy(baseline)
        token = self.manager.prepare(first, 'stop')['confirmation_id']
        self.current['processes'].append({'pid':980003, 'parent':980001,
            'created':'2026-11-24T02:00:00+00:00', 'command':['python','fixture-child.py']})
        with self.assertRaises(ServiceError):
            self.manager.stop(first, token)
        self.assertFalse(self.spawned)
        self.assertFalse(self.terminated)

    def test_shared_confirmation_rechecks_impact_and_never_uses_process_terminator(self):
        shared = self.manager.shared_services = FixtureSharedServices()
        self.manager.refresh()
        self.assertTrue(self.row('advanced.postgres')['can_stop'])
        prepared = self.manager.prepare('advanced.postgres', 'stop')
        self.assertTrue(prepared['requires_confirmation'])
        self.assertFalse(shared.executed)
        with self.assertRaises(ServiceError):
            self.manager.stop('advanced.postgres')
        shared.impact.append({'id':'new.fixture-client', 'pid':981002, 'created':'2026-11-24T02:00:00+00:00'})
        with self.assertRaises(ServiceError):
            self.manager.stop('advanced.postgres', prepared['confirmation_id'])
        self.assertFalse(shared.executed)
        self.confirm_stop('advanced.postgres')
        self.assertEqual(len(shared.executed), 1)
        self.assertEqual(shared.executed[0]['impact'], shared.impact)
        self.assertFalse(self.terminated)
        self.assertFalse(self.spawned)

    def test_cross_chat_graceful_channel_requires_confirmation_and_mode_changes_invalidate_it(self):
        record = self.start_live()
        record['chat'] = 'another-chat'
        self.control_owner(record)
        identifier = 'run.' + record['id']
        prepared = self.manager.prepare(identifier, 'stop')
        self.assertTrue(prepared['requires_confirmation'])
        self.assertEqual(prepared['targets'][0]['mode'], 'persistent')
        self.assertFalse((Path(record['control_directory']) / 'stop-request.json').exists())
        (Path(record['control_directory']) / 'control-owner.json').unlink()
        with self.assertRaises(ServiceError):
            self.manager.stop(identifier, prepared['confirmation_id'])
        self.assertFalse(self.terminated)
        self.control_owner(record)
        self.confirm_stop(identifier)
        self.assertTrue((Path(record['control_directory']) / 'stop-request.json').exists())
        self.assertFalse(self.terminated)

    def test_capture_becoming_active_after_confirmation_refuses_even_cross_chat_stop(self):
        record = self.start_live('fixed.capture')
        record['chat'] = 'another-chat'
        active = [0]
        self.manager.health = lambda r: {'pid':record['pid'], 'created':record['created'], 'chat':'another-chat',
                                         'capabilities':{'shutdown':True}, 'active_sessions':active[0]}
        identifier = 'run.' + record['id']
        prepared = self.manager.prepare(identifier, 'stop')
        self.assertTrue(prepared['requires_confirmation'])
        self.assertEqual(prepared['targets'][0]['mode'], 'capture')
        active[0] = 1
        with patch.object(self.manager, '_shutdown_capture') as shutdown, self.assertRaises(ServiceError):
            self.manager.stop(identifier, prepared['confirmation_id'])
        shutdown.assert_not_called()
        self.assertFalse(self.terminated)

    def test_external_worktree_start_requires_confirmed_source_and_reserved_port(self):
        tree = self.repo / '其他聊天工作树'
        directory = tree / 'games/cash-mania/instance'
        directory.mkdir(parents=True)
        (directory / 'service.json').write_text(json.dumps({'id':'cash-mania', 'games':['cash-mania'], 'port':18115}), encoding='utf-8')
        entry = tree / 'other/runtime/server/dist/cli.js'
        entry.parent.mkdir(parents=True)
        entry.write_text('// 隔离夹具，不执行真实服务', encoding='utf-8')
        config = tree / 'other/diagnostics/cash-mania/postgres.json'
        config.parent.mkdir(parents=True)
        route = {'driver':'postgres', 'isolated':True,
                 'sources':[{'kind':'local', 'schema':'cash_mania', 'path':str(directory / 'fixture.sqlite')}]}
        config.write_text(json.dumps(route), encoding='utf-8')
        self.manager._worktree_provider = lambda:[self.repo, tree]
        self.manager._worktrees_checked = 0
        self.current = {'processes':[{'pid':982001, 'created':'2026-11-24T01:00:00+00:00', 'parent':42,
                                     'executable':'node.exe', 'command':['node',str(entry),'service','--service-dir',str(directory)]}],
                        'listeners':[{'pid':982001, 'port':18115, 'address':'127.0.0.1'}]}
        self.manager.refresh()
        identifier = next(row['id'] for row in self.manager.snapshot()['services'] if row['id'].startswith('worktree-demo.'))
        prepared = self.manager.prepare(identifier, 'start')
        self.assertTrue(prepared['requires_confirmation'])
        self.assertEqual(prepared['targets'][0]['cwd'], str(tree))
        self.assertNotEqual(prepared['targets'][0]['port'], 18115)
        self.assertFalse(self.spawned)
        with self.assertRaises(ServiceError):
            self.manager.start(identifier)
        config.write_text(json.dumps(dict(route, isolated=False)), encoding='utf-8')
        with self.assertRaises(ServiceError):
            self.manager.start(identifier, prepared['confirmation_id'])
        self.assertFalse(self.spawned)
        config.write_text(json.dumps(route), encoding='utf-8')
        prepared = self.manager.prepare(identifier, 'start')
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1', prepared['targets'][0]['port']))
            occupied.listen()
            with self.assertRaises(ServiceError):
                self.manager.start(identifier, prepared['confirmation_id'])
        self.assertFalse(self.spawned)
        fixture_env = dict(os.environ, PGPASSWORD='fixture-private-password', PGDATABASE='fixture-platform-db')
        with patch.object(os, 'environ', fixture_env):
            prepared = self.manager.prepare(identifier, 'start')
            result = self.manager.start(identifier, prepared['confirmation_id'])
            self.manager.jobs[result['run_id']].join(5)
        record = self.manager.records[result['run_id']]
        self.assertIsNotNone(record['pid'])
        self.assertEqual(record['port'], prepared['targets'][0]['port'])
        command, options, _ = self.spawned[-1]
        self.assertEqual(options['cwd'], str(tree))
        self.assertIn(str(entry), command)
        self.assertIn('--import', command)
        self.assertEqual(command[command.index('--service-dir') + 1], str(directory))
        self.assertEqual(options['env']['GTT_PG_CONFIG'], str(config))
        self.assertNotIn('PGPASSWORD', options['env'])
        self.assertNotIn('PGDATABASE', options['env'])
        self.assertFalse(self.terminated)

    def test_logs_are_bounded_redacted_and_cannot_escape_record_directory(self):
        record = self.start_live()
        secrets = ['fixture-token-11', 'fixture-basic-22', 'fixture-session-33', 'fixture-refresh-44',
                   'fixture word secret', 'fixture-user:fixture-pass']
        text = ('x' * 35000 + '\nAuthorization: Bearer ' + secrets[0] + '\nAuthorization: Basic ' + secrets[1]
                + '\nCookie: session=' + secrets[2] + '; refresh=' + secrets[3]
                + '\npassword="' + secrets[4] + '"\nhttps://' + secrets[5] + '@localhost/db')
        Path(record['log']).write_text(text, encoding='utf-8')
        started = time.monotonic()
        result = self.manager.logs('run.' + record['id'])
        self.assertLess(time.monotonic() - started, 5, '32KB 长日志脱敏不应阻塞控制台数十秒')
        self.assertTrue(result['truncated'])
        self.assertLessEqual(len(result['text']), 32768)
        for secret in secrets:
            self.assertNotIn(secret, result['text'])
        outside = self.repo / 'private.txt'
        outside.write_text('fixture-outside-secret', encoding='utf-8')
        record['log'] = str(outside)
        self.assertNotIn('fixture-outside-secret', self.manager.logs('run.' + record['id'])['text'])

    def test_adapter_control_requires_consistent_launcher_child_and_control_identity(self):
        registry = OriginalGames(self.repo, self.repo / 'captures')
        registry.owner['chat'] = 'fixture-current-chat'
        folder = self.repo / 'other/diagnostics/response-capture-previews/adapter-fixture'
        (folder / 'service').mkdir(parents=True)
        command = ['node', str(self.repo / 'runtime/dist/cli.js'), 'game', 'fixture']
        child = {'pid':949001, 'created':'2026-11-24T01:00:00+00:00', 'chat':'fixture-current-chat',
                 'cwd':str(self.repo / 'runtime'), 'command':command}
        job = {'mode':'adapter', 'service_pid':child['pid'], 'service_created':child['created'],
               'chat':child['chat'], 'record':str(folder / 'ownership.json'),
               'control_directory':str(folder), 'control_nonce':'b'*32}
        owner = {'pid':child['pid'], 'chat':child['chat'], 'cwd':child['cwd'], 'command':command,
                 'nonce':job['control_nonce'], 'started':'2026-11-24T02:00:00+00:00', 'state':'ready'}
        def save_child(value):
            (folder / 'service/ownership.json').write_text(json.dumps(value), encoding='utf-8')
        def save_owner(value):
            (folder / 'control-owner.json').write_text(json.dumps(value), encoding='utf-8')
        save_child(child)
        save_owner(owner)
        self.assertTrue(registry.adapter_control(job))
        for key, value in [('service_pid',99999), ('service_created','2026-11-24T03:00:00+00:00'),
                           ('control_nonce','c'*32), ('chat','another-chat'), ('control_directory',str(self.repo))]:
            with self.subTest(job=key):
                self.assertFalse(registry.adapter_control(dict(job, **{key:value})))
        for key, value in [('chat','another-chat'), ('cwd',str(self.repo / 'different-runtime')),
                           ('command',['node','other-game.js']), ('pid',949002)]:
            with self.subTest(child=key):
                save_child(dict(child, **{key:value}))
                self.assertFalse(registry.adapter_control(job))
        save_child(child)
        registry.shutdown_adapter(job, inspector=lambda pid:child)
        request = json.loads((folder / 'stop-request.json').read_text(encoding='utf-8'))
        self.assertEqual(request['pid'], child['pid'])
        self.assertEqual(request['nonce'], job['control_nonce'])

    def test_adapter_preview_injects_file_bridge_and_keeps_nonce_out_of_public_job(self):
        registry = OriginalGames(self.repo, self.repo / 'captures')
        registry.owner['chat'] = 'fixture-current-chat'
        artifact = self.repo / 'adapter-artifact'
        artifact.mkdir()
        item = {'folder':artifact, 'public':{}, 'spec':{'mode':'adapter',
                 'config':self.repo / 'isolated-pg.json', 'template':"$arguments = @('dist/cli.js', 'fixture')\n"}}
        process = Mock(pid=959001)
        with patch.object(registry, '_item', return_value=item), patch.object(registry, '_watch'), \
             patch('original_games.subprocess.Popen', return_value=process) as spawn:
            public = registry.preview('d'*32)
        job = registry.jobs[public['run_id']]
        self.addCleanup(job['log_stream'].close)
        env = spawn.call_args.kwargs['env']
        self.assertEqual(env['CODEX_THREAD_ID'], 'fixture-current-chat')
        self.assertEqual(env['GTT_CAPTURE_CONTROL_DIR'], job['control_directory'])
        self.assertEqual(env['GTT_CAPTURE_CONTROL_NONCE'], job['control_nonce'])
        self.assertEqual(env['GTT_CAPTURE_CONTROL_HELPER'], Path(__file__).with_name('service_control.mjs').resolve().as_uri())
        launcher = Path(job['record']).parent / 'launch-original.ps1'
        script = launcher.read_text(encoding='utf-8-sig')
        self.assertIn("'--import'", script)
        self.assertIn("Join-Path $runtime 'dist/cli.js'", script)
        self.assertNotIn(job['control_nonce'], json.dumps(public))
        self.assertNotIn('control_nonce', registry.job(public['run_id']))
        self.assertNotIn('control_directory', registry.job(public['run_id']))


@unittest.skipUnless(os.name == 'nt', '真实进程句柄核验仅适用于 Windows')
class NativeTerminationTest(unittest.TestCase):
    def test_same_handle_rejects_reused_identity_then_stops_only_fixture_process(self):
        command = [sys.executable, '-c', 'import time; time.sleep(60)']
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
        try:
            created = process_created(process)
            self.assertTrue(created)
            actual = {'pid': process.pid, 'created': created, 'command': command}
            record = dict(actual, created='2000-01-01T00:00:00+00:00')
            with self.assertRaises(ServiceError):
                terminate_checked(record, actual)
            self.assertIsNone(process.poll())
            terminate_checked(actual, actual)
            self.assertEqual(process.wait(timeout=5), 0)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)

    @unittest.skipUnless(shutil.which('node'), '需要本机 Node.js 执行真实正常退出夹具')
    def test_node_bridge_finishes_inflight_request_before_exit_and_releases_port(self):
        self.run_node_shutdown('stdin')

    @unittest.skipUnless(shutil.which('node'), '需要本机 Node.js 执行真实正常退出夹具')
    def test_persistent_node_bridge_stops_without_original_console_pipe(self):
        self.run_node_shutdown('file')

    def run_node_shutdown(self, mode):
        with tempfile.TemporaryDirectory(prefix='service-node-stop-fixture-') as folder:
            root = Path(folder) / '中文路径正常退出夹具'
            root.mkdir()
            control = root / 'run-control'
            control.mkdir()
            entry = root / 'server.mjs'
            bridge = Path(__file__).with_name('controlled_node.mjs').resolve().as_uri()
            entry.write_text('import http from "node:http";\n'
                             'import {installStopBridge} from '+json.dumps(bridge)+';\n'
                             'const emit = event => console.log(JSON.stringify(event));\n'
                             'const server = http.createServer((req,res) => {\n'
                             '  emit({event:"request"});\n'
                             '  setTimeout(() => {res.end("fixture-completed");emit({event:"complete"});},700);\n'
                             '});\n'
                             'installStopBridge(process.stdin,process,()=>{});\n'
                             'process.on("SIGTERM",()=>{emit({event:"stopping"});server.close(()=>{emit({event:"closed"});process.exit(0);});});\n'
                             'server.listen(0,"127.0.0.1",()=>emit({event:"ready",port:server.address().port}));\n', encoding='utf-8')
            command = [shutil.which('node'), str(entry)]
            if mode == 'file':
                command = [shutil.which('node'), '--import', Path(__file__).with_name('service_control.mjs').resolve().as_uri(), str(entry)]
            env = dict(os.environ)
            if mode == 'file':
                env.update(CODEX_THREAD_ID='fixture-current-chat', GTT_CAPTURE_CONTROL_DIR=str(control),
                           GTT_CAPTURE_CONTROL_NONCE='a'*32)
            else:
                env.pop('GTT_CAPTURE_CONTROL_DIR', None)
                env.pop('GTT_CAPTURE_CONTROL_NONCE', None)
            process = subprocess.Popen(command, cwd=root, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, encoding='utf-8', creationflags=NO_WINDOW)
            lines = queue.Queue()
            def read_output():
                for line in process.stdout:
                    lines.put(line)
            reader = threading.Thread(target=read_output, daemon=True)
            reader.start()
            connection = None
            try:
                ready = json.loads(lines.get(timeout=5))
                self.assertEqual(ready['event'], 'ready')
                port = ready['port']
                record = {'chat':'fixture-current-chat', 'cwd':str(root), 'command':command,
                          'pid':process.pid, 'created':process_created(process), 'port':port,
                          'control_directory':str(control), 'control_nonce':'a'*32, 'ownership_file':str(control / 'ownership.json')}
                (control / 'ownership.json').write_text(json.dumps(record), encoding='utf-8')
                self.assertTrue(record['created'])
                if mode == 'file':
                    deadline = time.monotonic() + 5
                    while not (control / 'control-owner.json').exists() and time.monotonic() < deadline:
                        time.sleep(.02)
                    self.assertTrue((control / 'control-owner.json').is_file())
                    owner = json.loads((control / 'control-owner.json').read_text(encoding='utf-8'))
                    actual = inspect_process(process.pid)
                    self.assertTrue(command_matches(owner['command'], actual['command']))
                    self.assertTrue(command_matches(command, actual['command']))
                    process.stdin.close()
                connection = HTTPConnection('127.0.0.1', port, timeout=5)
                connection.request('GET', '/')
                self.assertEqual(json.loads(lines.get(timeout=5))['event'], 'request')
                if mode == 'file':
                    request_stop(record, root, record['chat'], inspector=lambda pid:{'pid':process.pid,
                        'created':process_created(process), 'command':command})
                else:
                    process.stdin.write('stop\n')
                    process.stdin.flush()
                self.assertEqual(json.loads(lines.get(timeout=5))['event'], 'stopping')
                self.assertIsNone(process.poll())
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), b'fixture-completed')
                connection.close()
                connection = None
                self.assertEqual(json.loads(lines.get(timeout=5))['event'], 'complete')
                self.assertEqual(json.loads(lines.get(timeout=5))['event'], 'closed')
                self.assertEqual(process.wait(timeout=5), 0)
                with socket.socket() as check:
                    check.settimeout(.5)
                    self.assertNotEqual(check.connect_ex(('127.0.0.1', port)), 0)
            finally:
                if connection:
                    connection.close()
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
                if not process.stdin.closed:
                    process.stdin.close()
                reader.join(timeout=2)
                process.stdout.close()


if __name__ == '__main__':
    unittest.main()
