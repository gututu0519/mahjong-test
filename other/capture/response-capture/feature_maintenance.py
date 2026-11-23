"""随抓取工具启动维护表监督器；不改变抓取浏览器或原站请求。"""
import os
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def _process_creation_time(process):
    """Windows 使用 Popen 持有的原始进程句柄读取创建时间，不按 PID 找进程。"""
    if os.name != 'nt' or getattr(process, '_handle', None) is None:
        return None
    try:
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        kernel.GetProcessTimes.restype = wintypes.BOOL
        created, exited, system, user = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(int(process._handle), ctypes.byref(created), ctypes.byref(exited), ctypes.byref(system), ctypes.byref(user)):
            return None
        return str((created.dwHighDateTime << 32) | created.dwLowDateTime)
    except (OSError, AttributeError, TypeError, ValueError):
        return None


def start_supervisor(root=None):
    if os.environ.get('CAPTURE_FEATURE_MAINTENANCE') == '0':
        return None
    try:
        root = Path(root or Path(__file__).resolve().parents[3]).resolve()
        script = root / 'other/tooling/feature-maintenance/watch.mjs'
        node = shutil.which('node')
        if not node or not script.is_file():
            print('维护表监督器未启动：需要 Node.js 和项目中的监督脚本；抓取继续运行。', flush=True)
            return None
        logs = root / 'other/diagnostics/feature-maintenance'
        logs.mkdir(parents=True, exist_ok=True)
        command = [node, str(script), '--capture-url', 'http://127.0.0.1:8090', '--interval-ms', '10000', '--parent-pipe']
        with (logs / 'supervisor.log').open('ab') as log:
            process = subprocess.Popen(
                command, cwd=root, stdin=subprocess.PIPE, stdout=log, stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
    except OSError:
        # 日志目录不可写、Node 启动失败等不能中断已经启动的抓取服务器。
        print('维护表监督器未启动：本地日志或进程启动失败；抓取继续运行。', flush=True)
        return None
    owner = dict(capture_pid=os.getpid(), pid=process.pid, command=command, cwd=str(root),
                 created_filetime=_process_creation_time(process), started_at=datetime.now(timezone.utc).isoformat(),
                 listening_ports=[], capture_api='http://127.0.0.1:8090')
    # 终止只能使用本次调用返回的子进程对象；元数据不授予按 PID 终止的能力。
    process._capture_feature_owner = owner
    try:
        (logs / ('supervisor-owner-' + str(process.pid) + '.json')).write_text(
            json.dumps(owner, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    except OSError:
        print('维护表监督器归属文件暂不可写；本次进程句柄仍由抓取工具持有。', flush=True)
    return process


def stop_supervisor(process):
    if process is None:
        return
    owner = getattr(process, '_capture_feature_owner', None)
    if not isinstance(owner, dict) or owner.get('capture_pid') != os.getpid() or owner.get('pid') != process.pid:
        print('维护表监督器归属无法确认，保留进程。', flush=True)
        return
    try:
        if process.poll() is not None:
            return
        if owner.get('created_filetime') is not None and owner['created_filetime'] != _process_creation_time(process):
            print('维护表监督器创建时间无法匹配，保留进程。', flush=True)
            return
        # Windows terminate 会绕过 Node 的 finally，可能截断工作簿提交。
        # 固定控制管道只请求当前子进程收尾退出，任何异常都不升级为强制终止。
        if process.stdin is None:
            print('维护表监督器控制管道不可用，保留进程完成当前工作。', flush=True)
            return
        if not process.stdin.closed:
            process.stdin.write(b'stop\n')
            process.stdin.flush()
            process.stdin.close()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        print('维护表监督器正在收尾，保留进程完成当前写入后退出。', flush=True)
    except (OSError, ValueError):
        print('维护表监督器退出状态暂无法核对，未强制终止任何进程。', flush=True)
