"""从大厅目录、批次的定向标记和已保存的专属请求恢复游戏身份。"""
import copy
import json
import os
import re
import stat
import subprocess
import tempfile
import threading
import unicodedata
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from capture_layout import SESSION_ID, plain_directory, session_folders
from library_input import CATALOG_PATH, PATHS, project_session


UNKNOWN = '未识别游戏'
INVALID_CHARS = str.maketrans('<>:"/\\|?*', '＜＞：＂／＼｜？＊')
DEVICE = re.compile(r'^(?:CON|NUL|PRN|AUX|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)', re.I)
LAUNCH = re.compile(r'/api/v1/games/([a-zA-Z0-9_-]{1,80})/launch')
ASSET = re.compile(r'(?:image|audio|video|font)/|application/(?:json|javascript|octet-stream|wasm|x-javascript)$|text/(?:css|javascript)$')


def _text(value):
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return ''
    return str(value).strip()[:160]


def _target(item):
    if not isinstance(item, dict):
        return {}
    return {key: text for key in ('site', 'brand', 'externalId', 'zh', 'name')
            if (text := _text(item.get(key)))}


def _component(value):
    value = unicodedata.normalize('NFC', value).translate(INVALID_CHARS)
    value = ''.join(c for c in value if not unicodedata.category(c).startswith('C'))
    value = value.strip().rstrip(' .')
    if DEVICE.match(value):
        value = '_' + value
    return value


def game_label(target):
    """历史选项和物理游戏目录共用标签。缺乏任一必要字段时返回空字符串。"""
    target = _target(target)
    parts = [_component(v) for v in (target.get('brand', '').upper(), target.get('externalId', ''),
                                     target.get('zh') or target.get('name', ''))]
    if not all(parts):
        return ''
    label = '-'.join(parts)
    # 给 SID、bodies 和文件名留下足够的 Windows 路径空间。
    return label.encode('utf-16le')[:232].decode('utf-16le', errors='ignore').rstrip(' .')


def _history_url(value):
    try:
        parts = urlsplit(value)
        if parts.scheme in ('http', 'https') and parts.hostname:
            host = '[' + parts.hostname + ']' if ':' in parts.hostname else parts.hostname
            if parts.port:
                host += ':' + str(parts.port)
            paths = PATHS.get(parts.hostname)
            path = parts.path if paths and paths.fullmatch(parts.path) else '/'
            return parts.scheme + '://' + host + path
    except (ValueError, TypeError):
        pass
    return ''


