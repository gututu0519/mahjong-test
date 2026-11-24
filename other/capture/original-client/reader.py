"""只读项目采集清单或内嵌响应正文的 HAR。请求 URL 仅供内存匹配。"""

import base64
import binascii
import hashlib
import json
import os
import re
import stat
from collections import Counter
from functools import partial
from pathlib import Path, PureWindowsPath
from urllib.parse import urlsplit


# HAR 可内嵌所有响应。单份索引和单份响应分别限制，避免不受控分配。
MAX_INDEX = 512 * 1024 * 1024
MAX_BODY = 128 * 1024 * 1024


def _unlinked(path):
    for part in (path, *path.parents):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError("采集路径含符号链接或重解析点")


def _file_bytes(path, limit, expected=None):
    try:
        _unlinked(path)
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("采集文件必须是普通文件")
        if before.st_size > limit:
            raise ValueError(f"采集文件超过 {limit // (1024 * 1024)} MiB 上限")
        if expected is not None and before.st_size != expected:
            raise ValueError("响应正文字节数与索引不符")
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            _unlinked(path)
            if not os.path.samestat(before, opened) or not os.path.samestat(path.lstat(), opened):
                raise ValueError("采集文件在读取时已变更")
            data = stream.read(before.st_size + 1)
        if len(data) != before.st_size:
            raise ValueError("采集文件在读取时已变更")
        return data
    except OSError:
        raise ValueError("采集文件缺失或无法读取") from None


def _body_key(name):
    return os.path.normcase(os.path.normpath(name.replace("\\", "/")))


def _body_path(root, name):
    # 同时按 Windows 规则审查，避免换机器后出现驱动器路径、设备路径或 ADS。
    pieces = name.replace("\\", "/").split("/")
    if len(pieces) < 2 or pieces[0] != "bodies":
        raise ValueError("响应正文路径不属于采集 bodies 目录")
    for piece in pieces:
        if (piece in ("", ".", "..") or piece.endswith((" ", ".")) or
                re.search(r'[\x00-\x1f<>:"|?*]', piece) or PureWindowsPath(piece).is_reserved()):
            raise ValueError("响应正文路径无效")
    if pieces[-1].lower().endswith(".request.bin"):
        raise ValueError("索引将请求正文标记为响应")
    return root.joinpath(*pieces)


def _size(value):
    if value is None or (type(value) is int and value == -1):
        return None
    if type(value) is not int or value < 0:
        raise ValueError("响应大小字段无效")
    return value


