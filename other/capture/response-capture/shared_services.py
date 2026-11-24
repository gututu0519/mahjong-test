"""共享依赖的固定对象管理；确认令牌由控制层持有，本模块执行前复核实际影响。"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from original_games import NO_WINDOW, plain_file, read_json


class SharedServiceError(ValueError):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


class SharedServices:
    def __init__(self, repo, inventory=None, runner=None):
        self.repo = Path(repo).resolve()
        self.inventory = inventory
        self.runner = runner or subprocess.run
        self.data = self.repo / 'gateway/instance/data/local-postgres/pgdata'
        self.home = self.repo / 'other/diagnostics/service-console'
        self._extra_cache, self._extra_at = {}, 0

    def _run(self, argv, timeout=15):
        return self.runner([str(v) for v in argv], capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=timeout, creationflags=NO_WINDOW, shell=False, check=False)

    def _read_text(self, relative, limit=65536):
        try:
            path = plain_file(self.repo, relative)
            return path.read_bytes()[:limit].decode('utf-8-sig')
        except (OSError, ValueError, UnicodeError):
            return ''

    def _startup(self):
        try:
            return read_json(self.repo, 'gateway/instance/data/local-postgres/startup-record.json', 65536)
        except (OSError, ValueError):
            return {}

    def _port(self):
        lines = self._read_text('gateway/instance/data/local-postgres/pgdata/postmaster.pid').splitlines()
        if len(lines) > 3 and lines[3].isdigit() and 0 < int(lines[3]) < 65536:
            return int(lines[3])
        # 停止后仍使用已登记的同一实例端口，不扫描私有 env 或数据库密码。
        ports = self._startup().get('ports') or []
        return ports[0] if len(ports) == 1 and isinstance(ports[0], int) and 0 < ports[0] < 65536 else 15432

    def _extras(self, fresh=False):
        if not fresh and time.monotonic() - self._extra_at < 5:
            return copy.deepcopy(self._extra_cache)
        if os.name != 'nt':
            return {'windows_services': [], 'connections': [], 'docker': {'available': False, 'reason': '当前管理入口仅实现 Windows。'}}
        script = r"""$ErrorActionPreference='Stop'
