# GTT

平台控制台：<http://127.0.0.1:8112/>；商户专属工作台：<http://127.0.0.1:8112/merchant/>。平台管理员在“账户与权限”中创建商户角色并绑定商户，商户即可管理自己的接入资料、密钥、团队及交易。商户数据由服务端隔离；使用说明见 [平台与商户后台](docs/gtt-admin.md)。

新商户接入仅需商户号与 GTT 自动生成的 `merchant_secret`，游戏 API、钱包和预派彩共用统一 HMAC 签名。全部本机商户已统一，密钥无需领取，可在后台随时查看／复制。见 [统一接入密钥](docs/gtt-merchant-wallet-v1.md)。

GTT 预下注决策支持按商户调用合作平台接口、整局派彩区间、固定时间戳重试与原客户端逐步展示；接入约定和本机模拟见 [GTT 预派彩说明](docs/gtt-prebet.md)。FP 仅为设计参考，不是对接依赖。

管理后台已提供首版：<http://127.0.0.1:8112/>。首次执行 `python -m server.merchant.sandbox admin-init` 生成私有登录凭据，再运行 `python -m server.merchant.sandbox admin`。支持三类角色、商户配置、游戏授权、密钥轮换、交易查询与恢复、操作审计，配置修改即时生效。详见 [管理后台说明](docs/gtt-admin.md)。

GTT 商户接入与模拟平台已提供首版：签名启动 Buffalo Win，平台持有玩家余额，支持购买免费、扣款／派奖去重和故障恢复。首次执行 `python -m server.merchant.sandbox init`，再分别运行 `python -m server.merchant.sandbox platform` 和 `python -m server.merchant.sandbox gateway`，打开 <http://127.0.0.1:8111/> 联调。完整约定见 [商户与钱包接口 v1](docs/gtt-merchant-wallet-v1.md)。

Captain's Bounty（PG Soft，54）英文客户端和独立 8102 服务已接入，本轮按 447 条旋转、2 轮完整免费数据收尾。启动 `python -m server.run --service-dir services/captains-bounty`；实现及验收范围见 [规则记录](docs/captains-bounty-rules.md)。

Fortune Rabbit（PG Soft，1543462）英文客户端已接入独立服务 8101 和大厅：`python -m server.run --service-dir services/fortune-rabbit`。普通旋转、奖金符号、完整 8 次福兔功能、规则和历史已接入并核对原版样本；验证范围见 [规则记录](docs/fortune-rabbit-rules.md)。

Great Game Serengeti（Hacksaw Gaming）已接入原版中英文客户端及大厅，独立端口 8098。启动：`python -m server.run --service-dir services/great-game-serengeti`。规则、证据和验证范围见 [接入记录](services/great-game-serengeti/README.md)。

Dr Zappo（Hacksaw Gaming）独立服务：`python -m server.run --service-dir services/dr-zappo`，端口 8097，原版中英文客户端及大厅入口。规则、证据与验收范围见 [接入记录](services/dr-zappo/README.md)。

Le Vampire（Hacksaw Gaming）已接入原版中英文客户端及大厅，独立端口 8096。启动：`python -m server.run --service-dir services/le-vampire`。玩法、验收及证据边界见 [接入记录](services/le-vampire/README.md)。

Wicked Grin（Hacksaw Gaming）独立服务启动：`python -m server.run --service-dir services/wicked-grin`，端口 8095。实现、抓取证据及未完成验收见 [接入记录](services/wicked-grin/README.md)。

独立服务的入口、配置、数据与进程隔离以 [服务目录说明](services/README.md) 为准。

本仓库包含本地多游戏服务端、麻将客户端资源，以及浏览器请求抓取工具。

```text
clients/           # 所有原客户端资源和脱敏 fixtures，按游戏 slug 分类
server/            # 公共核心、游戏引擎、协议适配和服务入口
tools/pg_capture/  # PG 离线导入、规则分析、旧样本回放及诊断工具
docs/              # 接入、规则分析和资源缺失记录
response-capture/  # 浏览器请求与响应抓取工具
services/          # 各游戏独立启动器、配置、数据库和日志
start-server.bat   # 麻将服务启动入口
```

目录归属、服务分类和后续接入约定见 [多游戏、多服务架构](server/ARCHITECTURE.md)。

各款仍缺的原版证据、本地验收、资源与补抓操作统一见 [各游戏待验证与资源缺口](docs/game-validation-and-resource-gaps.md)，覆盖全部 19 款游戏。

## 启动独立服务端

双击 `start-server.bat`，或在仓库根目录执行：

```powershell
python -m server.app
```

访问 <http://localhost:8080/?mock=1> 直接打开游戏。
这里的 `mock=1` 只是原客户端的本地登录开关；牌面、中奖和补牌由新引擎生成，不循环播放抓取样本。
游戏目录在 <http://localhost:8080/api/v1/games>，服务状态在 <http://localhost:8080/health>。

完整架构、API、接入新游戏的方法、实现边界与分阶段规划见 [服务端说明](server/README.md)。

## 演示站

