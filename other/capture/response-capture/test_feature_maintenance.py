"""监督器启动/退出隔离测试；所有子进程均为 mock，不操作现有抓取或服务。"""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import feature_maintenance as maintenance


class ControlPipe(io.BytesIO):
    def close(self):
        self.payload = self.getvalue()
        super().close()


class Child:
    def __init__(self):
        self.pid = 12345
        self.returncode = None
        self.terminated = 0
        self.waited = []
        self.stdin = ControlPipe()

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated += 1

    def wait(self, timeout):
        self.waited.append(timeout)
        self.returncode = 0
        return 0


class FeatureMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='feature-supervisor-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        script = self.root / 'other/tooling/feature-maintenance/watch.mjs'
        script.parent.mkdir(parents=True)
        script.write_text('// mock only', encoding='utf8')
        self.child = Child()
        for patcher in (
            patch.dict(os.environ, {'CAPTURE_FEATURE_MAINTENANCE': '1'}),
            patch.object(maintenance.shutil, 'which', return_value='node'),
            patch.object(maintenance.subprocess, 'Popen', return_value=self.child),
            patch.object(maintenance, '_process_creation_time', return_value='synthetic-creation-time'),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.output = io.StringIO()
        redirect = contextlib.redirect_stdout(self.output)
        redirect.__enter__()
        self.addCleanup(redirect.__exit__, None, None, None)

    def test_disabled_or_missing_dependency_never_launches(self):
        with patch.dict(os.environ, {'CAPTURE_FEATURE_MAINTENANCE': '0'}):
            self.assertIsNone(maintenance.start_supervisor(self.root))
        maintenance.subprocess.Popen.assert_not_called()
        with patch.object(maintenance.shutil, 'which', return_value=None):
            self.assertIsNone(maintenance.start_supervisor(self.root))
        maintenance.subprocess.Popen.assert_not_called()

    def test_log_failure_does_not_abort_capture(self):
        with patch.object(Path, 'mkdir', side_effect=PermissionError('secret-path-do-not-print')):
            self.assertIsNone(maintenance.start_supervisor(self.root))
        maintenance.subprocess.Popen.assert_not_called()
        self.assertNotIn('secret-path-do-not-print', self.output.getvalue())

    def test_launch_failure_is_contained(self):
        with patch.object(maintenance.subprocess, 'Popen', side_effect=OSError('secret-command-do-not-print')):
            self.assertIsNone(maintenance.start_supervisor(self.root))
        self.assertNotIn('secret-command-do-not-print', self.output.getvalue())

    def test_owns_exact_child_and_records_command_creation_and_ports(self):
        child = maintenance.start_supervisor(self.root)
        self.assertIs(child, self.child)
        args, kwargs = maintenance.subprocess.Popen.call_args
        self.assertEqual(args[0][0], 'node')
        self.assertEqual(args[0][2:], ['--capture-url', 'http://127.0.0.1:8090', '--interval-ms', '10000', '--parent-pipe'])
        self.assertEqual(kwargs['stdin'], subprocess.PIPE)
        self.assertEqual(kwargs['cwd'], self.root.resolve())
        self.assertNotIn('shell', kwargs)
        self.assertEqual(kwargs['creationflags'], subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        recorded = json.loads((self.root / 'other/diagnostics/feature-maintenance/supervisor-owner-12345.json').read_text(encoding='utf8'))
        self.assertEqual(recorded['capture_pid'], os.getpid())
        self.assertEqual(recorded['pid'], child.pid)
        self.assertEqual(recorded['created_filetime'], 'synthetic-creation-time')
        self.assertEqual(recorded['listening_ports'], [])
        maintenance.stop_supervisor(child)
        self.assertEqual(child.terminated, 0)
        self.assertEqual(child.stdin.payload, b'stop\n')
        self.assertEqual(child.waited, [5])

    def test_record_failure_retains_owned_handle(self):
        with patch.object(Path, 'write_text', side_effect=PermissionError('do-not-print')):
            child = maintenance.start_supervisor(self.root)
        self.assertIs(child, self.child)
        maintenance.stop_supervisor(child)
        self.assertEqual(child.terminated, 0)
        self.assertEqual(child.stdin.payload, b'stop\n')

    def test_unowned_other_parent_or_changed_creation_cannot_be_stopped(self):
        maintenance.stop_supervisor(self.child)
        self.assertEqual(self.child.terminated, 0)
        child = maintenance.start_supervisor(self.root)
        child._capture_feature_owner['capture_pid'] = os.getpid() + 1
        maintenance.stop_supervisor(child)
        self.assertEqual(child.terminated, 0)
        child._capture_feature_owner['capture_pid'] = os.getpid()
        with patch.object(maintenance, '_process_creation_time', return_value='other-creation-time'):
            maintenance.stop_supervisor(child)
        self.assertEqual(child.terminated, 0)

    def test_completed_child_is_not_terminated_again(self):
        child = maintenance.start_supervisor(self.root)
        child.returncode = 1
        maintenance.stop_supervisor(child)
        self.assertEqual(child.terminated, 0)

    def test_timeout_or_pipe_failure_never_force_terminates(self):
        child = maintenance.start_supervisor(self.root)
        with patch.object(child, 'wait', side_effect=subprocess.TimeoutExpired('node', 5)):
            maintenance.stop_supervisor(child)
        self.assertEqual(child.terminated, 0)
        child.stdin = ControlPipe()
        with patch.object(child.stdin, 'write', side_effect=OSError('secret-do-not-print')):
            maintenance.stop_supervisor(child)
        self.assertNotIn('secret-do-not-print', self.output.getvalue())
        self.assertEqual(child.terminated, 0)


if __name__ == '__main__':
    unittest.main()
