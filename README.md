# Mahjong Test

独立服务的入口、配置、数据与进程隔离以 [服务目录说明](services/README.md) 为准。

本仓库包含本地多游戏服务端、麻将客户端资源，以及浏览器请求抓取工具。

```text
server/              # 多游戏平台，内部按公共核心、游戏、协议、服务入口分类
Mahjong Ways 2/      # 原客户端资源、协议分析与旧样本回放工具
response-capture/   # 浏览器请求与响应抓取工具
start-server.bat    # 新服务端启动入口
```

目录归属、服务分类和后续接入约定见 [多游戏、多服务架构](server/ARCHITECTURE.md)。

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

同一个麻将服务启动后，访问 <http://localhost:8080/demo/> 打开 SPINLAB Slot 试玩大厅。
大厅提供游戏搜索及可试玩／即将上线筛选；当前麻将、美洲野牛与宙斯可试玩，另外两个主题是展示预告。
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

`Mahjong Ways 2/SPIN_INTERFACE_ANALYSIS.txt` 和 `analyze_spin.py` 保存了协议与规则分析。
旧的 `serve_local.py` 仍可手动启动，专用于抓取样本回放对照：

```powershell
python ".\Mahjong Ways 2\serve_local.py" --port 8081
```

旧钱包仍保存在 `Mahjong Ways 2/diagnostics/local-spin-state.json`，不会被新服务自动迁移或覆盖。
原始规则面板与资源来源说明保留在游戏目录的 `fixtures/` 中。

## Buffalo Win 独立游戏服务

运行 `python -m server.services.buffalo_demo` 启动独立的 8083 服务，然后在试玩大厅选择「美洲野牛 → 试玩」。已接入生成引擎、扩展转轴、免费旋转和独立持久化钱包；当前开放中文试玩。概率与未覆盖规则采用明确标注的本地配置，详见 [服务说明](services/buffalo-win/README.md)。

## 抓取工具

Gates of Olympus（PP）已提供中英文横竖屏本地试玩：运行 `python -m server.run --service-dir services/gates-of-olympus`，
访问 <http://127.0.0.1:8085/> 或在大厅选择对应试玩卡片。已接入生成旋转、连消、倍率球、免费回合、免费购买及独立虚拟钱包。功能保留和补抓约定见 [AGENTS.md](AGENTS.md)。
资源及本地适配说明见 [PP 独立试玩服务](services/gates-of-olympus/README.md)。

双击 `response-capture/start.bat`。首次启动会创建虚拟环境并安装依赖。
访问 <http://127.0.0.1:8090>；详细说明见 [抓取工具文档](response-capture/README.md)。

数据库、抓取数据、诊断文件、虚拟环境和运行日志只保留在本机，不提交到 Git。
