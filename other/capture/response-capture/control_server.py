"""本机抓取工具，同时提供录制、归档、游戏列表和服务管理。"""
import argparse
from datetime import datetime, timezone
import errno
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import threading
from types import SimpleNamespace
import webbrowser
from http.client import HTTPConnection, HTTPException
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from original_games import OriginalGames, inspect_process, owned_listener, process_created, same_creation
from game_covers import serve_cover
from service_runtime import ServiceError
import app as recorder


ROOT = Path(__file__).resolve().parent
STATIC = {'/service-console.js': 'text/javascript; charset=utf-8',
          '/service-console.css': 'text/css; charset=utf-8'}
ASSETS = '<link rel="stylesheet" href="/service-console.css"><script defer src="/service-console.js"></script>'
TOKEN_PATTERN = re.compile(r"\btoken\s*=\s*(['\"])([A-Za-z0-9_-]{16,256})\1")


class CaptureProxy:
    def __init__(self):
        self.tokens = {}
        self.lock = threading.Lock()

    def token(self, port, refresh=False):
        with self.lock:
            if not refresh and port in self.tokens:
                return self.tokens[port]
            connection = HTTPConnection('127.0.0.1', port, timeout=10)
            try:
                connection.request('GET', '/', headers={'Host': f'127.0.0.1:{port}'})
                response = connection.getresponse()
                document = response.read(4 * 1024 * 1024 + 1)
                if response.status != 200 or len(document) > 4 * 1024 * 1024:
                    raise ValueError('抓取服务首页暂不可读取。')
                token = TOKEN_PATTERN.search(document.decode('utf-8'))
                if not token or b'Response Capture' not in document:
                    raise ValueError('目标端口不是可核验的抓取服务。')
                self.tokens[port] = token[2]
                return token[2]
            finally:
                connection.close()

    def open(self, port, method, path, body=None, content_type=None):
        for attempt in range(2):
            headers = {'Host': f'127.0.0.1:{port}', 'Accept': '*/*'}
            if method == 'POST':
                headers.update({'Origin': f'http://127.0.0.1:{port}', 'Sec-Fetch-Site': 'same-origin',
                                'X-Capture-Token': self.token(port, refresh=attempt == 1),
                                'Content-Type': content_type or 'application/json', 'Content-Length': str(len(body))})
            connection = HTTPConnection('127.0.0.1', port, timeout=60)
            try:
                connection.request(method, path, body=body, headers=headers)
                response = connection.getresponse()
                if method == 'POST' and response.status == 403 and attempt == 0:
                    response.read(64 * 1024)
                    connection.close()
                    continue
                return connection, response
            except Exception:
                connection.close()
                raise
        raise ValueError('抓取服务认证暂不可用，请稍后重试。')


class ControlServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = os.name != 'nt'

    def server_bind(self):
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def capture_row(self):
        with recorder.MANAGER_LOCK:
            active = recorder.unfinished_count()
            paused = self.capture_paused
        return dict(id='fixed.capture', name='抓取工具', category='fixed', kind='capture', integrated=True,
                    description='在游戏列表中抓取、停止并保存、检查证据和下载历史记录。',
                    status='stopped' if paused else 'running', reason=f'当前有 {active} 个批次正在录制或保存。' if active else '',
                    running_count=int(not paused), pid=os.getpid(), port=self.server_port, instances=[],
                    open_url=f'http://127.0.0.1:{self.server_port}/', can_start=paused, can_stop=not paused and not active)

    def capture_operation(self, action, *, prepare=False):
        with recorder.MANAGER_LOCK:
            if action == 'stop' and recorder.unfinished_count():
                raise ServiceError('请先在游戏行停止并保存所有活动抓取。', 409)
            if prepare:
                return {'requires_confirmation': False, 'targets': [], 'warnings': []}
            self.capture_paused = action == 'stop'
        return {'ok': True, 'id': 'fixed.capture', 'state': 'stopped' if action == 'stop' else 'running',
                'message': '已暂停接收新抓取，历史记录仍可查看和下载。' if action == 'stop' else '已恢复接收新抓取。'}

    def capture_log(self):
        with recorder.MANAGER_LOCK:
            batches = list(recorder.SESSIONS.values())
        lines = [f'{recorder.PROCESS_STARTED} 抓取工具启动，端口 {self.server_port}']
        for batch in batches[-100:]:
            item = batch.snapshot(include_rows=False)
            lines.append(f"{item['created']}  {item['id']}  {item['state']}")
        return {'id': 'fixed.capture', 'text': '\n'.join(lines), 'truncated': len(batches) > 100}


