"""按 HTML、CSS 和脚本中的静态引用恢复可离线预览的原版网页。"""
import hashlib
import re
import tempfile
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urljoin, urlsplit

from jpeg_interlace import convert_jpeg
from png_interlace import convert_png

MAX_FILE = 32 * 1024 * 1024
MAX_CLIENT = 192 * 1024 * 1024
MAX_FILES = 4096
MAX_HTML = 2 * 1024 * 1024
SUPPORTED = {".html", ".htm", ".js", ".css", ".png", ".jpg", ".jpeg", ".ogg", ".mp3", ".wav", ".woff", ".woff2", ".ttf"}
EXTENSIONS = r"html?|m?js|css|png|jpe?g|webp|gif|svg|avif|ogg|mp3|wav|m4a|woff2?|ttf|otf|json|wasm|bin|atlas|xml|mp4"
RESERVED = re.compile(r"^(?:con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\.|$)", re.I)
PRIVATE = re.compile(r"""(?i)(?:\b(?:access_token|refresh_token|session_?id|session_?token|securetoken|mgckey|authorization|set-cookie|bearer|api[_-]?key|password|passwd|client_secret|private[_-]?key)\b|(?:\b(?:ops|ot|sid|token|account_?id|user_?id)\b["']?\s*[:=])|eyJ[\w-]{10,}\.eyJ[\w-]{8,}\.|[\w.%+-]+@[\w.-]+\.[a-z]{2,})""")
DYNAMIC = re.compile(r"\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|RTCPeerConnection|WebTransport|Worker|SharedWorker|serviceWorker|sendBeacon|importScripts|eval|Function|indexedDB|localStorage|sessionStorage)\b|(?:document\s*\.\s*(?:cookie|write)\b|\bimport\b\s*(?:\(|[\w*{'\" ]))")
INCOMPATIBLE = re.compile(r"(?:<svg\b|image/svg\+xml|#[Ee]ntry\b|\b(?:0[xX][\da-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+|[\d_]+)n\b|\?\.|\?\?|\|\|=|&&=|\.replaceAll\s*\(|\bBigInt\s*\()")
GAME_MARKER = re.compile(r"(?:^|[-_ ])(?:game|canvas|playfield|board)(?:$|[-_ ])", re.I)
QUERY_KEYS = {"v", "ver", "version", "hash", "rev", "t", "lang", "locale", "cache", "cb"}
EXTERNAL_LITERAL = re.compile(r"""(?:["'\x60]\s*(?:https?:)?//|(?:data|blob|file|javascript):)""", re.I)


class Gap(Exception):
    def __init__(self, status, detail):
        super().__init__(detail)
        self.status = status


def need_adapter(detail):
    raise Gap("needs_adapter", detail)


def address(raw):
    """保留主机和解码路径供定位，避免 Windows 别名、目录逃逸和查询值进入文件名。"""
    if len(raw) > 8192 or any(ord(c) < 32 for c in raw) or "\\" in raw:
        raise ValueError("地址含控制字符或反斜线")
    u = urlsplit(raw)
    if u.scheme not in {"http", "https"} or not u.hostname or u.username is not None or u.password is not None:
        raise ValueError("不支持的资源地址")
    path = unquote(u.path or "/", errors="strict")
    if re.search(r"%2f|%5c", u.path, re.I) or "%" in path or "\\" in path or any(ord(c) < 32 for c in path):
        raise ValueError("路径编码不明确")
    parts = path.strip("/").split("/") if path.strip("/") else []
    if len(path) > 700 or "//" in path or any(
        p in {".", ".."} or not p or p.endswith((".", " ")) or len(p) > 160 or RESERVED.match(p)
        or re.search(r'[<>:"|?*#;]', p) or PRIVATE.search(p)
        or re.fullmatch(r"(?=[A-Za-z0-9_-]*\d)[A-Za-z0-9_-]{28,}", p) for p in parts
    ):
        raise ValueError("路径不能安全保存")
    # 全部匹配均使用相同序列化，端口、协议也属于来源身份。
    host = "[" + u.hostname + "]" if ":" in u.hostname else u.hostname
    port = u.port
    if port is not None and port != (443 if u.scheme == "https" else 80):
        host += ":" + str(port)
    return u.scheme + "://" + host, path


