"""实时、只读的采集完整度检查；不使用本地实现状态作为采集标准。"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import re
import struct
import time
from urllib.parse import urlsplit

import feature_evidence as feature_detector

REQUIREMENTS = Path(__file__).with_name('capture-requirements.json')
DETAIL_LIMIT = 80


def _requirements():
    data = json.loads(REQUIREMENTS.read_text(encoding='utf-8-sig'))
    if data.get('version') != 1 or not isinstance(data.get('games'), dict):
        raise ValueError('requirements')
    return data['games']


def _path(url):
    try:
        p = urlsplit(url).path
    except (ValueError, TypeError):
        return None
    if not p.startswith('/') or len(p) > 512 or any(ord(c) < 32 for c in p):
        return None
    return p


def _body_path(root, row):
    name = row.get('body')
    if not isinstance(name, str) or not re.fullmatch(r'bodies/[0-9]+(?:\.request)?\.[A-Za-z0-9]+', name):
        return None
    p = (root / name).resolve()
    declared = row.get('size')
    if type(declared) is not int or declared < 0:
        return None
    return p if p.is_relative_to(root) and p.is_file() and p.stat().st_size == declared else None


def _saved(root, row):
    try:
        return row.get('state') == 'complete' and row.get('status') == 200 and _body_path(root, row) is not None
    except OSError:
        return False


def _safe_example(path):
    # 未识别路径不能假定没有账号或令牌；仅展示首段和固定省略标记。
    first = path.strip('/').split('/')[0] if path else ''
    return '/' + first + '/[未分类路径已省略]' if re.fullmatch(r'[A-Za-z0-9_-]{1,30}', first) else '/[未分类路径已省略]'


def _read(root, row, limit=8 * 1024 * 1024):
    path = _body_path(root, row)
    if path is None or path.stat().st_size > limit:
        raise ValueError('body unavailable')
    content = path.read_bytes()
    if len(content) != row.get('size'):
        raise ValueError('body changed during read')
    return content


def _cash_features(rows, root, targets):
    """只验证已确认的普通局金额关系；未确认特殊状态保持未知/候选。"""
    common = {'sid': (1, 'string'), 'psid': (2, 'string'), 'st': (3, 'int32'), 'nst': (4, 'int32'),
              'blb': (12, 'double'), 'blab': (13, 'double'), 'bl': (14, 'double'),
              'tb': (15, 'double'), 'tbb': (16, 'double'), 'tw': (17, 'double'),
              'ml': (51, 'int32'), 'cs': (52, 'double')}
    fields = {k: {'id': n, 'type': t} for k, (n, t) in common.items()}
    fields.update({k: {'id': n, 'type': t, 'rule': 'repeated'} for k, n, t in [('rl', 53, 'int32'), ('rv', 106, 'double'), ('orl', 107, 'int32'), ('orv', 108, 'double'), ('rsrl', 109, 'int32'), ('rsrv', 110, 'double')]})
    fields['nfp'] = {'id': 111, 'type': 'int32', 'keyType': 'int32'}
    schema = {'__root__': {'fields': fields}}
    evidence, nudge, respin, seen = [], [], [], set()
    wins = losses = invalid = 0
    for row in rows:
        if _path(row.get('url')) != '/game-api/cash-mania/v4/Spin' or not _saved(root, row):
            continue
        try:
            request_bytes = feature_detector._saved_bytes(root, row.get('request_body'))
            raw_request, seed = feature_detector.protocol.unpack(request_bytes, salt=23)
            request = feature_detector.protocol.decode_request(raw_request)
            response_bytes = _read(root, row, 16384)
            raw, _ = feature_detector.protocol.unpack(response_bytes, seed, salt=23)
            tx = feature_detector._decode(raw, schema)
            if tx.get('st') != 1 or tx.get('nst') != 1 or request.get('fb', 0):
                continue
            board, values = tx.get('rl'), tx.get('rv')
            if not isinstance(board, list) or not isinstance(values, list) or len(board) != 9 or len(values) != 9 or not all(type(s) is int for s in board):
                raise ValueError('board')
            if not all(0 <= board[p] <= 5 for p in [0, 1, 2, 6, 7, 8]) or not 0 <= board[4] <= 11:
                continue
            if not all(0 <= board[p] <= 14 for p in [3, 4, 5]):
                raise ValueError('symbol')
            basis = request['cs'] * request['ml']
            side = [1, 5, 10, 50, 100]
            middle = [1, 2, 3, 5, 10, 15, 20, 30, 40, 50, 100]
            close = feature_detector._close
            if not feature_detector._finite(basis) or basis <= 0 or not close(tx.get('cs'), request['cs']) or tx.get('ml') != request['ml']:
                raise ValueError('bet')
            if not all(close(values[p], basis * side[board[p]-1] if board[p] else 0) for p in [0, 1, 2, 6, 7, 8]):
                raise ValueError('side values')
            if not all(close(values[p], middle[board[p]-1] if board[p] else 0) for p in [3, 4, 5] if board[p] <= 11):
                raise ValueError('middle values')
            win = values[1] * values[4] if board[1] and board[1] == board[7] else 0
            if not close(tx.get('tw', 0), win) or not close(tx.get('tb'), basis * 10) or not close(tx.get('tbb'), basis * 10):
                raise ValueError('payout')
            if not close(tx.get('blab'), tx['blb'] - tx['tb']) or not close(tx.get('bl'), tx['blab'] + win):
                raise ValueError('wallet')
            identity = (request.get('atk'), tx.get('sid'))
            if not all(isinstance(v, str) and v for v in identity) or identity in seen:
                continue
            seen.add(identity)
            sample = {'path': row['body'], 'sha256': hashlib.sha256(response_bytes).hexdigest()}
            if win > 0:
                wins += 1
            else:
                losses += 1
            evidence.append(sample)
            if tx.get('nfp') and len(tx.get('orl', [])) == 9 and len(tx.get('orv', [])) == 9:
                nudge.append(sample)
            if tx.get('rsrl') and tx.get('rsrv'):
                respin.append(sample)
        except (OSError, ValueError, KeyError, TypeError, OverflowError, struct.error):
            invalid += 1
    result = []
    for target in targets:
        f = {**target, 'status': 'unknown', 'checks': [], 'evidence': [], 'pending_reasons': []}
        if target['feature_id'] == 'normal_spin':
            f.update(status='evidence_complete' if wins and losses else ('candidate' if evidence else 'pending'),
                     checks=[{'name': '普通中奖和未中奖均有有效盘面与钱包响应', 'passed': bool(wins and losses)}],
                     evidence=evidence[:DETAIL_LIMIT], sample_count=len(evidence), winning_samples=wins, losing_samples=losses, invalid_samples=invalid)
            if not wins or not losses:
                f['pending_reasons'].append('尚缺可解码并通过金额核对的中奖或未中奖样本。')
        elif target['feature_id'] == 'nudge':
            f.update(status='candidate' if nudge else 'pending', evidence=nudge[:DETAIL_LIMIT], sample_count=len(nudge))
            f['pending_reasons'].append('只识别 nfp/orl/orv 候选，完整微移规则与资源覆盖尚未核验。')
        elif target['feature_id'] == 'respin':
            f.update(status='candidate' if respin else 'unknown', evidence=respin[:DETAIL_LIMIT], sample_count=len(respin))
            f['pending_reasons'].append('只识别 rsrl/rsrv 非空候选；不能因 st/nst 仍为 1 就否认特殊字段，也不能据此声称完整重旋已抓齐。')
        else:
            f['pending_reasons'].append('尚无该玩法的已核验完整采集判据，不能依据普通回包认定完成。')
        result.append(f)
    return result


def analyze_capture(detail, bodies_root, now_timestamp=None):
    """返回脱敏质量状态；网络静默、导入成功和本地功能状态均不能使其变绿。"""
    root = Path(bodies_root).resolve()
    stamp = time.time() if now_timestamp is None else float(now_timestamp)
    generated = datetime.fromtimestamp(stamp, timezone.utc).isoformat().replace('+00:00', 'Z')
    try:
        rules = _requirements()
        requirement_error = False
    except (OSError, ValueError, TypeError):
        rules, requirement_error = {}, True
    rows = detail.get('rows', []) if isinstance(detail.get('rows'), list) else []
    prefixes = [(prefix, code) for code, rule in rules.items() for prefix in rule.get('static_prefixes', [])]
    per_game, assets, shared, unknown_paths = defaultdict(list), defaultdict(list), [], []
    identity_sources = defaultdict(set)
    saved_cache = {}

    def saved(row):
        key = id(row)
        if key not in saved_cache:
            saved_cache[key] = _saved(root, row)
        return saved_cache[key]

    for row in rows:
        if not isinstance(row, dict):
            continue
        path = _path(row.get('url'))
        if path is None:
            unknown_paths.append('/[无法安全识别路径]')
            continue
        match = re.match(r'^/game-api/([a-z0-9-]{1,60})/', path)
        if '/shell-res/ad/' in path or '/telemetry/' in path or '/analytics/' in path or (match and match.group(1) == 'lobby'):
            unknown_paths.append(_safe_example(path))
            continue
        code = match.group(1) if match else next((c for p, c in prefixes if path.startswith(p)), None)
        if code:
            per_game[code].append(row)
            identity_sources[code].add('API 路径' if match else '仓库已核对的数字静态目录')
            if not match and row.get('status') not in (301, 302, 303, 307, 308):
                assets[code].append(row)
        elif path.startswith('/shared/'):
            shared.append(row)
        else:
            unknown_paths.append(_safe_example(path))

    # 共用包无法可靠绑定到某个页签时不强行分配；单游戏时可作为当前上下文依赖。
    if len(per_game) == 1:
        assets[next(iter(per_game))].extend(shared)
    manifest_parser = None
    try:
        manifest_parser = importlib.import_module('capture_asset_dependencies').analyze_asset_manifest
    except ImportError:
        pass
    try:
        feature_report = feature_detector.analyze_session(detail, root)
    except (OSError, ValueError, TypeError, KeyError):
        feature_report = {'features': []}
    games = []
    for code, game_rows in sorted(per_game.items()):
        rule = rules.get(code, {})
        req = rule.get('requirements', {})
        scope = rule.get('scope', '尚未定义当前版本、语言及功能范围的完整采集清单')
        grouped = defaultdict(list)
        for row in assets[code]:
            # URL 仅用于内存中区分变体；任何 query、origin、headers 都不输出。
            grouped[row.get('url', '')].append(row)
        counts = Counter(total=len(grouped), requests=len(assets[code]), saved=0, failed=0, pending=0, missing_body=0)
        missing, unknown = [], []
        available, hash_cache = defaultdict(list), {}
        for group in grouped.values():
            path = _path(group[0]['url'])
            good = [r for r in group if saved(r)]
            if good:
                counts['saved'] += 1
                available[path].extend(good)
                continue
            if any(r.get('state') == 'pending' or r.get('status') is None for r in group):
                counts['pending'] += 1
                why, severity = '请求尚未完成', 'pending'
            elif any(r.get('state') in ('failed', 'unavailable') or isinstance(r.get('status'), int) and r['status'] >= 400 for r in group):
                counts['failed'] += 1
                why, severity = '请求失败或响应不可获取', 'error'
            else:
                counts['missing_body'] += 1
                why, severity = '未取得本次资源的完整正文文件（仅有状态码或局部响应不够）', 'error'
            action = '保持抓取，在原站重新打开对应界面；若持续失败，重试加载并核对请求状态'
            if '/paytable-rules/' in path:
                action = '在原站打开规则或赔付表并等待加载；若此文件仍失败，保留该缺口，继续普通旋转不会证明规则已采齐'
            missing.append({'path': path, 'severity': severity, 'reason': why, 'action': action})
        pending_requests = sum(r.get('state') == 'pending' or r.get('status') is None for r in assets[code])
        counts['pending_requests'] = pending_requests

        def good_path(path, digest=None):
            for row in available.get(path, []):
                if digest is None:
                    return True
                name = row.get('body')
                try:
                    if name not in hash_cache:
                        hash_cache[name] = hashlib.sha256(_read(root, row)).hexdigest()
                    if hash_cache[name] == digest:
                        return True
                except (OSError, ValueError):
                    continue
            return False

        required_missing = []
        targets = req.get('assets', [])
        for target in targets:
            if not good_path(target['path'], target.get('sha256')):
                required_missing.append({'path': target['path'], 'severity': 'missing', 'reason': '已核对目标文件未保存，或版本摘要不匹配', 'action': target.get('action', '重新加载对应原站界面并等待保存')})
        required = {'defined': bool(targets), 'verified': req.get('verified') is True, 'label': req.get('label', '完整资源清单未定义'),
                    'source': req.get('source'), 'total': len(targets), 'saved': len(targets)-len(required_missing), 'missing': required_missing}

        deps, manifests, dynamic_unknown, native, bundle_names = {}, [], [], [], set()
        manifest_paths = {p for p in available if re.search(r'/config\.[A-Za-z0-9]+\.json$', p) or re.fullmatch(r'/shared/[^/]+/index\.json', p)}
        expected_manifests = req.get('manifests', [])
        for path in expected_manifests:
            if not good_path(path):
                dynamic_unknown.append('必需资源配置尚未保存：' + path)
        if not manifest_paths:
            dynamic_unknown.append('尚未取得可解析的资源配置清单，无法判断未被访问的依赖。')
        if manifest_parser is None:
            dynamic_unknown.append('资源配置解析器尚不可用。')
        for path in sorted(manifest_paths):
            if manifest_parser is None:
                break
            variants = set()
            for row in available[path]:
                try:
                    content = _read(root, row)
                    digest = hashlib.sha256(content).hexdigest()
                    if digest in variants:
                        continue
                    variants.add(digest)
                    parsed = manifest_parser(path, content)
                    if not parsed.get('recognized'):
                        dynamic_unknown.append('某个已保存变体不是可识别的资源配置：' + path)
                        continue
                    manifests.append({'path': path, 'sha256': digest})
                    config = json.loads(content.decode('utf-8-sig'))
                    if parsed.get('kind') == 'cocos-bundle-config' and isinstance(config.get('name'), str):
                        bundle_names.add(config['name'])
                    for dep in parsed.get('dependencies', []):
                        dep_path = dep.get('path')
                        if isinstance(dep_path, str) and _path(dep_path) == dep_path:
                            deps[dep_path] = dep
                    native.extend(parsed.get('native_candidates', []))
                    dynamic_unknown.extend(parsed.get('unknown', []))
                except (OSError, ValueError, TypeError, KeyError):
                    dynamic_unknown.append('资源配置未保存完整或暂不可解析：' + path)
            if len(variants) > 1:
                dynamic_unknown.append('同一路径保存了不同正文，当前版本/错误页变体尚需核对：' + path)
        # native 扩展名只能来自实际捕获，不从类型猜测 PNG/音频后缀。
        for item in native:
            prefix = item.get('path_prefix')
            stem = prefix if isinstance(prefix, str) and prefix.endswith('.') else str(prefix) + '.'
            observed = [p for p in available if isinstance(prefix, str) and p.startswith(stem)]
            if len(observed) == 1:
                deps[observed[0]] = {'path': observed[0], 'kind': 'native'}
            else:
                dynamic_unknown.append('原生资源扩展名/实际请求尚未核对：' + str(prefix))
        dynamic_unknown = [s for s in dynamic_unknown if not s.startswith('native-extension:') and not any(s.startswith('bundle-dependency:' + name + ':') for name in bundle_names)]
        if native:
            dynamic_unknown.append('原生资源仅按已捕获路径关联扩展名，其他语言或平台变体尚未确认；已关联不代表原生资源全集已齐。')
        dynamic_missing = []
        for p in sorted(deps):
            if good_path(p):
                continue
            dep = deps[p]
            names = dep.get('logical_names', [])
            hint = dep.get('scope', 'bundle-declared')
            action = '先确认是否需要覆盖此按需界面；可按原站规则、历史、设置、音量或加速菜单逐项访问，不要仅反复普通旋转'
            if 'language-hint=' in hint:
                action = '此项带其他语言/语言包提示，先确认目标语言范围；无需为当前语言强行遍历所有语言，也不要只靠继续旋转补齐'
            elif hint in ('entry-scene', 'package-entry'):
                action = '在原站重新进入对应游戏或页面，等待入口场景与共用包请求保存'
            dynamic_missing.append({'path': p, 'severity': 'unknown', 'scope': hint, 'logical_names': names[:5],
                                    'reason': '配置声明项尚未保存；可能属于其他语言、按需界面或平台变体，尚未确认是当前范围必需', 'action': action})
        dynamic = {'inspected_manifests': len(manifests), 'total': len(deps), 'saved': len(deps)-len(dynamic_missing),
                   'missing': dynamic_missing[:DETAIL_LIMIT], 'missing_count': len(dynamic_missing), 'unknown': list(dict.fromkeys(dynamic_unknown))[:DETAIL_LIMIT],
                   'unknown_count': len(set(dynamic_unknown)), 'sources': manifests,
                   'note': '配置覆盖范围可能跨语言和按需界面；这些缺项不等于当前画面立即缺失，也不能当作全部资源已齐。'}
        features = [dict(f) for f in feature_report['features'] if f['game_code'] == code]
        for f in features:
            f['action'] = ('在原站完成该功能的触发、所有中间状态、退出及随后普通一局，等待请求保存；' +
                           ('购买还需报价与首笔扣款证据' if f['feature_id'] == 'feature_buy' else '不要仅停留在触发画面'))
        if code == 'cash-mania':
            features.extend(_cash_features(game_rows, root, rule.get('feature_targets', [])))
        feature_map = {f['feature_id']: f for f in features}
        for fid in req.get('features', []):
            if fid not in feature_map:
                f = {'feature_id': fid, 'feature_name': fid, 'status': 'unknown', 'checks': [], 'evidence': [], 'pending_reasons': ['没有对应的已核验检测器'], 'action': '先定义并核验该玩法的完整采集判据'}
                features.append(f)
                feature_map[fid] = f
        if not features:
            unknown.append('该游戏尚未定义可自动判断完整的功能样本清单。')
        if not targets or not req.get('verified'):
            unknown.append('尚未登记并核验必需资源清单。')
        if req.get('exhaustive') is not True:
            unknown.append('当前清单不是已核验的完整范围；已观察资源全部保存也不能判断可以停抓。')
        unknown.extend(req.get('unknown', []))
        if len(per_game) > 1 and shared:
            unknown.append('多游戏共用资源尚未逐项绑定；不能把其他游戏加载的 shared 文件直接当作本游戏依赖齐全。')
        unknown.extend(dynamic['unknown'])
        all_resources = bool(targets and req.get('verified') is True and req.get('exhaustive') is True and expected_manifests and not required_missing and not dynamic_missing and not dynamic_unknown and len(manifests) >= len(expected_manifests))
        observed_complete = counts['total'] > 0 and counts['saved'] == counts['total'] and not pending_requests
        feature_complete = bool(req.get('features')) and all(feature_map[fid]['status'] == 'evidence_complete' for fid in req['features'])
        can_stop = all_resources and observed_complete and feature_complete and not unknown
        concrete_missing = list({item['path']: item for item in reversed(missing + required_missing + dynamic_missing)}.values())
        priority = {'error': 0, 'missing': 1, 'pending': 2, 'unknown': 3}
        concrete_missing.sort(key=lambda item: (priority.get(item.get('severity'), 3), item.get('path', '')))
        failed_required = required_missing or counts['failed'] or counts['missing_body']
        status = 'complete' if can_stop else ('blocked' if failed_required else ('collecting' if counts['pending'] else 'unknown'))
        games.append({'game_code': code, 'name': rule.get('name', code), 'status': status, 'can_stop': can_stop, 'scope': scope,
                      'recognition': {'methods': sorted(identity_sources[code]), 'static_prefixes': rule.get('static_prefixes', []), 'source': rule.get('identity_source')},
                      'assets': {'observed': dict(counts), 'required': required, 'dynamic_dependencies': dynamic, 'observed_complete': observed_complete, 'all_resources_verified': all_resources},
                      'features': features, 'missing': concrete_missing[:DETAIL_LIMIT], 'missing_count': len(concrete_missing), 'unknown': list(dict.fromkeys(unknown))[:DETAIL_LIMIT]})
    overall = bool(games) and all(g['can_stop'] for g in games) and not requirement_error
    status = 'complete' if overall else ('blocked' if any(g['status'] == 'blocked' for g in games) else ('collecting' if any(g['status'] == 'collecting' for g in games) else 'unknown'))
    notes = ['网络空闲或停止出现新请求不代表资源全集完整。', '本页只判断抓取资料是否齐全，接入和维护表验收另行记录。']
    if requirement_error:
        notes.append('采集目标声明无法读取，当前不能判定完整。')
    if not games:
        notes.append('尚未识别到游戏 API 或已核对的数字静态目录。')
    if unknown_paths:
        notes.append('未分类请求仅统计，不据此猜测游戏或功能；它们不计入已核对的游戏资源清单。')
    return {'version': 1, 'session_id': detail.get('id', detail.get('session_id', '')), 'generated_at': generated,
            'summary': {'status': status, 'can_stop': overall, 'headline': '登记范围的采集目标已满足，可以停止当前范围抓取' if overall else '尚不能确认可以停抓：请查看资源缺口、功能样本和未定义范围',
                        'scope': '；'.join(g['name'] + '：' + g['scope'] for g in games) if games else '游戏和采集范围未识别', 'notes': notes},
            'games': games, 'unknown_requests': {'count': len(unknown_paths), 'examples': list(dict.fromkeys(unknown_paths))[:10]}}
