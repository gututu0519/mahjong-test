# 独立服务目录

Dr Zappo（Hacksaw Gaming）：端口 8097，`dr_zappo_client`，独立钱包、原版中英文客户端及大厅入口。启动 `python -m server.run --service-dir services/dr-zappo`，规则与证据见 [接入记录](dr-zappo/README.md)。

Le Vampire（Hacksaw Gaming）：端口 8096，`le_vampire_client`，独立钱包、原版中英文客户端及大厅入口。实现和验证范围见 [接入记录](le-vampire/README.md)。

Wicked Grin（Hacksaw Gaming）：端口 8095，`wicked_grin_client`，独立钱包与原版客户端。当前接入和验证范围见 [接入记录](wicked-grin/README.md)。

每个子目录代表一个独立运行的服务，不代表共享服务里的一个路由。

```text
services/
  mahjong-ways2/        麻将网页及其服务，8080
    start.bat          只启动本服务
    service.json       服务 ID、入口、端口、明确装载的游戏
    config/            本服务自己的游戏配置
    data/              本服务自己的 SQLite、钱包、会话及存档（不提交）
    logs/              本服务自己的运行日志（不提交）
  game-api/            独立 JSON API 演示服务，8082，同样一套目录
  buffalo-win/         美洲野牛网页及其服务，8083，同样一套目录
  gates-of-olympus/    PP 英文横竖屏试玩，8085，独立引擎和数据库
  sweet-bonanza-pop/   PP 英文试玩，8086，独立引擎和数据库
```

双击相应目录中的 `start.bat`，或在仓库根目录分别执行：

```powershell
python -m server.run --service-dir services/mahjong-ways2
python -m server.run --service-dir services/game-api
python -m server.run --service-dir services/buffalo-win
```

每条命令运行一个进程。Ctrl+C 只停止所在终端的服务；后台进程按对应 PID 停止。
根目录 `start-server.bat`、原游戏启动脚本及 `python -m server.app` 只启动麻将服务。
`GET /health` 返回 `service_id`，可确认当前访问的是哪个服务。

## 隔离约定

- 各自数据库：账号、令牌、余额、局面、去重记录及账本默认互不共享。
- 各自配置：调整 A 的概率配置不会修改 B。修改后只重启对应服务；未结束回合的规则版本保护仍有效。
- 各自进程和端口：一个进程停止不结束另一个；重复端口会启动失败，不会抢占已有服务。
- 各自日志：日志归属 `logs/service.log`。目录不要设成指向另一服务的链接，也不要让不同服务复用同一目录。
- 当前复用同一仓库的 Python 公共代码和解释器。运行隔离已经实现，**代码发布版本和 CPU／内存配额尚未隔离**。
  修改公共代码后，下一次启动会加载新版本；正式独立部署时应为每个服务构建、固定依赖及发布版本，
  再用独立虚拟环境或容器部署，不能把共用源码目录当成独立发布隔离。

跨服务账户和钱包没有隐式同步；将来若需要统一账号或跨服务转账，应另外设计显式接口。
`game-api` 默认装载麻将引擎；可显式选择已注册游戏并提供本服务自己的配置。
`buffalo-win` 是独立的第二款游戏服务，玩法覆盖和本地参数见 [美洲野牛服务说明](buffalo-win/README.md)。

## 增加服务

TaDa Fortune Gems 2：端口 8089，`fortune_gems2_client`。当前为未完成的开发检查点，介绍页停在 100%，尚未接入大厅；明天的继续步骤、排障证据和补抓项见 [Fortune Gems 2 接续文档](fortune-gems2/README.md)。

JILI Super Ace：端口 8088，`super_ace_client`。客户端启动与主游戏试玩已打通，平台附加功能仍待补齐；验证范围及继续步骤见 [Super Ace 交接说明](super-ace/README.md)。

PP Gates of Olympus 的独立生成服务见 [服务说明](gates-of-olympus/README.md)。
Sweet Bonanza POP 的接入状态与补抓项见 [服务说明](sweet-bonanza-pop/README.md)，入口 `sweet_bonanza_pop_client`，端口 8086。
`olympus_client` 入口只装载 `gates-of-olympus`，钱包、局面与设置保存到本服务 SQLite。旧 `olympus_preview` 入口仅供资源预览，`games` 必须为空。

新建 `services/<service-id>/`，提供唯一 ID、独立端口和 `service.json`，在 `config/` 中放该服务选择的游戏配置。
JSON API 使用 `entry: "json_api"`。游戏必须先在代码目录登记；不会自动加载全部游戏。
复制模板时只复制启动脚本和配置，不复制 `data/`、`logs/`。启动脚本中的目录名必须改为新服务名。
全新交互类型（如实时房间）新增独立入口；当前 JSON API 仅支持逐步回合契约。

现有麻将存档已从 `server/data/games.sqlite3` 使用 SQLite 备份接口复制到
`services/mahjong-ways2/data/games.sqlite3`。旧文件保留作迁移备份，不再是当前服务的数据库。
重启不会自动重新导入旧库，避免覆盖新进度。

公共实现仍放在 `server/` 作为代码库：
`core/storage.py` 管理存储，`sessions.py` 管理身份，`queries.py` 管理查询和初始状态，
`settlement.py` 管理单次原子结算，`service.py` 只组装这些组件。
游戏规则和客户端协议继续分别归属于 `games/` 和 `adapters/`。

双进程隔离测试：`python -m unittest server.tests.test_process_isolation -v`。

## Big Bass Bonanza

已接入中英文横竖屏原客户端与独立生成引擎；启动 `python -m server.run --service-dir services/big-bass-bonanza`，端口 8087，数据库 `services/big-bass-bonanza/data/games.sqlite3`，不共享其他服务账户或钱包。支持普通旋转、免费收鱼与追加，从大厅进入。抓取证据、验证范围及补抓项见 [服务说明](../services/big-bass-bonanza/README.md)。

JILIUS Joker’s Fortune WinX：端口 8091，`jokers_fortune_winx_client`，已接入大厅。实现及补抓项见 [接入记录](jokers-fortune-winx/README.md)。

### 3 Billion Vaults

独立服务 `services/3-billion-vaults/start.bat`，端口 8092。原版横竖屏客户端与本地钱包，接入证据、验证范围和待补抓项见 [接入记录](3-billion-vaults/README.md)。

## Money Pot DELUXE

端口 8093，`money_pot_deluxe_client`，已加入试玩大厅。原版英文横竖屏、六线收集、神秘符号、Golden Lock Respin 与三档 EX 的实现和证据见 [服务说明](money-pot-deluxe/README.md)。

## Roma X 10000

端口 8094，`roma_x_10000_client`。普通连消、免费及追加、两档购买、战斗、转盘战斗、竖屏、大厅与余额恢复已完成核心流程验收；原版罕见边界和动画断点恢复仍待证据。验证范围及补抓项见 [服务说明](roma-x-10000/README.md)。