def public_url(origin, path):
    return origin + path


def disk_name(path):
    return path.lstrip("/") + ("index.html" if path.endswith("/") else "")


def jpeg_target(source_name, reserved):
    preferred = Path(source_name).with_suffix(".png")
    names = [preferred.name, Path(source_name).name + ".png"]
    digest = hashlib.sha256(source_name.encode("utf-8")).hexdigest()[:20]
    # 原 PNG、大小写别名以及同名目录都优先保留。映射仅作用于本地预览的旧 JPEG 请求。
    for index in range(256):
        leaf = names[index] if index < len(names) else f"image-{digest}-{index}.png"
        candidate = (preferred.parent / leaf).as_posix()
        if len(leaf) <= 160 and candidate.casefold() not in reserved:
            reserved.add(candidate.casefold())
            return candidate
    need_adapter("原始文件与 JPEG 转换后的名称冲突过多")


def valid_query(url):
    values = parse_qsl(urlsplit(url).query, keep_blank_values=True)
    return all(k.lower() in QUERY_KEYS and re.fullmatch(r"[\w.-]{0,100}", v) for k, v in values)


class Document(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.game = False
        self.has_script = False
        self.refs = []
        self.scripts = []
        self.block = ""
        self.inline = []
        self.issue = ""

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): v or "" for k, v in attrs}
        if tag == "script" and a.get("src"):
            self.scripts.append(a["src"])
        if tag == "canvas" or GAME_MARKER.search(a.get("id", "")) or GAME_MARKER.search(a.get("class", "")):
            self.game = True
        if tag in {"iframe", "frame", "base", "form", "object", "embed", "svg", "applet", "portal"}:
            self.issue = "入口包含嵌套页面、表单、矢量图或动态资源入口，需要匹配客户端适配器"
        if tag == "meta" and a.get("http-equiv", "").lower() in {"refresh","content-security-policy"}:
            self.issue = "入口含跳转或自定义内容策略，需要检查加载路径"
        if "srcset" in a or "imagesrcset" in a or "srcdoc" in a or "nonce" in a or "ping" in a or "xlink:href" in a:
            self.issue = "页面有多源加载、会话属性或嵌入内容，需要确认依赖"
        if tag == "script" and a.get("type", "").strip().lower() not in {"", "application/javascript", "text/javascript"}:
            self.issue = "入口脚本类型需要专用适配"
        if tag in {"script", "style"}:
            self.block = tag
        if tag == "script" and a.get("src"):
            self.has_script = True
        for k, v in a.items():
            if k in {"src", "href", "poster", "background", "data-src"} and v and not v.startswith("#"):
                self.refs.append(v)
            elif k.startswith("on"):
                self.inline.append(("script", v))
                self.has_script |= bool(v.strip())
            elif k == "style":
                self.inline.append(("style", v))

    def handle_endtag(self, tag):
        if self.block == tag:
            self.block = ""

    def handle_data(self, data):
        if self.block:
            self.inline.append((self.block, data))
            if self.block == "script" and data.strip():
                self.has_script = True