def _read_batch(folder, manifest):
    with manifest.open('rb') as f:
        data = json.load(f)
    if data.get('id') != folder.name or not isinstance(data.get('rows'), list):
        raise ValueError('批次清单身份不符')
    # 投影器只读取有正文且来源可信的大厅目录文件，其余记录仅核验文件路径和字节数。
    rows = []
    for row in data['rows'] if plain_directory(folder / 'bodies') else ():
        if not isinstance(row, dict) or not isinstance(row.get('url'), str):
            continue
        body = re.fullmatch(r'bodies/([0-9]{1,20})\.[A-Za-z0-9]+', str(row.get('body', '')))
        if not body or str(int(body[1])) != str(row.get('id')):
            continue
        if row.get('method') not in ('GET', 'POST'):
            continue
        try:
            path = urlsplit(row.get('url', '')).path
        except (TypeError, ValueError):
            continue
        if path == CATALOG_PATH:
            if (row['method'] != 'GET' or row.get('status') != 200 or
                    str(row.get('mime')).split(';')[0].strip().lower() != 'application/json'):
                continue
            try:
                info = (folder / row['body']).lstat()
                if (not stat.S_ISREG(info.st_mode)
                        or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                    continue
            except OSError:
                continue
        rows.append(row)
    projection = project_session({'rows': rows}, folder)
    catalog = {}
    for items in projection['catalogs'].values():
        for item in items:
            target = _target(dict(site=item['id'], externalId=item['externalId'], name=item['name'],
                                  zh=item['nameZh'], brand=item['metadata']['brand'] or item['provider']['code']))
            if target.get('site') and game_label(target):
                key = (target['site'], target['brand'].upper(), target['externalId'])
                catalog[key] = target
    signals = set()
    for row in projection['rows']:
        url = urlsplit(row['url'])
        mime = row['mime'].split(';')[0].strip().lower() if isinstance(row.get('mime'), str) else ''
        if (url.hostname == 'sdstest.ink' and row['method'] == 'POST'
                and mime in ('application/json', 'application/vnd.sds.encrypted+json')):
            launch = LAUNCH.fullmatch(url.path)
            if launch:
                signals.add(('site', launch[1]))
        if (url.hostname in ('s5.mmga1.com', 'static5.mmga1.com') and row['status'] == 200 and row['method'] == 'GET' and
                (mime == 'text/html' and url.path.endswith('/index.html') or ASSET.match(mime))):
            # project_session 已将 PG 路径限制到该游戏的入口、包或历史模块，不含大厅封面。
            signals.add(('pg', url.path.split('/')[1]))
    summary = {key: data[key] for key in ('id', 'created', 'state', 'game_stage') if isinstance(data.get(key), str)}
    if summary.get('state') == 'complete':
        summary['state'] = 'completed'
    if type(data.get('ws_count')) is int:
        summary['ws_count'] = data['ws_count']
    summary['url'] = _history_url(data.get('url', ''))
    return {'summary': summary, 'target': _target(data.get('target_game')),
            'catalog': catalog, 'signals': signals}


class _Catalog:
    def __init__(self, catalogs):
        self.sites = defaultdict(dict)
        self.pg = defaultdict(dict)
        for catalog in catalogs:
            for key, target in catalog.items():
                site, brand, external = key
                self.sites[site][key] = target
                if brand == 'PG':
                    self.pg[external][key] = target

    def lookup(self, signal):
        kind, code = signal
        group = (self.sites if kind == 'site' else self.pg).get(code)
        if group and len(group) == 1:
            return next(iter(group.values()))
        return None


def _enrich(target, catalog):
    target = _target(target)
    saved = catalog.lookup(('site', target.get('site', '')))
    if not saved:
        return target
    for key in ('brand', 'externalId'):
        if key in target and target[key].casefold() != saved[key].casefold():
            return target
    return {**saved, **target}


def _summary(batch, catalog):
    info = dict(batch['summary'])
    games, unresolved = {}, False
    local = _Catalog([batch['catalog']])
    target = _enrich(batch['target'], local)
    target = _enrich(target, catalog)
    if target:
        info['target_game'] = target
        if game_label(target):
            games[game_label(target)] = target
        else:
            unresolved = True
    for signal in sorted(batch['signals']):
        game = local.lookup(signal) or catalog.lookup(signal)
        if game:
            games[game_label(game)] = game
        else:
            unresolved = True
    info['identity_games'] = [games[label] for label in sorted(games)]
    info['identity_unresolved'] = unresolved
    if len(games) == 1 and not unresolved:
        label, game = next(iter(games.items()))
        info.setdefault('target_game', game)
        info['display_name'] = label
    elif games:
        labels = sorted(games) + ([UNKNOWN] if unresolved else [])
        info['display_name'] = '多游戏：' + '、'.join(labels)
    else:
        info['display_name'] = UNKNOWN
    return info


class _Archive:
    def __init__(self, root):
        self.root = root
        self.lock = threading.Lock()
        self.batches = {}
        self.index = {}
        self.catalog = _Catalog([])

    def refresh(self):
        with self.lock:
            current = {}
            changed = False
            for sid, folder in session_folders(self.root, skip_ambiguous=True).items():
                manifest = folder / 'manifest.json'
                prior = self.batches.get(sid)
                try:
                    info = manifest.lstat()
                    if (not stat.S_ISREG(info.st_mode)
                            or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                        continue
                    sig = (folder, info.st_mtime_ns, info.st_size)
                    if prior and prior[0] == sig:
                        current[sid] = prior
                    else:
                        current[sid] = (sig, _read_batch(folder, manifest))
                        changed = True
                except (OSError, ValueError, TypeError, KeyError, AttributeError):
                    # 原采集器可能还在写入清单，下次轮询继续核对这一份。
                    if prior and prior[0][0] == folder:
                        current[sid] = prior
                    continue
            if changed or current.keys() != self.batches.keys():
                catalog = _Catalog(batch['catalog'] for _, batch in current.values())
                self.index = {sid: {'folder': sig[0], 'summary': _summary(batch, catalog)}
                              for sid, (sig, batch) in current.items()}
                self.catalog = catalog
                self.batches = current
            return self.index, self.catalog


@lru_cache(maxsize=8)
def _archive(root):
    return _Archive(root)


def archive_index(root):
    """按根目录、清单修改时间和大小缓存，返回只含游戏和历史概况的映射。"""
    index, _ = _archive(Path(root).resolve()).refresh()
    return copy.deepcopy(index)


def enrich_target(root, target):
    """只用唯一的真实目录记录补齐目标信息，未知站内 ID 保留其原有字段。"""
    _, catalog = _archive(Path(root).resolve()).refresh()
    return _enrich(target, catalog)


_LINK_LOCK = threading.Lock()
_POWERSHELL_LINKS = """
$ErrorActionPreference = 'Stop'
$jobs = ConvertFrom-Json -InputObject ([Console]::In.ReadToEnd())
$shell = New-Object -ComObject WScript.Shell
foreach ($job in $jobs) {
    $link = $shell.CreateShortcut($job.link)
    $link.TargetPath = $job.target
    $link.Save()
}
"""


def _existing_pointer(path, sid):
    try:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_size > 128
                or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            return False
        with path.open('rb') as f:
            data = json.load(f)
        return data == {'schema': 1, 'sid': sid} and type(data['schema']) is int
    except (OSError, TypeError, ValueError):
        return False


def _publish_pointer(path, sid):
    """先写完临时文件，再原子发布，避免中断或并发留下半份引用。"""
    with tempfile.TemporaryDirectory(dir=path.parent, prefix='.capture-ref-') as tmp:
        staging = Path(tmp) / 'ref.json'
        staging.write_bytes(json.dumps({'schema': 1, 'sid': sid}).encode('ascii'))
        if os.name == 'nt':
            staging.rename(path)
        else:
            os.link(staging, path)


def _valid_label(label):
    return (isinstance(label, str) and bool(label) and label == _component(label)
            and len(label.encode('utf-16le')) <= 232 and not SESSION_ID.fullmatch(label))


def _write_shortcuts(jobs, root, result):
    if not jobs or os.name != 'nt':
        return
    with tempfile.TemporaryDirectory(prefix='.capture-links-', dir=root) as tmp:
        batch = []
        for n, (link, target) in enumerate(jobs.items()):
            batch.append({'link': str(Path(tmp) / f'{n}.lnk'), 'target': str(target)})
        subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', _POWERSHELL_LINKS],
                       input=json.dumps(batch), text=True, capture_output=True, check=True,
                       timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        for entry, link in zip(batch, jobs):
            try:
                # Windows rename 在目标已存在时失败，可避免覆盖同时写入的文件。
                Path(entry['link']).rename(link)
                result['shortcuts'] += 1
            except FileExistsError:
                continue


def _link_groups(root, groups):
    root = Path(root).absolute()
    result = {'references': 0, 'shortcuts': 0, 'conflicts': 0}
    if not plain_directory(root):
        return result
    jobs = {}
    with _LINK_LOCK:
        for sid, labels in groups.items():
            if not isinstance(sid, str) or not SESSION_ID.fullmatch(sid):
                continue
            source = root / sid
            if not plain_directory(source):
                continue
            for label in dict.fromkeys(labels):
                if not _valid_label(label):
                    continue
                group = root / label
                try:
                    group.mkdir(exist_ok=True)
                    if not plain_directory(group):
                        result['conflicts'] += 1
                        continue
                    ref = group / (sid + '.capture-ref.json')
                    shortcut = group / (sid + '.lnk')
                    if not os.path.lexists(ref) and not os.path.lexists(shortcut):
                        try:
                            _publish_pointer(ref, sid)
                            result['references'] += 1
                        except FileExistsError:
                            pass
                    if not _existing_pointer(ref, sid):
                        result['conflicts'] += 1
                        continue
                    if not os.path.lexists(shortcut):
                        jobs[shortcut] = source
                except OSError:
                    result['conflicts'] += 1
        try:
            _write_shortcuts(jobs, root, result)
        except (OSError, subprocess.SubprocessError):
            result['conflicts'] += len(jobs) - result['shortcuts']
    return result


def link_legacy_session(root, sid, labels):
    """为已知身份的旧批次补建分组入口，原始录制目录可继续写入。"""
    return _link_groups(root, {sid: [labels] if isinstance(labels, str) else labels})


def sync_legacy_groups(root, index):
    """一次补齐已结束旧批次的入口；新批次已位于实际游戏目录内。"""
    root = Path(root).absolute()
    groups = {}
    for sid, batch in index.items():
        info = batch['summary']
        if batch['folder'] != root / sid or info.get('state') not in ('complete', 'completed', 'error'):
            continue
        labels = [game_label(game) for game in info.get('identity_games', [])]
        if info.get('identity_unresolved'):
            labels.append(UNKNOWN)
        groups[sid] = [label for label in labels if label] or [UNKNOWN]
    return _link_groups(root, groups)
