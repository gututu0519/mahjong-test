"""批量关闭预检：保护当前页面、未保存抓取和保留服务的依赖。"""
import copy
from datetime import datetime, timezone, timedelta
from http.client import HTTPConnection, HTTPException
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlsplit
import uuid

from original_games import read_json, same_creation
from service_confirmation import fingerprint, reject


class ServiceCleanup:
    def __init__(self, manager, capture_probe=None):
        self.manager = manager
        self.capture_probe = capture_probe or self._capture_state
        self.confirmations = {}

    def _origin(self, value):
        try:
            source = urlsplit(value)
            if (source.scheme != 'http' or source.hostname not in ('127.0.0.1', 'localhost') or not source.port
                    or source.username or source.password or source.path or source.query or source.fragment
                    or value != f'http://{source.hostname}:{source.port}'):
                raise ValueError()
            return value, source.port
        except (TypeError, ValueError):
            reject('当前抓取页面来源无效，请重新打开页面。', 400)

    def _capture_state(self, record):
        """旧采集器只有完成状态仍不足以证明落盘；进一步核对固定归档目录。"""
        manager = self.manager
        try:
            health = manager.health(record)
            if health.get('pid') == record.get('pid') and type(health.get('active_sessions')) is int:
                if health.get('created') and not same_creation(health['created'], record['created']):
                    return 'unknown'
                return 'active' if health['active_sessions'] else 'idle'
            port = record.get('port')
            if type(port) is not int or not 0 < port < 65536:
                return 'unknown'
            connection = HTTPConnection('127.0.0.1', port, timeout=1)
            try:
                connection.request('GET', '/api/sessions')
                response = connection.getresponse()
                raw = response.read(16 * 1024 * 1024 + 1)
                if response.status != 200 or len(raw) > 16 * 1024 * 1024:
                    return 'unknown'
                records = json.loads(raw)
            finally:
                connection.close()
            if not isinstance(records, list) or any(not isinstance(value, dict) for value in records):
                return 'unknown'
            if any(value.get('state') in ('starting', 'recording', 'stopping', 'saving', 'running') for value in records):
                return 'active'
            if any(value.get('state') not in ('completed', 'complete', 'error') for value in records):
                return 'unknown'
            directory = Path(manager._process_directory(manager.processes.get(record['pid'], {})))
            if not directory.is_absolute() or directory.name != 'response-capture':
                return 'unknown'
            from capture_layout import session_folder
            for value in records:
                sid = value.get('id')
                if not isinstance(sid, str) or not re.fullmatch(r'[0-9a-f]{32}', sid):
                    return 'unknown'
                folder = session_folder(directory / 'captures', sid)
                if not folder:
                    return 'unknown'
                manifest = read_json(folder, 'manifest.json')
                if manifest.get('id') != sid or manifest.get('state') not in ('completed', 'complete', 'error'):
                    return 'unknown'
            return 'idle'
        except (OSError, HTTPException, ValueError, TypeError, KeyError):
            return 'unknown'

    def _collect(self, current_origin):
        origin, current_port = self._origin(current_origin)
        manager = self.manager
        manager.refresh(wait=True)
        snapshot = manager.snapshot()
        if snapshot.get('error'):
            reject('服务状态核验失败，不能准备批量关闭。', 503)
        items, records, seen = [], {}, set()
        rows = snapshot.get('services', [])
        by_service = {row['id']: row for row in rows}
        shared_ids = ('advanced.postgres', 'advanced.docker')
        for row in rows:
            candidates = [row] if row['id'] in shared_ids else row.get('instances', []) or ([row] if row.get('pid') else [])
            for candidate in candidates:
                if candidate.get('status') not in ('running', 'starting', 'stopping', 'unknown'):
                    continue
                identifier = candidate['id']
                shared = identifier in shared_ids
                key = ('shared', identifier) if shared else (candidate.get('pid'), candidate.get('created'))
                if key in seen or not shared and not candidate.get('pid'):
                    continue
                seen.add(key)
                try:
                    record = manager._resolve_action(identifier) if not shared else {'service_id': identifier, 'kind': 'shared'}
                    record = manager._canonical_record(record)
                except (ValueError, KeyError, TypeError):
                    record = {'service_id': row['id'], 'pid': candidate.get('pid'), 'created': candidate.get('created'), 'kind': 'unknown'}
                spec = manager.registry.get(record.get('service_id')) or manager._specs.get(record.get('service_id')) or {}
                kind = record.get('kind') or ('original' if record.get('original') else spec.get('kind'))
                name = row.get('name') if row['id'] not in ('fixed.capture',) else candidate.get('name', row.get('name'))
                item = {'id': identifier, 'name': name or identifier, 'pid': candidate.get('pid'), 'created': candidate.get('created'),
                        'port': candidate.get('port'), 'status': candidate['status'], 'required_keep': False,
                        'default_keep': shared or kind == 'watch', 'keep_reason': '', 'dependencies': []}
                if shared:
                    item['keep_reason'] = '共享依赖，建议保留；取消保留后仍需确认其全部影响。'
                    if not row.get('can_stop'):
                        item.update(required_keep=True, default_keep=True, keep_reason=row.get('reason') or '没有可核验的共享服务正常关闭入口。')
                elif kind == 'capture':
                    try:
                        state = self.capture_probe(record)
                    except (OSError, ValueError, TypeError, KeyError):
                        state = 'unknown'
                    if candidate.get('port') == current_port:
                        item.update(required_keep=True, default_keep=True, keep_reason='当前页面对应的抓取服务，必须保留。')
                    elif state != 'idle':
                        item.update(required_keep=True, default_keep=True, keep_reason='仍有活动抓取或尚未保存，必须保留。' if state == 'active' else '无法确认抓取已全部保存，自动保留。')
                if not shared and not candidate.get('can_stop'):
                    item.update(required_keep=True, default_keep=True, keep_reason=item['keep_reason'] or candidate.get('reason') or '该实例暂时无法核验安全关闭条件。')
                if kind == 'watch' and not item['keep_reason']:
                    item['keep_reason'] = '维护表监督器，建议保留以继续核对抓取记录。'
                if record.get('service_id') == 'demo.mahjong-ways2':
                    item['keep_reason'] = '同一进程同时提供试玩大厅和麻将入口；关闭会同时中断两个入口。'
                records[identifier] = dict(record, _cleanup_kind=kind)
                items.append(item)
        controller_pid = getattr(manager, 'control_pid', os.getpid())
        controller = manager.processes.get(controller_pid, {})
        controller_id = 'cleanup.controller.' + str(controller_pid)
        items = [value for value in items if value.get('pid') != controller_pid]
        items.append({'id': controller_id, 'name': '当前服务控制台', 'pid': controller_pid, 'created': controller.get('created'),
                      'port': manager.control_port, 'status': 'running', 'required_keep': True, 'default_keep': True,
                      'keep_reason': '当前操作入口，必须保留。', 'dependencies': []})
        records[controller_id] = controller
        by_id = {item['id']: item for item in items}
        by_pid = {item['pid']: item['id'] for item in items if item.get('pid')}
        pg = by_service.get('advanced.postgres', {})
        pg_id = 'advanced.postgres' if 'advanced.postgres' in by_id else None
        for item in items:
            record = records[item['id']]
            kind = record.get('_cleanup_kind')
            if pg_id and (record.get('service_id') in ('fixed.gateway', 'fixed.admin', 'fixed.mock', 'fixed.rtp')
                          or kind == 'demo' or kind == 'original' and record.get('mode') == 'adapter'):
                item['dependencies'].append(pg_id)
            if kind == 'watch':
                from service_runtime import argv_of
                args = argv_of(record.get('command'))
                try:
                    url = urlsplit(args[args.index('--capture-url') + 1])
                    for capture in items:
                        if capture.get('port') == url.port and records[capture['id']].get('_cleanup_kind') == 'capture':
                            item['dependencies'].append(capture['id'])
                except (ValueError, IndexError):
                    pass
        if pg_id:
            for dependent in pg.get('impact', {}).get('dependents', []):
                identifier = by_pid.get(dependent.get('pid'))
                if identifier and identifier != pg_id:
                    by_id[identifier]['dependencies'].append(pg_id)
            if pg.get('method') == 'docker-container' and 'advanced.docker' in by_id:
                by_id[pg_id]['dependencies'].append('advanced.docker')
        for item in items:
            item['dependencies'] = sorted(set(item['dependencies']))
        while True:
            protected = {item.get('pid') for item in items if item['required_keep']}
            added = False
            for item in items:
                if item['required_keep'] or not item.get('pid'):
                    continue
                if any(child['pid'] in protected for child in manager._descendants(item['pid'])):
                    item.update(required_keep=True, default_keep=True, keep_reason='进程树中包含当前窗口或必须保留的服务，自动保留该父实例。')
                    added = True
            if not added:
                break
        return origin, current_port, sorted(items, key=lambda item: (not item['required_keep'], item['name'], item['id'])), records

    def options(self, current_origin):
        with self.manager._operation_lock:
            _, port, items, _ = self._collect(current_origin)
            return {'items': items, 'current_capture_port': port}

    def _build(self, keep_ids, current_origin):
        if not isinstance(keep_ids, list) or len(keep_ids) > 1024 or any(not isinstance(value, str) or not 0 < len(value) <= 200 for value in keep_ids):
            reject('保留列表格式无效。', 400)
        origin, port, items, records = self._collect(current_origin)
        by_id = {item['id']: item for item in items}
        if any(identifier not in by_id for identifier in keep_ids):
            reject('服务列表已经变化，请重新选择保留项。')
        kept = set(keep_ids) | {item['id'] for item in items if item['required_keep']}
        while True:
            before = set(kept)
            for identifier in list(kept):
                kept.update(by_id[identifier]['dependencies'])
            # 不允许强制关闭的进程树包含另一个被保留的实际实例。
            kept_pids = {by_id[identifier].get('pid') for identifier in kept}
            for item in items:
                if item['id'] in kept or not item.get('pid'):
                    continue
                if any(value['pid'] in kept_pids for value in self.manager._descendants(item['pid'])):
                    kept.add(item['id'])
                    item['keep_reason'] = '进程树中包含已勾选保留的服务，自动保留该父实例。'
            if kept == before:
                break
        plans = {item['id']: self.manager._operation_plan(item['id'], 'stop') for item in items if item['id'] not in kept}
        covered = {}
        for identifier, plan in list(plans.items()):
            if plan['mode'] != 'force':
                continue
            descendants = {value['pid'] for value in plan.get('identity', []) if value['pid'] != plan['record']['pid']}
            for child_id, child in plans.items():
                if child_id != identifier and child.get('record', {}).get('pid') in descendants:
                    previous = covered.get(child_id)
                    if previous is None or len(plans[previous].get('identity', [])) < len(plan.get('identity', [])):
                        covered[child_id] = identifier
        for child_id in covered:
            plans.pop(child_id, None)
        ordered, visited = [], set()
        def visit(identifier):
            if identifier in visited:
                return
            visited.add(identifier)
            for dependency in by_id[identifier]['dependencies']:
                if dependency in plans:
                    visit(dependency)
            ordered.append(identifier)
        for identifier in sorted(plans):
            visit(identifier)
        ordered.reverse()
        target_plans = [plans[identifier] for identifier in ordered]
        warnings = ['仅关闭已列出的服务进程，不删除抓取记录、原版文件、数据库或其他磁盘数据。']
        warnings.extend(item['name'] + '：' + item['keep_reason'] for item in items if item['id'] in kept and '自动保留该父实例' in item['keep_reason'])
        warnings.extend(by_id[parent]['name'] + ' 的强制关闭范围包含 ' + by_id[child]['name'] + '，合并为一个进程树操作，不重复关闭。' for child, parent in covered.items())
        warnings.extend(warning for plan in target_plans for warning in plan['warnings'])
        if any(records[identifier].get('service_id') == 'demo.mahjong-ways2' for identifier in plans):
            warnings.append('试玩大厅与麻将胡了 2 使用同一进程，关闭该实例会同时关闭两个入口。')
        identity = {'origin': origin, 'keep_ids': sorted(kept),
                    'items': [{key: item.get(key) for key in ('id', 'pid', 'created', 'port', 'status', 'required_keep', 'dependencies')} for item in items],
                    'processes': {identifier: {key: records[identifier].get(key) for key in ('pid', 'created', 'command', 'chat')} for identifier in by_id},
                    'plans': [self.manager._plan_identity(plan) for plan in target_plans]}
        return {'origin': origin, 'keep_ids': sorted(kept), 'plans': target_plans, 'items': items,
                'records': records,
                'warnings': list(dict.fromkeys(warnings)), 'targets': [target for plan in target_plans for target in plan['targets']],
                'fingerprint': fingerprint(identity), 'current_capture_port': port}

    def _expected_reduction(self, original, fresh, completed_pids, completed_shared):
        """只放行本批已核验退出所造成的范围缩小；新进程、新连接一律不沿用确认。"""
        if any(original.get(key) != fresh.get(key) for key in ('id', 'action', 'mode')):
            return False
        if original['mode'] == 'shared':
            before, after = copy.deepcopy(original['shared']), copy.deepcopy(fresh['shared'])
            left, right = before.get('identity', {}), after.get('identity', {})
            prior = left.pop('dependents', [])
            current = right.pop('dependents', [])
            if any(value not in prior for value in current):
                return False
            if any(value.get('pid') not in completed_pids for value in prior if value not in current):
                return False
            if original['id'] == 'advanced.docker' and 'advanced.postgres' in completed_shared:
                allowed = completed_shared['advanced.postgres']
                old_containers, new_containers = left.get('containers', []), right.get('containers', [])
                if len(old_containers) != len(new_containers):
                    return False
                restored = []
                for container in new_containers:
                    value = dict(container)
                    old = next((c for c in old_containers if c.get('id') == value.get('id')), None)
                    if old and value.get('id') == allowed and old.get('running') is True and value.get('running') is False:
                        value['running'] = True
                    restored.append(value)
                right['containers'] = restored
            return (left == right and before.get('internal') == after.get('internal')
                    and before.get('method') == after.get('method'))
        if not isinstance(original.get('identity'), list) or not isinstance(fresh.get('identity'), list):
            return False
        before, after = original['identity'], fresh['identity']
        return (original.get('warnings') == fresh.get('warnings')
                and all(value in before for value in after)
                and all(value['pid'] in completed_pids for value in before if value not in after))

    def prepare(self, keep_ids, current_origin):
        with self.manager._operation_lock:
            batch = self._build(keep_ids, current_origin)
            token = uuid.uuid4().hex + uuid.uuid4().hex
            self.confirmations = {key: value for key, value in self.confirmations.items() if value['expires'] > time.monotonic()}
            self.confirmations[token] = {'expires': time.monotonic() + 120, 'origin': batch['origin'], 'keep_ids': batch['keep_ids'], 'fingerprint': batch['fingerprint']}
            return {'requires_confirmation': True, 'confirmation_id': token, 'expires_at': (datetime.now(timezone.utc) + timedelta(seconds=120)).isoformat(),
                    'execution_label': '关闭未保留的服务', 'warnings': batch['warnings'], 'targets': batch['targets'],
                    'close_count': len(batch['plans']), 'kept_count': len(batch['keep_ids']), 'keep_ids': batch['keep_ids'],
                    'kept_items': [item for item in batch['items'] if item['id'] in batch['keep_ids']]}

    def execute(self, confirmation_id, current_origin):
        with self.manager._operation_lock:
            receipt = self.confirmations.pop(confirmation_id, None) if isinstance(confirmation_id, str) else None
            origin, _ = self._origin(current_origin)
            if not receipt or receipt['expires'] <= time.monotonic() or receipt['origin'] != origin:
                reject('批量关闭确认已失效或页面来源变化，请重新预览。')
            batch = self._build(receipt['keep_ids'], origin)
            if batch['fingerprint'] != receipt['fingerprint']:
                reject('服务身份、保留集合或依赖影响已经变化，尚未关闭任何实例，请重新预览。')
            results = []
            items = {item['id']: item for item in batch['items']}
            submitted_pids, completed_shared = set(), {}
            for plan in batch['plans']:
                identifier = plan['id']
                name = items[identifier]['name']
                try:
                    self.manager.refresh(wait=True)
                    fresh_rows = {row['id']: row for row in self.manager.snapshot().get('services', [])}
                    dependent_ids = [key for key, item in items.items() if identifier in item['dependencies']]
                    live_dependencies = [key for key in dependent_ids if items[key].get('pid') in self.manager.processes
                                         or key in ('advanced.postgres', 'advanced.docker') and fresh_rows.get(key, {}).get('status') != 'stopped']
                    failed_dependencies = [value['id'] for value in results if value['id'] in dependent_ids and value['state'] == 'failed']
                    if live_dependencies or failed_dependencies:
                        results.append({'id': identifier, 'name': name, 'state': 'skipped', 'message': '仍有依赖此服务的实例运行，已跳过，保留服务可用。'})
                        continue
                    pid = plan.get('record', {}).get('pid')
                    if pid and pid not in self.manager.processes:
                        message = '该实例已由本批前项关闭范围覆盖并退出，未重复请求关闭。' if pid in submitted_pids else '该实例已退出，未重复请求关闭。'
                        results.append({'id': identifier, 'name': name, 'state': 'skipped', 'message': message})
                        continue
                    fresh = self.manager._operation_plan(identifier, 'stop')
                    target_pids = {value['pid'] for value in fresh.get('identity', [])} if isinstance(fresh.get('identity'), list) else {pid}
                    unsafe_capture = False
                    for capture in batch['records'].values():
                        if capture.get('_cleanup_kind') != 'capture' or capture.get('pid') not in target_pids:
                            continue
                        try:
                            safe = self.capture_probe(capture) == 'idle'
                        except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
                            safe = False
                        if not safe:
                            unsafe_capture = True
                            break
                    if unsafe_capture:
                        results.append({'id': identifier, 'name': name, 'state': 'skipped', 'message': '执行前发现活动抓取或无法确认已保存，已保留该实例及关联进程树。'})
                        continue
                    if self.manager._plan_identity(fresh) != self.manager._plan_identity(plan):
                        completed = {pid for pid in submitted_pids if pid not in self.manager.processes}
                        if not self._expected_reduction(plan, fresh, completed, completed_shared):
                            results.append({'id': identifier, 'name': name, 'state': 'skipped', 'message': '该实例身份、进程树或退出方式已变化，未扩大关闭范围。'})
                            continue
                    response = self.manager._execute_stop_plan(fresh)
                    if isinstance(plan.get('identity'), list):
                        submitted_pids.update(value['pid'] for value in plan['identity'])
                    if identifier in ('advanced.postgres', 'advanced.docker'):
                        completed_shared[identifier] = plan.get('shared', {}).get('identity', {}).get('container', {}).get('id')
                    results.append({'id': identifier, 'name': name, 'state': 'stopping', 'message': response.get('message') or '已提交关闭，等待实际退出。'})
                except (OSError, ValueError, TypeError, KeyError, HTTPException, subprocess.SubprocessError) as error:
                    results.append({'id': identifier, 'name': name, 'state': 'failed', 'message': str(error) if isinstance(error, ValueError) else '关闭请求失败；其余实例仅按已确认范围处理。'})
            self.manager._wake.set()
            counts = {state: sum(value['state'] == state for value in results) for state in ('stopping', 'failed', 'skipped')}
            return {'ok': not counts['failed'] and not counts['skipped'], 'results': results,
                    'submitted_count': counts['stopping'], 'failed_count': counts['failed'], 'skipped_count': counts['skipped']}