class ControlHandler(recorder.Handler):
    def log_message(self, *_):
        pass

    def send(self, status, value, mime='application/json; charset=utf-8'):
        raw = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if getattr(self, '_cors_origin', None):
            self.send_header('Access-Control-Allow-Origin', self._cors_origin)
            self.send_header('Vary', 'Origin')
        self.end_headers()
        self.wfile.write(raw)

    def allowed(self):
        port = self.server.server_port
        return (self.client_address[0] in ('127.0.0.1', '::1') and
                self.headers.get('Host') in (f'127.0.0.1:{port}', f'localhost:{port}'))

    def allowed_post(self):
        origin = self.headers.get('Origin')
        local = origin is None or origin == 'http://' + self.headers.get('Host', '')
        cross = not local and self.capture_origin()
        return (self.allowed() and self.headers.get('X-Capture-Token') == self.server.token
                and (local or cross)
                and self.headers.get('Sec-Fetch-Site', 'none') in (('none', 'same-origin', 'same-site', 'cross-site') if cross else ('none', 'same-origin')))

    def capture_origin(self):
        """旧抓取页只可访问控制台接口；其它本机网页不能取得操作令牌。"""
        origin = self.headers.get('Origin')
        if not origin or self.path.split('?', 1)[0] not in (
                '/api/services', '/api/services/capture', '/api/services/bootstrap',
                '/api/services/control-status', '/api/services/logs', '/api/services/start', '/api/services/stop', '/api/services/prepare',
                '/api/services/cleanup/options', '/api/services/cleanup/prepare', '/api/services/cleanup'):
            return False
        try:
            source = urlsplit(origin)
            if (source.scheme != 'http' or source.hostname not in ('127.0.0.1', 'localhost')
                    or source.username or source.password or source.path or source.query or source.fragment
                    or not source.port or origin != f'http://{source.hostname}:{source.port}'):
                return False
            if not self.server.capture_origin_verifier(source.port):
                return False
            self._cors_origin = origin
            return True
        except (OSError, ValueError, TypeError, KeyError, HTTPException, subprocess.SubprocessError):
            return False

    def do_OPTIONS(self):
        if not self.allowed() or not self.capture_origin():
            return self.send(403, {'error': '不允许的控制台来源'})
        requested = {v.strip().lower() for v in self.headers.get('Access-Control-Request-Headers', '').split(',') if v.strip()}
        if (self.headers.get('Access-Control-Request-Method') not in ('GET', 'POST')
                or not requested.issubset({'content-type', 'x-capture-token'})):
            return self.send(403, {'error': '不允许的控制台预检请求'})
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', self._cors_origin)
        self.send_header('Vary', 'Origin')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Capture-Token')
        self.send_header('Access-Control-Max-Age', '10')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def target(self):
        target = urlsplit(self.path)
        if target.scheme or target.netloc or target.fragment or not target.path.startswith('/'):
            raise ValueError('不接受外部网址。')
        return target

    def capture_port(self):
        if self.server.integrated:
            return self.server.server_port
        port = getattr(self.server.manager, 'capture_port', self.server.capture_port)
        if type(port) is not int or not 1 <= port <= 65535 or port == self.server.server_port:
            raise ValueError('抓取服务端口无效。')
        return port

    def cleanup_origin(self):
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + self.headers.get('Host', ''):
            # allowed_post 已核验跨源捕获页；不能由请求正文指定保留哪个窗口。
            return origin
        return 'http://127.0.0.1:' + str(self.capture_port())

    def fail(self, error):
        status = getattr(error, 'status', 400 if isinstance(error, (ValueError, TypeError, KeyError)) else 503)
        if status not in (400, 403, 404, 409, 503):
            status = 503
        message = str(error) if isinstance(error, ValueError) or hasattr(error, 'status') else '服务操作暂不可用，请查看控制台状态与日志。'
        return self.send(status, {'error': message})

    def do_GET(self):
        if not self.allowed():
            return self.send(403, {'error': '不允许的本机来源'})
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + self.headers.get('Host', '') and not self.capture_origin():
            return self.send(403, {'error': '不允许的控制台来源'})
        try:
            target = self.target()
            if target.path.startswith('/game-covers/'):
                return serve_cover(self, target.path)
            if target.path == '/':
                document = (ROOT / 'index.html').read_text(encoding='utf-8')
                document = document.replace('__LOCAL_GAME_COVERS__', '1')
                document = document.replace('__TOKEN__', self.server.token).replace('__GAME_CAPTURE_VERSION__', '1').replace('__PARALLEL_CAPTURE_VERSION__', '1')
                mode = ' data-integrated-capture="1"' if self.server.integrated else ''
                document = re.sub(r'<html\b', '<html data-service-console="1"' + mode, document, count=1)
                document = document.replace('http://127.0.0.1:18096/service-console.', '/service-console.')
                if '<!-- /SERVICE_CONSOLE_ASSETS -->' in document:
                    document = re.sub(r'<!-- SERVICE_CONSOLE_ASSETS -->.*?<!-- /SERVICE_CONSOLE_ASSETS -->', ASSETS, document, count=1, flags=re.S)
                elif '<!-- SERVICE_CONSOLE_ASSETS -->' in document:
                    document = document.replace('<!-- SERVICE_CONSOLE_ASSETS -->', ASSETS)
                else:
                    document = document.replace('</head>', ASSETS + '</head>', 1)
                return self.send(200, document.encode('utf-8'), 'text/html; charset=utf-8')
            if target.path in STATIC:
                return self.send(200, (ROOT / target.path[1:]).read_bytes(), STATIC[target.path])
            if target.path == '/api/services/bootstrap':
                if target.query:
                    raise ValueError('控制台初始化不接受查询参数。')
                return self.send(200, {'token': self.server.token, 'control_port': self.server.server_port})
            if target.path in ('/api/services', '/api/services/capture'):
                if target.query:
                    raise ValueError('服务状态不接受查询参数。')
                snapshot = self.server.manager.snapshot()
                if self.server.integrated:
                    others = [s for s in snapshot.get('services', []) if s.get('id') != 'fixed.capture']
                    capture = self.server.capture_row()
                    capture['legacy_count'] = sum(s.get('category') == 'capture-instances' for s in others)
                    snapshot = dict(snapshot, capture_port=self.server.server_port,
                                    services=[capture, *others])
                if target.path.endswith('/capture'):
                    snapshot = {'capture_port': self.capture_port(), 'services': [s for s in snapshot.get('services', [])
                                if s.get('id') == 'fixed.capture' or s.get('category') == 'capture-instances']}
                return self.send(200, snapshot)
            if target.path == '/api/services/control-status':
                return self.send(200, self.server.identity)
            if target.path == '/api/services/logs':
                query = parse_qs(target.query, keep_blank_values=True, strict_parsing=True)
                if set(query) != {'id'} or len(query['id']) != 1 or not query['id'][0] or len(query['id'][0]) > 200:
                    raise ValueError('日志查询只接受一个服务 ID。')
                if self.server.integrated and query['id'][0] == 'fixed.capture':
                    return self.send(200, self.server.capture_log())
                return self.send(200, self.server.manager.logs(query['id'][0]))
            if target.path == '/api/original-games':
                return self.send(200, self.server.original_games.catalog())
            if target.path.startswith('/api/original-games/previews/'):
                return self.send(200, self.server.original_games.job(target.path.rsplit('/', 1)[-1]))
            if target.path.startswith('/api/'):
                return super().do_GET() if self.server.integrated else self.proxy('GET', target)
            return self.send(404, {'error': '没有该页面或接口'})
        except (OSError, ValueError, TypeError, KeyError, HTTPException, subprocess.SubprocessError) as error:
            return self.fail(error)

    def do_POST(self):
        if not self.allowed_post():
            return self.send(403, {'error': '请刷新本地控制台后重试'})
        try:
            target = self.target()
            if target.query:
                raise ValueError('操作接口不接受查询参数。')
            if self.headers.get('Transfer-Encoding'):
                raise ValueError('操作接口需要明确的请求长度。')
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 16384:
                raise ValueError('请求长度无效。')
            raw = self.rfile.read(length)
            data = json.loads(raw)
            if target.path == '/api/services/cleanup/options':
                if data != {}:
                    raise ValueError('清理选项不接受自定义来源或目标路径。')
                return self.send(200, self.server.cleanup.options(self.cleanup_origin()))
            if target.path == '/api/services/cleanup/prepare':
                if (not isinstance(data, dict) or set(data) != {'keep_ids'} or not isinstance(data['keep_ids'], list)
                        or len(data['keep_ids']) > 1024 or any(not isinstance(value, str) or not 0 < len(value) <= 200 for value in data['keep_ids'])):
                    raise ValueError('清理预检只接受保留服务 ID 列表。')
                return self.send(200, self.server.cleanup.prepare(data['keep_ids'], self.cleanup_origin()))
            if target.path == '/api/services/cleanup':
                if not isinstance(data, dict) or set(data) != {'confirmation_id'} or not isinstance(data['confirmation_id'], str) or not re.fullmatch(r'[a-f0-9]{64}', data['confirmation_id']):
                    raise ValueError('批量关闭确认凭据无效，请重新预览。')
                return self.send(200, self.server.cleanup.execute(data['confirmation_id'], self.cleanup_origin()))
            if target.path == '/api/services/prepare':
                if not isinstance(data, dict) or set(data) != {'id', 'action'} or not isinstance(data['id'], str) or not 0 < len(data['id']) <= 200 or data['action'] not in ('start', 'stop'):
                    raise ValueError('预检只接受服务 ID 和启动或关闭动作。')
                if self.server.integrated and data['id'] == 'fixed.capture':
                    return self.send(200, self.server.capture_operation(data['action'], prepare=True))
                return self.send(200, self.server.manager.prepare(data['id'], data['action']))
            if target.path in ('/api/services/start', '/api/services/stop'):
                if not isinstance(data, dict) or set(data) not in ({'id'}, {'id', 'confirmation_id'}) or not isinstance(data['id'], str) or not 0 < len(data['id']) <= 200:
                    raise ValueError('请指定一个服务 ID，不能提交任意启动命令。')
                if 'confirmation_id' in data and (not isinstance(data['confirmation_id'], str) or not re.fullmatch(r'[a-f0-9]{64}', data['confirmation_id'])):
                    raise ValueError('操作确认凭据无效，请重新预检。')
                if self.server.integrated and data['id'] == 'fixed.capture':
                    return self.send(200, self.server.capture_operation(target.path.rsplit('/', 1)[1]))
                method = self.server.manager.start if target.path.endswith('/start') else self.server.manager.stop
                return self.send(200, method(data['id'], confirmation_id=data['confirmation_id']) if 'confirmation_id' in data else method(data['id']))
            if target.path in ('/api/original-games/open-directory', '/api/original-games/preview'):
                if not isinstance(data, dict) or set(data) != {'id'}:
                    raise ValueError('请指定一个原版产物 ID，不能提交路径或启动命令。')
                method = self.server.original_games.open_folder if target.path.endswith('/open-directory') else self.server.original_games.preview
                return self.send(200, method(data['id']))
            if target.path.startswith('/api/'):
                return self.capture_post(target.path, data) if self.server.integrated else self.proxy('POST', target, raw)
            return self.send(404, {'error': '没有该操作接口'})
        except (OSError, ValueError, TypeError, KeyError, HTTPException, subprocess.SubprocessError) as error:
            return self.fail(error)

    def proxy(self, method, target, body=None):
        path = target.path + ('?' + target.query if target.query else '')
        try:
            connection, response = self.server.proxy.open(self.capture_port(), method, path, body, self.headers.get('Content-Type'))
        except (OSError, ValueError, HTTPException):
            return self.send(503, {'error': '抓取服务尚未运行或暂不可连接；服务控制台仍可使用。'})
        try:
            self.send_response(response.status)
            for name in ('Content-Type', 'Content-Length', 'Content-Disposition', 'Location'):
                value = response.getheader(name)
                if value is not None:
                    self.send_header(name, value)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            while chunk := response.read(64 * 1024):
                self.wfile.write(chunk)
        except (OSError, HTTPException):
            # 已发送响应头后不追加另一份 JSON，下载中断由浏览器按实际字节数处理。
            self.close_connection = True
        finally:
            connection.close()