def _verified(data, expected, digest):
    if len(data) > MAX_BODY:
        raise ValueError("响应正文超过大小上限")
    if expected is not None and len(data) != expected:
        raise ValueError("响应正文字节数与索引不符")
    if digest is not None:
        if not isinstance(digest, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", digest):
            raise ValueError("SHA-256 字段无效")
        if hashlib.sha256(data).hexdigest() != digest.lower():
            raise ValueError("响应正文 SHA-256 与索引不符")
    return data


def _disk_body(path, size, digest):
    return _verified(_file_bytes(path, MAX_BODY, size), size, digest)


def _har_body(text, encoding, mime, size, digest):
    if encoding == "base64":
        if len(text) > (MAX_BODY + 2) // 3 * 4 + 1024 * 1024:
            raise ValueError("HAR 编码的响应超过大小上限")
        try:
            raw = base64.b64decode("".join(text.split()), validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("HAR 响应的 Base64 无效") from None
    elif encoding in ("", None):
        if len(text) > MAX_BODY:
            raise ValueError("HAR 文本响应超过大小上限")
        charset = re.search(r"""\bcharset\s*=\s*["']?([\w.-]+)""", mime, re.I)
        try:
            raw = text.encode(charset.group(1) if charset else "utf-8")
        except (UnicodeError, LookupError, ValueError):
            raise ValueError("HAR 的文本字符集无法还原") from None
    else:
        raise ValueError("HAR 响应使用不支持的编码")
    return _verified(raw, size, digest)


def _fail(reason):
    raise ValueError(reason)


def _entry_row(entry, har, root, issues, request_files):
    if not isinstance(entry, dict):
        raise ValueError("记录结构无效")
    req = entry.get("request") if har else entry
    res = entry.get("response") if har else entry
    if not isinstance(req, dict) or not isinstance(res, dict):
        raise ValueError("缺请求或响应索引")
    url = req.get("url")
    if not isinstance(url, str):
        raise ValueError("缺请求 URL")
    try:
        parsed = urlsplit(url)
        parsed.port
    except ValueError:
        raise ValueError("URL 无效") from None
    if parsed.scheme not in ("http", "https", "ws", "wss") or not parsed.hostname:
        raise ValueError("非网络 URL 或缺主机")
    status = res.get("status")
    status = status if type(status) is int and 100 <= status <= 599 else 0
    method = req.get("method", "GET")
    method = method.upper() if isinstance(method, str) else ""
    content = res.get("content") if har else res
    content = content if isinstance(content, dict) else {}
    mime = content.get("mimeType" if har else "mime", "")
    mime = mime if isinstance(mime, str) else ""
    resource_type = entry.get("_resourceType" if har else "type", "")
    size = None
    available = True
    try:
        size = _size(content.get("size"))
        if size is not None and size > MAX_BODY:
            raise ValueError("响应正文超过大小上限")
        digest = content.get("sha256", content.get("body_sha256"))
        if har:
            body = content.get("text")
            if not isinstance(body, str):
                raise ValueError("HAR 未内嵌响应正文")
            read = partial(_har_body, body, content.get("encoding"), mime, size, digest)
        else:
            if res.get("state") not in (None, "complete"):
                raise ValueError("采集器未完整保存该响应")
            name = res.get("body")
            if not isinstance(name, str) or not name:
                raise ValueError("缺响应正文文件")
            path = _body_path(root, name)
            if _body_key(name) in request_files:
                raise ValueError("索引将请求正文标记为响应")
            read = partial(_disk_body, path, size, digest)
    except ValueError as err:
        if method != "HEAD" and (status == 0 or 200 <= status < 300 and status not in (204, 205)):
            issues[str(err)] += 1
        read = partial(_fail, str(err))
        available = False
    return {"url": url, "method": method, "mime": mime, "status": status, "size": size,
            "resource_type": resource_type if isinstance(resource_type, str) else "",
            "has_body": available, "read": read}


def _index(source):
    _unlinked(source)
    if source.is_dir():
        manifest = source / "manifest.json"
        # manifest 和 network.har 在项目采集器中属于同一批，优先使用外置的原始字节。
        if manifest.is_file():
            return manifest, False
        hars = [item for item in source.iterdir() if item.suffix.lower() == ".har" and item.is_file()]
        if len(hars) == 1:
            return hars[0], True
        if hars:
            raise ValueError("此目录含多份 HAR，请直接选择需要的一份 HAR 文件")
        raise ValueError("请选择单个抓取批次目录，其中应含 manifest.json 或一份 HAR")
    if source.name == "manifest.json" or source.suffix.lower() == ".har":
        return source, source.suffix.lower() == ".har"
    raise ValueError("请选择单个抓取目录、manifest.json 或 HAR 文件")


def read_capture(folder: Path) -> tuple[list[dict], list[str]]:
    """正文按需读取。read() 会校验实际长度、SHA-256 和路径，失败时抛出脱敏的 ValueError。"""
    try:
        path, har = _index(Path(os.path.abspath(folder)))
        document = json.loads(_file_bytes(path, MAX_INDEX))
    except OSError:
        raise ValueError("抓取目录或索引不可读") from None
    except (json.JSONDecodeError, UnicodeError, RecursionError):
        raise ValueError("采集索引不是有效的 JSON 文档") from None
    header = document.get("log") if har and isinstance(document, dict) else document
    records = header.get("entries" if har else "rows") if isinstance(header, dict) else None
    if not isinstance(records, list):
        raise ValueError("该索引缺少 HAR entries 或采集 rows")
    # 旧版或其他导出器可能将请求正文保存为普通 .bin，用元数据排除这些文件。
    request_files = set()
    if not har:
        for record in records:
            name = record.get("request_body") if isinstance(record, dict) else None
            if isinstance(name, str):
                request_files.add(_body_key(name))
    issues = Counter()
    rows = []
    for entry in records:
        try:
            rows.append(_entry_row(entry, har, path.parent, issues, request_files))
        except ValueError as err:
            issues[str(err)] += 1
    return rows, [f"{reason}（{count} 条）" for reason, count in sorted(issues.items())]