同一个麻将服务启动后，访问 <http://localhost:8080/demo/> 打开 GTT Slot 试玩大厅。
大厅提供游戏搜索、状态及厂商筛选，数量按游戏卡片自动统计。当前接入进度和未完成的验收项见 [阶段记录](DEVELOPMENT_HANDOFF.md)。
前端位于 `demo/`，无需安装依赖或构建。点击「试玩」请求
`POST /api/v1/games/mahjong-ways2/launch`（JSON `{"language":"zh"}` 或 `{"language":"en"}`，省略默认中文），后端创建独立会话，
返回 `launch_url`、`expires_at`、`balance_minor`、`minor_unit` 和 `currency`。
前端使用返回的同源链接在 iframe 内打开游戏，支持重载、全屏和返回大厅。
大厅右上角可切换中文／EN，选择保存在浏览器中，也可通过 `?lang=en` 或 `?lang=zh` 指定。
游戏启动链接中的 `l=en`／`l=zh` 让原客户端加载对应语言的文字、图片和面板。

每次进入分配 2,000 虚拟积分，会话有效期 24 小时；重载保留当前局面，
返回大厅后再次试玩创建新会话。旧游戏入口仍使用原来的本地共享钱包。
游戏链接包含试玩凭据，不应分享；仅限本地演示，不提供充值或提现。
通用 `game-api` 服务不提供大厅或启动链接。对外部署前需另行配置身份、限流和 HTTPS。

## 游戏服务说明

- 新数据库默认位于 `services/mahjong-ways2/data/games.sqlite3`，初始虚拟积分 2000，重启保留进度。
- 所有游戏共用事务钱包和结算流水，各自保存游戏状态。
- 麻将包含独立算奖、金牌转换、消除补牌、普通和免费旋转状态机。
- 符号权重和金牌概率是明确的本地配置，不宣称等于原版概率或原版 RTP。
- 新启动器与旧回放服务使用同一默认端口，请勿同时占用 8080；可用 `--port 8081` 隔离。

独立通用 API 服务可同时运行，默认端口 8082、独立数据库，无客户端资源依赖：

```powershell
python -m server.run --service-dir services/game-api
```

运行后端测试：

```powershell
python -m unittest discover -s server/tests -v
```

需要 Python 3.10+；客户端模块修复还需要 Node.js。新后端不需要额外 Python 包。

## 规则分析与旧回放工具

`docs/mahjong-ways2-spin-interface.txt` 和 `tools/pg_capture/mahjong_ways2/analyze_spin.py` 保存了协议与规则分析。
旧的回放服务仍可手动启动，专用于抓取样本回放对照：

```powershell
python -m tools.pg_capture.mahjong_ways2.serve_local --port 8081
```

旧回放钱包和诊断文件已随目录整理迁至 `diagnostics/mahjong-ways2/`，默认钱包仍为其中的 `local-spin-state.json`，文件内容不变；与正式服务 SQLite 钱包隔离。
原始规则面板与资源来源说明保留在各客户端目录的 `fixtures/` 中。共享模块修复器及校验脚本位于 `server/adapters/pg/`，游戏服务不再通过修改 `sys.path` 引用客户端中的 Python 文件。

## Buffalo Win 独立游戏服务

运行 `python -m server.services.buffalo_demo` 启动独立的 8083 服务，然后在试玩大厅选择「美洲野牛 → 试玩」。已接入生成引擎、扩展转轴、免费旋转和独立持久化钱包；当前开放中文试玩。概率与未覆盖规则采用明确标注的本地配置，详见 [服务说明](services/buffalo-win/README.md)。

## 抓取工具

Sweet Bonanza POP 已接入独立英文服务：运行 `python -m server.run --service-dir services/sweet-bonanza-pop`，访问 <http://127.0.0.1:8086/> 或从大厅进入。普通旋转、连消、免费、倍率与追加已有样本验证；POP 专用动画协议及其他补抓项见 [服务说明](services/sweet-bonanza-pop/README.md)。

Gates of Olympus（PP）已提供中英文横竖屏本地试玩：运行 `python -m server.run --service-dir services/gates-of-olympus`，
访问 <http://127.0.0.1:8085/> 或在大厅选择对应试玩卡片。已接入生成旋转、连消、倍率球、免费回合、免费购买及独立虚拟钱包。功能保留和补抓约定见 [AGENTS.md](AGENTS.md)。
资源及本地适配说明见 [PP 独立试玩服务](services/gates-of-olympus/README.md)。

双击 `response-capture/start.bat`。首次启动会创建虚拟环境并安装依赖。
访问 <http://127.0.0.1:8090>；详细说明见 [抓取工具文档](response-capture/README.md)。

数据库、抓取数据、诊断文件、虚拟环境和运行日志只保留在本机，不提交到 Git。

## Big Bass Bonanza

已接入中英文横竖屏原客户端与独立生成引擎；启动 `python -m server.run --service-dir services/big-bass-bonanza`，端口 8087，数据库 `services/big-bass-bonanza/data/games.sqlite3`，不共享其他服务账户或钱包。支持普通旋转、免费收鱼与追加，从大厅进入。抓取证据、验证范围及补抓项见 [服务说明](services/big-bass-bonanza/README.md)。

## Tower Run Treasure Steps

Tower Run Treasure Steps（Play’n GO，1098）已接入中英文原版客户端和独立生成服务 8099；启动 `python -m server.run --service-dir services/tower-run-treasure-steps`，可从大厅进入。规则、证据范围及补抓项见 [接入文档](docs/tower-run-treasure-steps-rules.md)。
