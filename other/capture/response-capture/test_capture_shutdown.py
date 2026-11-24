"""隔离 HTTP 实例验证抓取主服务正常收尾及关停期间的启动边界。"""
import json
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import app


class CaptureShutdownTest(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(app, 'SESSIONS', {})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=2)

    def request(self, method, path, body=None, headers=None):
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        supplied = {'X-Capture-Token': app.TOKEN, 'Content-Type': 'application/json'}
        supplied.update(headers or {})
        try:
            connection.request(method, path, json.dumps(body) if body is not None else None, supplied)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_status_reports_identity_without_token_or_credentials(self):
        app.SESSIONS['a'*32] = SimpleNamespace(state='recording', archived=False)
        code, state = self.request('GET', '/api/status')
        self.assertEqual(200, code)
        self.assertEqual('response-capture', state['service'])
        self.assertEqual(self.server.server_port, state['port'])
        self.assertEqual(1, state['active_sessions'])
        self.assertTrue(state['capabilities']['shutdown'])
        self.assertNotIn(app.TOKEN, json.dumps(state))
        self.assertNotIn('token', state)

    def test_active_and_unfinished_manifest_refuse_shutdown(self):
        for capture in (SimpleNamespace(state='recording', archived=False),
                        SimpleNamespace(state='completed', archived=False),
                        SimpleNamespace(state='error', archived=False)):
            app.SESSIONS['a'*32] = capture
            code, result = self.request('POST', '/api/shutdown', {})
            self.assertEqual(409, code)
            self.assertIn('停止并保存', result['error'])
            self.assertFalse(getattr(self.server, 'stopping', False))
            self.assertTrue(self.worker.is_alive())

    def test_saved_capture_allows_graceful_shutdown(self):
        app.SESSIONS['a'*32] = SimpleNamespace(state='completed', archived=True)
        code, result = self.request('POST', '/api/shutdown', {})
        self.assertEqual(200, code)
        self.assertEqual('stopping', result['state'])
        self.worker.join(timeout=2)
        self.assertFalse(self.worker.is_alive())
        self.assertTrue(self.server.stopping)

    def test_stopping_cannot_create_another_capture(self):
        self.server.stopping = True
        with patch.object(app, 'Capture') as capture:
            code, result = self.request('POST', '/api/start', {'url': 'https://fixture.invalid/'})
        self.assertEqual(409, code)
        self.assertIn('正在关闭', result['error'])
        capture.assert_not_called()

    def test_shutdown_needs_token_same_origin_and_empty_payload(self):
        for headers in ({'X-Capture-Token': ''}, {'Origin': 'https://outside.invalid'},
                        {'Sec-Fetch-Site': 'cross-site'}):
            code, _ = self.request('POST', '/api/shutdown', {}, headers)
            self.assertEqual(403, code)
        code, _ = self.request('POST', '/api/shutdown', {'pid': 1})
        self.assertEqual(400, code)
        self.assertTrue(self.worker.is_alive())


if __name__ == '__main__':
    unittest.main()