def create_server(address=('127.0.0.1', 18096), *, manager=None, capture_port=None, previous_port=None, repo=None, capture_origin_verifier=None):
    if address[0] != '127.0.0.1' or (capture_port is not None and (type(capture_port) is not int or not 1 <= capture_port <= 65535)):
        raise ValueError('控制台只能监听本机回环地址，并需有效的抓取服务端口。')
    if previous_port is not None and (type(previous_port) is not int or not 1 <= previous_port <= 65535 or previous_port in (capture_port, address[1])):
        raise ValueError('旧抓取服务端口必须有效，并与控制台及当前抓取服务不同。')
    server = ControlServer(address, ControlHandler)
    try:
        server.integrated = capture_port is None
        server.capture_paused = False
        if server.server_port in (capture_port, previous_port):
            raise ValueError('控制台与抓取服务不能使用同一端口。')
        if server.integrated:
            capture_port = server.server_port
        server.previous_recorder = recorder.PreviousRecorder(previous_port) if server.integrated and previous_port else None
        repository = Path(repo or ROOT.parents[2]).absolute()
        if manager is None:
            from service_runtime import ServiceManager
            options = {'capture_port': capture_port, 'control_port': server.server_port, 'owner_chat': os.environ.get('CODEX_THREAD_ID')}
            if previous_port is not None:
                options['previous_port'] = previous_port
            manager = ServiceManager(repository, **options)
        server.manager, server.capture_port = manager, capture_port
        manager.control_pid = os.getpid()
        from service_cleanup import ServiceCleanup
        server.cleanup = ServiceCleanup(manager)
        server.previous_port = previous_port
        server.token = secrets.token_urlsafe(32)
        server.proxy = None if server.integrated else CaptureProxy()
        verified_origins = {}
        def verify_capture_origin(port):
            from service_runtime import argv_of
            snapshot = manager.snapshot()
            if snapshot.get('error'):
                return False
            candidates = {capture_port, previous_port, getattr(manager, 'capture_port', capture_port)}
            rows = [row for row in snapshot.get('services', []) if row.get('id') == 'fixed.capture'
                    or row.get('category') == 'capture-instances']
            candidates.update(row.get('port') for row in rows)
            instances = [v for row in rows for v in row.get('instances', [])]
            candidates.update(v.get('port') for v in instances)
            if port not in candidates:
                return False
            processes, listeners = getattr(manager, 'processes', {}), getattr(manager, 'listeners', [])
            occupants = [listener for listener in listeners if listener.get('port') == port]
            if not occupants:
                # 原页面停止抓取后仍能重开服务；端口空闲时没有新的网页可冒用来源。
                return port in verified_origins
            for listener in occupants:
                if listener.get('port') != port or listener.get('address') != '127.0.0.1':
                    continue
                process = processes.get(listener.get('pid'), {})
                if process.get('pid') != listener.get('pid') or not process.get('created'):
                    continue
                args = argv_of(process.get('command'))
                if any(Path(value).is_absolute() and Path(value).resolve() == (ROOT / 'app.py').resolve() for value in args[1:]):
                    verified_origins[port] = {'pid': process.get('pid'), 'created': process.get('created')}
                    return True
                if 'app.py' in args[1:]:
                    parent = processes.get(process.get('parent'), {})
                    expected = ROOT / '.venv/Scripts/python.exe'
                    parent_args = argv_of(parent.get('command'))
                    executables = [parent.get('executable')] + parent_args[:1]
                    try:
                        after_parent = datetime.fromisoformat(process['created']) >= datetime.fromisoformat(parent['created'])
                    except (KeyError, TypeError, ValueError):
                        after_parent = False
                    if after_parent and any(value and Path(value).is_absolute() and Path(value).resolve() == expected.resolve() for value in executables):
                        verified_origins[port] = {'pid': process.get('pid'), 'created': process.get('created')}
                        return True
            # 一旦发现端口被其它进程接管，撤销旧页面的来源记录。
            verified_origins.pop(port, None)
            return False
        server.capture_origin_verifier = capture_origin_verifier or verify_capture_origin
        try:
            created = process_created(SimpleNamespace(pid=os.getpid(), _handle=-1)) if os.name == 'nt' else None
        except OSError:
            created = None
        server.identity = {'service': 'response-capture-console', 'version': 2, 'integrated': server.integrated,
                           'capture_port': capture_port, 'previous_port': previous_port, 'pid': os.getpid(),
                           'created': created, 'chat': os.environ.get('CODEX_THREAD_ID'), 'repo': str(repository),
                           'cwd': str(ROOT), 'entry': str(ROOT / 'control_server.py'), 'port': server.server_port,
                           'command': [sys.executable, *sys.argv]}
        original = getattr(manager, 'original_games', None)
        if original is None:
            original = OriginalGames(repository, repository / 'other/capture/response-capture/captures')
            manager.original_games = original
        server.original_games = original
        return server
    except Exception:
        server.server_close()
        raise


