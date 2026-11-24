"""把已核对的游戏和批次映射到本机实际目录，不接收浏览器传入的路径。"""
import os
import re
from pathlib import Path

from archive_identity import game_label
from capture_layout import SESSION_ID, plain_directory


GAME_ID = re.compile(r'[A-Za-z0-9_-]{1,80}')


def checked_directory(root, folder):
    """只允许 captures 内的实际目录；逐层拒绝符号链接和 Windows 目录联接。"""
    root, folder = Path(root).absolute(), Path(folder).absolute()
    try:
        relative = folder.relative_to(root)
    except ValueError:
        return None
    if not relative.parts or any(part in ('.', '..') for part in relative.parts):
        return None
    if not plain_directory(root):
        return None
    current = root
    for part in relative.parts:
        current = current / part
        if not plain_directory(current):
            return None
    try:
        if current.resolve() != root.resolve().joinpath(*relative.parts):
            return None
    except OSError:
        return None
    return current


def display_directory(root, folder):
    checked = checked_directory(root, folder)
    return 'captures/' + checked.relative_to(Path(root).absolute()).as_posix() if checked else None


def annotate_directories(root, records, folders):
    """补充列表所需的路径和活动定向身份；不修改或搬动抓取文件。"""
    for sid, record in records.items():
        folder = folders.get(sid)
        record['directory'] = display_directory(root, folder) if folder else None
        games = list(record.get('identity_games') or [])
        target = record.get('target_game')
        if isinstance(target, dict) and not any(game.get('site') == target.get('site') for game in games):
            games.append(target)
        record['identity_games'] = games
        grouped = {}
        for game in games:
            site, label = game.get('site'), game_label(game)
            if not isinstance(site, str) or not GAME_ID.fullmatch(site) or not label:
                continue
            directory = display_directory(root, Path(root) / label)
            if directory:
                grouped[(site, directory)] = {'game_id': site, 'name': label, 'path': directory}
        record['game_directories'] = list(grouped.values())
    return records


def requested_directory(root, records, folders, request):
    """仅从服务端刚核对过的批次和游戏身份解析操作目标。"""
    if not isinstance(request, dict) or set(request) not in ({'session_id'}, {'game_id'}, {'game_id', 'session_id'}):
        raise ValueError('请指定批次 ID 或站内游戏 ID；游戏历史目录可附带所属批次 ID，不能直接提交目录路径。')
    if set(request) == {'session_id'}:
        sid = request['session_id']
        if not isinstance(sid, str) or not SESSION_ID.fullmatch(sid):
            raise ValueError('无效的抓取批次 ID。')
        folder = folders.get(sid) if sid in records else None
        checked = checked_directory(root, folder) if folder else None
    else:
        site = request['game_id']
        if not isinstance(site, str) or not GAME_ID.fullmatch(site):
            raise ValueError('无效的站内游戏 ID。')
        candidates = records.values()
        if 'session_id' in request:
            sid = request['session_id']
            if not isinstance(sid, str) or not SESSION_ID.fullmatch(sid):
                raise ValueError('无效的抓取批次 ID。')
            candidates = [records[sid]] if sid in records else []
        choices = {}
        for record in candidates:
            for game in record.get('game_directories') or []:
                if game.get('game_id') == site:
                    folder = checked_directory(root, Path(root) / game['name'])
                    if folder:
                        choices[str(folder)] = folder
        if len(choices) > 1:
            raise ValueError('该游戏对应多个历史目录，请打开具体批次目录。')
        checked = next(iter(choices.values()), None)
    if checked is None:
        raise ValueError('对应抓取目录不存在、无法唯一确认或不是安全的实际文件夹。')
    return checked


def open_directory(folder):
    if os.name != 'nt':
        raise OSError('当前系统不支持 Windows 资源管理器，请根据页面路径打开目录。')
    os.startfile(str(folder), 'explore')
