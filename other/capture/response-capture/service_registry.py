"""服务控制台的固定命令登记；界面不能提交命令、路径或任意启动参数。"""
import json
import re
from pathlib import Path


CATEGORIES = [
    {'id': 'fixed', 'title': '常用服务'},
    {'id': 'capture-instances', 'title': '抓取工具实例'},
    {'id': 'original-previews', 'title': '原版游戏试玩'},
    {'id': 'game-demos', 'title': '本地独立试玩'},
    {'id': 'game-compute', 'title': '游戏计算服务'},
    {'id': 'advanced', 'title': '高级服务与共享依赖'},
]


def _json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return {}


def game_catalog(repo):
    """按平台稳定编号读取，目录存在不等同于已登记计算服务。"""
    repo = Path(repo)
    try:
        source = (repo / 'gateway/src/catalog.ts').read_text(encoding='utf-8-sig')
        block = re.search(r'export const GAME_CODES\s*=\s*\[(.*?)\]', source, re.S)
        codes = re.findall(r'"([a-z0-9-]+)"', block[1]) if block else []
    except OSError:
        codes = []
    try:
        source = (repo / 'gateway/src/game-names.ts').read_text(encoding='utf-8-sig')
        names = dict(re.findall(r'"([a-z0-9-]+)"\s*:\s*\[\s*"([^"\n]+)"', source))
    except OSError:
        names = {}
    return [(code, names.get(code, code), 8211 + index) for index, code in enumerate(codes)]


def build_registry(repo):
    repo = Path(repo).resolve()
    entries = []
    def add(identifier, name, category, description, kind, action=None, port=None, **extra):
        entries.append(dict(id=identifier, name=name, category=category, description=description,
                            kind=kind, action=action, default_port=port, **extra))
    add('fixed.gateway', '平台网关', 'fixed', '游戏入口、协议与钱包接口；依赖平台数据库和计算服务。', 'node', 'gateway', 8110, port_env='GATEWAY_PORT')
    add('fixed.admin', '管理后台', 'fixed', '平台管理与商户管理共用的后台服务。', 'node', 'admin', 8112, port_env='ADMIN_PORT')
    add('fixed.mock', '模拟平台', 'fixed', '本机模拟商户钱包与回调服务。', 'node', 'mock', 8111, port_env='MOCK_PORT')
    add('fixed.capture', '抓取工具', 'fixed', '抓取浏览器、保存、下载及历史记录。停止前必须保存活动抓取。', 'capture', port=18095)
    add('fixed.watch', '维护表监督器', 'fixed', '持续核对抓取证据与维护表；无监听端口。', 'watch')
    add('fixed.rtp', 'RTP 任务服务', 'fixed', '执行数据库中的 RTP 校准任务；无监听端口。', 'node', 'rtp-worker')
    for code, name, port in game_catalog(repo):
        home = repo / 'games' / code
        spec = _json(home / 'instance/service.json')
        title = name if name != code else code
        demo_title = '本地游戏试玩大厅 / 麻将胡了 2' if code == 'mahjong-ways2' else title
        demo_description = '同一服务提供 /demo/ 本地游戏试玩大厅与麻将胡了 2 入口；关闭会同时中断这两个入口。' if code == 'mahjong-ways2' else '本地客户端、会话、钱包和游戏引擎一体试玩；不等同于独立计算服务。'
        add('demo.' + code, demo_title, 'game-demos', demo_description,
            'demo', code, spec.get('port'), code=code, registered=spec.get('id') == code, directory=str(home))
        add('compute.' + code, title, 'game-compute', '单款游戏计算接口；不提供玩家页面，按版本独立运行。',
            'compute', code, port, code=code, registered=code in _json(repo / 'gateway/config/game-descriptors.json'), directory=str(home))
    add('advanced.quality', '抓取检查兼容服务', 'advanced', '旧版采集器的只读检查侧车；默认读取 8090。', 'quality', port=8091)
    add('advanced.buffalo', '历史美洲野牛计算', 'advanced', 'embedded 旧拓扑兼容；remote 独立计算不依赖此实例。', 'node', 'buffalo', 8113, port_env='BUFFALO_PORT')
    add('advanced.game-api', '兼容 JSON 游戏接口', 'advanced', '旧版麻将 JSON API 兼容入口。', 'demo', 'game-api', 8082, directory=str(repo / 'other/game-api'), registered=(repo / 'other/game-api/service.json').is_file())
    add('advanced.games-batch', '计算服务批量启动组', 'advanced', '控制台逐款启动缺少的计算服务；跳过已有实例，仅停止本组新建实例，不修改平台激活登记。', 'group')
    add('advanced.postgres', 'PostgreSQL', 'advanced', '平台和多个试玩共用的数据库。', 'postgres', port=15432, reason='尚未识别可核验的数据库管理入口；识别后需先确认共享影响。')
    add('advanced.docker', 'Docker', 'advanced', '数据库容器及其他共享后台依赖。', 'docker', reason='尚未识别可核验的 Docker 管理入口；识别后需先确认共享影响。')
    return entries
