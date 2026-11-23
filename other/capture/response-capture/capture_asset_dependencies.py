"""纯解析已保存清单，不读文件、不联网、不执行客户端脚本。

仅输出能由清单与已核对的 Cocos 规则确定的路径；native 扩展名缺失时
输出版本化 path_prefix，调用者只能与实际已捕获路径关联，不能补猜扩展名。
"""
from __future__ import annotations

import json
import posixpath
import re
from urllib.parse import unquote, urlsplit


_BASE64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
_UUID = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
_SHORT = re.compile(r'^[0-9a-fA-F]{2}[A-Za-z0-9+/]{20}$')


def decode_cocos_uuid(value):
    """已在所抓引擎模块251核对，而非把任意字符串当Base64 UUID猜测。

    源文件 shared/c03a2652ad/f5fe73e9f2.261de.js 的 decode-uuid：
    首两位十六进制保留，其后每两位六比特字符映射成三位十六进制。
    """
    if not isinstance(value, str):
        return None
    if _UUID.fullmatch(value):
        return value.lower()
    if not _SHORT.fullmatch(value):
        return None
    digits = value[:2].lower()
    for offset in range(2, 22, 2):
        left, right = _BASE64.index(value[offset]), _BASE64.index(value[offset + 1])
        digits += f'{left >> 2:x}{((left & 3) << 2) | (right >> 4):x}{right & 15:x}'
    return '-'.join((digits[:8], digits[8:12], digits[12:16], digits[16:20], digits[20:]))


def _safe_path(value):
    if not isinstance(value, str) or not value.startswith('/') or '\\' in value or '\x00' in value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        return None
    decoded = unquote(parsed.path)
    if '\\' in decoded or '\x00' in decoded or any(part in ('.', '..') for part in decoded.split('/')):
        return None
    return decoded


def _base(root, child):
    if not isinstance(child, str) or not child or child.startswith('/') or ':' in child or '\\' in child or '\x00' in child:
        return None
    child = unquote(child)
    if ':' in child or '\\' in child or '\x00' in child or any(part in ('', '.', '..') for part in child.split('/')):
        return None
    return posixpath.join(root, child)


def _pairs(values, label, unknown):
    if not isinstance(values, list) or len(values) % 2:
        unknown.append(f'{label} 版本列表格式无效，不能枚举全部条目')
        return []
    result = []
    for offset in range(0, len(values), 2):
        key, version = values[offset:offset + 2]
        if not isinstance(version, str) or not re.fullmatch(r'[a-zA-Z0-9_-]+', version):
            unknown.append(f'{label} 第{offset // 2 + 1}项版本号格式未知')
            continue
        result.append((key, version))
    return result


def _names(config, indices):
    paths = config.get('paths', {})
    if not isinstance(paths, dict):
        return []
    return sorted({value[0] for index in indices
                   if isinstance(value := paths.get(str(index)), list) and value
                   and isinstance(value[0], str)})


def _scope(names, scene=False):
    if scene:
        return 'entry-scene'
    languages = set()
    for name in names:
        match = re.search(r'(?:^atlas/|/hd/)([a-z]{2}(?:_[a-z]+)?)/', name)
        if match:
            languages.add(match.group(1))
        elif name.startswith('spine/zh/'):
            languages.add('zh')
    # 此处只是路径语言提示，不能推断其他无名字的 pack 成员没有共同依赖。
    return 'bundle-declared' + (':language-hint=' + ','.join(sorted(languages)) if languages else '')


