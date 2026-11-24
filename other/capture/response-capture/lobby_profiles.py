"""在本机临时目录独占租用抓取工具自己的浏览器资料。"""
import atexit
from dataclasses import dataclass
import hmac
import os
from pathlib import Path
import secrets
import shutil
import stat
import tempfile
import threading
import time


@dataclass(frozen=True, eq=False)
class ProfileLease:
    path: Path
    returning: bool


@dataclass(frozen=True)
class _Profile:
    path: Path
    key: bytes
    created: os.stat_result

    def is_original_directory(self):
        info = self.path.lstat()
        return (stat.S_ISDIR(info.st_mode)
                and not getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
                and os.path.samestat(info, self.created))


class LobbyProfiles:
    MAX_IDLE = 8
    IDLE_SECONDS = 30 * 60

    def __init__(self):
        self._root = Path(tempfile.gettempdir()).resolve()
        if self._root.is_relative_to(Path(__file__).resolve().parent / 'captures'):
            raise ValueError('系统临时目录不能位于抓取归档内。')
        self._secret = secrets.token_bytes(32)
        self._lock = threading.Lock()
        self._active = {}
        self._idle = []
        self._discarded = []
        self._closed = False
        atexit.register(self.close)

    def _trim(self, now):
        while self._idle and (len(self._idle) > self.MAX_IDLE
                              or self._idle[0][0] + self.IDLE_SECONDS <= now):
            self._discarded.append(self._idle.pop(0)[1])

    def _clean_discarded(self):
        with self._lock:
            discarded, self._discarded = self._discarded, []
        retry = []
        for profile in discarded:
            try:
                if (profile.path.parent == self._root and profile.is_original_directory()
                        and profile.path.resolve(strict=True) == profile.path):
                    shutil.rmtree(profile.path)
            except FileNotFoundError:
                pass
            except OSError:
                # 浏览器退出时文件可能暂被 Windows 占用，下次归还、租用或退出时重试。
                retry.append(profile)
        with self._lock:
            self._discarded.extend(retry)

    def acquire(self, account, password):
        username = account.strip().encode('utf-8', 'surrogatepass')
        message = len(username).to_bytes(4, 'big') + username + password.encode('utf-8', 'surrogatepass')
        key = hmac.digest(self._secret, message, 'sha256')
        with self._lock:
            if self._closed:
                raise RuntimeError('登录资料池已关闭。')
            self._trim(time.monotonic())
            profile = None
            for i in reversed(range(len(self._idle))):
                if self._idle[i][1].key == key:
                    candidate = self._idle.pop(i)[1]
                    try:
                        if candidate.is_original_directory():
                            profile = candidate
                            break
                    except OSError:
                        pass
                    self._discarded.append(candidate)
            returning = profile is not None
            if not returning:
                path = Path(tempfile.mkdtemp(prefix='sds-lobby-', dir=self._root))
                profile = _Profile(path, key, path.lstat())
            lease = ProfileLease(profile.path, returning)
            self._active[lease] = profile
        self._clean_discarded()
        return lease

    def release(self, lease, reusable=False):
        """浏览器关闭后归还。认证失败或资料异常时丢弃本次租用。"""
        with self._lock:
            profile = self._active.pop(lease, None)
            if profile is None:
                return
            now = time.monotonic()
            if reusable and not self._closed:
                self._idle.append((now, profile))
            else:
                self._discarded.append(profile)
            self._trim(now)
        self._clean_discarded()

    def close(self):
        """清理已归还的目录。仍在使用的目录留到其浏览器实际退出后归还。"""
        with self._lock:
            self._closed = True
            self._discarded.extend(profile for _, profile in self._idle)
            self._idle.clear()
        self._clean_discarded()
        with self._lock:
            if not self._active and not self._discarded:
                atexit.unregister(self.close)
