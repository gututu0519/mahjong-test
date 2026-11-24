"""独立服务控制台：固定入口、实时进程身份核验与操作确认。"""
import copy
import ctypes
import hashlib
import json
import os
import re
import shlex
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http.client import HTTPConnection
from pathlib import Path

from service_registry import CATEGORIES, build_registry
from original_games import OriginalGames, NO_WINDOW, process_created, same_creation, read_json, worktrees
from archive_identity import enrich_target
from service_confirmation import ConfirmedOperations


class ServiceError(ValueError):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def now():
    return datetime.now(timezone.utc).isoformat()


def redact(value):
    value = str(value)
    value = re.sub(r'(?im)((?:authorization|(?:set-)?cookie)\s*:\s*)[^\r\n]*', r'\1[已隐藏]', value)
    value = re.sub(r'(?i)((?:Bearer|Basic)\s+)[^\s,;"\']+', r'\1[已隐藏]', value)
    key = r'(?<![A-Za-z_])(?:[A-Za-z_]*password|passwd|pwd|[A-Za-z_]*token|[A-Za-z_]*secret|authorization|cookie|api[_-]?key)'
    value = re.sub(r'(?i)(' + key + r'["\']?\s*[:=]\s*)(["\'])(?:\\.|(?!\2)[^\r\n])*?\2', r'\1"[已隐藏]"', value)
    value = re.sub(r'(?i)(' + key + r'["\']?\s*[:=]\s*)(?!["\'])[^\s,;&}]+', r'\1[已隐藏]', value)
    value = re.sub(r'(?i)(https?://)[^/\s:@]+:[^/\s@]+@', r'\1[已隐藏]@', value)
    return value


def argv_of(command):
    if isinstance(command, (list, tuple)):
        return [str(v) for v in command]
    if not isinstance(command, str) or not command.strip():
        return []
    if os.name == 'nt':
        from ctypes import wintypes
        count = ctypes.c_int()
        split = ctypes.windll.shell32.CommandLineToArgvW
        split.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
        split.restype = ctypes.POINTER(wintypes.LPWSTR)
        result = split(command, ctypes.byref(count))
        if not result:
            return []
        try:
            return [result[i] for i in range(count.value)]
        finally:
            ctypes.windll.kernel32.LocalFree(result)
    try:
        return [v.strip('"') for v in shlex.split(command, posix=False)]
    except ValueError:
        return []


def normalized(value):
    return str(value).replace('\\', '/').rstrip('/').casefold()


def command_matches(expected, actual):
    return [normalized(v) for v in argv_of(expected)] == [normalized(v) for v in argv_of(actual)]


def windows_inventory():
    """一次取得进程与监听快照；不向网页返回命令中的私有参数。"""
    if os.name != 'nt':
        raise OSError('当前服务进程发现仅支持 Windows。')
    script = r"""$ErrorActionPreference='Stop'
$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new()
$items=@(Get-CimInstance Win32_Process | ForEach-Object {
 $created=if ($_.CreationDate) {$_.CreationDate.ToUniversalTime().ToString('o')} else {''}
 @{pid=[int]$_.ProcessId;parent=[int]$_.ParentProcessId;created=$created;command=$_.CommandLine;executable=$_.ExecutablePath;name=$_.Name}
})
$ports=@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | ForEach-Object {@{pid=[int]$_.OwningProcess;port=[int]$_.LocalPort;address=$_.LocalAddress}})
@{processes=$items;listeners=$ports}|ConvertTo-Json -Depth 5 -Compress
"""
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                            capture_output=True, timeout=20, check=True, creationflags=NO_WINDOW)
    return json.loads(result.stdout.decode('utf-8-sig'))


def terminate_checked(record, actual):
    """使用同一个已核验创建时间的系统句柄终止，避免检查后 PID 被复用。"""
    if os.name != 'nt':
        raise ServiceError('此平台尚未实现可核验的进程停止。', 503)
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000 | 0x0001, False, int(actual['pid']))
    if not handle:
        raise ServiceError('进程已退出或无法取得核验句柄。')
    try:
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            raise ServiceError('无法核验进程创建时间。')
        ticks = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        created = datetime.fromtimestamp((ticks - 116444736000000000) / 10000000, timezone.utc).isoformat()
        if not same_creation(created, actual['created']) or not same_creation(created, record['created']):
            raise ServiceError('进程身份已变化，拒绝停止。', 403)
        if not kernel.TerminateProcess(handle, 0):
            raise OSError('停止进程失败。')
    finally:
        kernel.CloseHandle(handle)