def analyze_asset_manifest(path: str, content: bytes):
    result = {'recognized': False, 'kind': 'unknown', 'dependencies': [], 'unknown': [], 'notes': []}
    safe = _safe_path(path)
    if safe is None:
        result['unknown'].append('清单路径不合法或仍含查询参数')
        return result
    if not isinstance(content, bytes) or len(content) > 16 * 1024 * 1024:
        result['unknown'].append('清单内容不是字节或超过解析上限')
        return result
    try:
        config = json.loads(content.decode('utf-8-sig'))
    except (ValueError, UnicodeError):
        result['unknown'].append('清单不是可解析的UTF-8 JSON')
        return result
    directory = posixpath.dirname(safe)
    if isinstance(config, dict) and isinstance(config.get('main'), str) and 'assets' in config and 'name' in config:
        result.update(recognized=True, kind='shared-package-index')
        main = _base(directory, config['main'])
        if main and main.endswith('.js'):
            result['dependencies'].append({'path': main, 'kind': 'package-script', 'scope': 'package-entry'})
        else:
            result['unknown'].append('shared包入口路径不合法或类型尚未识别')
        if config['assets']:
            result['unknown'].append('shared-assets: assets 为编码或未支持结构，尚未枚举内部文件')
        result['notes'].append('main入口可以直接核对；assets未解码时不能声称shared包依赖闭包完整。')
        return result
    if not (isinstance(config, dict) and isinstance(config.get('uuids'), list)
            and isinstance(config.get('versions'), dict) and 'importBase' in config and 'nativeBase' in config):
        if isinstance(config, str):
            result['kind'] = 'encoded-json-string'
            result['unknown'].append('JSON内容为编码字符串，未解码前不能枚举依赖')
        return result

    result.update(recognized=True, kind='cocos-bundle-config', native_candidates=[])
    unknown = result['unknown']
    if config.get('encrypted') or config.get('isZip'):
        unknown.append('当前bundle声明加密或ZIP，逐文件URL规则未验证')
        return result
    import_base, native_base = _base(directory, config['importBase']), _base(directory, config['nativeBase'])
    if not import_base or not native_base:
        unknown.append('bundle的importBase/nativeBase不属于可安全解析的相对目录')
        return result
    uuids, packs = config['uuids'], config.get('packs', {})
    if not isinstance(packs, dict):
        unknown.append('packs结构无效')
        return result
    scenes = set()
    if isinstance(config.get('scenes'), dict):
        for index in config['scenes'].values():
            if type(index) is int and 0 <= index < len(uuids):
                scenes.add(index)
            else:
                unknown.append('scene索引结构未识别，不能判定主场景必需范围')
    covered, seen_paths = set(), set()
    for key, version in _pairs(config['versions'].get('import', []), 'import', unknown):
        indices = []
        if isinstance(key, str) and key in packs and re.fullmatch(r'[a-zA-Z0-9_-]{2,80}', key):
            asset_id = key
            if not isinstance(packs[key], list) or any(type(index) is not int or index < 0 or index >= len(uuids) for index in packs[key]):
                unknown.append(f'pack {key} 的成员索引无效')
                continue
            indices = packs[key]
        elif type(key) is int and 0 <= key < len(uuids):
            asset_id = decode_cocos_uuid(uuids[key])
            indices = [key]
        else:
            asset_id = decode_cocos_uuid(key)
        if not asset_id:
            unknown.append(f'import标识 {key!r} 不能由已验证规则解析')
            continue
        covered.update(indices)
        names = _names(config, indices)
        dependency = posixpath.join(import_base, asset_id[:2], asset_id + '.' + version + '.json')
        if dependency not in seen_paths:
            seen_paths.add(dependency)
            result['dependencies'].append({'path': dependency, 'kind': 'cocos-import', 'scope': _scope(names, any(i in scenes for i in indices)), 'logical_names': names})

    for key, version in _pairs(config['versions'].get('native', []), 'native', unknown):
        asset_id = decode_cocos_uuid(uuids[key]) if type(key) is int and 0 <= key < len(uuids) else decode_cocos_uuid(key)
        if not asset_id:
            unknown.append(f'native标识 {key!r} 不能由已验证规则解析')
            continue
        names = _names(config, [key]) if type(key) is int else []
        prefix = posixpath.join(native_base, asset_id[:2], asset_id + '.' + version + '.')
        result['native_candidates'].append({'path_prefix': prefix, 'logical_names': names, 'scope': _scope(names)})
    if result['native_candidates']:
        unknown.append(f'native-extension: {len(result["native_candidates"])}个版本节点未在此config声明扩展名，只能关联实际捕获路径，不能猜png/mp3等后缀')
    redirect = config.get('redirect', [])
    if isinstance(redirect, list) and len(redirect) % 2 == 0:
        covered.update(value for value in redirect[::2] if type(value) is int and 0 <= value < len(uuids))
    elif redirect:
        unknown.append('redirect格式未识别')
    undeclared = len(set(range(len(uuids))) - covered)
    if undeclared:
        unknown.append(f'uuid-unversioned: {undeclared}个UUID未由版本化import/pack/redirect覆盖，是否存在额外加载方式尚未确认')
    for name in config.get('deps', []) if isinstance(config.get('deps'), list) else []:
        if isinstance(name, str):
            unknown.append(f'bundle-dependency:{name}: 需与已捕获同名bundle配置关联，不能猜目录和版本')
    result['notes'].extend([
        '清单声明范围包含多语言及按需资源；未保存的清单项不等于当前语言画面必需缺失。',
        'scope的language-hint来自逻辑路径，只是提示，不能据此排除pack中未命名成员。',
        '这里只枚举当前清单，不推断未知动态bundle、原厂资源全集或全部玩法资源闭包。',
    ])
    return result
