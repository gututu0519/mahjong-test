# Node 运行时

游戏客户端前端版本由构建自动编号，平台“游戏前端版本”可检查、切换新会话和回退，旧会话保持原资源。在本目录执行 `npm run frontend:stage -- --game buffalo-win` 可构建并本地安装，不自动激活；部署与验证边界见 [游戏前端版本](../docs/game-frontend-versions.md)。后端游戏包也自动读取构建发布号，平台注册不再要求手填版本。

当前默认拓扑为独立网关 + 每款独立游戏计算服务。平台后台提供“游戏服务与版本”，支持注册、检查、切换和回退；商户后台没有该入口和权限。新整局切换版本，进行中整局和重试保留原版本。完整操作及部署说明见 [独立游戏服务与版本切换](../docs/game-service-architecture.md)。

后端目录已统一：当前 Node 实现位于 `server/`，旧 Python 实现位于 `py/`，实例配置、数据库和日志仍归根目录 `services/`。从仓库根目录使用 `node server/tools/start.mjs <服务>`；Python 回退使用 `python -m py.run` 或各服务的 `start-python.bat`。迁移生成模块位于 `migrated/py/`，资源包内使用 `resources/py/` 保存必要的协议资料，运行时不执行 Python。

19 款游戏、通用游戏 API、商户网关、模拟商户平台、平台/商户管理后台和 RTP worker 均有 Node 实现。正常构建、测试、启动不调用 Python。抓包、解包工具继续保留 Python；旧后端源码与回退脚本暂留。当前完成本地迁移与自动化验证，未切换线上流量。

## 目录与职责

接入中心规范以 `config/integration.json` 为源文件。修改后执行 `npm run docs:build` 同步下载指南与 OpenAPI，执行 `npm run docs:check` 检查三份内容一致；历史 Python 文档不作为 Node 接入规范生成源。v1.11 新整局通过 decision_id、game_id、round_id 串联预派彩和钱包，签名 `/gtt/v1/rounds/get` 查询当前整局，`/gtt/v1/rounds/changes` 按持久化游标拉取变化；查询返回实际取档、RTP 回退及已确认累计账务。

RTP 配置支持游戏覆盖、商户继承和默认 96%，保留已有玩家覆盖。配置预派彩地址后自动尝试，调用或返回格式校验失败时回退 RTP，无需开关；已有整局绑定保持不变。配置目标不代表模型已通过标定；规则、逐款任务和统计验证边界见 [RTP 继承与标定](../docs/rtp-inheritance.md)。

商户钱包六项回调支持 `wallet_endpoints` 独立完整 URL（`balance`、`debit`、`credit`、`refund`、`transactions/get`、`transactions/list`），未填写项沿用 `wallet_url` 加标准路径。全部独立配置后默认地址可留空，签名使用实际 pathname。已有数据库启动时增加独立配置表，不改原余额、密钥和入口；指南下载包含实际回调地址。

运营可以开放任何游戏，`config/game-readiness.json` 的收集状态和缺失项仅供查看，不限制开放、新启动或新整局。新商户默认授权全部游戏；目录可导出 HTML/CSV/JSON。当前证据清单仍有 19 款待补，详见 [开放规则与维护流程](../docs/game-integration-readiness.md)。

运营控制台显示完整目录和待补项，平台管理员/运营可管理开放开关（默认关闭、持久化、版本校验及审计）；收集状态不影响开放。商户工作台、签名目录、公共网关目录及商户导出只返回可接入游戏，不包含内部审核资料。关闭返回 `GAME_CLOSED` 并禁止新整局，已开始回合继续恢复结算。

| 业务块 | 位置 | 职责 |
| --- | --- | --- |
| 前端 | 仓库 `clients/`、`demo/`；`frontend/admin/` | 原游戏、大厅、平台和商户后台；游戏素材按 S3 构建规则发布 |
| 后端网关 | `gateway/`、`shared/`、`services/` | 商户鉴权、钱包回调、结算、后台、模拟平台、HTTP/WebSocket 传输 |
| 游戏服务 | `games/buffalo-win/`、`migrated/py/games/` | 19 款引擎；可独立运行原客户端服务或内部计算进程 |
| 协议和通用核心 | `migrated/py/adapters/`、`migrated/py/core/` | 原 PG、PP、JILI/TaDa、Hacksaw、Play’n GO 协议和独立游戏事务存储 |
| 语义兼容层 | `compat/` | Node SQLite、文件、二进制、随机数、整数/浮点/集合等原实现语义 |

剩余游戏采用离线 AST 转换生成 TypeScript，并配套 Node 语义实现；生成结果已入库，运行时执行编译后的 JavaScript，不解释 Python 源码，也不代理 Python 服务。网关、后台、独立传输层及美洲野牛商户计算服务为手写 TypeScript。`tools/translate-runtime.py` 和参考导出脚本只用于迁移开发，**不属于 npm 构建依赖**。后续业务修改以 TypeScript 为准；重新生成会覆盖 `migrated/`，必须评审差异并重新验证。

## 原入口启动

需要 Node.js 24.17+；本次验证版本 24.19.0。首次在 `server/` 执行：

```powershell
npm ci
npm test
```

之后双击原 `start-server.bat` 或 `services/<名称>/start.bat`。这些入口已默认 Node；工具检测源码变化后编译。各游戏仍使用原 `service.json`、端口、`config/` 和 `data/games.sqlite3`。原脚本保存为同目录 `start-python.bat`。

仓库根目录的命令形式：

```powershell
node server/tools/start.mjs mahjong-ways2
node server/tools/start.mjs fortune-rabbit
node server/tools/start.mjs game-api
node server/tools/start.mjs games
node server/tools/start.mjs gateway
node server/tools/start.mjs mock
node server/tools/start.mjs admin
```

