"""将单个手动登录游戏窗口的记录逐条写成 HAR 1.2。"""
import base64
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from urllib.parse import parse_qsl, urlencode, urlsplit

from capture_layout import plain_directory


def _private_name(name):
    key = re.sub(r'[^a-z0-9]', '', name.lower())
    return (key in {'account', 'username', 'userpass', 'pwd', 'sid', 'jwt', 'ticket',
                    'auth', 'xauth', 'sign', 'signature'}
            or any(word in key for word in ('authorization', 'authenticat', 'cookie', 'password',
                   'passwd', 'secret', 'token', 'session', 'credential', 'apikey', 'accesskey', 'csrf', 'xsrf')))


def _public_pairs(pairs):
    # 大厅游戏入口也可能携带供应商自己的会话参数。
    return [(k, v) for k, v in pairs if not _private_name(k) and k.lower() not in ('key', 'ot', 'ops', 'ao')
            and not v.lower().startswith(('bearer ', 'basic '))]


def safe_url(url, *, _depth=0):
    """保留游戏资源地址与普通查询参数，移除地址中的凭据、会话参数及片段。"""
    try:
        parts = urlsplit(url)
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        retained = _public_pairs(pairs)
        for i, (name, value) in enumerate(retained):
            if value.lower().startswith(('http://', 'https://', '//')):
                retained[i] = (name, safe_url(value, _depth=_depth + 1) if _depth < 2 else '')
        return parts._replace(netloc=parts.netloc.rsplit('@', 1)[-1], fragment='',
                              query=urlencode(retained) if retained != pairs else parts.query).geturl()
    except (TypeError, ValueError):
        return ''


def safe_headers(headers):
    result = []
    for header in headers or ():
        if not isinstance(header, dict):
            continue
        name, value = header.get('name'), header.get('value')
        if not isinstance(name, str) or not isinstance(value, str) or _private_name(name):
            continue
        if name.lower() in ('referer', 'location', 'origin', 'content-location'):
            value = safe_url(value)
        if name.lower() in ('link', 'refresh', 'sec-websocket-protocol') or value.lower().startswith(('bearer ', 'basic ')):
            continue
        result.append({'name': name, 'value': value})
    return result


def _saved_body(folder, row, *, request):
    number = row.get('id')
    if type(number) is not int or number < 1:
        return None
    name = row.get('request_body' if request else 'body')
    if not isinstance(name, str):
        return None
    match = re.fullmatch(r'bodies/([0-9]{1,20})(\.request)?\.[a-zA-Z0-9_-]+', name)
    if not match or int(match[1]) != number or bool(match[2]) != request:
        return None
    if not request and row.get('state') != 'complete':
        return None
    path = folder / name
    try:
        if not plain_directory(path.parent):
            return None
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
                or not request and info.st_size != row.get('size')):
            return None
        with path.open('rb') as body:
            if not os.path.samestat(info, os.fstat(body.fileno())):
                return None
            raw = body.read()
        return raw if len(raw) == info.st_size else None
    except OSError:
        return None


def _private_json(value):
    if isinstance(value, dict):
        return {k: _private_json(v) for k, v in value.items() if not _private_name(k)}
    if isinstance(value, list):
        return [_private_json(item) for item in value]
    if isinstance(value, str) and value.lower().startswith(('https://', 'http://', 'wss://', 'ws://')):
        return safe_url(value)
    return value


