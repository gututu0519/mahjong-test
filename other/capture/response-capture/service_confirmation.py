"""服务操作预检与一次性确认；前端不能指定命令、路径或强杀模式。"""
import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta

from original_games import read_json, same_creation


def reject(message, status=409):
    from service_runtime import ServiceError
    raise ServiceError(message, status)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


class ConfirmedOperations:
    def _load_external_specs(self):
        try:
            saved = read_json(self.home, 'external-services.json', 2 * 1024 * 1024)
            for spec in saved.get('services', []):
                if spec.get('external_registered') and str(spec.get('id', '')).startswith(('worktree-demo.', 'reopen.capture.')):
                    self.registry[spec['id']] = spec
        except (OSError, ValueError, TypeError, KeyError):
            pass

    def _remember_external(self, spec, process, port):
        from service_runtime import argv_of, normalized
        result = dict(spec)
        args = argv_of(process.get('command'))
        if spec.get('id') == 'fixed.capture' and port:
            tree = None
            for candidate in self._worktree_roots:
                entry = Path(candidate) / 'other/capture/response-capture/app.py'
                if any(normalized(value) == normalized(entry) for value in args):
                    tree = Path(candidate)
                    break
                if 'app.py' in args and Path(self._process_directory(process)).resolve() == entry.parent.resolve():
                    tree = Path(candidate)
                    break
            if tree is None:
                return
            suffix = hashlib.sha256(str(tree).lower().encode()).hexdigest()[:12]
            result.update(id=f'reopen.capture.{suffix}.{port}', name=f'抓取入口 {port}', category='capture-instances',
                          description='保留已核验抓取实例的启动入口，服务关闭后仍可重新开启。', worktree=str(tree),
                          directory=str(tree / 'other/capture/response-capture'), default_port=port, kind='capture')
            if '--previous-port' in args:
                try:
                    result['previous_port'] = int(args[args.index('--previous-port') + 1])
                except (IndexError, ValueError):
                    pass
        elif not str(spec.get('id', '')).startswith('worktree-demo.'):
            return
        result.update(external_registered=True, registered=True)
        if result['kind'] == 'capture':
            result.update(observed_pid=process['pid'], observed_created=process['created'])
        else:
            result.pop('observed_pid', None)
            result.pop('observed_created', None)
        prior = self.registry.get(result['id'])
        self.registry[result['id']] = result
        if prior != result:
            values = [v for v in self.registry.values() if v.get('external_registered')]
            pending = self.home / 'external-services.pending'
            pending.write_text(json.dumps({'services': values}, ensure_ascii=False, indent=2), encoding='utf-8')
            pending.replace(self.home / 'external-services.json')

    def _external_start_spec(self, spec):
        from original_games import plain_file
        tree = Path(spec.get('worktree') or '').resolve()
        if tree not in [Path(value).resolve() for value in self._worktree_roots]:
            reject('所属工作区已不在本仓库登记中，不能重新启动。')
        if spec['kind'] == 'capture':
            entry = plain_file(tree, 'other/capture/response-capture/app.py')
            return {'entry': str(entry), 'tree': str(tree), 'signature': hashlib.sha256(entry.read_bytes()).hexdigest()}
        directory = Path(spec['directory']).resolve()
        code = spec.get('game_code') or directory.parent.name
        if directory != tree / 'games' / code / 'instance':
            reject('试玩目录与已登记游戏身份不一致。')
        info = read_json(tree, directory.relative_to(tree) / 'service.json', 128 * 1024)
        if info.get('id') != code or code not in info.get('games', []):
            reject('试玩启动配置已改变，请重新核对游戏登记。')
        entry = plain_file(tree, 'other/runtime/server/dist/cli.js')
        config = plain_file(tree, Path('other/diagnostics') / code / 'postgres.json')
        route = read_json(tree, config.relative_to(tree), 1024 * 1024)
        sources = [value for value in route.get('sources', []) if value.get('kind') == 'local' and value.get('schema') == code.replace('-', '_')]
        if route.get('driver') != 'postgres' or route.get('isolated') is not True or len(sources) != 1 or not isinstance(sources[0].get('path'), str) or not sources[0]['path']:
            reject('缺少该游戏已核验的隔离 PostgreSQL 路由，不能沿用控制台数据库配置重新启动。')
        return {'entry': str(entry), 'tree': str(tree), 'directory': str(directory), 'config': str(config), 'database': sources[0]['path'],
                'signature': fingerprint([info, route, hashlib.sha256(entry.read_bytes()).hexdigest()])}

    def _external_command(self, spec, port):
        import shutil
        source = self._external_start_spec(spec)
        # 外部试玩必须采用已核验的隔离路由，不能继承当前平台数据库凭据。
        env = {key: value for key, value in os.environ.items() if not key.startswith(('PG', 'GTT_PG_', 'GTT_PLATFORM_'))}
        env.update(CODEX_THREAD_ID=self.owner_chat, PYTHONUTF8='1', CAPTURE_FEATURE_MAINTENANCE='0')
        if spec['kind'] == 'capture':
            env['PYTHONPATH'] = str(Path(source['tree']) / 'other/capture/response-capture/.venv/Lib/site-packages')
            command = [getattr(sys, '_base_executable', sys.executable), source['entry'], '--port', str(port)]
            if spec.get('previous_port'):
                command += ['--previous-port', str(spec['previous_port'])]
        else:
            helper = (Path(__file__).parent / 'service_control.mjs').as_uri()
            command = [shutil.which('node'), '--import', helper, source['entry'], 'service', '--service-dir', source['directory'],
                       '--database', source['database'], '--port', str(port)]
            env['GTT_PG_CONFIG'] = source['config']
            env['GTT_WORKSPACE_ROOT'] = source['tree']
        return command, env

    def _process_directory(self, process):
        from service_runtime import argv_of
        for arg in argv_of(process.get('command'))[1:]:
            if Path(arg).is_absolute() and str(arg).endswith(('.py', '.mjs', '.js')):
                return str(Path(arg).parent)
        parent = self.processes.get(process.get('parent'), {})
        executable = Path(parent.get('executable') or '')
        if executable.is_absolute() and executable.name.lower() == 'python.exe' and executable.parent.name.lower() == 'scripts':
            return str(executable.parents[2])
        return ''

    def _valid_process(self, record):
        from service_runtime import command_matches
        actual = self.processes.get(record.get('pid'))
        try:
            return bool(actual and record.get('created') and record.get('command')
                        and same_creation(record['created'], actual.get('created'))
                        and command_matches(record['command'], actual.get('command')))
        except (ValueError, TypeError):
            return False

    def _known_record_roots(self):
        roots = []
        for tree in [self.repo, *self._worktree_roots]:
            for name in ('service-console', 'response-capture-previews'):
                root = Path(tree) / 'other/diagnostics' / name
                if root not in roots:
                    roots.append(root)
        return roots

    def _canonical_record(self, record):
        result = dict(record)
        job = record.get('original_record')
        if job and job.get('service_pid'):
            try:
                home = Path(job['record']).parent
                if not any(home.parent == root for root in self._known_record_roots()):
                    return result
                child = read_json(home, 'service/ownership.json', 128 * 1024)
                if child.get('pid') != job['service_pid'] or child.get('chat') != job.get('chat') or not same_creation(child.get('created'), job.get('service_created')):
                    return result
                result.update(pid=child['pid'], created=child['created'], cwd=child['cwd'], command=child['command'])
            except (OSError, ValueError, TypeError, KeyError):
                return result
        return result

    def _control_channel(self, record):
        from service_control import read_control
        candidates = [self._canonical_record(record)]
        if not record.get('control_nonce'):
            if getattr(self, '_control_records_cache', None) is None:
                self._control_records_cache = []
                for root in self._known_record_roots():
                    for folder in root.glob('*') if root.is_dir() else []:
                        try:
                            saved = read_json(root, folder.name + '/ownership.json', 128 * 1024)
                            if saved.get('service_pid'):
                                saved = dict(saved, original_record=saved)
                            self._control_records_cache.append(self._canonical_record(saved))
                        except (OSError, ValueError, TypeError, KeyError):
                            pass
            candidates.extend(value for value in self._control_records_cache if value.get('pid') == record.get('pid'))
        for candidate in candidates:
            if not self._valid_process(candidate):
                continue
            for root in self._known_record_roots():
                if read_control(candidate, root, candidate.get('chat')):
                    return candidate, root
        return None

    def _stop_details(self, record):
        record = self._canonical_record(record)
        if not self._valid_process(record):
            reject('进程身份已变化或资料不完整，请刷新后重新选择实例。', 403)
        spec = self.registry.get(record.get('service_id')) or self._specs.get(record.get('service_id')) or {}
        kind = record.get('kind') or ('original' if record.get('original') else spec.get('kind'))
        if kind in ('postgres', 'docker'):
            reject('共享依赖必须从对应服务卡片预检，不能按普通进程强制关闭。')
        channel = self._control_channel(record)
        if kind == 'capture':
            health = self.health(record)
            if health.get('pid') == record['pid'] and health.get('active_sessions'):
                reject('仍有活动抓取或文件尚未归档，请先在游戏行停止并保存。')
            shutdown = health.get('capabilities', {}).get('shutdown') is True or health.get('can_shutdown') is True
            if shutdown and health.get('pid') == record['pid']:
                if health.get('created') and not same_creation(health['created'], record['created']):
                    reject('抓取服务身份已变化，请重新预检。')
                if health.get('active_sessions'):
                    reject('仍有活动抓取或文件尚未归档，请先在游戏行停止并保存。')
                return record, 'capture', None
        if channel:
            return record, 'persistent', channel
        handle = self._handles.get(record.get('id'))
        if record.get('chat') == self.owner_chat and handle and handle.stdin and kind in ('watch', 'node', 'demo', 'compute'):
            return record, 'pipe', None
        return record, 'force', None

    def _expose_confirmed_operations(self, rows, actions):
        for row in rows.values():
            if row['id'] in ('advanced.postgres', 'advanced.docker'):
                continue
            for instance in row.get('instances', []):
                record = actions.get(instance['id'])
                if not record or not record.get('pid') or instance.get('status') == 'stopping':
                    continue
                if record.get('pid') not in self.processes:
                    continue
                try:
                    canonical, mode, channel = self._stop_details(record)
                    cross = canonical.get('chat') != self.owner_chat
                    instance.update(can_stop=True, requires_confirmation=cross or mode == 'force' or canonical.get('service_id') in ('fixed.gateway', 'fixed.admin', 'fixed.rtp', 'fixed.mock'), stop_mode=mode,
                                    execution_label='强制关闭' if mode == 'force' else '关闭服务')
                    if instance.get('status') == 'unknown':
                        instance['status'], instance['running_count'] = 'running', 1
                    instance['reason'] = ('没有可核验的正常退出通道，强制关闭前会列出数据风险。' if mode == 'force'
                                          else '该实例属于其他聊天或既有进程，关闭前需要确认影响。' if cross else '')
                except (OSError, ValueError, TypeError, KeyError) as error:
                    instance['can_stop'], instance['reason'] = False, str(error)
        if self.shared_services:
            try:
                shared = self.shared_services.snapshot(inventory=getattr(self, '_latest_inventory', None))
                for entry in shared.get('services', []):
                    if entry.get('id') in ('advanced.postgres', 'advanced.docker'):
                        base = rows.get(entry['id'], {})
                        base.update(entry)
                        base.setdefault('instances', [])
                        base.setdefault('can_logs', False)
                        base.setdefault('logs_available', False)
                        base['requires_confirmation'] = True
                        rows[entry['id']] = base
            except (OSError, ValueError, TypeError) as error:
                for identifier in ('advanced.postgres', 'advanced.docker'):
                    rows[identifier].update(can_start=False, can_stop=False, reason=str(error))

    def _tree_identity(self, record):
        descendants = self._descendants(record['pid'])
        values = [self.processes[record['pid']], *descendants]
        pids = {value['pid'] for value in values}
        if any(value.get('parent') in pids and value['pid'] not in pids for value in self.processes.values()):
            reject('子进程的创建时间或归属无法完整核验，未准备强制关闭。')
        if any(not value.get('created') or not value.get('command') for value in values):
            reject('进程树身份资料不足，无法准备关闭。')
        return sorted([{'pid': value['pid'], 'created': value['created'], 'command': value['command'], 'parent': value.get('parent'),
                        'ports': sorted(v['port'] for v in self.listeners if v['pid'] == value['pid'])} for value in values], key=lambda value: value['pid'])

    def _operation_plan(self, identifier, action, planned_port=None):
        if action not in ('start', 'stop') or not isinstance(identifier, str):
            reject('预检只接受已登记服务的启动或关闭操作。', 400)
        if self._snapshot.get('error'):
            reject('实时状态核验失败，未执行服务操作。', 503)
        if identifier in ('advanced.postgres', 'advanced.docker'):
            if not self.shared_services:
                reject('当前环境尚未识别可核验的共享服务管理入口。')
            shared = self.shared_services.prepare(identifier, action, inventory=getattr(self, '_latest_inventory', None))
            return {'id': identifier, 'action': action, 'requires_confirmation': True, 'mode': 'shared', 'shared': shared,
                    'execution_label': shared.get('execution_label') or ('启动共享服务' if action == 'start' else '关闭共享服务'),
                    'warnings': shared.get('warnings', []), 'targets': shared.get('targets', []),
                    'identity': shared.get('identity_fingerprint') or fingerprint(shared)}
        if action == 'start':
            spec = self.registry.get(identifier) or self._specs.get(identifier)
            if not spec:
                reject('该实例尚无已核验的重开方案；请选择已登记的服务入口。', 404)
            reason = self._available(spec)
            if reason:
                reject(reason)
            row = next((r for r in self._snapshot['services'] if r['id'] == identifier), {})
            if any(v.get('status') == 'starting' for v in row.get('instances', [])):
                reject('该服务正在启动，请等待。')
            cross = bool(spec.get('worktree') and Path(spec['worktree']).resolve() != self.repo)
            active = [v for v in row.get('instances', []) if v.get('status') in ('running', 'starting', 'stopping')]
            if not active and row.get('status') == 'running' and row.get('pid'):
                active = [row]
            warnings = ['将在其他工作区启动新的独立实例，使用该工作区已经核验的运行文件及隔离配置。'] if cross else []
            if active:
                warnings.append('该服务已有运行实例，本次会新增实例并占用额外端口和资源；请确认是否需要同时运行。')
            source = self._external_start_spec(spec) if spec.get('external_registered') else None
            if spec.get('external_registered'):
                warnings.append('这是已登记的既有服务重开入口；将创建新进程，不恢复已关闭进程中的临时状态。')
            if warnings and spec.get('default_port'):
                occupied = {value['port'] for value in self.listeners} | self._ports | {self.control_port}
                if planned_port is not None:
                    if planned_port in occupied:
                        reject('预检选定的启动端口已被占用，请重新预检。')
                    with socket.socket() as sock:
                        try:
                            sock.bind(('127.0.0.1', planned_port))
                        except OSError:
                            reject('预检选定的启动端口已不可用，请重新预检。')
                else:
                    with socket.socket() as sock:
                        preferred = int(spec['default_port'])
                        try:
                            sock.bind(('127.0.0.1', preferred if preferred not in occupied else 0))
                        except OSError:
                            sock.bind(('127.0.0.1', 0))
                        planned_port = sock.getsockname()[1]
            targets = [{'id': identifier, 'name': spec.get('name', identifier), 'cwd': spec.get('worktree') or str(self.repo), 'mode': 'start', 'port': planned_port or spec.get('default_port')}]
            return {'id': identifier, 'action': action, 'requires_confirmation': bool(warnings), 'mode': 'start', 'planned_port': planned_port,
                    'execution_label': '启动服务', 'targets': targets, 'warnings': warnings,
                    'identity': fingerprint([spec, source, [{'pid': v.get('pid'), 'created': v.get('created'), 'port': v.get('port')} for v in active]])}
        record = self._resolve_action(identifier)
        if record.get('service_id') == 'advanced.games-batch':
            children = [self._operation_plan('run.' + child, 'stop') for child in record.get('children', [])
                        if self.records.get(child, {}).get('state') in ('starting', 'running')]
            return {'id': identifier, 'action': action, 'mode': 'group', 'record': record, 'children': children,
                    'requires_confirmation': any(c['requires_confirmation'] for c in children), 'execution_label': '关闭服务组',
                    'warnings': list(dict.fromkeys(w for c in children for w in c['warnings'])),
                    'targets': [t for c in children for t in c['targets']], 'identity': [self._plan_identity(c) for c in children]}
        record, mode, channel = self._stop_details(record)
        cross = record.get('chat') != self.owner_chat
        warnings = []
        if cross:
            warnings.append('该实例属于其他聊天或既有服务。关闭会中断正在使用它的页面、任务和连接。')
        if mode == 'force':
            warnings.append('没有可核验的正常退出通道，将精确终止本实例及已核验子进程；未完成的抓取、钱包事务或任务可能中断。')
        if record.get('service_id') in ('fixed.gateway', 'fixed.admin', 'fixed.rtp', 'fixed.mock'):
            warnings.append('依赖此实例的页面或后台任务会暂时不可用；共享数据库不会随该实例一起关闭。')
        identity = self._tree_identity(record)
        name = (self.registry.get(record['service_id']) or self._specs.get(record['service_id']) or {}).get('name', identifier)
        targets = [{'id': identifier, 'name': name, 'pid': record['pid'], 'created': record['created'],
                    'port': record.get('port'), 'cwd': record.get('cwd', ''), 'mode': mode,
                    'child_count': len(identity) - 1}]
        return {'id': identifier, 'action': action, 'mode': mode, 'record': record, 'channel': channel,
                'requires_confirmation': bool(warnings), 'execution_label': '强制关闭' if mode == 'force' else '关闭服务',
                'warnings': warnings, 'targets': targets, 'identity': identity}

    def _plan_identity(self, plan):
        return fingerprint({key: plan.get(key) for key in ('id', 'action', 'mode', 'requires_confirmation', 'identity', 'targets', 'warnings')})

    def prepare(self, identifier, action):
        with self._operation_lock:
            self.refresh(wait=True)
            plan = self._operation_plan(identifier, action)
            result = {key: copy.deepcopy(plan[key]) for key in ('requires_confirmation', 'execution_label', 'warnings', 'targets')}
            if plan['requires_confirmation']:
                token = uuid.uuid4().hex + uuid.uuid4().hex
                self._confirmations = {k: v for k, v in self._confirmations.items() if v['expires'] > time.monotonic()}
                self._confirmations[token] = {'id': identifier, 'action': action, 'fingerprint': self._plan_identity(plan), 'expires': time.monotonic() + 120, 'planned_port': plan.get('planned_port')}
                result.update(confirmation_id=token, expires_at=(datetime.now(timezone.utc) + timedelta(seconds=120)).isoformat())
            return result

    def _confirmed_plan(self, identifier, action, confirmation_id):
        receipt = self._confirmations.pop(confirmation_id, None) if isinstance(confirmation_id, str) else None
        self.refresh(wait=True)
        plan = self._operation_plan(identifier, action, planned_port=receipt.get('planned_port') if receipt else None)
        if confirmation_id is not None or plan['requires_confirmation']:
            if not receipt or receipt['expires'] <= time.monotonic() or receipt['id'] != identifier or receipt['action'] != action:
                reject('操作确认已失效或不属于本次操作，请重新预检并确认。')
            if receipt['fingerprint'] != self._plan_identity(plan):
                reject('服务身份、退出方式或影响范围已经变化，请重新预检并确认。')
        return plan

    def start(self, identifier, confirmation_id=None):
        with self._operation_lock:
            plan = self._confirmed_plan(identifier, 'start', confirmation_id)
            if plan['mode'] == 'shared':
                return self.shared_services.execute(plan['shared'])
            return self._start_legacy(identifier, planned_port=plan.get('planned_port'))

    def stop(self, identifier, confirmation_id=None):
        with self._operation_lock:
            plan = self._confirmed_plan(identifier, 'stop', confirmation_id)
            result = self._execute_stop_plan(plan)
            self._wake.set()
            return result

    def _execute_stop_plan(self, plan):
        if plan['mode'] == 'shared':
            return self.shared_services.execute(plan['shared'])
        if plan['mode'] == 'group':
            for child in plan['children']:
                self._execute_stop_plan(child)
            plan['record']['state'] = 'stopping'
            self._save(plan['record'])
            return {'ok': True, 'state': 'stopping', 'message': '已请求本组实例关闭，等待实际进程结束。'}
        record, mode = plan['record'], plan['mode']
        if mode == 'capture':
            self._shutdown_capture(record)
        elif mode == 'persistent':
            from service_control import request_stop
            candidate, root = plan['channel']
            probe = (lambda pid: self.processes.get(pid)) if self._injected_inventory else None
            request_stop(candidate, root, candidate['chat'], inspector=probe)
        elif mode == 'pipe':
            handle = self._handles.get(record['id'])
            if not handle or not handle.stdin:
                reject('正常退出通道已经断开，请重新预检。')
            handle.stdin.write(b'stop\n')
            handle.stdin.flush()
        elif mode == 'force':
            self.refresh(wait=True)
            fresh = self._operation_plan(plan['id'], 'stop')
            if self._plan_identity(fresh) != self._plan_identity(plan):
                reject('进程树在执行前已经变化，未强制关闭，请重新预检。')
            for process in reversed(self._descendants(record['pid'])):
                self.terminator(dict(record, pid=process['pid'], created=process['created'], command=process['command']), process)
            self.terminator(record, self.processes[record['pid']])
        if record.get('id') in self.records:
            self.records[record['id']]['state'] = 'stopping'
            self._save(self.records[record['id']])
        return {'ok': True, 'id': plan['id'], 'state': 'stopping', 'message': '已提交关闭，实际状态会自动更新。'}
