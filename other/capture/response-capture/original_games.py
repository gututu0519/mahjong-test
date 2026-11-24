"""发现同仓库工作区的原版导出，只通过已核验的产物启动独立预览。"""
import ast
import ctypes
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlsplit

from archive_identity import archive_index, enrich_target
from capture_layout import SESSION_ID, plain_directory
from capture_directories import GAME_ID, checked_directory, open_directory


OUTPUT = Path('other/diagnostics/original-clients')
CONVERTER = Path('other/capture/original-client')
ARTIFACT_ID = re.compile(r'[0-9a-f]{32}')
READY_STATUSES = {'captured_candidate': 'offline', 'static_candidate': 'static', 'adapter_ready': 'adapter'}
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def plain_file(root, relative):
    relative = Path(relative)
    if relative.anchor or not relative.parts or any(p in ('.', '..') or ':' in p for p in relative.parts):
        raise ValueError('原版产物包含无效路径。')
    current = Path(root).absolute()
    if not plain_directory(current):
        raise ValueError('原版产物目录不是实际文件夹。')
    for n, part in enumerate(relative.parts):
        current = current / part
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError('原版产物路径包含符号链接或目录联接。')
        if n < len(relative.parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise ValueError('原版产物路径不是目录。')
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('原版产物文件不存在。')
    return current


def read_json(root, relative, limit=16 * 1024 * 1024):
    path = plain_file(root, relative)
    if path.stat().st_size > limit:
        raise ValueError('原版产物索引超过读取上限。')
    return json.loads(path.read_bytes().decode('utf-8-sig'))


def digest(path):
    with path.open('rb') as stream:
        result = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def worktrees(repo):
    result = subprocess.run(['git', '-C', str(repo), 'worktree', 'list', '--porcelain', '-z'],
                            check=True, capture_output=True, timeout=8, creationflags=NO_WINDOW)
    return [Path(part[9:]).absolute() for part in result.stdout.decode('utf-8').split('\0')
            if part.startswith('worktree ')]


def inspect_process(pid, port=0):
    """读取实际创建时间、父进程和监听者；不根据进程名称猜测服务归属。"""
    if os.name != 'nt':
        raise OSError('当前预览进程核验仅支持 Windows。')
    script = """$ErrorActionPreference='Stop'
$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new()
$p=Get-CimInstance Win32_Process -Filter ('ProcessId = '+$env:CAPTURE_PROBE_PID)
if (-not $p) { throw 'process unavailable' }
$listeners=@()
if ([int]$env:CAPTURE_PROBE_PORT -gt 0) {
  $listeners=@(Get-NetTCPConnection -LocalPort ([int]$env:CAPTURE_PROBE_PORT) -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,OwningProcess)
}
@{pid=[int]$p.ProcessId;parent=[int]$p.ParentProcessId;created=$p.CreationDate.ToUniversalTime().ToString('o');command=$p.CommandLine;listeners=$listeners} | ConvertTo-Json -Depth 4 -Compress
"""
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                            env={**os.environ, 'CAPTURE_PROBE_PID': str(pid), 'CAPTURE_PROBE_PORT': str(port)},
                            capture_output=True, check=True, timeout=8, creationflags=NO_WINDOW)
    return json.loads(result.stdout.decode('utf-8-sig'))


def process_created(process):
    """Popen 保留的进程句柄在启动器正常退出后仍有效，避免快启动时丢失创建时间。"""
    if os.name != 'nt':
        return inspect_process(process.pid)['created']
    from ctypes import wintypes
    created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
    get_times = ctypes.windll.kernel32.GetProcessTimes
    get_times.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    get_times.restype = wintypes.BOOL
    if not get_times(int(process._handle), ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)):
        raise OSError('无法核验本次启动器的创建时间。')
    ticks = (created.dwHighDateTime << 32) | created.dwLowDateTime
    return datetime.fromtimestamp(ticks / 10_000_000 - 11_644_473_600, timezone.utc).isoformat()


def same_creation(left, right):
    return abs((datetime.fromisoformat(left) - datetime.fromisoformat(right)).total_seconds()) <= .001


def owned_listener(info, pid, port):
    listeners = info.get('listeners') or []
    return (info.get('pid') == pid and 0 < port < 65536 and bool(listeners)
            and all(p.get('OwningProcess') == pid and p.get('LocalAddress') == '127.0.0.1' for p in listeners))


