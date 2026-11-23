"""只读检查已保存的 PG 功能证据；不操作浏览器、工作簿或实现状态。

公开入口：analyze_session(session_detail, bodies_root)。session_detail 可来自
8090 的 session API 或同结构的 manifest.json。CLI 只向 stdout 输出脱敏 JSON。
evidence_complete 仅表示本检测器要求的协议样本链完整，不表示功能已实现。
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import struct
import sys
from urllib.parse import urlsplit


REPO = Path(__file__).resolve().parents[3]
PG_ROOT = REPO / 'other/legacy/py/adapters/pg'
_spec = importlib.util.spec_from_file_location('_feature_evidence_pg_protocol', PG_ROOT / 'protocol.py')
protocol = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(protocol)
SUPPORTED = {'wild-bandito': (5, 'wild_bandito'), 'mahjong-ways2': (11, 'mahjong_ways2')}
SCHEMAS = {code: json.loads((PG_ROOT / (name + '_schema.json')).read_text(encoding='utf8'))
           for code, (_, name) in SUPPORTED.items()}
_catalog = (REPO / 'gateway/src/catalog.ts').read_text(encoding='utf8').split('export const GAME_CODES = [', 1)[1].split('];', 1)[0]
KNOWN_GAMES = set(re.findall(r'"([a-z0-9-]+)"', _catalog))
FEATURES = {
    'wild-bandito': [('free_spins', '免费旋转'), ('free_retrigger', '免费追加')],
    'mahjong-ways2': [('feature_buy', '购买免费'), ('free_third_reel_gold', '免费第3列全金牌')],
}


def _decode(raw, types, name='__root__'):
    """按原项目 schema 解析，补齐 packed double；未知字段不推断含义。"""
    specs = {item['id']: (key, item) for key, item in types[name]['fields'].items()}
    result = {}

    def value(kind, wire, data):
        if kind == 'double':
            if wire != 1:
                raise ValueError('double wire')
            return struct.unpack('<d', data)[0]
        if kind == 'string':
            if wire != 2:
                raise ValueError('string wire')
            return data.decode('utf8')
        if kind == 'bytes':
            return data.hex()
        if kind in types:
            child = _decode(data, types, kind)
            return child.get('__value', []) if kind == 'Int32List' else child
        if wire != 0:
            raise ValueError('integer wire')
        return ((data & 0xffffffff) - (1 << 32)) if kind == 'int32' and data >= 1 << 31 else data

    for number, wire, data in protocol.fields(raw):
        if number not in specs:
            continue
        key, item = specs[number]
        kind = item['type']
        if 'keyType' in item:
            entry = {n: (w, v) for n, w, v in protocol.fields(data)}
            k = str(value(item['keyType'], *entry.get(1, (0, 0))))
            result.setdefault(key, {})[k] = value(kind, *entry.get(2, (0, 0)))
        elif item.get('rule') == 'repeated':
            out = result.setdefault(key, [])
            if wire == 2 and kind == 'double':
                out.extend(struct.unpack('<' + 'd' * (len(data) // 8), data))
            elif wire == 2 and kind in ('int32', 'uint32', 'int64', 'uint64', 'bool'):
                pos = 0
                while pos < len(data):
                    n, pos = protocol.read_varint(data, pos)
                    out.append(value(kind, 0, n))
            else:
                out.append(value(kind, wire, data))
        else:
            if key in result:
                raise ValueError('duplicate scalar')
            result[key] = value(kind, wire, data)
    return result


def _saved_bytes(root, relative):
    # 只允许录制器产生的 bodies 文件；拒绝绝对路径、跨目录和符号链接逃逸。
    if not isinstance(relative, str) or not re.fullmatch(r'bodies/[0-9]+(?:\.request)?\.[A-Za-z0-9]+', relative):
        raise ValueError('body path')
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size > 16384:
        raise ValueError('body unavailable')
    return path.read_bytes()


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _close(a, b):
    return _finite(a) and _finite(b) and abs(a - b) < 1e-6


def _basic(row):
    t, q = row['tx'], row['request']
    if t.get('st') not in (1, 4, 21, 22) or t.get('nst') not in (1, 4, 21, 22):
        return False
    if not all(isinstance(t.get(k), str) and t[k] for k in ('sid', 'psid')):
        return False
    if not all(_finite(t.get(k)) and t[k] > 0 for k in ('cs', 'ml', 'tbb')):
        return False
    if not _close(q.get('cs'), t['cs']) or q.get('ml') != t['ml']:
        return False
    if not all(_finite(t.get(k, 0)) and t.get(k, 0) >= 0 for k in ('tb', 'tw')):
        return False
    if not _close(t.get('blab'), t.get('blb', float('nan')) - t.get('tb', 0)):
        return False
    if not _close(t.get('bl'), t.get('blab', float('nan')) + t.get('tw', 0)):
        return False
    return 'np' not in t or _close(t['np'], t.get('tw', 0) - t.get('tb', 0))


def _edge(previous, current, same_round=True):
    p, t = previous['tx'], current['tx']
    return (_basic(previous) and _basic(current)
            and current['order'] > previous['order']
            and current['request'].get('id') == p['sid']
            and t['st'] == p['nst']
            and (not same_round or t['psid'] == p['psid'])
            and _close(p['bl'], t['blb'])
            and (not same_round or (p['cs'] == t['cs'] and p['ml'] == t['ml'] and _close(p['tbb'], t['tbb']))))


def _scatter_award(code, tx):
    board = tx.get('orl')
    size = 25 if code == 'wild-bandito' else 35
    visible = [c * 5 + r for c in range(5) for r in range(1, 5)] if size == 25 else [*range(1, 5), *range(8, 13), *range(15, 20), *range(22, 27), *range(29, 33)]
    if not isinstance(board, list) or len(board) != size:
        return None
    count = sum(board[p] == 1 for p in visible)
    if count < 3 or tx.get('sc') != count:
        return None
    return (12 if code == 'wild-bandito' else 10) + (count - 3) * 2


def _free_counts(code, previous, current):
    p, t = previous['tx'].get('fs'), current['tx'].get('fs')
    if not isinstance(p, dict) or not isinstance(t, dict):
        return False
    numbers = [p.get('s', 0), p.get('ts', 0), t.get('s', 0), t.get('ts', 0), t.get('nosa', 0)]
    if not all(isinstance(n, int) and n >= 0 for n in numbers):
        return False
    added = t.get('nosa', 0)
    return ((not added or added == _scatter_award(code, current['tx']))
            and t.get('s', 0) == p.get('s', 0) - int(current['tx']['st'] == 21) + added
            and t.get('ts', 0) == p.get('ts', 0) + added
            and t.get('s', 0) <= t.get('ts', 0)
            and _close(t.get('aw', 0), p.get('aw', 0) + current['tx'].get('tw', 0)))


def _third_gold(row):
    t = row['tx']
    before, after = t.get('orl'), t.get('rl')
    if t.get('st') not in (21, 22) or not isinstance(before, list) or not isinstance(after, list) or len(before) != 35 or len(after) != 35:
        return False
    if not all(isinstance(n, int) and 0 <= n <= 10 for n in before + after):
        return False
    gold = set((t.get('ssb') or {}).values())
    remaining = set((t.get('ss') or {}).values())
    ordinary = {p for p in range(15, 20) if before[p] >= 2}
    return (bool(ordinary) and ordinary <= gold
            and all(after[p] == (before[p] if p in remaining else 0) for p in ordinary))


def _full_chains(code, rows):
    """只从完整付费起点走到免费结束后的下一笔付费，不用截图补缺口。"""
    by_sid = {r['tx']['sid']: r for r in rows}
    next_rows = defaultdict(list)
    for row in rows:
        next_rows[row['request'].get('id')].append(row)
    complete = []
    for trigger in rows:
        t = trigger['tx']
        if t.get('st') not in (1, 4) or t.get('nst') != 21 or (t.get('fs') or {}).get('s', 0) <= 0:
            continue
        award = _scatter_award(code, t)
        if award is None or t['fs'].get('s') != award or t['fs'].get('ts') != award:
            continue
        prefix, current, seen = [trigger], trigger, {t['sid']}
        while current['tx']['st'] == 4:
            previous = by_sid.get(current['request'].get('id'))
            if previous is None or previous['tx']['sid'] in seen or not _edge(previous, current) or current['tx'].get('tb', 0) != 0:
                break
            seen.add(previous['tx']['sid'])
            prefix.insert(0, previous)
            current = previous
        if current['tx']['st'] != 1 or not _basic(current) or current['tx'].get('tb', 0) <= 0:
            continue
        # 含购买标记的链可以是候选，但不能冒充自然触发的免费来源。
        chain, current = list(prefix), trigger
        while len(chain) <= len(rows):
            following = next_rows.get(current['tx']['sid'], [])
            if len(following) != 1:
                break
            nxt = following[0]
            if nxt['tx']['sid'] in seen or not _edge(current, nxt):
                break
            n = nxt['tx']
            if n['st'] not in (21, 22) or n.get('tb', 0) != 0 or not _free_counts(code, current, nxt):
                break
            seen.add(n['sid'])
            chain.append(nxt)
            current = nxt
            if n['nst'] == 1:
                after = next_rows.get(n['sid'], [])
                if ((n.get('fs') or {}).get('s', 0) == 0 and len(after) == 1
                        and _edge(nxt, after[0], same_round=False)
                        and after[0]['tx']['st'] == 1 and after[0]['tx'].get('tb', 0) > 0):
                    complete.append(chain + [after[0]])
                break
            if n['nst'] not in (21, 22) or (n['nst'] == 21 and (n.get('fs') or {}).get('s', 0) <= 0):
                break
    return complete


def _evidence(rows):
    result, seen = [], set()
    for row in rows:
        for item in row['evidence']:
            key = (item['path'], item['sha256'])
            if key not in seen:
                result.append(item)
                seen.add(key)
    return result


def analyze_session(detail, bodies_root):
    """返回脱敏证据；失败仅给固定原因，不回显 URL、请求内容或异常详情。"""
    root = Path(bodies_root).resolve()
    stats = Counter()
    groups = defaultdict(list)
    known_seen, other_games = set(), Counter()
    for order, saved in enumerate(detail.get('rows', [])):
        try:
            split = urlsplit(saved.get('url', ''))
            path = split.path
        except (ValueError, TypeError):
            stats['unclassified_rows'] += 1
            continue
        match = re.fullmatch(r'/game-api/([a-z0-9-]+)/v\d+/[A-Za-z/]+', path)
        code = match.group(1) if match else None
        if code in SUPPORTED:
            known_seen.add(code)
        is_saved = saved.get('state') == 'complete' and saved.get('status') == 200 and bool(saved.get('body'))
        if is_saved:
            stats['saved_responses'] += 1
            if code not in SUPPORTED:
                other_games[code if code in KNOWN_GAMES else 'unclassified'] += 1
        if code not in SUPPORTED or path != f'/game-api/{code}/v4/Spin':
            continue
        if not is_saved:
            stats['pending_or_failed_spins'] += 1
            continue
        try:
            request_body = _saved_bytes(root, saved.get('request_body'))
            response_body = _saved_bytes(root, saved['body'])
            salt = SUPPORTED[code][0]
            request_raw, seed = protocol.unpack(request_body, salt=salt)
            request = protocol.decode_request(request_raw)
            if not isinstance(request.get('atk'), str) or not request['atk'] or not isinstance(request.get('id'), str):
                raise ValueError('request identity')
            raw, _ = protocol.unpack(response_body, seed, salt=salt)
            tx = _decode(raw, SCHEMAS[code]['transaction']['nested'])
            tx.update(_decode(raw, SCHEMAS[code]['wallet']['nested']))
            record = {'order': order, 'request': request, 'tx': tx,
                      'evidence': [{'path': saved[k], 'sha256': hashlib.sha256(v).hexdigest()}
                                   for k, v in [('request_body', request_body), ('body', response_body)]]}
            if not _basic(record):
                raise ValueError('transaction checks')
            # 原始鉴权只在内存中分组，任何 token/hash/sid/余额均不进入输出。
            identity = hashlib.sha256(request['atk'].encode()).digest()
            groups[(code, split.netloc, identity)].append(record)
            stats['decoded_spins'] += 1
        except (OSError, ValueError, TypeError, KeyError, struct.error, OverflowError):
            stats['invalid_saved_spins'] += 1

    observations, chains, conflicts = defaultdict(list), defaultdict(list), Counter()
    for (code, _, _), rows in groups.items():
        unique, conflicting = {}, False
        for row in rows:
            sid = row['tx']['sid']
            previous = unique.get(sid)
            if previous is not None:
                a = {k: v for k, v in previous['request'].items() if k != 'atk'}
                b = {k: v for k, v in row['request'].items() if k != 'atk'}
                if previous['tx'] != row['tx'] or a != b:
                    conflicting = True
                else:
                    stats['duplicate_spins'] += 1
                continue
            unique[sid] = row
        rows = list(unique.values())
        observations[code].extend(rows)
        if conflicting:
            conflicts[code] += 1
        else:
            chains[code].extend(_full_chains(code, rows))

    features = []
    for code in sorted(known_seen):
        rows = observations[code]
        natural_chains = [chain for chain in chains[code] if not any(r['request'].get('fb', 0) for r in chain[:-1])]
        for feature_id, feature_name in FEATURES[code]:
            selected, successful = [], []
            checks = []
            if feature_id == 'free_spins':
                selected = [r for r in rows if r['tx']['st'] in (21, 22) or r['tx']['nst'] in (21, 22)]
                successful = natural_chains
                checks = [{'name': '自然付费触发、免费计数与钱包连续、结束后再次付费', 'passed': bool(successful)}]
            elif feature_id == 'free_retrigger':
                selected = [r for r in rows if r['tx']['st'] in (21, 22) and (r['tx'].get('fs') or {}).get('nosa', 0) > 0]
                successful = [chain for chain in natural_chains if any(r in selected for r in chain)]
                checks = [{'name': '免费链内追加并核对次数守恒及完整退出', 'passed': bool(successful)}]
            elif feature_id == 'feature_buy':
                selected = [r for r in rows if r['request'].get('fb', 0)]
                checks = [
                    {'name': '非零购买参数有成功可解码交易', 'passed': bool(selected)},
                    {'name': '购买报价与对应首次扣款已独立验证', 'passed': False},
                ]
                # 当前没有已验证的报价 schema；不能从单个 fb 或金额倒推购买价格。
            elif feature_id == 'free_third_reel_gold':
                selected = [r for r in rows if _third_gold(r)]
                for chain in natural_chains:
                    free = [r for r in chain if r['tx']['st'] in (21, 22)]
                    if (free and all(_third_gold(r) for r in free)
                            and any(r['tx']['st'] == 21 for r in free)
                            and any(r['tx']['st'] == 22 and (r['tx'].get('rs') or {}).get('rns') for r in free)):
                        successful.append(chain)
                checks = [
                    {'name': '免费第三列普通符号金框及转百搭已观察', 'passed': bool(selected)},
                    {'name': '完整自然免费链同时覆盖新盘与连消补牌', 'passed': bool(successful)},
                ]
            status = 'evidence_complete' if successful else ('candidate' if selected else 'pending')
            evidence_rows = [r for chain in successful for r in chain] if successful else selected
            reasons = []
            if not successful:
                reasons.append('缺少满足全部检查的连续协议样本；不能视为功能完成。')
            if feature_id == 'feature_buy':
                reasons.append('购买报价和价格 schema 未验证，当前分支最多输出候选。')
            if conflicts[code]:
                reasons.append('存在同会话同局号不同内容，相关会话不参与完整性判定。')
            features.append({'game_code': code, 'feature_id': feature_id, 'feature_name': feature_name,
                             'status': status, 'evidence': _evidence(evidence_rows), 'checks': checks,
                             'pending_reasons': reasons})
    return {'version': 1, 'session_id': detail.get('id', detail.get('session_id', '')),
            'scope': '仅判断已保存协议样本；不代表功能实现、UI 验收或原厂概率已完成。',
            'features': features, 'stats': dict(stats),
            'pending_games': [{'game_code': code, 'saved_responses': count, 'status': 'pending',
                               'reason': '尚无此游戏功能检测器；仅统计，不根据路径推定功能。'}
                              for code, count in sorted(other_games.items())]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', help='manifest/API JSON 文件，或 - 从 stdin 读取')
    parser.add_argument('--bodies-root', required=True, help='包含 bodies 子目录的该次捕获根目录')
    args = parser.parse_args()
    detail = json.load(sys.stdin) if args.manifest == '-' else json.loads(Path(args.manifest).read_text(encoding='utf-8-sig'))
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(analyze_session(detail, args.bodies_root), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