$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new()
$services=@(Get-CimInstance Win32_Service | Where-Object {$_.PathName -match 'postgres|pg_ctl|Docker'} | ForEach-Object {@{name=$_.Name;state=$_.State;pid=[int]$_.ProcessId;command=$_.PathName;start_mode=$_.StartMode}})
$connections=@(Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue | Where-Object {$_.RemotePort -eq PORT_VALUE -or $_.LocalPort -eq PORT_VALUE} | ForEach-Object {@{pid=[int]$_.OwningProcess;local_address=$_.LocalAddress;local_port=[int]$_.LocalPort;remote_address=$_.RemoteAddress;remote_port=[int]$_.RemotePort}})
@{windows_services=$services;connections=$connections}|ConvertTo-Json -Depth 5 -Compress
""".replace('PORT_VALUE', str(self._port()))
        result = self._run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script])
        if result.returncode:
            raise SharedServiceError('无法读取共享服务管理方式及连接影响，未执行操作。', 503)
        data = json.loads(result.stdout)
        data['docker'] = self._docker_inventory()
        self._extra_cache, self._extra_at = copy.deepcopy(data), time.monotonic()
        return data

    def _docker_inventory(self):
        cli = shutil.which('docker')
        if not cli:
            candidate = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Docker/Docker/resources/bin/docker.exe'
            cli = str(candidate) if candidate.is_file() else None
        if not cli:
            return {'available': False, 'engine_running': False, 'reason': '未找到 Docker CLI 或 Docker Desktop 固定管理入口；不会自动安装。'}
        result = {'available': True, 'cli': str(Path(cli).resolve()), 'engine_running': False,
                  'desktop_cli': False, 'containers': [], 'reason': ''}
        try:
            help_result = self._run([cli, 'desktop', '--help'], 8)
            result['desktop_cli'] = help_result.returncode == 0 and all(re.search(r'(?m)^\s+' + word + r'\s', help_result.stdout) for word in ('start', 'stop'))
            context = self._run([cli, 'context', 'show'], 8)
            name = context.stdout.strip()
            if context.returncode or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', name):
                raise SharedServiceError('无法核验本机 Docker context。')
            endpoint = self._run([cli, 'context', 'inspect', name, '--format', '{{json .Endpoints.docker.Host}}'], 8)
            host = json.loads(endpoint.stdout) if endpoint.returncode == 0 else ''
            if not (host.startswith('npipe:////./pipe/') or host.startswith('unix:///')):
                raise SharedServiceError('当前 Docker context 指向非本机端点，不纳入本机共享服务管理。')
            result.update(context=name, endpoint=host)
            # 显式 context 避免 DOCKER_HOST 环境变量把命令转向其他机器。
            listing = self._run([cli, '--context', name, 'ps', '-a', '--no-trunc', '--format', '{{.ID}}'], 8)
            if listing.returncode:
                result['reason'] = 'Docker 引擎尚未运行；启动后可能恢复已有容器。'
                return result
            result['engine_running'] = True
            ids = [v for v in listing.stdout.splitlines() if re.fullmatch(r'[0-9a-f]{64}', v)]
            for identifier in ids:
                template = ('{"id":{{json .Id}},"name":{{json .Name}},"image":{{json .Config.Image}},'
                            '"running":{{json .State.Running}},"started":{{json .State.StartedAt}},'
                            '"restart":{{json .HostConfig.RestartPolicy.Name}},"ports":{{json .HostConfig.PortBindings}},'
                            '"mounts":{{json .Mounts}}}')
                inspected = self._run([cli, '--context', name, 'inspect', '--type', 'container', '--format', template, identifier], 8)
                if inspected.returncode:
                    raise SharedServiceError('容器集合发生变化，需重新核验 Docker 影响范围。')
                item = json.loads(inspected.stdout)
                item['name'] = str(item.get('name', '')).lstrip('/')
                result['containers'].append(item)
            result['containers_known'] = True
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            result['reason'] = str(error) if isinstance(error, SharedServiceError) else 'Docker 管理入口不可读取，不能核实共享影响。'
        return result

    def _inventory(self, supplied=None, fresh=False):
        if supplied is not None:
            data = copy.deepcopy(supplied)
        elif self.inventory:
            data = copy.deepcopy(self.inventory())
        else:
            from service_runtime import windows_inventory
            data = windows_inventory()
        if self.inventory is None and not all(key in data for key in ('windows_services', 'connections', 'docker')):
            data.update(self._extras(fresh=fresh))
        data.setdefault('windows_services', [])
        data.setdefault('connections', [])
        data.setdefault('docker', {'available': False, 'reason': '未发现 Docker 管理入口。'})
        return data

    def _data_argument(self, command):
        from service_runtime import argv_of
        args = argv_of(command)
        for index, arg in enumerate(args[:-1]):
            if arg in ('-D', '--pgdata'):
                try:
                    return Path(args[index + 1]).resolve()
                except OSError:
                    return None
        return None

    def _dependencies(self, data, port):
        processes = {p['pid']: p for p in data.get('processes', [])}
        local, remote = {}, set()
        for connection in data['connections']:
            if connection.get('remote_port') == port and connection.get('remote_address') in ('127.0.0.1', '::1'):
                process = processes.get(connection.get('pid'), {})
                if process:
                    label = process.get('name') or Path(process.get('executable', '')).name or '进程'
                    command = process.get('command', '')
                    from service_runtime import argv_of
                    args = argv_of(command)
                    for action, title in (('gateway', '平台网关'), ('mock', '模拟平台'), ('admin', '管理后台'), ('rtp-worker', 'RTP 任务服务')):
                        if action in args:
                            label = title
                            break
                    local[process['pid']] = {'pid': process['pid'], 'created': process.get('created'), 'name': label,
                                             'command_fingerprint': fingerprint(command)}
                elif type(connection.get('pid')) is int and connection['pid'] > 0:
                    # 连接与进程表不是原子快照；新客户端尚未入表时也必须计入确认范围。
                    local[connection['pid']] = {'pid': connection['pid'], 'created': None, 'name': '未识别客户端',
                                                 'command_fingerprint': None, 'identity_unverified': True}
            if connection.get('local_port') == port and connection.get('remote_address') not in ('127.0.0.1', '::1'):
                remote.add(connection.get('remote_address'))
        return {'dependents': sorted(local.values(), key=lambda p: p['pid']), 'remote_clients': sorted(v for v in remote if v),
                'scope_note': '列出当前已建立连接的客户端；已配置但暂未连接的服务也会受数据库停机影响。'}

    @staticmethod
    def _base(identifier, name):
        return {'id': identifier, 'name': name, 'category': 'advanced', 'status': 'stopped', 'running_count': 0,
                'can_start': False, 'can_stop': False, 'reason': '', 'method': None, 'pid': None, 'port': None,
                'open_url': '', 'endpoint_url': '', 'endpoint_text': '', 'can_logs': False, 'logs_available': False,
                'instances': [], 'warnings': [], 'impact': {}, 'identity': {}, 'internal': {}}

    def _postgres(self, data):
        from service_runtime import argv_of, command_matches
        row = self._base('advanced.postgres', 'PostgreSQL')
        port = self._port()
        row.update(port=port, default_port=port, endpoint_text='127.0.0.1:' + str(port),
                   description='当前项目使用的共享数据库；启停前必须确认对所有连接方的影响。',
                   impact=self._dependencies(data, port))
        matches = [p for p in data.get('processes', []) if self._data_argument(p.get('command')) == self.data.resolve()
                   and Path(p.get('executable', '')).name.lower() in ('postgres.exe', 'postgres')]
        services = [s for s in data['windows_services'] if self._data_argument(s.get('command')) == self.data.resolve()]
        process = matches[0] if len(matches) == 1 else None
        startup = self._startup()
        binary = process.get('executable') if process else startup.get('executablePath')
        if not binary:
            options = argv_of(self._read_text('gateway/instance/data/local-postgres/pgdata/postmaster.opts'))
            binary = options[0] if options else None
        version = self._read_text('gateway/instance/data/local-postgres/pgdata/PG_VERSION').strip()
        valid_data = bool(re.fullmatch(r'[0-9]{1,2}', version))
        if binary and Path(binary).name.lower() in ('postgres.exe', 'postgres'):
            pg_ctl = Path(binary).with_name('pg_ctl.exe' if os.name == 'nt' else 'pg_ctl')
        else:
            pg_ctl = None
        listening = process and any(v.get('pid') == process['pid'] and v.get('port') == port for v in data.get('listeners', []))
        identity = {'data_directory': str(self.data), 'port': port,
                    'pid': process.get('pid') if process else None, 'created': process.get('created') if process else None,
                    'command_fingerprint': fingerprint(process.get('command')) if process else None,
                    'dependents': row['impact']['dependents'], 'remote_clients': row['impact']['remote_clients']}
        row.update(status='running' if listening else ('unknown' if process else 'stopped'), running_count=int(bool(listening)),
                   pid=identity['pid'], identity=identity)
        lock = self._read_text('gateway/instance/data/local-postgres/pgdata/postmaster.pid').splitlines()
        if process and (not lock or lock[0] != str(process['pid']) or len(lock) < 2 or Path(lock[1]).resolve() != self.data.resolve()):
            row['reason'] = '数据目录中的 PostgreSQL 锁记录与实际进程不一致，暂不能安全启停。'
            return row
        identity.update(cluster_version=version, lock_pid=lock[0] if lock else None)
        if len(matches) > 1 or len(services) > 1:
            row['reason'] = '同一数据目录对应多个候选管理对象，无法唯一确定目标。'
            return row
        if services:
            service = services[0]
            args = argv_of(service.get('command'))
            executable = Path(args[0]) if args else None
            if not executable or not executable.is_file() or executable.name.lower() not in ('pg_ctl.exe', 'postgres.exe'):
                row['reason'] = 'Windows 服务入口未通过 PostgreSQL 固定程序核验。'
                return row
            name = service.get('name', '')
            if not re.fullmatch(r'[A-Za-z0-9_.-]{1,120}', name):
                row['reason'] = 'Windows 服务名称不在受控格式内。'
                return row
            row.update(method='windows-service', can_start=service.get('state') == 'Stopped', can_stop=service.get('state') == 'Running')
            identity.update(method=row['method'], service=name, service_command=service['command'], service_pid=service.get('pid'))
            row['internal'] = {'program': str(Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/sc.exe'), 'service': name}
        elif valid_data and pg_ctl and pg_ctl.is_file():
            # 数据目录与 PG_VERSION 必须都在当前项目的普通目录中，不能初始化或换库。
            command = process.get('command') if process else startup.get('commandLine')
            args = argv_of(command) if command else argv_of(self._read_text('gateway/instance/data/local-postgres/pgdata/postmaster.opts'))
            expected = [str(binary), '-D', str(self.data)]
            reconstructable = command_matches(args, expected)
            row.update(method='pg_ctl', can_start=not bool(process) and reconstructable, can_stop=bool(listening and process.get('created')))
            identity.update(method='pg_ctl', executable=str(pg_ctl.resolve()), executable_mtime=pg_ctl.stat().st_mtime_ns)
            row['internal'] = {'program': str(pg_ctl.resolve()), 'data_directory': str(self.data)}
            if not reconstructable and not process:
                row['reason'] = '原 PostgreSQL 启动参数无法由固定入口安全重建，未提供启动操作。'
            elif not process and any(v.get('port') == port for v in data.get('listeners', [])):
                row.update(can_start=False, reason='数据库登记端口已由其他进程占用；不会修改共享端口或结束占用者。')
        else:
            container = self._project_container(data['docker'])
            if container:
                docker = data['docker']
                row.update(method='docker-container', status='running' if container['running'] else 'stopped',
                           running_count=int(container['running']), can_start=not container['running'], can_stop=bool(container['running']))
                identity.update(method=row['method'], context=docker['context'], endpoint=docker['endpoint'], container=container)
                row['internal'] = {'program': docker['cli'], 'context': docker['context'], 'container': container['id']}
            else:
                row['reason'] = '没有找到与本项目数据目录匹配的 pg_ctl、Windows 服务或明确登记的 Docker 容器。'
        row['warnings'] = ['停止 PostgreSQL 会断开当前连接并回滚未提交事务；依赖数据库的网关、后台、模拟平台及试玩可能暂时不可用。',
                           row['impact']['scope_note']]
        if row['impact']['dependents']:
            row['warnings'].append('当前连接方：' + '、'.join(p['name'] + '（PID ' + str(p['pid']) + '）' for p in row['impact']['dependents']))
        return row

    def _project_container(self, docker):
        if not docker.get('engine_running') or not docker.get('containers_known'):
            return None
        # 只读取明确管理登记中的对象名/卷名，不读取或返回 env、密码、容器环境变量。
        try:
            metadata = read_json(self.repo, 'gateway/instance/data/postgres-migration.json', 65536)
            name, volume = metadata.get('container'), metadata.get('volume')
        except (OSError, ValueError):
            return None
        if not isinstance(name, str) or not re.fullmatch(r'gtt-postgres-[0-9]{14}', name) or volume != name + '-data':
            return None
        matches = []
        for item in docker.get('containers', []):
            ports = item.get('ports') or {}
            bindings = ports.get('5432/tcp') or []
            if (item.get('name') == name and re.fullmatch(r'[0-9a-f]{64}', item.get('id', ''))
                    and any(v.get('Name') == volume and v.get('Destination') == '/var/lib/postgresql/data' for v in item.get('mounts', []))
                    and any(str(v.get('HostPort')) == str(self._port()) and v.get('HostIp') in ('127.0.0.1', '::1') for v in bindings)):
                matches.append(item)
        return matches[0] if len(matches) == 1 else None

    def _docker(self, data):
        docker = data['docker']
        row = self._base('advanced.docker', 'Docker Desktop')
        containers = [{k: c.get(k) for k in ('id', 'name', 'image', 'running', 'started', 'restart')} for c in docker.get('containers', [])]
        live = [c for c in containers if c['running']]
        row.update(status='running' if docker.get('engine_running') else 'stopped', running_count=int(bool(docker.get('engine_running'))),
                   method='docker-desktop' if docker.get('desktop_cli') else None,
                   description='本机共享容器运行环境，关闭会影响其中的运行容器。',
                   impact={'running_containers': live, 'registered_containers': containers},
                   reason=docker.get('reason', ''),
                   identity={'cli': docker.get('cli'), 'context': docker.get('context'), 'endpoint': docker.get('endpoint'),
                             'engine_running': bool(docker.get('engine_running')), 'containers': containers},
                   internal={'program': docker.get('cli')})
        local = str(docker.get('endpoint', '')).startswith(('npipe:////./pipe/', 'unix:///'))
        row['can_start'] = bool(docker.get('available') and docker.get('desktop_cli') and local and not docker.get('engine_running'))
        row['can_stop'] = bool(docker.get('available') and docker.get('desktop_cli') and local and docker.get('engine_running') and docker.get('containers_known'))
        if not row['can_start'] and not row['can_stop'] and not row['reason']:
            row['reason'] = '缺少已核验的 Docker Desktop start/stop 管理命令或完整容器清单。'
        row['warnings'] = ['关闭 Docker Desktop 会停止本机 Docker 引擎，影响列出的所有运行容器及其访问方。',
                           '启动 Docker Desktop 可能按既有 restart 策略恢复容器；本操作不会新建或删除容器、镜像、持久卷。']
        if live:
            row['warnings'].append('当前运行容器：' + '、'.join(c['name'] + '（' + c['id'][:12] + '）' for c in live))
        return row

    def _rows(self, data):
        rows = [self._postgres(data), self._docker(data)]
        for row in rows:
            row['identity_fingerprint'] = fingerprint(row['identity'])
        return rows

    @staticmethod
    def _public_impact(impact):
        result = copy.deepcopy(impact)
        for dependent in result.get('dependents', []):
            dependent.pop('command_fingerprint', None)
        return result

    def snapshot(self, inventory=None):
        rows = self._rows(self._inventory(inventory))
        public = [{k: v for k, v in row.items() if k not in ('internal', 'identity', 'identity_fingerprint')} for row in rows]
        for row in public:
            row['impact'] = self._public_impact(row['impact'])
        return {'services': public}

    def prepare(self, identifier, action, inventory=None):
        if identifier not in ('advanced.postgres', 'advanced.docker') or action not in ('start', 'stop'):
            raise SharedServiceError('未知共享服务或操作。', 400)
        row = next(r for r in self._rows(self._inventory(inventory, fresh=True)) if r['id'] == identifier)
        if not row['can_' + action]:
            raise SharedServiceError(row['reason'] or '当前共享服务状态不支持此操作。')
        warnings = row['warnings'] if action == 'stop' else [v for v in row['warnings'] if v.startswith('启动')]
        if action == 'start' and identifier == 'advanced.postgres':
            warnings = ['启动既有 PostgreSQL 数据目录，可能恢复等待数据库的应用；不会初始化数据库、迁移数据或修改账号。']
        return {'id': identifier, 'action': action, 'method': row['method'], 'identity': row['identity'],
                'identity_fingerprint': row['identity_fingerprint'],
                'targets': [{'id': identifier, 'name': row['name'], 'pid': row['pid'],
                             'created': row['identity'].get('created'), 'port': row['port'],
                             'cwd': row['identity'].get('data_directory'), 'mode': row['method']}],
                'warnings': warnings, 'impact': self._public_impact(row['impact']), 'internal': row['internal']}

    def execute(self, plan):
        if not isinstance(plan, dict):
            raise SharedServiceError('缺少已确认的共享服务计划。', 400)
        fresh = self.prepare(plan.get('id'), plan.get('action'))
        if fresh['identity_fingerprint'] != plan.get('identity_fingerprint'):
            raise SharedServiceError('共享服务身份或影响范围已经变化，请重新查看副作用并确认。')
        action, mode, target = fresh['action'], fresh['method'], fresh['internal']
        if mode == 'pg_ctl':
            argv = [target['program'], action, '-D', target['data_directory'], '-w', '-t', '60']
            if action == 'stop':
                argv += ['-m', 'fast']
            else:
                self.home.mkdir(parents=True, exist_ok=True)
                argv += ['-l', str(self.home / 'postgres-start.log')]
        elif mode == 'windows-service':
            argv = [target['program'], action, target['service']]
        elif mode == 'docker-container':
            argv = [target['program'], '--context', target['context'], action]
            if action == 'stop':
                argv += ['--time', '-1']
            argv += [target['container']]
        elif mode == 'docker-desktop':
            argv = [target['program'], 'desktop', action]
        else:
            raise SharedServiceError('此管理方式没有固定执行入口。')
        result = self._run(argv, timeout=75)
        if result.returncode:
            raise SharedServiceError('共享服务正常' + ('启动' if action == 'start' else '停止') + '命令失败，未执行强制结束。', 503)
        self._extra_at = 0
        return {'ok': True, 'id': fresh['id'], 'state': 'starting' if action == 'start' else 'stopping',
                'message': '已执行正常' + ('启动' if action == 'start' else '停止') + '命令，后续以实际进程和监听状态确认。'}