def _content(raw, mime, *, request=False, dynamic=False):
    result = {'mimeType': mime}
    if raw is None:
        return {**result, 'size': 0, 'comment': '未取得完整正文'}
    media = mime.split(';', 1)[0].strip().lower()
    textual = (media.startswith('text/') or media.endswith(('json', 'xml', 'javascript', 'ecmascript'))
               or media == 'application/x-www-form-urlencoded')
    if textual:
        charset = re.search(r"""\bcharset\s*=\s*["']?([\w.-]+)""", mime, re.I)
        encoding = charset[1] if charset else 'utf-8'
        try:
            text = raw.decode(encoding)
            if text.encode(encoding) == raw:
                if dynamic and media.endswith('json'):
                    try:
                        value = json.loads(text)
                        cleaned = _private_json(value)
                        if cleaned != value:
                            text = json.dumps(cleaned, ensure_ascii=True, separators=(',', ':'))
                    except (ValueError, RecursionError):
                        # 畸形 JSON 可能夹有身份字段，保留记录及 MIME，省略该正文。
                        return {**result, 'size': 0, 'comment': '无法核对 JSON 内的身份字段'}
                elif dynamic and media == 'application/x-www-form-urlencoded':
                    pairs = parse_qsl(text, keep_blank_values=True)
                    retained = [(k, safe_url(v) if v.lower().startswith(('https://', 'http://')) else v)
                                for k, v in _public_pairs(pairs)]
                    if retained != pairs:
                        text = urlencode(retained)
                return {**result, 'size': len(text.encode(encoding)), 'text': text}
        except (LookupError, UnicodeError):
            if dynamic and (media.endswith('json') or media == 'application/x-www-form-urlencoded'):
                return {**result, 'size': 0, 'comment': '无法解码并核对身份字段'}
    return {**result, 'size': len(raw), '_encoding' if request else 'encoding': 'base64',
            'text': base64.b64encode(raw).decode('ascii')}


def _entry(folder, row, started):
    url = safe_url(row['url'])
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https', 'ws', 'wss') or not parts.hostname:
        return None
    if parts.hostname == 'sdstest.ink' and (parts.path.rstrip('/') in ('/login', '/register') or
            parts.path.startswith('/api/') and not parts.path.startswith('/api/v1/games/')):
        return None
    headers = safe_headers(row.get('request_headers'))
    req = {'url': url, 'method': row['method'], 'httpVersion': '', 'headers': headers,
           'cookies': [], 'queryString': [{'name': k, 'value': v} for k, v in parse_qsl(parts.query, keep_blank_values=True)],
           'headersSize': -1, 'bodySize': -1}
    raw = _saved_body(folder, row, request=True)
    if raw is not None:
        mime = next((h['value'] for h in headers if h['name'].lower() == 'content-type'), 'application/octet-stream')
        post = _content(raw, mime, request=True, dynamic=True)
        req['bodySize'] = post.pop('size')
        req['postData'] = post
    headers = safe_headers(row.get('response_headers'))
    asset = '/assets/' in parts.path or parts.path.lower().endswith(('.json', '.atlas', '.map', '.js', '.css', '.html'))
    dynamic = (row['method'] not in ('GET', 'HEAD') or
               not asset and any(segment in parts.path for segment in ('/api/', '/game-api/', '/web-api/')))
    res = {'status': row.get('status') or 0, 'statusText': '', 'httpVersion': '', 'headers': headers,
           'cookies': [], 'content': _content(_saved_body(folder, row, request=False),
                                              row.get('mime') or 'application/octet-stream', dynamic=dynamic),
           'headersSize': -1, 'bodySize': -1,
           'redirectURL': next((h['value'] for h in headers if h['name'].lower() == 'location'), '')}
    # 单页记录没有协议版本和分段耗时；HAR 要求这三个计时字段非负。
    return {'startedDateTime': row.get('started') or started, 'time': 0, 'request': req, 'response': res,
            'cache': {}, 'timings': {'send': 0, 'wait': 0, 'receive': 0, 'comment': '未测量分段耗时'},
            '_resourceType': row.get('type', '')}


def write_page_har(folder, rows, started):
    """仅使用调用者交付的行和同批响应文件，完整写完后发布。"""
    folder = Path(folder)
    if not plain_directory(folder):
        raise ValueError('游戏批次目录不可用。')
    temp = tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=folder, suffix='.pending', delete=False)
    path = Path(temp.name)
    try:
        with temp:
            temp.write('{"log":{"version":"1.2","creator":{"name":"Response Capture","version":"1"},"entries":[')
            first = True
            for row in rows:
                entry = _entry(folder, row, started)
                if entry is not None:
                    if not first:
                        temp.write(',')
                    first = False
                    json.dump(entry, temp, ensure_ascii=True, separators=(',', ':'))
            temp.write(']}}')
        path.replace(folder / 'network.har')
    finally:
        path.unlink(missing_ok=True)