游戏命令支持 `--port`、`--database`，不会自动启动其他游戏。大厅仍通过原端口访问各独立服务。

已有 GTT 本机环境：首次启动辅助服务时，在原私有 `sandbox.json` 旁新增 `node.json`，继续使用原商户、游戏、平台三库和 8110/8111/8112 入口。不覆盖旧配置、不重新生成商户密钥、不重置余额。先停止旧进程再启动 Node，禁止 Python 与 Node 同时写同一库。默认独立服务模式先运行 `games`（8211–8229），再分别运行网关和后台；网关与后台也允许先启动后注册服务。8113 只供历史计算服务兼容，默认网关不再监督该子进程。新增配置及游戏服务密钥受现有 `services/*/data/` 忽略规则保护。

辅助命令 `admin-init`、`launch --language en`、`transactions`、`retry --operation-id <ID>`、`rtp-worker --once` 也可通过 `tools/start.mjs` 执行。显式配置使用 `--config <绝对路径>`。旧商户编号离线维护工具仍作为历史工具保留，不是运行服务。

## 初始化本机商户环境

在 `server/` 执行：

```powershell
npm run init
npm run sandbox-init
npm run games
# 另开终端，分别启动：
npm run gateway
npm run platform
npm run admin
npm run rtp-worker
```

`init` 拒绝覆盖已有配置；默认配置写入 `services/gtt-gateway/data/node.json`，首次管理员凭据写入同目录私有 `admin-bootstrap.json`。`sandbox-init` 创建模拟商户并写入私有凭据文件。端口为网关 8110、平台 8111、后台 8112，19 个内部游戏服务使用 8211–8229。已有配置不能重复初始化，启动时复用已有三库、账号和商户密钥，不创建第二套环境。平台和商户后台分别为 `/`、`/merchant/`。

全部 19 款现已接入统一网关与平台/商户后台。新商户钱包统一固定精度 10000，后台不再提供选择，创建接口拒绝其他精度；新建模拟商户授权 1–19，初始余额 2000.0000 USD。商户无需传入或回传 minor_unit，钱包回调也不发送此字段；签名目录、交易结果、整局与取档金额均换算为 10000，预派彩主币种字符串固定四位小数。游戏引擎与原客户端保留原生金额单位。当前本机无真实商户，原两位精度测试数据已备份并等值换算，账号、密钥和游戏状态保留；平台管理员可编辑授权。详细编号、原生金额精度和接入流程见 [统一商户接入](../docs/unified-merchant-games.md)。本机游戏地址分别使用 `g1.localhost:8110` 至 `g19.localhost:8110`，始终打开签名启动接口返回的完整 URL。

## 19 款内部计算服务

每个进程选择一款游戏，独立端口、配置和内部密钥，不连接玩家数据库或商户钱包：

```powershell
node dist/cli.js game --game-id fortune-rabbit --game-config ../services/fortune-rabbit/config/fortune-rabbit.json --secret-file <内部密钥文件> --port 8214
```

密钥至少 32 字符。所有请求需 `Authorization: Bearer ...`；提供 `/health`、`POST /v1/describe`、`/v1/initial`、`/v1/normalize`、`/v1/step`。`step` 接收 `state`、原投注 `bet`、固定字符串 `seed` 和 `operation_id`；重试返回相同计算结果。它不会自动向商户网关注册游戏。现有美洲野牛商户计算服务继续使用 `buffalo` 命令，保留整局预派彩接口。

## 构建和资源

```powershell
npm run package -- --build-id gtt-node-<唯一编号> --assets-manifest ../diagnostics/releases/gtt-game-assets-2e8b417be6a438768bc4/manifest.json
node tools/smoke-release.mjs ../diagnostics/releases/<构建ID>
```

输出到 `diagnostics/releases/<构建ID>/`：

- `gateway.tar.gz`：商户网关、后台、RTP worker 及必要协议/启动资料；默认经 HTTP 调用独立游戏服务。
- `game-<游戏代码>.tar.gz`：19 款游戏分别独立打包，包含 `GAME.json` 发布身份和单款配置。新旧版本可用不同端口并行运行，后台切换新整局路由。
- `buffalo-win.tar.gz`：历史商户美洲野牛计算服务兼容包，新拓扑使用 `game-buffalo-win.tar.gz`。
- `all-services.tar.gz`：全部 Node 运行代码、20 份服务配置、协议 schema、私有启动资料、大厅和后台。
- `frontend.tar.gz`、`infra.tar.gz`：后台前端及部署模板。
- `release.json`、包内清单：来源、文件和归档 SHA-256、服务范围、现有 S3 素材绑定；`verification.json` 由成功的独立验收生成。

运行包无需 npm 安装，也不含 Python、测试、数据库、密钥或抓包。`all-services` 不包含全部游戏图片、音效、脚本素材：部署独立游戏时，把原完整 `clients/` 合并/挂载到包内 `resources/clients/`；或用 `GTT_RESOURCE_ROOT` 指向与 `resources/` 同形的完整资源根目录。不能只用最小包宣称完整客户端已可游玩。

现有美洲野牛 S3 素材版本与 374 个文件字节继续校验绑定。其他游戏的 Node 迁移不意味着其 S3 白名单、CDN 路由已完成；当前素材发布器仍只支持美洲野牛。构建不上传 S3、不重启线上服务。

验证结果见 [VALIDATION.md](VALIDATION.md)，切换与回退见 [迁移实施](../docs/node-migration.md)。原版规则证据边界仍以各游戏文档为准；Node/Python 一致不代表新增规则得到原版抓包证明。
