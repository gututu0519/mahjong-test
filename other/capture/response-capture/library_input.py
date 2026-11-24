"""为本机游戏清单投影单个批次，不返回原始请求参数、报文或玩家数据。"""
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from capture_quality import _body_path


CATALOG_PATH = '/api/v1/games/catalog'
PG_STATIC = re.compile(r'/\d+/(?:index\.html|assets/.+|history/index\.json|[a-f0-9]{8,64}\.[a-f0-9]{5,64}\.(?:js|json|png))')
PATHS = {
    'sdstest.ink': re.compile(r'/api/v1/games/(?:catalog|[a-zA-Z0-9_-]{1,80}/launch)'),
    's5.mmga1.com': PG_STATIC, 'static5.mmga1.com': PG_STATIC,
    'api.mmga1.com': re.compile(r'/game-api/[a-z0-9-]{1,60}/v\d+/(?:Spin|GameInfo/Get)'),
    'static.funapptoday.com': re.compile(r'/[a-z0-9-]+/v\d+/[a-zA-Z0-9_-]{1,80}/(?:index\.html|.+/studios/[^/]+/games/[a-zA-Z0-9_-]+/.+)'),
}


def project_session(session, folder):
    root = Path(folder).resolve()
    rows, catalogs, unreadable = [], {}, False
    for row in session['rows']:
        if row.get('state') != 'complete' or row.get('status') not in (200, 201) or not row.get('size'):
            continue
        try:
            url = urlsplit(row['url'])
            paths = PATHS.get(url.netloc)
            if url.scheme != 'https' or not paths or not paths.fullmatch(url.path):
                continue
            body = _body_path(root, row)
            if body is None:
                unreadable = True
                continue
            if url.netloc == 'sdstest.ink' and url.path == CATALOG_PATH:
                if row['size'] > 4 * 1024 * 1024:
                    raise ValueError('目录响应超过读取上限')
                data = json.loads(body.read_bytes())
                if not isinstance(data, dict) or not isinstance(data.get('items'), list):
                    raise ValueError('目录格式待识别')
                catalogs[str(row['id'])] = [project_game(item) for item in data['items'] if isinstance(item, dict)]
        except (OSError, ValueError, TypeError, KeyError):
            unreadable = True
            continue
        entry = {key: row.get(key) for key in ('id', 'method', 'status', 'mime', 'size', 'started')}
        entry['url'] = f'https://{url.netloc}{url.path}'
        rows.append(entry)
    return {'rows': rows, 'catalogs': catalogs, 'verified_files': True, 'unreadable': unreadable}


def project_game(item):
    result = {key: item.get(key) for key in ('id', 'externalId', 'name', 'nameZh')}
    meta = item.get('metadata') if isinstance(item.get('metadata'), dict) else {}
    result['metadata'] = {key: meta.get(key) for key in ('brand', 'legacyGameId')}
    provider = item.get('provider') if isinstance(item.get('provider'), dict) else {}
    result['provider'] = {'code': provider.get('code')}
    return result


def catalog_target(rows, folder, site_id):
    """仅从真实大厅目录读取站内 ID 和用于界面检索的名称。"""
    root = Path(folder).resolve()
    for row in rows:
        if (row.get('method') != 'GET' or row.get('status') != 200 or row.get('state') != 'complete'
                or not isinstance(row.get('size'), int) or not 0 < row['size'] <= 4 * 1024 * 1024):
            continue
        try:
            url = urlsplit(row['url'])
            if (url.scheme, url.netloc, url.path) != ('https', 'sdstest.ink', CATALOG_PATH):
                continue
            body = _body_path(root, row)
            if body is None or '.request.' in body.name:
                continue
            payload = json.loads(body.read_bytes())
            items = payload.get('items') if isinstance(payload, dict) else None
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict) and str(item.get('id', '')) == site_id:
                    names = [v.strip()[:160] if isinstance(v, str) else '' for v in (item.get('name'), item.get('nameZh'))]
                    if any(names):
                        result = {'site': site_id, 'name': names[0], 'zh': names[1]}
                        external = item.get('externalId')
                        if isinstance(external, (str, int)) and not isinstance(external, bool):
                            result['externalId'] = str(external).strip()[:80]
                        meta = item.get('metadata')
                        brand = meta.get('brand') if isinstance(meta, dict) else None
                        if not brand and isinstance(item.get('provider'), dict):
                            brand = item['provider'].get('code')
                        if isinstance(brand, str) and brand.strip():
                            result['brand'] = brand.strip()[:32]
                        return result
        except (KeyError, TypeError, ValueError, OSError):
            continue
    return None