def script_refs(code):
    if PRIVATE.search(code) or DYNAMIC.search(code) or EXTERNAL_LITERAL.search(code):
        need_adapter("原脚本含网络、动态加载、会话读取或外部地址，需要协议或资源适配")
    if INCOMPATIBLE.search(code):
        need_adapter("原脚本含需要降级的语法或 SVG，须保留原件并登记适配")
    if re.search(r"""\.(?:src|href)\s*=\s*(?!\s*['"])|\b(?:setAttribute|createElement)\s*\(\s*['"](?:src|href|script|iframe|link)['"]|\.innerHTML\s*=|[\x60][^\x60]*\$\{[^}]+\}[^\x60]*[\x60]""", code, re.I):
        need_adapter("原脚本动态构造资源地址或文档，依赖无法静态核对")
    # 只解析能完整定位的字面量。脚本加载图片/音效的相对位置以所属页面为准。
    matches = re.findall(r"""(['"])([^'"\r\n\\]*?\.(?:""" + EXTENSIONS + r""")(?:[?#][^'"\r\n\\]*)?)\1""", code, re.I)
    if re.search(r"""(['"])[^'"\r\n]*\.(?:""" + EXTENSIONS + r""")\1\s*\+|\+\s*['"][^'"\r\n]*\.(?:""" + EXTENSIONS + r""")['"]""", code, re.I):
        need_adapter("脚本按运行时参数拼接资源名，需补充资源映射")
    return [url for _, url in matches]


def css_refs(code):
    if PRIVATE.search(code) or INCOMPATIBLE.search(code) or EXTERNAL_LITERAL.search(code) or "\\" in code:
        need_adapter("样式含外部或编码资源，须核实引用")
    urls = re.findall(r"""url\(\s*['"]?([^)'"]+)['"]?\s*\)""", code, re.I)
    urls += re.findall(r"""@import\s+['"]([^'"]+)['"]""", code, re.I)
    if any(x.lstrip().startswith(("var(", "#")) for x in urls):
        need_adapter("样式含动态纹理或矢量引用")
    return [x.strip() for x in urls]


def read_asset(group, limit):
    body = None
    for r in group:
        if not valid_query(r["url"]):
            need_adapter("资源地址含会话或未验证的查询参数")
        if not r["has_body"]:
            continue
        if r.get("size") is not None and r["size"] > limit:
            need_adapter("单个资源超出静态导出大小范围")
        try:
            raw = r["read"]()
        except (ValueError, OSError) as error:
            raise Gap("needs_capture", "原始响应正文丢失或校验失败") from error
        if not isinstance(raw, bytes) or not raw or len(raw) > limit:
            raise Gap("needs_capture", "原始响应为空、超出范围或格式错误")
        if body is not None and raw != body:
            need_adapter("同一原始路径存在不同版本的正文，须选定单一版本")
        body = raw
    if body is None:
        raise Gap("needs_capture", "缺少此资源的完整成功响应正文")
    return body


def text_body(raw):
    if b"\0" in raw:
        need_adapter("文本资源包含二进制数据或未识别字符集")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise Gap("needs_adapter", "文本资源需要匹配原始字符集") from error


def parse_document(html):
    doc = Document()
    try:
        doc.feed(html)
        doc.close()
    except (AssertionError, ValueError) as error:
        raise Gap("needs_adapter", "原始 HTML 的声明或结构需要单独解析") from error
    return doc


