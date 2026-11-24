"""持久化正常退出请求；仅操作当前聊天中已核验实例自己的固定记录文件。"""
from datetime import datetime
import json
from pathlib import Path
import re
import uuid

from original_games import read_json, inspect_process, same_creation, plain_file
from capture_directories import checked_directory


def read_control(record, root, owner_chat):
    """状态刷新只读本地文件，实时进程核验由调用者的进程快照负责。"""
    try:
        if not owner_chat or record.get('chat') != owner_chat or not record.get('created'):
            return None
        nonce = record.get('control_nonce')
        if not isinstance(nonce, str) or not re.fullmatch(r'[0-9a-f]{32,128}', nonce):
            return None
        folder = Path(record.get('control_directory', '')).absolute()
        anchor = Path(record.get('ownership_file') or record.get('record') or '').absolute().parent
        if folder != anchor or not checked_directory(Path(root).absolute(), folder):
            return None
        owner = read_json(folder, 'control-owner.json', 64 * 1024)
        from service_runtime import command_matches
        if (owner.get('pid') != record.get('pid') or owner.get('chat') != owner_chat
                or owner.get('nonce') != nonce or owner.get('state') not in ('ready', 'stopping')
                or Path(owner.get('cwd', '')).resolve() != Path(record.get('cwd', '')).resolve()
                or not owner.get('command') or not command_matches(owner['command'], record.get('command'))
                or datetime.fromisoformat(owner['started']) < datetime.fromisoformat(record['created'])):
            return None
        return owner
    except (OSError, KeyError, ValueError, TypeError):
        return None


def request_stop(record, root, owner_chat, *, inspector=None):
    """写请求前重新核验 PID、创建时间和完整命令；不发送操作系统终止信号。"""
    owner = read_control(record, root, owner_chat)
    if not owner:
        raise ValueError('该实例没有可核验的正常退出通道，请保留现有服务。')
    actual = (inspector or inspect_process)(record['pid'])
    from service_runtime import command_matches
    if (not isinstance(actual, dict) or actual.get('pid') != record['pid'] or not actual.get('created')
            or not same_creation(actual.get('created'), record['created'])
            or not command_matches(record.get('command'), actual.get('command'))):
        raise ValueError('进程身份已经变化，未请求停止。')
    folder = Path(record['control_directory'])
    destination = folder / 'stop-request.json'
    if destination.exists() or destination.is_symlink():
        plain_file(folder, 'stop-request.json')
    pending = folder / ('stop-request-' + uuid.uuid4().hex + '.pending')
    with pending.open('x', encoding='utf-8') as stream:
        json.dump({'pid': record['pid'], 'created': record['created'], 'chat': owner_chat, 'nonce': owner['nonce']}, stream)
    pending.replace(destination)
    return {'ok': True, 'state': 'stopping', 'message': '已请求正常退出，等待在途任务和连接结束。'}
