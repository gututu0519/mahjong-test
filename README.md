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

访问 <http://localhost:8080/?mock=1>。页面显示“本地独立引擎 · 虚拟余额”。
这里的 `mock=1` 只是原客户端的本地登录开关；牌面、中奖和补牌由新引擎生成，不循环播放抓取样本。
游戏目录在 <http://localhost:8080/api/v1/games>，服务状态在 <http://localhost:8080/health>。

完整架构、API、接入新游戏的方法、实现边界与分阶段规划见 [服务端说明](server/README.md)。

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

## 抓取工具

双击 `response-capture/start.bat`。首次启动会创建虚拟环境并安装依赖。
访问 <http://127.0.0.1:8090>；详细说明见 [抓取工具文档](response-capture/README.md)。

数据库、抓取数据、诊断文件、虚拟环境和运行日志只保留在本机，不提交到 Git。