class ServiceManager(ConfirmedOperations):
    def __init__(self, repo, capture_port=18095, control_port=18096, owner_chat=None, *,
                 previous_port=None, inventory=None, spawner=None, creation=None,
                 terminator=None, original_games=None, start_background=True, health=None, worktree_provider=None, shared_services=None):
        self.repo = Path(repo).resolve()
        self.capture_port, self.control_port = int(capture_port), int(control_port)
        self.previous_port = int(previous_port) if previous_port else None
        self.owner_chat = owner_chat or os.environ.get('CODEX_THREAD_ID', '')
        self.home = self.repo / 'other/diagnostics/service-console'
        self.home.mkdir(parents=True, exist_ok=True)
        if not self.owner_chat:
            try:
                scope = read_json(self.home, 'local-scope.json', 2048)
                self.owner_chat = scope.get('scope', '')
                if not re.fullmatch(r'local-console-[0-9a-f]{32}', self.owner_chat):
                    raise ValueError('无效的本地控制台标识')
            except FileNotFoundError:
                self.owner_chat = 'local-console-' + uuid.uuid4().hex
                try:
                    with (self.home / 'local-scope.json').open('x', encoding='utf-8') as stream:
                        json.dump({'scope': self.owner_chat}, stream)
                except FileExistsError:
                    self.owner_chat = read_json(self.home, 'local-scope.json', 2048)['scope']
        self.registry = {row['id']: row for row in build_registry(self.repo)}
        self.registry['fixed.capture']['default_port'] = self.capture_port
        self.original_games = original_games if original_games is not None else OriginalGames(self.repo, self.repo / 'other/capture/response-capture/captures')
        if hasattr(self.original_games, 'owner'):
            self.original_games.owner['chat'] = self.owner_chat
        self.inventory = inventory or windows_inventory
        self._injected_inventory = inventory is not None
        self._worktree_provider = worktree_provider or (lambda: worktrees(self.repo))
        self._worktree_roots, self._worktrees_checked = [self.repo], 0
        self._load_external_specs()
        self.spawner, self.creation = spawner or subprocess.Popen, creation or process_created
        self.terminator, self.health = terminator or terminate_checked, health or self._capture_health
        self.records, self.jobs, self.processes, self.listeners = {}, {}, {}, []
        self._handles, self._actions, self._specs, self._ports = {}, {}, {}, set()
        self._lock, self._refresh_lock = threading.RLock(), threading.Lock()
        self._operation_lock = threading.RLock()
        self._confirmations = {}
        if shared_services is None and inventory is None:
            try:
                from shared_services import SharedServices
                shared_services = SharedServices(self.repo)
            except ImportError:
                pass
        self.shared_services = shared_services
        self._closed, self._wake = threading.Event(), threading.Event()
        self._snapshot = {'version': 1, 'capture_port': self.capture_port, 'control_port': self.control_port,
                          'categories': copy.deepcopy(CATEGORIES), 'services': [], 'updated_at': None,
                          'refreshing': True, 'error': ''}
        self._load_records()
        self._render([], {})
        if start_background:
            self._worker = threading.Thread(target=self._poll, name='service-console-inventory', daemon=True)
            self._worker.start()

    def close(self):
        """关闭管理轮询不等于停止业务服务。"""
        self._closed.set()
        self._wake.set()

    def _poll(self):
        while not self._closed.is_set():
            self.refresh()
            self._wake.wait(3)
            self._wake.clear()

    def _load_records(self):
        for folder in self.home.glob('run-*'):
            try:
                record = read_json(self.home, folder.name + '/ownership.json', 128 * 1024)
                if record.get('id') == folder.name[4:] and record.get('service_id') in self.registry:
                    self.records[record['id']] = record
            except (OSError, ValueError, KeyError, TypeError):
                continue

    def _save(self, record):
        folder = self.home / ('run-' + record['id'])
        folder.mkdir(exist_ok=True)
        path = folder / 'ownership.json'
        pending = folder / 'ownership.pending'
        with self._lock:
            pending.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
            pending.replace(path)

    def _controller_record(self):
        actual = self.processes.get(os.getpid())
        if not actual or not any(v['pid'] == os.getpid() and v['port'] == self.control_port for v in self.listeners):
            return
        record = {'chat': self.owner_chat, 'pid': os.getpid(), 'created': actual['created'],
                  'command': argv_of(actual.get('command')), 'cwd': str(self.repo),
                  'port': self.control_port, 'service': 'service-console', 'updated_at': now()}
        path = self.home / ('controller-' + str(os.getpid()) + '.json')
        if not path.exists():
            path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')

    def snapshot(self):
        with self._lock:
            return copy.deepcopy(self._snapshot)

    def _available(self, spec):
        kind = spec['kind']
        if spec.get('external_registered'):
            try:
                self._external_start_spec(spec)
                return ''
            except (OSError, ValueError, TypeError, KeyError) as error:
                return str(error) if isinstance(error, ValueError) else '缺少已核验的外部启动配置或运行文件，不能重新启动。'
        if kind in ('postgres', 'docker', 'readonly'):
            return spec.get('reason', '该服务仅支持只读查看。')
        if not self.owner_chat:
            return '缺少当前聊天标识，不能创建无法归属的服务。'
        if kind == 'original':
            return '' if spec.get('can_preview') else spec.get('reason') or '该产物缺少可核验的试玩入口。'
        if kind in ('capture', 'quality'):
            path = self.repo / 'other/capture/response-capture' / ('app.py' if kind == 'capture' else 'quality_service.py')
            return '' if path.is_file() else '缺少启动入口：' + str(path)
        if kind == 'group':
            return ''
        if not shutil.which('node'):
            return '未找到 Node.js。'
        entry = self.repo / ('other/tooling/feature-maintenance/watch.mjs' if kind == 'watch' else 'other/tooling/run.mjs')
        if not entry.is_file():
            return '缺少启动入口：' + str(entry)
        if kind in ('demo', 'compute') and not spec.get('registered'):
            return '目录未登记有效启动配置。'
        if kind in ('demo', 'compute') and not Path(spec['directory']).is_dir():
            return '已登记但缺少游戏目录。'
        if kind == 'compute':
            code = spec['code']
            for path in (self.repo / 'games' / code / 'instance/config' / (code + '.json'),
                         self.repo / 'gateway/instance/data/game-service-keys' / (code + '.key')):
                if not path.is_file():
                    return '缺少计算服务配置：' + str(path.relative_to(self.repo))
        return ''

    def _choose_port(self, preferred):
        if preferred is None:
            return None
        occupied = {v['port'] for v in self.listeners} | self._ports | {self.control_port}
        with socket.socket() as sock:
            candidate = int(preferred) if int(preferred) not in occupied else 0
            try:
                sock.bind(('127.0.0.1', candidate))
            except OSError:
                sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        self._ports.add(port)
        return port

    def _command(self, spec, port):
        if spec.get('external_registered'):
            return self._external_command(spec, port)
        env = dict(os.environ, CODEX_THREAD_ID=self.owner_chat, PYTHONUTF8='1')
        kind = spec['kind']
        base = self.repo / 'other/capture/response-capture'
        if kind in ('capture', 'quality'):
            env['PYTHONPATH'] = str(base / '.venv/Lib/site-packages')
            env['CAPTURE_FEATURE_MAINTENANCE'] = '0'
            command = [getattr(sys, '_base_executable', sys.executable), str(base / ('app.py' if kind == 'capture' else 'quality_service.py'))]
            command += ['--port', str(port)]
            if kind == 'quality':
                command += ['--capture-port', str(self.capture_port)]
            if kind == 'capture' and self.previous_port:
                command += ['--previous-port', str(self.previous_port)]
        elif kind == 'watch':
            command = [shutil.which('node'), str(self.repo / 'other/tooling/feature-maintenance/watch.mjs'),
                       '--capture-url', 'http://127.0.0.1:' + str(self.capture_port), '--interval-ms', '10000', '--parent-pipe']
        elif spec['id'] == 'advanced.buffalo':
            command = [shutil.which('node'), str(base / 'controlled_node.mjs'), 'run', 'cli', 'buffalo']
            env['BUFFALO_PORT'] = str(port)
        else:
            command = [shutil.which('node'), str(base / 'controlled_node.mjs'), 'source']
            if kind == 'compute':
                command += ['game', spec['code'], '--port', str(port), '--host', '127.0.0.1']
            else:
                command += [spec['action']]
                if kind == 'demo':
                    command += ['--port', str(port)]
            if spec.get('port_env'):
                env[spec['port_env']] = str(port)
                env[spec['port_env'].replace('_PORT', '_HOST')] = '127.0.0.1'
        return command, env

    def _start_legacy(self, identifier, planned_port=None):
        with self._lock:
            spec = self.registry.get(identifier) or self._specs.get(identifier)
            if not spec:
                raise ServiceError('未知服务 ID。', 404)
            reason = self._available(spec)
            if reason:
                raise ServiceError(reason, 409)
            if any(r.get('service_id') == identifier and r.get('state') == 'starting' for r in self.records.values()):
                raise ServiceError('该服务正在启动，请等待状态更新。')
            if spec['kind'] == 'original':
                result = self.original_games.preview(spec['artifact_id'])
                self._wake.set()
                return dict(result, id=identifier, message=result.get('message', '正在启动原版试玩。'))
            run_id = uuid.uuid4().hex
            folder = self.home / ('run-' + run_id)
            folder.mkdir()
            record = {'id': run_id, 'service_id': identifier, 'chat': self.owner_chat, 'cwd': spec.get('worktree') if spec.get('external_registered') else str(self.repo),
                      'pid': None, 'created': None, 'command': [], 'port': planned_port if planned_port is not None else self._choose_port(spec.get('default_port')),
                      'state': 'starting', 'started_at': now(), 'log': str(folder / 'service.log'),
                      'ownership_file': str(folder / 'ownership.json'), 'children': []}
            if spec['kind'] in ('node', 'demo', 'compute'):
                record.update(control_nonce=uuid.uuid4().hex, control_directory=str(folder))
            self.records[run_id] = record
            self._save(record)
            worker = threading.Thread(target=self._start_group if spec['kind'] == 'group' else self._spawn,
                                      args=(spec, record), name='service-start-' + run_id[:8], daemon=True)
            self.jobs[run_id] = worker
            worker.start()
            self._wake.set()
            return {'ok': True, 'id': identifier, 'run_id': run_id, 'state': 'starting', 'message': '正在启动，进度会自动更新。'}

    def _spawn(self, spec, record):
        try:
            command, env = self._command(spec, record['port'])
            if record.get('control_nonce'):
                env.update(GTT_CAPTURE_CONTROL_DIR=record['control_directory'], GTT_CAPTURE_CONTROL_NONCE=record['control_nonce'])
            with Path(record['log']).open('ab') as stream:
                process = self.spawner(command, cwd=record['cwd'], env=env, stdin=subprocess.PIPE if spec['kind'] in ('watch', 'node', 'demo', 'compute') else subprocess.DEVNULL,
                                       stdout=stream, stderr=subprocess.STDOUT, creationflags=NO_WINDOW, shell=False)
            record.update(pid=process.pid, created=self.creation(process), command=command,
                          command_line=subprocess.list2cmdline(command))
            self._handles[record['id']] = process
            if not record['created']:
                raise ServiceError('未能记录进程创建时间，禁止后续停止。')
            if spec['id'] == 'fixed.capture':
                self.capture_port = record['port']
            self._save(record)
        except Exception as error:
            record.update(state='error', message=redact(str(error)))
            self._save(record)
        finally:
            self._wake.set()

    def _start_group(self, spec, record):
        # 每次只启动一个构建流水线，避免同时改写当前工作区编译目录。
        try:
            for entry in self.registry.values():
                if entry['kind'] != 'compute' or record.get('state') == 'stopping':
                    continue
                self.refresh()
                row = next((r for r in self.snapshot()['services'] if r['id'] == entry['id']), {})
                if row.get('running_count') or not row.get('can_start'):
                    continue
                result = self.start(entry['id'])
                record['children'].append(result['run_id'])
                self._save(record)
                self.jobs[result['run_id']].join()
                deadline = time.monotonic() + 180
                while time.monotonic() < deadline:
                    self.refresh()
                    state = self.records[result['run_id']]['state']
                    if state != 'starting' or record.get('state') == 'stopping':
                        break
                    self._closed.wait(.5)
                if state == 'starting':
                    raise ServiceError('某款计算服务尚未就绪，已暂停后续批量启动。')
            if record.get('state') != 'stopping':
                record['state'] = 'running'
        except Exception as error:
            record.update(state='error', message=redact(str(error)))
        finally:
            self._save(record)
            self._wake.set()

    def _owned(self, record, actual):
        if not actual or not self.owner_chat or record.get('chat') != self.owner_chat:
            return False
        try:
            cwd = Path(record.get('cwd', '')).resolve()
            actual_cwd = actual.get('cwd')
            return (cwd in [self.repo, *[Path(tree).resolve() for tree in self._worktree_roots]] and (not actual_cwd or Path(actual_cwd).resolve() == cwd)
                    and record.get('pid') == actual['pid'] and bool(record.get('created'))
                    and same_creation(record['created'], actual.get('created'))
                    and bool(record.get('command')) and command_matches(record['command'], actual.get('command')))
        except (ValueError, TypeError, OSError):
            return False

    def _descendants(self, pid):
        result, pending = [], [pid]
        while pending:
            parent = pending.pop()
            for process in self.processes.values():
                parent_process = self.processes.get(parent, {})
                try:
                    after_parent = datetime.fromisoformat(process.get('created', '')) >= datetime.fromisoformat(parent_process.get('created', ''))
                except (ValueError, TypeError):
                    after_parent = False
                if process.get('parent') == parent and after_parent and process['pid'] != pid and process not in result:
                    result.append(process)
                    pending.append(process['pid'])
        return result

    def _capture_health(self, record):
        connection = HTTPConnection('127.0.0.1', int(record['port']), timeout=.65)
        try:
            connection.request('GET', '/api/status')
            response = connection.getresponse()
            result = json.loads(response.read(65536))
            return result if response.status == 200 and result.get('service') == 'response-capture' else {}
        except (OSError, ValueError):
            return {}
        finally:
            connection.close()

    def _exited_state(self, record):
        state = record['state']
        if state != 'starting':
            return 'error' if state == 'error' else 'stopped'
        process = self._handles.get(record['id'])
        if process is not None and hasattr(process, 'poll') and process.poll() is None:
            return 'starting'  # 进程创建晚于这份系统快照。
        from original_games import plain_file
        try:
            path = plain_file(self.home, 'run-' + record['id'] + '/service.log')
            with path.open('rb') as stream:
                stream.seek(max(0, path.stat().st_size - 8192))
                lines = stream.read().decode('utf-8', errors='replace').splitlines()
        except (OSError, ValueError):
            lines = []
        for line in reversed(lines):
            if line.startswith('启动流水线失败：'):
                record['message'] = redact(line[:500])
                break
            if process is None and ' listening on ' in line:
                return 'stopped'  # 旧版启动记录可能未保存曾经就绪的状态。
        return 'error'

    def _record_instance(self, record):
        actual = self.processes.get(record.get('pid'))
        owned = self._owned(record, actual)
        spec = self.registry[record['service_id']]
        descendants = self._descendants(record['pid']) if owned else []
        pids = {record.get('pid')} | {v['pid'] for v in descendants}
        listening = any(v['pid'] in pids and v['port'] == record.get('port') for v in self.listeners)
        state = record.get('state', 'stopped')
        if actual and not owned:
            state = 'unknown'
        elif not actual and record.get('pid') and hasattr(self, '_latest_inventory'):
            state = self._exited_state(record)
        elif owned and state != 'stopping':
            state = 'running' if (not record.get('port') or listening) else 'starting'
        can_stop = owned and state in ('running', 'starting')
        reason = record.get('message', '')
        if state == 'error' and not reason:
            reason = '启动进程已退出，未确认服务就绪；请查看日志。'
        if actual and not owned:
            reason = '实例身份尚未核验完整，暂不可执行关闭。'
        if owned and spec['kind'] == 'capture':
            health = self.health(record) if listening else {}
            shutdown = health.get('capabilities', {}).get('shutdown') is True or health.get('can_shutdown') is True
            can_stop = bool(shutdown and health.get('pid') == record['pid'] and health.get('chat') == self.owner_chat)
            if not can_stop:
                reason = '此抓取实例尚未提供可核验的正常退出接口；请先在对应页面停止并保存。'
            elif health.get('active_sessions'):
                can_stop, reason = False, '仍有活动抓取；请先在游戏行停止并保存。'
        if owned and spec['kind'] == 'watch' and record['id'] not in self._handles:
            can_stop, reason = False, '监督器来自先前控制台，无法取得其正常退出通道。'
        if owned and spec['kind'] in ('node', 'demo', 'compute') and not any(str(v).endswith('controlled_node.mjs') for v in record.get('command', [])):
            can_stop, reason = False, '该 Node 实例缺少正常退出通道；强制关闭前需要确认风险。'
        elif owned and spec['kind'] in ('node', 'demo', 'compute') and record['id'] not in self._handles and not self._persistent_control(record):
            can_stop, reason = False, '该 Node 实例来自先前控制台，无法取得正常退出通道；强制关闭前需要确认风险。'
        if state in ('stopped', 'error'):
            self._ports.discard(record.get('port'))
        previous = record['state']
        record['state'] = state
        if previous != state and record['id'] in self._handles and state in ('running', 'error', 'stopped'):
            self._save(record)
        return dict(id='run.' + record['id'], name=spec['name'], pid=record.get('pid'), port=record.get('port'),
                    status=state, owned=owned, can_stop=can_stop, can_start=False, reason=reason,
                    cwd=record.get('cwd'), created=record.get('created'), open_url=self._url(spec, record.get('port')) if listening else '',
                    lobby_url=('http://127.0.0.1:' + str(record['port']) + '/demo/?lang=zh#games') if listening and spec['id'] == 'demo.mahjong-ways2' else '',
                    endpoint_url=('http://127.0.0.1:' + str(record['port']) + '/') if listening and spec['kind'] == 'compute' else '',
                    endpoint_text='', can_logs=True, logs_available=True, running_count=int(state == 'running'))

    @staticmethod
    def _url(spec, port):
        if port and spec['kind'] not in ('compute', 'postgres', 'docker') and spec.get('action') != 'buffalo':
            return 'http://127.0.0.1:' + str(port) + '/'
        return ''

    def _classify(self, process):
        args = argv_of(process.get('command'))
        text = normalized(' '.join(args))
        name = normalized(process.get('name') or Path(process.get('executable') or '').name)
        if name == 'postgres.exe':
            return 'advanced.postgres'
        if name in ('dockerd.exe', 'com.docker.backend.exe', 'docker desktop.exe'):
            return 'advanced.docker'
        # 捕获其他工作区时仅展示路径明确的入口，绝不因此获得所有权。
        if any(normalized(a) == normalized(Path(tree) / 'other/capture/response-capture/app.py') for tree in self._worktree_roots for a in args):
            return 'fixed.capture'
        if 'app.py' in args:
            parent = self.processes.get(process.get('parent'), {})
            ancestor = [normalized(parent.get('executable') or '')] + [normalized(a) for a in argv_of(parent.get('command'))[:1]]
            try:
                after_parent = datetime.fromisoformat(process['created']) >= datetime.fromisoformat(parent['created'])
            except (ValueError, TypeError, KeyError):
                after_parent = False
            if after_parent and any(normalized(Path(tree) / 'other/capture/response-capture/.venv/Scripts/python.exe') in ancestor for tree in self._worktree_roots):
                return 'fixed.capture'
        roots = [normalized(tree) for tree in self._worktree_roots]
        if not any(normalized(a) == root or normalized(a).startswith(root + '/') for root in roots for a in args):
            return None
        if 'feature-maintenance/watch.mjs' in text:
            return 'fixed.watch'
        if 'quality_service.py' in text or ('service_launcher.py' in text and 'quality' in args):
            return 'advanced.quality'
        for action, identifier in [('gateway', 'fixed.gateway'), ('admin', 'fixed.admin'), ('platform', 'fixed.mock'),
                                   ('mock', 'fixed.mock'), ('rtp-worker', 'fixed.rtp'), ('buffalo', 'advanced.buffalo'), ('games', 'advanced.games-batch')]:
            if action in args and any(a.endswith(('.mjs', 'cli.js')) for a in args):
                return identifier
        for spec in self.registry.values():
            code = spec.get('code') or ('game-api' if spec['id'] == 'advanced.game-api' else None)
            if not code:
                continue
            if 'game' in args and (code in args or '--game-id=' + code in args):
                return 'compute.' + code
            if code in args or any(normalized(a).endswith('/services/' + code) or normalized(a) in (normalized(spec.get('directory', '')), normalized(spec.get('directory', '')) + '/instance') for a in args):
                return 'demo.' + code if code != 'game-api' else 'advanced.game-api'
        return None

    def _external_demo(self, process):
        """只读发现合法工作区的明确试玩入口，不把目录存在当作运行。"""
        args = argv_of(process.get('command'))
        executable = normalized(process.get('executable') or (args[0] if args else '')).rsplit('/', 1)[-1]
        if executable not in ('node', 'node.exe'):
            return None
        for tree in self._worktree_roots:
            tree = Path(tree).absolute()
            directory = None
            # 直接 CLI 必须是 service 动作，并且只提供一个绝对 service-dir。
            runtime_entry = normalized(tree / 'other/runtime/server/dist/cli.js')
            entries = [i for i, arg in enumerate(args[:-1]) if normalized(arg) in ('dist/cli.js', runtime_entry) and args[i + 1] == 'service']
            if entries and args.count('--service-dir') == 1:
                index = args.index('--service-dir')
                if index + 1 < len(args) and Path(args[index + 1]).is_absolute():
                    directory = Path(args[index + 1]).absolute()
            # 源码试玩入口以脚本的完整路径和单款游戏参数确定所属工作区。
            source = normalized(tree / 'other/tooling/start-source.mjs')
            if directory is None:
                entries = [i for i, arg in enumerate(args[:-1]) if normalized(arg) == source]
                if len(entries) == 1 and re.fullmatch(r'[a-z0-9-]{1,80}', args[entries[0] + 1]):
                    directory = tree / 'games' / args[entries[0] + 1] / 'instance'
            if directory is None:
                continue
            try:
                relative = directory.relative_to(tree)
                if (len(relative.parts) != 3 or relative.parts[0] != 'games' or relative.parts[2] != 'instance'
                        or not re.fullmatch(r'[a-z0-9-]{1,80}', relative.parts[1])):
                    continue
                code = relative.parts[1]
                spec = read_json(tree, relative / 'service.json', 128 * 1024)
                if spec.get('id') != code or not isinstance(spec.get('games'), list) or code not in spec['games']:
                    continue
                # 当前工作区的既有 20 项继续由固定登记展示。
                if tree.resolve() == self.repo and 'demo.' + code in self.registry:
                    continue
                suffix = hashlib.sha256(normalized(tree).encode('utf-8')).hexdigest()[:12]
                name = spec.get('title') or spec.get('name') or code
                return {'id': 'worktree-demo.' + suffix + '.' + code, 'name': str(name) + ' · 外部实例',
                        'category': 'game-demos', 'game_code': code, 'kind': 'demo',
                        'description': '其他工作区的试玩服务；所属工作区：' + str(tree),
                        'default_port': spec.get('port'), 'worktree': str(tree), 'directory': str(directory)}
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return None

    def refresh(self, wait=False):
        if not self._refresh_lock.acquire(blocking=wait):
            return self.snapshot()
        try:
            data = self.inventory()
            processes = data.get('processes', [])
            if isinstance(processes, dict):
                processes = list(processes.values())
            self.processes = {p['pid']: p for p in processes}
            self.listeners = data.get('listeners', [])
            self._latest_inventory = data
            self._control_records_cache = None
            if time.monotonic() - self._worktrees_checked >= 30:
                try:
                    self._worktree_roots = [Path(p).absolute() for p in self._worktree_provider()]
                except (OSError, ValueError, subprocess.SubprocessError):
                    self._worktree_roots = [self.repo]
                self._worktrees_checked = time.monotonic()
            self._controller_record()
            catalog = self.original_games.catalog() if self.original_games else {'games': []}
            self._render(catalog.get('games', []), data)
        except Exception as error:
            with self._lock:
                self._snapshot.update(refreshing=False, error=redact(str(error)))
                # 失去实时核验能力后，不允许使用旧缓存停止。
                for row in self._snapshot['services']:
                    row['can_stop'] = False
                    for child in row.get('instances', []):
                        child['can_stop'] = False
        finally:
            self._refresh_lock.release()
        return self.snapshot()

    def _render(self, catalog, inventory):
        rows = {}
        actions = {}
        for spec in self.registry.values():
            observed = self.processes.get(spec.get('observed_pid'))
            if str(spec['id']).startswith('reopen.capture.') and observed and spec.get('observed_created') and same_creation(observed.get('created'), spec['observed_created']):
                continue
            reason = self._available(spec)
            rows[spec['id']] = {**{k: spec.get(k) for k in ('id', 'name', 'category', 'description', 'default_port')},
                               'game_code': spec.get('code') or spec.get('game_code', ''), 'status': 'stopped', 'running_count': 0,
                               'pid': None, 'port': None, 'can_start': not bool(reason), 'can_stop': False,
                               'reason': reason, 'open_url': '', 'endpoint_url': '', 'endpoint_text': '', 'instances': [], 'can_logs': False, 'logs_available': False}
            if str(spec['id']).startswith('worktree-demo.'):
                rows[spec['id']]['description'] = '其他工作区的试玩服务；所属工作区：' + str(spec.get('worktree', ''))
        seen = set()
        for record in list(self.records.values()):
            if record['service_id'] not in rows or self.registry[record['service_id']]['kind'] == 'group':
                continue
            instance = self._record_instance(record)
            rows[record['service_id']]['instances'].append(instance)
            actions[instance['id']] = record
            if self._valid_process(record):
                seen.add(record.get('pid'))
                seen.update(v['pid'] for v in self._descendants(record['pid']))
        self._preview_rows(rows, actions, catalog)
        for row in rows.values():
            if row.get('category') == 'original-previews':
                seen.update(v['pid'] for v in row['instances'] if v['status'] in ('running', 'starting'))
        for process in self.processes.values():
            if process['pid'] in seen:
                continue
            identifier = self._classify(process)
            spec = self.registry.get(identifier)
            if not identifier:
                spec = self._external_demo(process)
                if not spec:
                    continue
                identifier = spec['id']
            ports = sorted({v['port'] for v in self.listeners if v['pid'] == process['pid']})
            # 有端口的入口包装进程不重复计为运行中的服务。
            if not ports and (spec.get('default_port') or identifier.startswith('worktree-demo.')):
                continue
            if identifier not in rows:
                rows[identifier] = dict(spec, status='running', running_count=0, pid=None, port=None,
                                        can_start=False, can_stop=False, owned=False,
                                        reason='其他工作区的现有试玩；操作前会核验实例身份并说明影响。',
                                        open_url='', endpoint_url='', endpoint_text='', instances=[],
                                        can_logs=False, logs_available=False)
            port = ports[0] if ports else None
            if process.get('created') and process.get('command'):
                self._remember_external(spec, process, port)
                if spec['id'] in self.registry:
                    spec = self.registry[spec['id']]
                    if spec.get('external_registered'):
                        rows[identifier]['can_start'] = not bool(self._available(spec))
            instance = dict(id='external.' + str(process['pid']), name=rows[identifier]['name'], pid=process['pid'], port=port,
                            status='running', owned=False, can_start=False, can_stop=False, running_count=1,
                            reason='既有或其他窗口实例，操作前需核验进程身份与影响范围。',
                            created=process.get('created'), cwd=spec.get('directory', ''), open_url=self._url(spec, port),
                            lobby_url=('http://127.0.0.1:' + str(port) + '/demo/?lang=zh#games') if port and spec['id'] == 'demo.mahjong-ways2' else '',
                            endpoint_url=('http://127.0.0.1:' + str(port) + '/') if port and spec['kind'] == 'compute' else '',
                            endpoint_text=('127.0.0.1:' + str(port)) if port and identifier == 'advanced.postgres' else '',
                            can_logs=False, logs_available=False)
            rows[identifier]['instances'].append(instance)
            if identifier not in ('advanced.postgres', 'advanced.docker') and process.get('created') and process.get('command'):
                actions[instance['id']] = {'id': instance['id'], 'service_id': identifier, 'external': True,
                    'pid': process['pid'], 'created': process['created'], 'command': argv_of(process['command']),
                    'cwd': spec.get('directory') or self._process_directory(process), 'port': port, 'chat': '',
                    'kind': spec.get('kind', self.registry.get(identifier, {}).get('kind', 'node'))}
                self._specs[identifier] = spec
        for record in self.records.values():
            if record['service_id'] != 'advanced.games-batch':
                continue
            children = [self.records[c] for c in record.get('children', []) if c in self.records]
            live = [c for c in children if c.get('state') in ('starting', 'running', 'stopping')]
            if record['state'] == 'stopping' and not live:
                record['state'] = 'stopped'
                self._save(record)
            own = record.get('chat') == self.owner_chat
            instance = dict(id='run.' + record['id'], name='本控制台计算服务组', pid=None, port=None, status=record['state'] if live or record['state'] in ('starting', 'error') else 'stopped',
                            owned=own, can_stop=own and bool(live) and record['state'] != 'stopping', can_start=False, running_count=sum(c['state'] == 'running' for c in live), reason=record.get('message', ''),
                            can_logs=True, logs_available=True, open_url='')
            rows['advanced.games-batch']['instances'].append(instance)
            actions[instance['id']] = record
        self._expose_confirmed_operations(rows, actions)
        for row in rows.values():
            if row['id'] in ('advanced.postgres', 'advanced.docker') and self.shared_services:
                continue
            instances = row['instances']
            running = [v for v in instances if v['status'] == 'running']
            active = [v for v in instances if v['status'] in ('starting', 'running', 'stopping')]
            row['running_count'] = sum(v.get('running_count', int(v['status'] == 'running')) for v in instances)
            row['status'] = 'running' if running else next((s for s in ('starting', 'stopping', 'error', 'unknown') if any(v['status'] == s for v in instances)), 'stopped')
            row['can_stop'] = len(active) == 1 and active[0]['can_stop']
            row['can_logs'] = row['logs_available'] = any(v['can_logs'] for v in instances)
            if len(active) == 1:
                row.update(pid=active[0]['pid'], port=active[0]['port'], open_url=active[0].get('open_url', ''),
                           lobby_url=active[0].get('lobby_url', ''),
                           endpoint_url=active[0].get('endpoint_url', ''), endpoint_text=active[0].get('endpoint_text', ''))
                if not row['reason']:
                    row['reason'] = active[0].get('reason', '')
            if any(v['status'] == 'starting' for v in instances):
                row['can_start'] = False
            if not active and instances and not row['reason']:
                row['reason'] = instances[-1].get('reason', '')
            if row['id'] == 'fixed.capture':
                # 固定抓取入口用于控制当前目标，其他实例由列表单独显示。
                selected = next((v for v in active if v.get('port') == self.capture_port), None)
                row.update(can_start=not bool(selected), can_stop=bool(selected and selected['can_stop']),
                           port=self.capture_port, pid=selected.get('pid') if selected else None,
                           status=selected['status'] if selected else ('error' if any(v['status'] == 'error' and v.get('port') == self.capture_port for v in instances) else 'stopped'),
                           running_count=int(bool(selected and selected['status'] == 'running')),
                           open_url='http://127.0.0.1:' + str(self.capture_port) + '/' if selected else '')
                if selected:
                    row['reason'] = selected.get('reason', '')
                for child in instances:
                    rowspec = dict(child, category='capture-instances', description='抓取服务的独立实例。', default_port=None, instances=[])
                    rowspec['name'] = '抓取实例 ' + str(child.get('port') or child.get('pid') or '')
                    saved = next((v for v in self.registry.values() if str(v['id']).startswith('reopen.capture.') and v.get('observed_pid') == child.get('pid') and v.get('observed_created') == child.get('created')), None)
                    if saved:
                        rowspec.update(id=saved['id'], can_start=not bool(self._available(saved)), default_port=saved.get('default_port'))
                    actions[rowspec['id']] = actions.get(child['id'])
                    # 追加在循环外，避免改变字典大小。
                    self._capture_rows = getattr(self, '_capture_rows', []) + [rowspec]
                row['instances'] = [v for v in instances if v.get('port') == self.capture_port]
        services = list(rows.values()) + getattr(self, '_capture_rows', [])
        self._capture_rows = []
        with self._lock:
            self._actions = actions
            self._snapshot.update(services=services, capture_port=self.capture_port, updated_at=now(), refreshing=False, error='')

    def _preview_rows(self, rows, actions, catalog):
        self._specs = {}
        previews = []
        home = self.repo / 'other/diagnostics/response-capture-previews'
        for folder in home.glob('*') if home.is_dir() else []:
            try:
                previews.append(read_json(home, folder.name + '/ownership.json', 128 * 1024))
            except (OSError, ValueError, KeyError, TypeError):
                continue
        catalog = list(catalog)
        known = {item['id'] for item in catalog}
        for job in previews:
            artifact = job.get('artifact_id')
            if isinstance(artifact, str) and re.fullmatch(r'[0-9a-f]{32}', artifact) and artifact not in known:
                known.add(artifact)
                catalog.append({'id': artifact, 'title': '原版产物缺失', 'name': Path(job.get('cwd', '')).name,
                                'directory': job.get('cwd', ''), 'game_ids': [], 'can_preview': False, 'missing': True,
                                'reason': '产物目录或身份资料缺失；保留历史实例，无法重新启动或核验目录。'})
        for item in catalog:
            identifier = 'original.' + item['id']
            spec = dict(item, id=identifier, artifact_id=item['id'], kind='original')
            self._specs[identifier] = spec
            names = []
            for site in item.get('game_ids', []):
                target = enrich_target(getattr(self.original_games, 'captures', self.repo / 'other/capture/response-capture/captures'), {'site': site})
                label = target.get('zh') or target.get('name')
                if label and label not in names:
                    names.append(label)
            title = ' / '.join(names) or (str(item.get('brand') or '') + ' / ' + str(item.get('external_id') or '')).strip(' /') or item.get('title') or item.get('name')
            batch = re.search(r'\d{8}-\d{6}', str(item.get('name') or item.get('directory') or ''))
            if batch:
                title += ' · ' + batch[0]
            row = dict(id=identifier, name=title, category='original-previews',
                       description='已生成的原版产物；每个启动实例独立显示。', default_port=None,
                       status='stopped', running_count=0, pid=None, port=None, can_start=not bool(self._available(spec)),
                       can_stop=False, reason=item.get('reason', ''), open_url='', instances=[], can_logs=False, logs_available=False,
                       directory=item.get('directory'), artifact_id=item['id'], game_ids=item.get('game_ids', []))
            rows[identifier] = row
            for job in [p for p in previews if p.get('artifact_id') == item['id']]:
                pid = job.get('service_pid') or job.get('pid')
                actual = self.processes.get(pid)
                created = job.get('service_created') or job.get('created')
                alive = actual and created and same_creation(created, actual.get('created'))
                port = job.get('port')
                listening = alive and any(v['pid'] == pid and v['port'] == port for v in self.listeners)
                owned = False
                target = dict(job, id=job.get('run_id'), service_id=identifier, pid=pid, created=created,
                              log=str(Path(job.get('record', home / 'unknown')).parent / 'launcher.log'), original=True,
                              original_record=job)
                if alive and not item.get('missing') and job.get('chat') == self.owner_chat and Path(job.get('cwd', '')).resolve() == Path(item.get('directory', '')).resolve():
                    if not job.get('service_pid'):
                        owned = bool(job.get('command')) and command_matches(job['command'], actual.get('command'))
                    else:
                        try:
                            child = read_json(Path(job['record']).parent, 'service/ownership.json', 128 * 1024)
                            parent = self.processes.get(job['pid'])
                            command = child.get('command')
                            owned = (child.get('pid') == pid and child.get('chat') == self.owner_chat
                                     and same_creation(child.get('created'), created) and actual.get('parent') == job['pid']
                                     and Path(child.get('client', '')).resolve() == (Path(item['directory']) / 'client').resolve()
                                     and Path(child.get('repo', '')).resolve() == Path(item.get('worktree', '')).resolve()
                                     and Path(child.get('cwd', '')).resolve() == (Path(item.get('worktree', '')) / 'other/runtime/server').resolve()
                                     and datetime.fromisoformat(created) >= datetime.fromisoformat(job['created'])
                                     and bool(command) and command_matches(command, actual.get('command'))
                                     and (not parent or (same_creation(parent.get('created'), job.get('created')) and command_matches(job['command'], parent.get('command')))))
                            if owned:
                                target['command'] = argv_of(actual['command'])
                        except (OSError, ValueError, TypeError, KeyError):
                            owned = False
                state = 'running' if listening else ('error' if job.get('state') == 'error' else ('starting' if alive and job.get('state') == 'starting' else 'stopped'))
                can_stop = bool(owned and alive)
                reason = '' if owned else '等待核验启动记录与实际进程身份。'
                if can_stop and job.get('mode') == 'adapter':
                    control = getattr(self.original_games, 'adapter_control', None)
                    try:
                        available = callable(control) and bool(control(job))
                    except (OSError, ValueError, TypeError, KeyError):
                        available = False
                    if not available:
                        can_stop, reason = False, '此旧原版适配实例没有正常退出接口；强制关闭可能中断钱包写入，需要确认风险。'
                if state == 'error':
                    reason = redact(job.get('message') or job.get('error') or '原版试玩启动失败，请查看日志。')
                instance = dict(id='preview.' + str(job.get('run_id')), name=row['name'], pid=pid, port=port, status=state,
                                running_count=int(state == 'running'), owned=bool(owned), can_stop=can_stop, can_start=False,
                                reason=reason, cwd=job.get('cwd'), created=created,
                                open_url=job.get('url', '') if listening else '', can_logs=True, logs_available=True)
                row['instances'].append(instance)
                actions[instance['id']] = target

    def _resolve_action(self, identifier):
        if identifier in self._actions and self._actions[identifier]:
            return self._actions[identifier]
        row = next((v for v in self._snapshot['services'] if v['id'] == identifier), None)
        if row:
            active = [v for v in row.get('instances', []) if v['status'] in ('starting', 'running', 'stopping')]
            if identifier == 'fixed.capture':
                active = [v for v in active if v.get('port') == self.capture_port]
            if len(active) == 1:
                result = self._actions.get(active[0]['id'])
                if result:
                    return result
        raise ServiceError('请选择可验证归属的单个实例。', 403)

    def _persistent_control(self, record):
        if not record.get('control_nonce'):
            return None
        try:
            from service_control import read_control
            return read_control(record, self.home, self.owner_chat)
        except (ImportError, OSError, ValueError, KeyError, TypeError):
            return None

    def _stop_legacy(self, identifier):
        self.refresh()
        if self._snapshot.get('error'):
            raise ServiceError('实时进程核验失败，未停止任何服务。', 503)
        record = self._resolve_action(identifier)
        if record.get('service_id') == 'advanced.games-batch':
            if record.get('chat') != self.owner_chat:
                raise ServiceError('批量组不属于当前聊天。', 403)
            record['state'] = 'stopping'
            for child in record.get('children', []):
                if self.records.get(child, {}).get('state') in ('starting', 'running'):
                    self.stop('run.' + child)
            self._save(record)
            return {'ok': True, 'id': identifier, 'state': 'stopping', 'message': '已请求本组新建实例正常退出，等待实际进程结束。'}
        instance = next((v for row in self._snapshot['services'] for v in row.get('instances', []) if self._actions.get(v['id']) is record), None)
        if not instance or not instance.get('can_stop'):
            raise ServiceError(instance.get('reason', '该实例不能安全停止。') if instance else '该实例不可停止。', 403)
        actual = self.processes.get(record.get('pid'))
        if not actual or not same_creation(record.get('created'), actual.get('created')) or not command_matches(record.get('command'), actual.get('command')):
            raise ServiceError('进程身份已变化，拒绝停止。', 403)
        kind = 'original' if record.get('original') else self.registry[record['service_id']]['kind']
        if kind == 'capture':
            self._shutdown_capture(record)
        elif kind == 'original' and record.get('mode') == 'adapter':
            self.original_games.shutdown_adapter(record['original_record'])
        elif kind in ('node', 'demo', 'compute') and self._persistent_control(record):
            from service_control import request_stop
            probe = (lambda pid: self.processes.get(pid)) if self._injected_inventory else None
            request_stop(record, self.home, self.owner_chat, inspector=probe)
        elif kind in ('watch', 'node', 'demo', 'compute'):
            process = self._handles.get(record['id'])
            if not process or not process.stdin:
                raise ServiceError('无法取得该服务的正常退出通道。')
            process.stdin.write(b'stop\n')
            process.stdin.flush()
        else:
            descendants = self._descendants(record['pid'])
            checked_pids = {record['pid']} | {v['pid'] for v in descendants}
            unresolved = [v for v in self.processes.values() if v.get('parent') in checked_pids and v['pid'] not in checked_pids]
            if unresolved:
                raise ServiceError('存在创建时间早于父进程或缺少身份资料的子进程；无法核验进程树，未停止实例。', 403)
            # 只处理本次核验根进程的真实后代；每个句柄再次核验创建时间。
            for child in reversed(descendants):
                if not child.get('created') or not child.get('command'):
                    raise ServiceError('子进程身份信息不足，未停止实例。', 403)
            for child in reversed(descendants):
                child_record = dict(record, pid=child['pid'], created=child['created'], command=argv_of(child['command']))
                self.terminator(child_record, child)
            self.terminator(record, actual)
        record['state'] = 'stopping'
        if not record.get('original'):
            self._save(record)
        self._wake.set()
        return {'ok': True, 'id': identifier, 'state': 'stopping', 'message': '已提交停止，实际状态会自动更新。'}

    def _shutdown_capture(self, record):
        port = record['port']
        connection = HTTPConnection('127.0.0.1', port, timeout=5)
        try:
            connection.request('GET', '/')
            response = connection.getresponse()
            html = response.read(2 * 1024 * 1024).decode('utf-8')
            token = re.search(r"\btoken\s*=\s*['\"]([A-Za-z0-9_-]+)['\"]", html)
            if response.status != 200 or not token:
                raise ServiceError('无法取得此抓取实例的退出凭据。')
            connection.request('POST', '/api/shutdown', body='{}', headers={
                'Content-Type': 'application/json', 'Origin': 'http://127.0.0.1:' + str(port), 'X-Capture-Token': token[1]})
            response = connection.getresponse()
            result = json.loads(response.read(65536))
            if response.status != 200:
                raise ServiceError(result.get('error') or '抓取实例拒绝退出；请先停止并保存。', 409)
        finally:
            connection.close()

    def logs(self, identifier):
        try:
            record = self._resolve_action(identifier)
        except ServiceError:
            matches = [r for r in self.records.values() if r['service_id'] == identifier]
            if not matches:
                row = next((v for v in self._snapshot['services'] if v['id'] == identifier), {})
                matches = [self._actions[v['id']] for v in row.get('instances', []) if self._actions.get(v['id'])]
            if not matches:
                raise ServiceError('此实例没有本控制台可读取的日志。', 404)
            record = matches[-1]
        path = Path(record.get('log', ''))
        root = self.repo / ('other/diagnostics/response-capture-previews' if record.get('original') else 'other/diagnostics/service-console')
        try:
            relative = path.relative_to(root)
            # plain_file 会拒绝符号链接及目录联接，不能借日志接口读取其他文件。
            from original_games import plain_file
            safe = plain_file(root, relative)
            with safe.open('rb') as stream:
                size = safe.stat().st_size
                stream.seek(max(0, size - 32768))
                value = stream.read(32768).decode('utf-8', errors='replace')
            return {'id': identifier, 'text': redact(value), 'truncated': size > 32768}
        except (OSError, ValueError):
            return {'id': identifier, 'text': record.get('message') or '尚无启动日志。', 'truncated': False}