def existing_console(port, capture_port=None, previous_port=None):
    """端口占用时只核对并打开本仓库现有控制台，不结束或覆盖任何实例。"""
    connection = HTTPConnection('127.0.0.1', port, timeout=3)
    try:
        connection.request('GET', '/api/services/control-status')
        response = connection.getresponse()
        raw = response.read(32769)
        if response.status != 200 or len(raw) > 32768:
            return False
        identity = json.loads(raw)
        if (identity.get('service') != 'response-capture-console' or identity.get('port') != port
                or identity.get('integrated') is not (capture_port is None)
                or identity.get('capture_port') != (capture_port or port) or identity.get('previous_port') != previous_port
                or os.environ.get('CODEX_THREAD_ID') and identity.get('chat') != os.environ['CODEX_THREAD_ID']
                or Path(identity.get('repo', '')).resolve() != ROOT.parents[2].resolve()
                or Path(identity.get('entry', '')).resolve() != (ROOT/'control_server.py').resolve()):
            return False
        if os.name == 'nt':
            actual = inspect_process(identity['pid'], port)
            return owned_listener(actual, identity['pid'], port) and same_creation(actual['created'], identity['created'])
        return True
    except (OSError, ValueError, KeyError, TypeError, HTTPException, subprocess.SubprocessError):
        return False
    finally:
        connection.close()


