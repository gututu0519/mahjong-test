"""查找 captures 下平铺的旧批次和按游戏分组的新批次。"""
import re
import stat
from pathlib import Path


SESSION_ID = re.compile(r"[0-9a-f]{32}")


def plain_directory(path):
    try:
        info = path.lstat()
    except (FileNotFoundError, NotADirectoryError):
        return False
    return stat.S_ISDIR(info.st_mode) and not (
        getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _folders(root, sid=None):
    if not plain_directory(root):
        return
    for child in root.iterdir():
        if not plain_directory(child):
            continue
        if SESSION_ID.fullmatch(child.name):
            if sid is None or child.name == sid:
                yield child
            continue
        entries = (child / sid,) if sid is not None else child.iterdir()
        for batch in entries:
            if SESSION_ID.fullmatch(batch.name) and plain_directory(batch):
                yield batch


def _unique(folders, *, skip_ambiguous=False):
    result = {}
    ambiguous = set()
    for folder in folders:
        sid = folder.name
        if sid in ambiguous:
            continue
        if sid in result:
            if not skip_ambiguous:
                raise ValueError(f"抓取批次 ID 重复：{sid}")
            del result[sid]
            ambiguous.add(sid)
        else:
            result[sid] = folder
    return result


def session_folders(root, *, skip_ambiguous=False):
    """列出含录制中的批次，历史列表可跳过路径不唯一的 SID。"""
    return _unique(_folders(Path(root)), skip_ambiguous=skip_ambiguous)


def session_folder(root, sid):
    if not isinstance(sid, str) or not SESSION_ID.fullmatch(sid):
        return None
    return _unique(_folders(Path(root), sid)).get(sid)
