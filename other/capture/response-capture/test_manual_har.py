"""手动登录后按游戏标签页导出的 HAR 兼容性及隔离检查。"""
import base64
import json
from pathlib import Path
import tempfile
import unittest

from manual_har import safe_headers, safe_url, write_page_har


START = '2026-11-24T10:00:00+00:00'


class PageHarTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        (self.folder / 'bodies').mkdir()

    def row(self, number, url, body, mime):
        path = f'bodies/{number:06d}.bin'
        (self.folder / path).write_bytes(body)
        return dict(id=number, url=url, method='GET', state='complete', started=START, status=200,
                    mime=mime, size=len(body), body=path, request_headers=[], response_headers=[])

    def write(self, rows):
        write_page_har(self.folder, rows, START)
        result = (self.folder / 'network.har').read_bytes()
        log = json.loads(result)['log']
        self.assertEqual('1.2', log['version'])
        return log['entries'], result

    def test_keeps_only_selected_rows_and_roundtrips_static_resources(self):
        # key、sign 和 session 在静态游戏资料中可以是布局和贴图字段。
        raw = '{ "key":"图集1", "sign":"牌", "session":{"frame":1} }\r\n'.encode()
        one = self.row(1, 'https://example.test/api/assets/atlas.json?v=ab%20cd', raw, 'application/json')
        png = b'\x89PNG\r\n\x1a\n\xff\x00'
        two = self.row(2, 'https://example.test/texture', png, 'image/png')
        three = self.row(3, 'https://example.test/fonts/config.json', b'\xff\x10', 'application/json')
        self.row(4, 'https://other.test/other-game', b'other-game-marker', 'text/plain')
        entries, data = self.write([one, two, three])
        self.assertEqual(3, len(entries))
        self.assertNotIn(b'other-game-marker', data)
        self.assertEqual(one['url'], entries[0]['request']['url'])
        self.assertEqual(raw, entries[0]['response']['content']['text'].encode('utf-8'))
        for entry, expected in zip(entries[1:], [png, b'\xff\x10']):
            content = entry['response']['content']
            self.assertEqual('base64', content['encoding'])
            self.assertEqual(expected, base64.b64decode(content['text'], validate=True))
            self.assertEqual(len(expected), content['size'])

    def test_filters_login_auth_and_retains_ordinary_post_and_headers(self):
        login = self.row(1, 'https://sdstest.ink/api/v1/auth/login', b'PRIVATE-login-result', 'text/plain')
        row = self.row(2, 'https://sdstest.ink/api/v1/games/test/launch?token=PRIVATE-query&lang=en#PRIVATE',
                       b'{"key":"round","launch":"https://game.test/play?accessToken=PRIVATE-url&lang=en","refreshToken":"PRIVATE-json"}',
                       'application/json')
        row['method'] = 'POST'
        row['request_body'] = 'bodies/000002.request.bin'
        (self.folder / row['request_body']).write_bytes(b'bet=2&password=PRIVATE-password&username=PRIVATE-player')
        row['request_headers'] = [{'name': 'Cookie', 'value': 'PRIVATE-c'}, {'name': 'Authorization', 'value': 'PRIVATE-a'},
                                  {'name': 'Content-Type', 'value': 'application/x-www-form-urlencoded'},
                                  {'name': 'Referer', 'value': 'https://game.test/games?sid=PRIVATE-ref&lang=en'}]
        row['response_headers'] = [{'name': 'Set-Cookie', 'value': 'PRIVATE-sc'}, {'name': 'ETag', 'value': 'v1'}]
        entries, data = self.write([login, row])
        self.assertNotIn(b'PRIVATE', data)
        self.assertEqual(1, len(entries))
        req, res = entries[0]['request'], entries[0]['response']
        self.assertEqual('bet=2', req['postData']['text'])
        self.assertEqual([{'name': 'lang', 'value': 'en'}], req['queryString'])
        self.assertEqual([{'name': 'ETag', 'value': 'v1'}], res['headers'])
        self.assertEqual({'key': 'round', 'launch': 'https://game.test/play?lang=en'}, json.loads(res['content']['text']))

    def test_redirect_failed_response_and_binary_post(self):
        row = self.row(1, 'https://game.test/play', b'', 'text/plain')
        row.update(status=302, method='POST', response_headers=[{'name': 'Location', 'value': '/next?sessionId=PRIVATE&v=2'}],
                   request_body='bodies/000001.request.bin')
        (self.folder / row['request_body']).write_bytes(b'\x00\xff')
        pending = dict(id=2, url='https://game.test/next', method='GET', state='failed', status=None)
        entries, data = self.write([row, pending])
        self.assertNotIn(b'PRIVATE', data)
        post = entries[0]['request']['postData']
        self.assertEqual('base64', post['_encoding'])
        self.assertEqual(b'\x00\xff', base64.b64decode(post['text']))
        self.assertEqual('/next?v=2', entries[0]['response']['redirectURL'])
        self.assertEqual('', entries[0]['response']['content']['text'])
        self.assertNotIn('text', entries[1]['response']['content'])

    def test_refuses_another_row_or_external_body_and_publishes_atomically(self):
        row = self.row(1, 'https://game.test/a', b'owned', 'text/plain')
        other = self.row(2, 'https://game.test/b', b'other', 'text/plain')
        for path in (other['body'], '../other.bin', 'bodies/000001.request.bin'):
            contents, _ = self.write([{**row, 'body': path}])
            self.assertNotIn('text', contents[0]['response']['content'])
        _, before = self.write([row])

        def interrupted():
            yield row
            raise RuntimeError('模拟归档中断')

        with self.assertRaises(RuntimeError):
            self.write(interrupted())
        self.assertEqual(before, (self.folder / 'network.har').read_bytes())
        self.assertFalse(list(self.folder.glob('*.pending')))

    def test_url_userinfo_and_header_variants(self):
        self.assertEqual('https://game.test/path?a=1', safe_url('https://PRIVATE:PRIVATE@game.test/path?a=1#PRIVATE'))
        self.assertEqual([], safe_headers([{'name': k, 'value': 'PRIVATE'} for k in
                                          ('X-CSRF-Token', 'Proxy-Authorization', 'Cookie2', 'X-Api-Key', 'X-Auth')]))


if __name__ == '__main__':
    unittest.main()