def write_control_owner(server):
    root = ROOT.parents[2] / 'other/diagnostics/service-console'
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    destination = root / f'control-owner-{server.server_port}-{os.getpid()}-{stamp}.json'
    record = {**server.identity, 'started': datetime.now(timezone.utc).isoformat(),
              'capture_port': server.capture_port, 'listening_ports': [server.server_port]}
    # 文件名带端口和 PID，保留其它实例及历史归属，不写一个共享 owner 文件。
    with destination.open('x', encoding='utf-8') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
    return destination


def main():
    parser = argparse.ArgumentParser(description='本机抓取工具与服务管理')
    parser.add_argument('--port', type=int, help='固定工具端口，默认优先使用 18096')
    parser.add_argument('--capture-port', type=int, help='仅旧版分进程模式使用，指定要转发的抓取端口')
    parser.add_argument('--previous-port', type=int, help='新抓取实例只读显示此旧实例的活动批次')
    parser.add_argument('--open', action='store_true', help='打开本机控制台页面')
    args = parser.parse_args()
    configured = [p for p in (args.port, args.capture_port, args.previous_port) if p is not None]
    if any(not 1 <= p <= 65535 for p in configured) or len(configured) != len(set(configured)):
        parser.error('各端口必须有效且互不相同。')
    ports = [args.port] if args.port else [18096, *range(18098, 18106)]
    for port in ports:
        if port in (args.capture_port, args.previous_port):
            continue
        try:
            server = create_server(('127.0.0.1', port), capture_port=args.capture_port, previous_port=args.previous_port)
            break
        except OSError as error:
            if error.errno != errno.EADDRINUSE and getattr(error, 'winerror', None) not in (10013, 10048):
                raise
            if existing_console(port, args.capture_port, args.previous_port):
                address = f'http://127.0.0.1:{port}/'
                print('已有本项目抓取工具：' + address, flush=True)
                if args.open:
                    webbrowser.open(address)
                return
    else:
        raise SystemExit('工具端口已被占用，可通过 --port 指定其他空闲端口。')
    try:
        write_control_owner(server)
    except OSError:
        server.server_close()
        close = getattr(server.manager, 'close', None)
        if callable(close):
            close()
        raise SystemExit('无法记录本次控制台归属，已取消启动。') from None
    print(f'Response Capture Console: http://127.0.0.1:{server.server_port}', flush=True)
    if args.open:
        webbrowser.open(f'http://127.0.0.1:{server.server_port}/')
    try:
        while True:
            try:
                server.serve_forever()
                break
            except KeyboardInterrupt:
                with recorder.MANAGER_LOCK:
                    if server.integrated and recorder.unfinished_count():
                        print('仍有活动抓取，请在游戏行停止并保存后再退出。', flush=True)
                        continue
                    server.stopping = True
                    break
    finally:
        server.server_close()
        close = getattr(server.manager, 'close', None)
        if callable(close):
            close()
        if server.integrated:
            recorder.MANUAL_LOBBIES.shutdown()


if __name__ == '__main__':
    main()