class OriginalGames:
    def __init__(self, repo, captures):
        self.repo, self.captures = Path(repo).absolute(), Path(captures).absolute()
        self.lock = threading.RLock()
        self.items, self.jobs = {}, {}
        self.checked, self.errors = 0, []
        self.owner = {'chat': os.environ.get('CODEX_THREAD_ID'), 'recorder_pid': os.getpid()}

    def _trusted(self, folder, name, trees):
        script = plain_file(folder, name)
        for tree in trees:
            try:
                source = plain_file(tree, CONVERTER / name)
                if script.read_text(encoding='utf-8-sig') == source.read_text(encoding='utf-8-sig'):
                    return script
            except (OSError, ValueError):
                continue
        raise ValueError('启动文件与本仓库已登记的转换器不一致，请重新转换后再试玩。')

    def _adapter(self, folder, report, trees):
        plain_file(folder, 'launch-original.ps1')
        template = None
        for tree in trees:
            try:
                source = ast.parse(plain_file(tree, CONVERTER / 'known.py').read_text(encoding='utf-8-sig'))
                for statement in source.body:
                    if isinstance(statement, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'POWERSHELL' for t in statement.targets):
                        candidate = ast.literal_eval(statement.value)
                        if all(marker in candidate for marker in ('ready.json', 'ownership.json', '$process.StartTime', '$process.Kill()')):
                            template = candidate
            except (OSError, ValueError, SyntaxError):
                continue
        if not template:
            raise ValueError('没有可核验归属和就绪状态的原版游戏启动器。')
        spec = read_json(folder, 'project-launch.json')
        repo = Path(spec['repo']).resolve()
        game = spec['game']
        if repo not in [t.resolve() for t in trees] or game != report.get('game') or not re.fullmatch(r'[a-z0-9-]{1,80}', game):
            raise ValueError('原版游戏启动资料不属于本仓库已登记的工作区。')
        profiles = read_json(repo, CONVERTER / 'adapters.json')
        profile = profiles.get(game, {})
        if profile.get('blocking') or not re.fullmatch(r'GTT_[A-Z0-9_]+_CLIENT_ROOT', profile.get('client_root_env') or ''):
            raise ValueError('该原版游戏尚未具备可用的试玩适配。')
        config = plain_file(repo, Path('other/diagnostics') / game / 'postgres.json')
        routing = read_json(repo, config.relative_to(repo))
        sources = [s for s in routing.get('sources', []) if s.get('kind') == 'local' and s.get('schema') == game.replace('-', '_')]
        if routing.get('driver') != 'postgres' or routing.get('isolated') is not True or len(sources) != 1:
            raise ValueError('该原版游戏缺少已核验的隔离试玩数据库配置。')
        # sources[].path 是 PostgreSQL 兼容路由标识，原启动器传给 --database；不要求旧 SQLite 文件存在。
        if not isinstance(sources[0].get('path'), str) or not sources[0]['path']:
            raise ValueError('隔离试玩数据库路由标识缺失。')
        plain_file(repo, 'other/runtime/server/dist/cli.js')
        prebuild = "& $node (Join-Path $repo 'other/tooling/build.mjs')\nif ($LASTEXITCODE -ne 0) { throw '项目构建失败，请检查 Node.js 和项目构建依赖。' }"
        if prebuild not in template or "param([switch]$NoBrowser)" not in template:
            raise ValueError('原版启动器版本未登记为可隔离调用的版本。')
        template = template.replace(prebuild, "if (-not (Test-Path -LiteralPath (Join-Path $runtime 'dist/cli.js') -PathType Leaf)) { throw '现有试玩运行文件缺失，请先在所属工作区完成构建。' }")
        template = template.replace('param([switch]$NoBrowser)', 'param([switch]$NoBrowser,[string]$ArtifactRoot,[string]$RunRecord)')
        template = template.replace('$PSScriptRoot', '$ArtifactRoot')
        template = template.replace("$record = Join-Path $ArtifactRoot ('run-' + [guid]::NewGuid().ToString('N'))", '$record = $RunRecord')
        return {'mode': 'adapter', 'spec': spec, 'config': config, 'repo': repo, 'template': template}

    def _launch_spec(self, folder, report, trees):
        mode = READY_STATUSES.get(report.get('status'))
        if not mode:
            raise ValueError(report.get('detail') or '此产物尚未生成可用的原版试玩入口。')
        if not checked_directory(folder, folder / 'client'):
            raise ValueError('原版客户端目录缺失。')
        if mode == 'adapter':
            return self._adapter(folder, report, trees)
        launcher = self._trusted(folder, 'offline_runtime.py' if mode == 'offline' else 'preview.py', trees)
        if mode == 'offline':
            for helper in ('offline_samples.py', 'offline_vector.py', 'png_interlace.py'):
                self._trusted(folder, helper, trees)
            index = read_json(folder, 'offline-assets.json')
            entry = index.get('entry')
            if entry != report.get('entry'):
                raise ValueError('原版入口与资源索引不一致。')
            matches = [a for a in index.get('assets', []) if a.get('origin') == entry.get('origin') and a.get('path') == entry.get('path')]
            if len(matches) != 1 or digest(plain_file(folder, matches[0]['file'])) != matches[0].get('sha256'):
                raise ValueError('原版入口资源缺失或校验和不一致。')
        else:
            plain_file(folder, Path('client') / report['entry_path'])
        return {'launcher': launcher, 'mode': mode}

    def _source_identity(self, folder, report, trees, archives):
        """兼容早期无 input_batches 的适配产物，以资源来源和实际响应摘要核对。"""
        try:
            evidence = read_json(folder, '来源索引.json')
            launch = read_json(folder, 'project-launch.json')
            repo, game = Path(launch['repo']).resolve(), evidence['game']
            if repo not in [t.resolve() for t in trees] or game != report.get('game') or not re.fullmatch(r'[a-z0-9-]{1,80}', game):
                return []
            source_index = read_json(repo, Path('games') / game / evidence['project_index'])
            candidates = {('/' + r.get('source', '').lstrip('/'), r.get('source_sha256')): r for r in source_index.get('resources', [])}
            for item in evidence.get('resources', []):
                if item.get('source_path') != report.get('entry'):
                    continue
                source = candidates.get((item['source_path'], item.get('source_sha256')))
                if not source or not SESSION_ID.fullmatch(str(source.get('capture', ''))):
                    continue
                saved = archives.get(source['capture'])
                if not saved:
                    continue
                identities = saved['summary'].get('identity_games', [])
                if len(identities) != 1:
                    continue
                manifest = read_json(saved['folder'], 'manifest.json', 64 * 1024 * 1024)
                for row in manifest.get('rows', []):
                    url = urlsplit(row.get('url', ''))
                    if (row.get('id') == source.get('request') and row.get('status') == 200 and row.get('state') == 'complete'
                            and url.hostname == item.get('source_host') and url.path == item['source_path']
                            and digest(plain_file(saved['folder'], row['body'])) == item['source_sha256']):
                        return identities
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return []

    def _identities(self, folder, report, trees, archives):
        targets = {}
        for batch in report.get('input_batches', []):
            target = batch.get('target_game') or {}
            site = target.get('site')
            if isinstance(site, str) and GAME_ID.fullmatch(site):
                targets[site] = enrich_target(self.captures, target)
        entry = report.get('entry')
        pg = None
        if isinstance(entry, dict):
            origin = urlsplit(entry.get('origin', ''))
            match = re.fullmatch(r'/(\d+)/index\.html', entry.get('path', ''))
            if origin.scheme == 'https' and origin.netloc in ('static5.mmga1.com', 's5.mmga1.com') and match:
                pg = match[1]
        if len(targets) > 1:
            return []
        if not targets:
            for target in self._source_identity(folder, report, trees, archives):
                targets[target['site']] = target
        if not targets and pg:
            for batch in archives.values():
                for target in batch['summary'].get('identity_games', []):
                    if target.get('brand', '').upper() == 'PG' and str(target.get('externalId')) == pg:
                        targets[target['site']] = target
        if len(targets) != 1:
            return []
        target = next(iter(targets.values()))
        if pg and ((target.get('brand') and target['brand'].upper() != 'PG') or
                   (target.get('externalId') and str(target['externalId']) != pg)):
            return []
        return [target]

    def catalog(self, force=False):
        with self.lock:
            # 展示缓存仍每次检查目录；点击时重新读取报告和启动器。
            if not force and time.monotonic() - self.checked < 5:
                self.items = {key: value for key, value in self.items.items() if checked_directory(value['tree'], value['folder'])}
                return {'games': [i['public'] for i in self.items.values()], 'errors': list(self.errors)}
            trees = worktrees(self.repo)
            archives = archive_index(self.captures)
            items, errors = [], []
            for tree in trees:
                output = checked_directory(tree, tree / OUTPUT)
                if not output:
                    continue
                for folder in sorted(output.iterdir(), reverse=True):
                    if not folder.name.startswith('原版客户端-') or not checked_directory(output, folder):
                        continue
                    try:
                        report = read_json(folder, '转换结果.json')
                        if report.get('schema') != 1:
                            continue
                        identities = self._identities(folder, report, trees, archives)
                        if not identities:
                            errors.append({'directory': str(folder), 'reason': '缺少可唯一核对的游戏身份，未按名称猜测关联。'})
                            continue
                        key = hashlib.sha256(os.path.normcase(str(folder.resolve())).encode('utf-8')).hexdigest()[:32]
                        spec, reason = None, ''
                        try:
                            spec = self._launch_spec(folder, report, trees)
                        except (OSError, ValueError, KeyError, TypeError) as error:
                            reason = str(error) if isinstance(error, ValueError) else '原版启动资料或依赖文件缺失。'
                        public = {'id': key, 'game_ids': [g['site'] for g in identities],
                                  'brand': identities[0].get('brand', ''), 'external_id': identities[0].get('externalId', ''),
                                  'title': report.get('title') or folder.name, 'directory': str(folder), 'name': folder.name,
                                  'worktree': str(tree), 'status': report.get('status'), 'can_preview': bool(spec),
                                  'preview_mode': spec['mode'] if spec else READY_STATUSES.get(report.get('status'), ''), 'reason': reason}
                        items.append({'public': public, 'folder': folder, 'tree': tree, 'report': report, 'spec': spec})
                    except (OSError, ValueError, KeyError, TypeError):
                        errors.append({'directory': str(folder), 'reason': '产物报告不可读或路径未通过核验。'})
            items.sort(key=lambda i: i['folder'].name, reverse=True)
            self.items = {item['public']['id']: item for item in items}
            self.errors, self.checked = errors, time.monotonic()
            return {'games': [i['public'] for i in items], 'errors': errors}

    def _item(self, identifier):
        if not isinstance(identifier, str) or not ARTIFACT_ID.fullmatch(identifier):
            raise ValueError('无效的原版产物 ID。')
        self.catalog(force=True)
        item = self.items.get(identifier)
        if not item:
            raise ValueError('原版产物不存在或已无法核对所属游戏。')
        return item

    def open_folder(self, identifier):
        item = self._item(identifier)
        open_directory(item['folder'])
        return {'ok': True, 'directory': str(item['folder']), 'message': '已请求打开原版游戏文件夹。'}

    def _save_job(self, job):
        public = {key: value for key, value in job.items() if key not in ('process', 'item', 'before', 'log_stream')}
        path = Path(job['record'])
        pending = path.with_suffix('.pending')
        pending.write_text(json.dumps(public, ensure_ascii=False, indent=2), encoding='utf-8')
        pending.replace(path)

    def preview(self, identifier):
        item = self._item(identifier)
        if not item['spec']:
            raise ValueError(item['public']['reason'] or '该产物尚无可用试玩入口。')
        with self.lock:
            for existing in self.jobs.values():
                if existing['artifact_id'] == identifier and existing['state'] == 'starting':
                    return self.job(existing['run_id'])
            run_id = uuid.uuid4().hex
            records = self.repo / 'other/diagnostics/response-capture-previews' / run_id
            records.mkdir(parents=True)
            spec = item['spec']
            env = {**os.environ, 'PYTHONUTF8': '1', 'CODEX_THREAD_ID': self.owner['chat'] or ''}
            # Windows venv 的 python.exe 会另起包装子进程；使用真实解释器保证 PID 可核验。
            command = [getattr(sys, '_base_executable', sys.executable), str(spec.get('launcher', ''))]
            if spec['mode'] == 'adapter':
                launcher = records / 'launch-original.ps1'
                helper = plain_file(Path(__file__).resolve().parent, 'service_control.mjs')
                marker = "$arguments = @('dist/cli.js',"
                if marker not in spec['template']:
                    raise ValueError('原版启动器缺少已登记的正常退出桥接位置。')
                replacement = """$arguments = @('--import',('"'+$env:GTT_CAPTURE_CONTROL_HELPER+'"'),('"'+(Join-Path $runtime 'dist/cli.js')+'"'),"""
                template = spec['template'].replace(marker, replacement, 1)
                launcher.write_text(template, encoding='utf-8-sig')
                command = ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                           '-File', str(launcher), '-NoBrowser', '-ArtifactRoot', str(item['folder']),
                           '-RunRecord', str(records / 'service')]
                env['GTT_PG_CONFIG'] = str(spec['config'])
                env['GTT_CAPTURE_CONTROL_DIR'] = str(records)
                env['GTT_CAPTURE_CONTROL_NONCE'] = uuid.uuid4().hex
                env['GTT_CAPTURE_CONTROL_HELPER'] = helper.as_uri()
            elif spec['mode'] == 'static':
                command.append('--no-browser')
            stream = (records / 'launcher.log').open('wb')
            before = set()
            try:
                process = subprocess.Popen(command, cwd=item['folder'], env=env, stdin=subprocess.DEVNULL,
                                           stdout=stream, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
            except Exception:
                stream.close()
                raise
            job = {'ok': True, 'run_id': run_id, 'artifact_id': identifier, 'state': 'starting',
                   'message': '正在启动本次独立试玩窗口…', 'mode': spec['mode'], 'started': datetime.now(timezone.utc).isoformat(),
                   'pid': process.pid, 'cwd': str(item['folder']), 'command': command, **self.owner,
                   'record': str(records / 'ownership.json'), 'process': process, 'item': item, 'before': before, 'log_stream': stream}
            if spec['mode'] == 'adapter':
                job.update(control_directory=str(records), control_nonce=env['GTT_CAPTURE_CONTROL_NONCE'])
            self.jobs[run_id] = job
            self._save_job(job)
            threading.Thread(target=self._watch, args=(job,), daemon=True).start()
            return self.job(run_id)

    def _ready(self, job):
        folder, pid, mode = job['item']['folder'], job['pid'], job['mode']
        if mode in ('offline', 'static'):
            record = read_json(folder, f'预览进程-{pid}.json')
            started = datetime.fromisoformat(record.get('started', '')).astimezone(timezone.utc)
            command = record.get('command') or []
            if (record.get('pid') != pid or Path(record.get('cwd', '')).resolve() != folder.resolve()
                    or record.get('chat') != (self.owner['chat'] or '')
                    or started < datetime.fromisoformat(job['started'])
                    or not command or Path(command[0]).resolve() != job['item']['spec']['launcher'].resolve()):
                raise ValueError('预览进程归属不匹配。')
            port = record.get('port')
            actual = inspect_process(pid, port)
            if not same_creation(actual['created'], job['created']) or not owned_listener(actual, pid, port):
                raise ValueError('预览监听端口与本次进程不匹配。')
            if mode == 'static':
                url = urlsplit(record.get('url', ''))
                if url.scheme != 'http' or url.hostname != '127.0.0.1' or url.port != port:
                    raise ValueError('静态试玩地址不是本次本机实例。')
                return {'port': port, 'url': record['url'], 'message': '原版静态试玩实例已就绪。'}
            return {'port': port, 'message': '已打开独立离线试玩窗口。'}
        spec = job['item']['spec']
        record_home = Path(job['record']).parent
        for run in [record_home / 'service']:
            if not checked_directory(record_home, run):
                continue
            try:
                ownership, ready = read_json(run, 'ownership.json'), read_json(run, 'ready.json')
                child, port = ownership['pid'], ownership['port']
                info = inspect_process(child, port)
                created = datetime.fromisoformat(ownership['created']).astimezone(timezone.utc)
                actual = datetime.fromisoformat(info['created']).astimezone(timezone.utc)
                if (info.get('parent') != pid or abs((created-actual).total_seconds()) > .001
                        or ownership.get('chat') != (self.owner['chat'] or '') or ownership.get('game') != spec['spec']['game']
                        or Path(ownership['client']).resolve() != (folder/'client').resolve()
                        or ready.get('pid') != child or ready.get('port') != port or not owned_listener(info, child, port)):
                    continue
                origin = f'http://127.0.0.1:{port}'
                if ready.get('entry') != origin + '/' or ready.get('origin') != origin:
                    continue
                connection = HTTPConnection('127.0.0.1', port, timeout=3)
                try:
                    connection.request('GET', '/health')
                    response = connection.getresponse()
                    health = json.loads(response.read(1024 * 1024))
                    if response.status != 200 or health.get('status') != 'ok' or health.get('service_id') != spec['spec']['game']:
                        continue
                    connection.request('GET', spec['spec']['probe'])
                    response = connection.getresponse()
                    if response.status != 200 or hashlib.sha256(response.read()).hexdigest() != spec['spec']['probe_sha256']:
                        continue
                finally:
                    connection.close()
                result = {'port': port, 'service_pid': child, 'service_created': info['created'],
                        'service_ownership': str(run/'ownership.json'), 'url': ready['entry'], 'message': '本次独立原版试玩实例已就绪。'}
                if job.get('control_nonce') and not self.adapter_control(dict(job, **result)):
                    continue
                return result
            except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
                continue
        raise FileNotFoundError('尚未生成本次实例的就绪记录。')

    def _watch(self, job):
        try:
            job['created'] = process_created(job['process'])
            self._save_job(job)
            deadline = time.monotonic() + 150
            while time.monotonic() < deadline:
                try:
                    result = self._ready(job)
                    job.update(result, state='ready')
                    self._save_job(job)
                    return
                except (FileNotFoundError, json.JSONDecodeError):
                    pass
                code = job['process'].poll()
                if code is not None:
                    # 就绪文件可能在上一轮读取后、进程退出前刚写完，再核验一次。
                    if code == 0:
                        try:
                            result = self._ready(job)
                            job.update(result, state='ready')
                            self._save_job(job)
                            return
                        except (FileNotFoundError, json.JSONDecodeError):
                            pass
                    raise ValueError('本次试玩启动器已退出，未取得可核对的就绪记录，请查看启动记录。')
                time.sleep(.3)
            raise ValueError('本次试玩启动等待超时；启动记录已保留，未操作其他窗口的服务。')
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
            job.update(state='error', message=str(error) if isinstance(error, ValueError) else '本次试玩启动失败，请查看启动记录。')
            self._save_job(job)
        finally:
            job['log_stream'].close()

    def job(self, run_id):
        if not isinstance(run_id, str) or not ARTIFACT_ID.fullmatch(run_id) or run_id not in self.jobs:
            raise ValueError('不存在当前采集器所属的试玩启动记录。')
        job = self.jobs[run_id]
        return {key: job.get(key) for key in ('ok', 'run_id', 'state', 'message', 'pid', 'port', 'mode', 'record', 'url')}

    def _adapter_control_record(self, job):
        """把启动器归属与其已核验 Node 子服务合并；旧实例没有控制凭据。"""
        if job.get('mode') != 'adapter' or not job.get('service_pid') or not job.get('control_nonce'):
            return None
        root = self.repo / 'other/diagnostics/response-capture-previews'
        folder = Path(job.get('control_directory', '')).absolute()
        if not checked_directory(root, folder) or folder != Path(job.get('record', '')).absolute().parent:
            return None
        try:
            child = read_json(folder, 'service/ownership.json', 128 * 1024)
            if (child.get('pid') != job['service_pid'] or child.get('chat') != self.owner['chat']
                    or not same_creation(child.get('created'), job.get('service_created'))):
                return None
            return dict(job, pid=child['pid'], created=child['created'], cwd=child['cwd'], command=child['command'])
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def adapter_control(self, job):
        from service_control import read_control
        record = self._adapter_control_record(job)
        return read_control(record, self.repo / 'other/diagnostics/response-capture-previews', self.owner['chat']) if record else None

    def shutdown_adapter(self, job, *, inspector=None):
        from service_control import request_stop
        record = self._adapter_control_record(job)
        if not record:
            raise ValueError('该原版实例没有可核验的正常退出通道，请保留现有服务。')
        return request_stop(record, self.repo / 'other/diagnostics/response-capture-previews', self.owner['chat'], inspector=inspector)
