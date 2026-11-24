"""从大厅目录和已保存的图片生成可渐进显示的本地游戏封面。"""
from collections import defaultdict
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO
import json
from pathlib import Path
import re
import threading
import time
from urllib.parse import quote, unquote, urlsplit
from urllib.request import build_opener, HTTPRedirectHandler
from uuid import uuid4

from capture_layout import session_folders
from capture_quality import _body_path

ROOT = Path(__file__).resolve().parent
CDN = 'https://cdn.777sslot.com/common/game_icon_shu/'
LIMIT = 12 * 1024 * 1024
KEY = r'[A-Za-z0-9_-]{1,100}'
PNG = b'\x89PNG\r\n\x1a\n'


def cdn_url(value):
    if not isinstance(value, str) or not value.startswith(CDN) or len(value) > 600:
        return None
    url = urlsplit(value)
    if url.query or url.fragment:
        return None
    tail = unquote(value[len(CDN):])
    if (not tail.lower().endswith('.png') or any(part in ('', '.', '..') for part in tail.split('/'))
            or any(ord(c) < 32 or c in '\\%?#' for c in tail)):
        return None
    return CDN + quote(tail, safe='/')


def slug(value):
    return re.sub(r'[^a-z0-9]', '', value.lower())


class HallCards(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cards = {}
        self.card = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'article':
            self.card = {'brand': attrs.get('data-provider', '')}
        if self.card is None:
            return
        if tag == 'img' and re.fullmatch(r'/demo/[\w.-]+', attrs.get('src', '')):
            self.card['file'] = attrs['src'].split('/')[-1]
        code = attrs.get('data-launch', '')
        if code and re.fullmatch(KEY, code) and self.card.get('file'):
            self.cards[code] = self.card.copy()

    def handle_endtag(self, tag):
        if tag == 'article':
            self.card = None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def encode_cover(raw):
    import oxipng
    from PIL import Image

    try:
        opened = Image.open(BytesIO(raw))
    except Image.DecompressionBombError as exc:
        raise ValueError('封面尺寸超出上限') from exc
    with opened as source:
        if source.width * source.height > 12_000_000 or getattr(source, 'is_animated', False):
            raise ValueError('不支持该封面尺寸或动画格式')
        pixels = source.convert('RGBA').tobytes()
        if raw.startswith(PNG):
            png = raw
        else:
            out = BytesIO()
            source.save(out, format='PNG')
            png = out.getvalue()
        try:
            result = oxipng.optimize_from_memory(png, level=0, force=True, interlace=oxipng.Interlacing.Adam7,
                                                 bit_depth_reduction=False, palette_reduction=False,
                                                 grayscale_reduction=False, color_type_reduction=False)
        except oxipng.PngError as exc:
            raise ValueError('无法无损转换该封面') from exc
        with Image.open(BytesIO(result)) as check:
            if (not result.startswith(PNG) or result[28] != 1 or check.size != source.size
                    or check.convert('RGBA').tobytes() != pixels):
                raise ValueError('封面交错编码或像素校验未通过')
        return result


class GameCovers:
    def __init__(self, root=ROOT):
        self.root = root
        self.demo = root.parents[1] / 'demo'
        self.cache = root / '.cover-cache'
        self.index_lock = threading.Lock()
        self.locks = [threading.Lock() for _ in range(32)]
        self.transfers = threading.BoundedSemaphore(6)
        self.batches = {}
        self.signature = None
        self.checked = 0
        self.routes = {}
        self.saved = {}

    def read_batch(self, folder, manifest):
        catalog, saved = {}, {}
        for row in json.loads(manifest.read_bytes()).get('rows', []):
            if row.get('method') != 'GET' or row.get('status') != 200 or row.get('state') != 'complete':
                continue
            url = row.get('url', '')
            is_catalog = url.split('?', 1)[0] == 'https://sdstest.ink/api/v1/games/catalog'
            cover = cdn_url(url)
            if not is_catalog and not cover:
                continue
            body = _body_path(folder, row)
            if not body or not 0 < row['size'] <= LIMIT:
                continue
            if cover:
                saved[cover] = body
                continue
            try:
                for item in json.loads(body.read_bytes()).get('items', []):
                    meta = item.get('metadata') or {}
                    image = cdn_url(meta.get('imageUrl'))
                    if image and isinstance(item.get('id'), str):
                        catalog[item['id']] = (str(meta.get('brand','')).lower(), str(item.get('externalId','')),
                                               str(item.get('name','')), image)
            except (ValueError, TypeError, AttributeError):
                continue
        return catalog, saved

    def refresh(self):
        with self.index_lock:
            if time.monotonic() - self.checked < 15 and self.signature is not None:
                return
            hall = self.demo / 'index.html'
            sources = []
            for folder in session_folders(self.root / 'captures', skip_ambiguous=True).values():
                manifest = folder / 'manifest.json'
                if manifest.is_file():
                    stat = manifest.stat()
                    sources.append((stat.st_mtime_ns, stat.st_size, manifest))
            sources.sort()
            signature = (hall.stat().st_mtime_ns if hall.is_file() else 0, sources)
            if signature != self.signature:
                parser = HallCards()
                if hall.is_file():
                    parser.feed(hall.read_text(encoding='utf-8'))
                batches, catalog, saved = {}, {}, {}
                for stamp, size, manifest in sources:
                    key = (manifest, stamp, size)
                    try:
                        batches[key] = self.batches[key] if key in self.batches else self.read_batch(manifest.parent, manifest)
                    except (ValueError, OSError):
                        continue
                    items, images = batches[key]
                    catalog.update(items)
                    saved.update(images)
                routes = {('code', code): self.demo / card['file'] for code, card in parser.cards.items()}
                local = {(card['brand'], slug(code)): routes['code', code] for code, card in parser.cards.items()}
                names, brands = defaultdict(set), defaultdict(set)
                for site, (brand, ext, name, url) in catalog.items():
                    source = local.get((brand, slug(name)), url)
                    routes['site', site] = source
                    names[slug(name)].add(source)
                    brands[brand, ext].add(source)
                for (brand, ext), matches in brands.items():
                    if len(matches) == 1:
                        routes['brand', brand, ext] = next(iter(matches))
                # 外部工作区可能只有游戏代码；跨品牌重名时不猜图。
                for name, matches in names.items():
                    if len(matches) == 1:
                        routes['slug', name] = next(iter(matches))
                self.batches, self.routes, self.saved = batches, routes, saved
                self.signature = signature
            self.checked = time.monotonic()

    def get(self, path):
        if path.startswith('/game-covers/lobby/'):
            source = cdn_url(CDN + path.removeprefix('/game-covers/lobby/'))
            if not source:
                raise KeyError('无效的大厅封面路径')
            return self.convert(source)
        parts = path.removeprefix('/game-covers/').removesuffix('.png').split('/')
        if (not path.startswith('/game-covers/') or not path.endswith('.png') or
                len(parts) not in (2, 3) or parts[0] not in ('code', 'site', 'brand') or
                any(not re.fullmatch(KEY, p) for p in parts)):
            raise KeyError('未知封面')
        self.refresh()
        source = self.routes.get(tuple(parts))
        if not source and parts[0] == 'code' and len(parts) == 2:
            source = self.routes.get(('slug', slug(parts[1])))
        if not source:
            raise KeyError('缺少可唯一匹配的大厅封面')
        return self.convert(source)

    def convert(self, source):
        original = source if isinstance(source, Path) else self.saved.get(source)
        identity = str(source)
        if original and original.is_file():
            stat = original.stat()
            identity += f'/{stat.st_size}/{stat.st_mtime_ns}'
        key = sha256(identity.encode()).hexdigest()
        cached = self.cache / (key + '.png')
        with self.locks[int(key[:2], 16) % len(self.locks)]:
            if cached.is_file():
                return cached.read_bytes()
            with self.transfers:
                if original and original.is_file():
                    if original.stat().st_size > LIMIT:
                        raise ValueError('封面过大')
                    raw = original.read_bytes()
                elif isinstance(source, str):
                    with build_opener(NoRedirect).open(source, timeout=10) as response:
                        raw = response.read(LIMIT + 1)
                    if len(raw) > LIMIT or not raw.startswith(PNG):
                        raise ValueError('原大厅图片格式不符')
                else:
                    raise FileNotFoundError('本地大厅封面缺失')
                png = encode_cover(raw)
                self.cache.mkdir(exist_ok=True)
                temp = self.cache / (key + '.' + uuid4().hex + '.tmp')
                stats_tmp = temp.with_suffix('.json.tmp')
                try:
                    temp.write_bytes(png)
                    metrics = cached.with_suffix('.json')
                    stats_tmp.write_text(json.dumps({'source_bytes': len(raw), 'png_bytes': len(png),
                                                      'delta_bytes': len(png) - len(raw)}), encoding='utf-8')
                    stats_tmp.replace(metrics)
                    temp.replace(cached)
                finally:
                    temp.unlink(missing_ok=True)
                    stats_tmp.unlink(missing_ok=True)
                return png


COVERS = GameCovers()


def serve_cover(handler, path):
    try:
        payload = COVERS.get(path)
    except KeyError:
        return handler.send_error(404)
    except (OSError, ValueError, RuntimeError, ImportError):
        return handler.send_error(503)
    handler.send_response(200)
    handler.send_header('Content-Type', 'image/png')
    handler.send_header('Content-Length', str(len(payload)))
    handler.send_header('Cache-Control', 'private, max-age=300')
    handler.send_header('X-Content-Type-Options', 'nosniff')
    handler.end_headers()
    handler.wfile.write(payload)
