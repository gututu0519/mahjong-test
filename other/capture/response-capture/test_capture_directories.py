"""游戏行的历史归属、目录打开和本机请求边界回归测试。"""
import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import app
import archive_identity
from capture_directories import checked_directory


GAMES = [
    {'site': 'one', 'brand': 'PG', 'externalId': '12', 'name': 'First', 'zh': '甲'},
    {'site': 'two', 'brand': 'IGT', 'externalId': '18', 'name': 'Second', 'zh': '乙'},
]


class CaptureDirectoriesTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve() / 'captures'
        self.root.mkdir()
        for owner, name, value in ((app, 'DATA', self.root), (app, 'SESSIONS', {})):
            hook = patch.object(owner, name, value)
            hook.start()
            self.addCleanup(hook.stop)
        # 单元测试只验证实际目录，避免打开桌面窗口或生成系统快捷方式。
        hook = patch.object(archive_identity, '_write_shortcuts')
        hook.start()
        self.addCleanup(hook.stop)
        hook = patch.object(app, 'open_directory')
        self.opener = hook.start()
        self.addCleanup(hook.stop)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.origin = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=2)

    def request(self, method, path, body=None, headers=None):
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            supplied = {'X-Capture-Token': app.TOKEN, 'Content-Type': 'application/json'}
            supplied.update(headers or {})
            connection.request(method, path, json.dumps(body) if body is not None else None, supplied)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def batch(self, char, games=(), *, group=None, catalog=False, target=None):
        sid = char * 32
        folder = (self.root / group if group else self.root) / sid
        (folder / 'bodies').mkdir(parents=True)
        rows = []
        payloads = []
        if catalog:
            payloads.append(('https://sdstest.ink/api/v1/games/catalog', 'GET', 200,
                             {'items': [{'id': g['site'], 'externalId': g['externalId'],
                                         'name': g['name'], 'nameZh': g['zh'],
                                         'metadata': {'brand': g['brand']}} for g in GAMES]}))
        for game in games:
            payloads.append(('https://sdstest.ink/api/v1/games/' + game['site'] + '/launch', 'POST', 201, {}))
        for n, (url, method, status, body) in enumerate(payloads, 1):
            raw = json.dumps(body).encode()
            name = f'bodies/{n:06d}.json'
            (folder / name).write_bytes(raw)
            rows.append(dict(id=n, url=url, method=method, status=status, state='complete',
                             mime='application/json', size=len(raw), body=name))
        manifest = dict(id=sid, state='completed', created='2026-11-24T00:00:00Z',
                        url='https://sdstest.ink/', rows=rows, target_game=target)
        (folder / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        return folder

    def test_multigame_archive_belongs_to_each_game_without_moving(self):
        folder = self.batch('a', GAMES, catalog=True)
        original = (folder / 'manifest.json').read_bytes()
        status, records = self.request('GET', '/api/sessions')
        self.assertEqual(status, 200)
        self.assertEqual(records[0]['directory'], 'captures/' + folder.name)
        self.assertEqual({g['site'] for g in records[0]['identity_games']}, {'one', 'two'})
        self.assertEqual({g['path'] for g in records[0]['game_directories']},
                         {'captures/PG-12-甲', 'captures/IGT-18-乙'})
        for game in GAMES:
            status, result = self.request('POST', '/api/open-directory', {'game_id': game['site']})
            self.assertEqual(status, 200)
            self.assertTrue(result['ok'])
            self.opener.assert_called_with(self.root / archive_identity.game_label(game))
        self.assertEqual((folder / 'manifest.json').read_bytes(), original)
        self.assertTrue(folder.is_dir())

    def test_active_and_saved_nested_batches_have_separate_directory_targets(self):
        saved = self.batch('a', target=GAMES[0], group='PG-12-甲')
        active = app.Capture(app.LOBBY_URL, target=GAMES[1])
        app.SESSIONS[active.id] = active
        _, records = self.request('GET', '/api/sessions')
        by_id = {record['id']: record for record in records}
        self.assertEqual(by_id[active.id]['identity_games'], [GAMES[1]])
        self.assertEqual(by_id[saved.name]['directory'], 'captures/PG-12-甲/' + saved.name)
        for folder in (saved, active.folder):
            status, result = self.request('POST', '/api/open-directory', {'session_id': folder.name})
            self.assertEqual(status, 200)
            self.opener.assert_called_with(folder)
            self.assertEqual(result['directory'], 'captures/' + folder.relative_to(self.root).as_posix())

    def test_catalog_only_does_not_become_a_game_capture(self):
        self.batch('a', catalog=True)
        _, records = self.request('GET', '/api/sessions')
        self.assertEqual(records[0]['identity_games'], [])
        self.assertEqual(records[0]['game_directories'], [])
        status, _ = self.request('POST', '/api/open-directory', {'game_id': 'one'})
        self.assertEqual(status, 400)
        self.opener.assert_not_called()

    def test_renamed_game_directories_can_be_selected_by_their_own_batch(self):
        old_game = {**GAMES[0], 'zh': '旧名称'}
        new_game = {**GAMES[0], 'zh': '新名称'}
        old = self.batch('a', target=old_game, group=archive_identity.game_label(old_game))
        new = self.batch('b', target=new_game, group=archive_identity.game_label(new_game))
        status, _ = self.request('POST', '/api/open-directory', {'game_id': 'one'})
        self.assertEqual(status, 400)
        self.opener.assert_not_called()
        for folder in (old, new):
            status, result = self.request('POST', '/api/open-directory',
                                          {'game_id': 'one', 'session_id': folder.name})
            self.assertEqual(status, 200)
            self.assertEqual(result['directory'], 'captures/' + folder.parent.name)
            self.opener.assert_called_with(folder.parent)
        self.opener.reset_mock()
        for payload in ({'game_id': 'two', 'session_id': old.name},
                        {'game_id': 'one', 'session_id': 'c'*32},
                        {'game_id': 'one', 'session_id': '../outside'}):
            status, _ = self.request('POST', '/api/open-directory', payload)
            self.assertEqual(status, 400)
        self.opener.assert_not_called()

    def test_rejects_paths_unknown_ids_and_ambiguous_batches(self):
        self.batch('a', target=GAMES[0])
        self.batch('a', target=GAMES[0], group='duplicate')
        for payload in ({'path': str(self.root)}, {'session_id': '../outside'}, {'game_id': '../outside'},
                        {'session_id': 'a'*32}, {'session_id': 'b'*32}, {'game_id': 'missing'},
                        {'game_id': 'one', 'session_id': 'a'*32}, [], None):
            status, _ = self.request('POST', '/api/open-directory', payload)
            self.assertEqual(status, 400, payload)
        self.opener.assert_not_called()

    def test_rejects_foreign_origin_missing_token_and_bad_host(self):
        folder = self.batch('a', target=GAMES[0])
        for headers in ({'Origin': 'https://outside.invalid'}, {'Origin': 'null'},
                        {'Origin': self.origin, 'Sec-Fetch-Site': 'cross-site'},
                        {'X-Capture-Token': ''}, {'Host': 'outside.invalid'}):
            status, _ = self.request('POST', '/api/open-directory', {'session_id': folder.name}, headers)
            self.assertEqual(status, 403, headers)
        self.opener.assert_not_called()
        status, _ = self.request('POST', '/api/open-directory', {'session_id': folder.name},
                                 {'Origin': self.origin, 'Sec-Fetch-Site': 'same-origin'})
        self.assertEqual(status, 200)

    def test_does_not_open_missing_or_reparse_directories(self):
        self.assertIsNone(checked_directory(self.root, self.root.parent))
        self.assertIsNone(checked_directory(self.root, self.root / '..' / 'outside'))
        self.assertIsNone(checked_directory(self.root, self.root / 'missing'))
        outside = self.root.parent / 'outside'
        outside.mkdir()
        link = self.root / 'linked'
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            if os.name != 'nt':
                raise
            subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                            "New-Item -ItemType Junction -Path $env:CAPTURE_TEST_LINK -Target $env:CAPTURE_TEST_TARGET -ErrorAction Stop | Out-Null"],
                           env={**os.environ, 'CAPTURE_TEST_LINK': str(link), 'CAPTURE_TEST_TARGET': str(outside)},
                           check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            self.assertIsNone(checked_directory(self.root, link))
            self.assertIsNone(checked_directory(self.root, link / 'nested'))
        finally:
            if link.is_symlink():
                link.unlink()
            else:
                # 仅移除本测试创建的目录联接入口，保留被指向的目录。
                link.rmdir()

    def test_desktop_open_failure_is_reported(self):
        folder = self.batch('a', target=GAMES[0])
        self.opener.side_effect = OSError('测试桌面不可用')
        status, result = self.request('POST', '/api/open-directory', {'session_id': folder.name})
        self.assertEqual(status, 503)
        self.assertIn('无法打开资源管理器', result['error'])


if __name__ == '__main__':
    unittest.main()