def export_static(rows, output: Path, entry: str | None = None) -> dict:
    rows = list(rows)
    by_url = defaultdict(list)
    docs = set()
    backend = set()
    socket_origins = set()
    for r in rows:
        url = r["url"]
        kind = str(r.get("resource_type", "")).lower()
        if url.lower().startswith(("ws:", "wss:")) or kind in {"websocket", "eventsource"}:
            try:
                socket_origins.add(address(re.sub(r"^ws", "http", url, flags=re.I))[0])
            except (ValueError, UnicodeError):
                pass
            continue
        try:
            org, path = address(url)
        except (ValueError, UnicodeError):
            continue
        method = str(r.get("method", "")).upper()
        mime = str(r.get("mime", "")).split(";")[0].lower().strip()
        if method not in {"GET", "HEAD"} or (
            kind in {"fetch", "xhr"} and Path(path).suffix.lower() not in SUPPORTED):
            backend.add(org)
        if method != "GET" or r.get("status") != 200:
            continue
        key = (org, path)
        by_url[key].append(r)
        if mime in {"text/html", "application/xhtml+xml"} or Path(path).suffix.lower() in {".html", ".htm"}:
            docs.add(key)

    # 对多文档站点只列出可核实的游戏容器，避免从大厅或登录页启动。
    candidates = []
    rejected = []
    canvas = re.compile(r"""\.getContext\s*\(\s*["'](?:2d|webgl2?|experimental-webgl)["']""")
    script_markers = {}
    if len(docs) > 128:
        return {"status": "needs_adapter", "detail": "同一输入内包含过多页面，请按游戏拆分抓取", "entries": []}
    for key in sorted(docs):
        try:
            data = read_asset(by_url[key], MAX_HTML)
            document = parse_document(text_body(data))
            if not document.game and not document.issue:
                document.game = any(canvas.search(code) for kind, code in document.inline if kind == "script")
                for script in document.scripts:
                    if document.game:
                        break
                    try:
                        script_key = address(urljoin(public_url(*key), script))
                        if script_key[0] != key[0] or script_key not in by_url:
                            continue
                        if script_key not in script_markers:
                            script_markers[script_key] = bool(canvas.search(text_body(read_asset(by_url[script_key], MAX_FILE))))
                        document.game = script_markers[script_key]
                    except (Gap, ValueError, UnicodeError):
                        continue
            if document.game:
                candidates.append(key)
        except Gap as error:
            rejected.append((key, error))
    listing = [public_url(*key) for key in candidates]
    def result(status, detail, **fields):
        return {"status":status, "detail":detail, "entries":listing, **fields}
    try:
        if entry:
            matches = [k for k in candidates if entry in (public_url(*k), k[1])]
            if not matches:
                for k, problem in rejected:
                    if entry in (public_url(*k), k[1]):
                        raise problem
                return result("needs_adapter", "指定入口与已核实的游戏页面不匹配")
            candidates = matches
        if len(candidates) > 1:
            return result("choose_entry", "检测到多个原始游戏页面，请选择一个明确的入口地址")
        if not candidates:
            if rejected:
                raise rejected[0][1]
            if docs:
                return result("needs_adapter", "已找到 HTML，缺少可独立确认的游戏容器或匹配的专用适配器")
            return result("needs_capture", "未找到成功返回的原始游戏 HTML，请补抓从玩家入口冷启动")
        org, first = candidates[0]
        if org in socket_origins or org in backend:
            need_adapter("游戏来源还包含业务请求、WebSocket 或动态数据，需要核对协议")
        entry_url = public_url(org, first)
        queued = [first]
        files = {}
        provenance = []
        redirects = {}
        seen = set()
        total = 0
        names = {}
        reserved = set()
        for origin, path in by_url:
            if origin == org:
                original = Path(disk_name(path))
                reserved.add(original.as_posix().casefold())
                reserved.update(parent.as_posix().casefold() for parent in original.parents)
        while queued:
            path = queued.pop()
            if path in seen:
                continue
            seen.add(path)
            if len(seen) > MAX_FILES:
                need_adapter("客户端依赖数量超出静态导出范围")
            if (org, path) not in by_url:
                raise Gap("needs_capture", "缺少本地依赖的成功响应，请补抓 " + path)
            ext = Path(disk_name(path)).suffix.lower()
            if ext not in SUPPORTED:
                need_adapter("资源类型需要适配或转换：" + path)
            name = disk_name(path)
            if name.casefold() in names and names[name.casefold()] != path:
                need_adapter("不同原始文件在目标文件系统中重名")
            names[name.casefold()] = path
            group = by_url[(org, path)]
            mime = {r.get("mime", "").lower().split(";")[0].strip() for r in group if r.get("has_body")}
            declared = {".js": {"application/javascript", "text/javascript", "application/x-javascript", "text/ecmascript", "application/ecmascript"},
                        ".css": {"text/css"}, ".html": {"text/html"}, ".htm": {"text/html"}}
            if ext in declared and not mime <= declared[ext] | {"", "text/plain", "application/octet-stream"}:
                need_adapter("响应类型与原资源用途不符：" + path)
            raw = read_asset(group, MAX_HTML if ext in {".htm",".html"} else MAX_FILE)
            source_size = len(raw)
            source_hash = hashlib.sha256(raw).hexdigest()
            pixels = {}
            refs = []
            base = public_url(org, path)
            if ext in {".htm", ".html"}:
                if path != first:
                    need_adapter("游戏引用其他页面，需要核对导航和会话")
                html = text_body(raw)
                document = parse_document(html)
                if document.issue:
                    need_adapter(document.issue)
                if not document.has_script:
                    raise Gap("needs_capture", "入口有游戏容器，但缺少可识别的原始启动脚本")
                if PRIVATE.search(html) or INCOMPATIBLE.search(html):
                    need_adapter("入口含会话字段、SVG 或需降级的前端语法")
                refs.extend(document.refs)
                for kind, code in document.inline:
                    refs.extend(script_refs(code) if kind == "script" else css_refs(code))
            elif ext == ".js":
                base = entry_url
                code = text_body(raw)
                if code.lstrip().startswith(("<", "{\"", "[{")):
                    need_adapter("脚本路径返回文档或结构化数据，需要核对正文")
                refs = script_refs(code)
            elif ext == ".css":
                css = text_body(raw)
                if css.lstrip().startswith(("<", "{\"", "[{")):
                    need_adapter("样式路径返回文档或结构化数据，需要核对正文")
                refs = css_refs(css)
            elif ext == ".png":
                try:
                    raw = convert_png(raw)
                except ValueError as error:
                    raise Gap("needs_adapter", "无法无损转换并校验 PNG：" + path) from error
            elif ext in {".jpg", ".jpeg"}:
                try:
                    raw, pixels = convert_jpeg(raw)
                except ValueError as error:
                    raise Gap("needs_adapter", str(error) + "：" + path) from error
                name = jpeg_target(name, reserved)
                redirects[path] = name
            else:
                prefixes = {".ogg": (b"OggS",), ".wav": (b"RIFF",), ".mp3": (b"ID3", b"\xff"),
                            ".woff": (b"wOFF",), ".woff2": (b"wOF2",), ".ttf": (b"\x00\x01\x00\x00",)}
                if not raw.startswith(prefixes[ext]):
                    need_adapter("媒体或字体正文与扩展名不符：" + path)
            for ref in refs:
                target = urljoin(base, ref)
                try:
                    org2, path2 = address(target)
                except (ValueError, UnicodeError):
                    need_adapter("资源地址不能映射为本地原件")
                if not valid_query(target) or org != org2 or ref.startswith(("//", "http:", "https:")):
                    need_adapter("原版引用外部地址或含会话参数，需提供本地地址适配")
                queued.append(path2)
            total += len(raw)
            if total > MAX_CLIENT or len(raw) > MAX_FILE:
                need_adapter("客户端或单项产物超出静态导出大小范围")
            files[name] = raw
            provenance.append({"source": public_url(org, path), "file": name, **pixels,
                               "source_bytes": source_size, "source_sha256": source_hash,
                               "output_bytes": len(raw), "output_sha256": hashlib.sha256(raw).hexdigest()})
        folded = {name.casefold() for name in files}
        if any(parent.as_posix().casefold() in folded
               for name in files for parent in Path(name).parents if parent != Path(".")):
            need_adapter("文件路径与目录名称冲突")
        output = Path(output)
        output.mkdir(parents=True, exist_ok=True)
        if (output / "client").exists() or (output / "client").is_symlink():
            need_adapter("目标 client 目录已存在，请选择新的输出目录")
        with tempfile.TemporaryDirectory(prefix=".static-", dir=output) as tmp:
            root = Path(tmp) / "client"
            for name, raw in files.items():
                dest = root / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(raw)
            root.rename(output / "client")
        return result("static_candidate", "已按原始引用导出本地静态依赖，互动效果仍需浏览器验收",
                      entry_path=disk_name(first), resource_count=len(files), resources=provenance, redirects=redirects)
    except Gap as error:
        return result(error.status, str(error))
