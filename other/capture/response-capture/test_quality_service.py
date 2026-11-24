"""只读完整度接口回归；使用隔离 HTTP 夹具，不操作真实录制。"""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import quality_service


SID = 'a' * 32


class QualityServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.seen = []
        self.folders = []
        self.fail = False

        def source(sid):
            self.seen.append(sid)
            if self.fail:
                raise OSError('secret-token-must-not-leak')
            return {'id': sid, 'state': 'recording', 'rows': []}

        def analyzer(detail, folder):
            self.folders.append(folder)
            return {'version': 1, 'summary': {'status': 'unknown', 'can_stop': False}, 'games': []}

        self.server = quality_service.create_server(
            ('127.0.0.1', 0), detail_source=source, capture_root=Path(self.temp.name),
            quality_cache=quality_service.QualityCache(analyzer=analyzer, ttl=0))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def call(self, path=None, headers=None, method='GET'):
        req = Request(self.base + (path or '/api/sessions/' + SID + '/quality'), headers=headers or {}, method=method)
        try:
            response = urlopen(req, timeout=3)
        except HTTPError as error:
            response = error
        with response:
            data = response.read()
            try:
                value = json.loads(data)
            except ValueError:
                value = {'text': data.decode()}
            return response.status, response.headers, value

    def test_valid_session_is_read_only_and_has_freshness_and_cors(self):
        status, headers, value = self.call(headers={'Origin': 'http://127.0.0.1:8090'})
        self.assertEqual(status, 200)
        self.assertEqual(headers['Access-Control-Allow-Origin'], 'http://127.0.0.1:8090')
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(value['session_id'], SID)
        self.assertEqual(value['capture_state'], 'recording')
        self.assertIn('generated_at', value)
        self.assertFalse(value['summary']['can_stop'])
        self.assertEqual(self.seen, [SID])
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_remote_origin_host_invalid_id_and_arbitrary_url_are_rejected(self):
        for path, headers, expected in [
            (None, {'Origin': 'https://example.com'}, 403),
            (None, {'Host': 'evil.example'}, 403),
            ('/api/sessions/../../private/quality', {}, 404),
            ('/api/sessions/' + SID + '/quality?url=https://example.com', {}, 400),
        ]:
            self.assertEqual(self.call(path, headers)[0], expected)
        self.assertEqual(self.seen, [])

    def test_quality_reads_the_recording_in_its_game_folder(self):
        folder = Path(self.temp.name) / 'PG-123-游戏甲' / SID
        folder.mkdir(parents=True)
        self.assertEqual(self.call()[0], 200)
        self.assertEqual(self.folders, [folder])

    def test_failed_live_source_never_returns_cached_green_or_private_errors(self):
        self.assertEqual(self.call()[0], 200)
        self.fail = True
        status, _, value = self.call()
        self.assertEqual(status, 503)
        self.assertEqual(value['status'], 'unknown')
        self.assertNotIn('secret-token', json.dumps(value))

    def test_health_does_not_read_capture_and_post_cannot_mutate(self):
        self.assertEqual(self.call('/health')[2]['read_only'], True)
        self.assertEqual(self.call(method='POST')[0], 501)
        self.assertEqual(self.seen, [])

    def test_cache_copies_result_and_expiry_errors_do_not_reuse_success(self):
        calls = []

        def analyze(detail, folder):
            calls.append(True)
            if len(calls) > 1:
                raise OSError('offline')
            return {'summary': {'status': 'complete', 'can_stop': True}}

        cache = quality_service.QualityCache(analyzer=analyze, ttl=10)
        detail = {'id': SID, 'state': 'recording'}
        value = cache.get(detail, Path(self.temp.name))
        value['summary']['can_stop'] = False
        self.assertTrue(cache.get(detail, Path(self.temp.name))['summary']['can_stop'])
        cache.ttl = 0
        with self.assertRaises(OSError):
            cache.get(detail, Path(self.temp.name))

    def test_new_capture_handler_uses_same_analysis_interface(self):
        import app
        server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            detail = {'id': SID, 'state': 'recording', 'rows': []}
            root = Path(self.temp.name)
            folder = root / 'PG-456-游戏乙' / SID
            folder.mkdir(parents=True)
            with patch.object(app, 'DATA', root), patch.object(app, 'snapshot', return_value=detail), patch.object(app, 'get_session_quality', return_value={'summary': {'can_stop': False}}) as check:
                req = Request('http://127.0.0.1:' + str(server.server_port) + '/api/sessions/' + SID + '/quality')
                with urlopen(req, timeout=3) as result:
                    self.assertFalse(json.load(result)['summary']['can_stop'])
                check.assert_called_once_with(detail, folder)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
