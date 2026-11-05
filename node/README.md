# Node 运行时

19 款游戏、通用游戏 API、商户网关、模拟商户平台、平台/商户管理后台和 RTP worker 均有 Node 实现。正常构建、测试、启动不调用 Python。抓包、解包工具继续保留 Python；旧后端源码与回退脚本暂留。当前完成本地迁移与自动化验证，未切换线上流量。

## 目录与职责

| 业务块 | 位置 | 职责 |
| --- | --- | --- |
| 前端 | 仓库 `clients/`、`demo/`；`frontend/admin/` | 原游戏、大厅、平台和商户后台；游戏素材按 S3 构建规则发布 |
| 后端网关 | `gateway/`、`shared/`、`services/` | 商户鉴权、钱包回调、结算、后台、模拟平台、HTTP/WebSocket 传输 |
| 游戏服务 | `games/buffalo-win/`、`migrated/server/games/` | 19 款引擎；可独立运行原客户端服务或内部计算进程 |
| 协议和通用核心 | `migrated/server/adapters/`、`migrated/server/core/` | 原 PG、PP、JILI/TaDa、Hacksaw、Play’n GO 协议和独立游戏事务存储 |
| 语义兼容层 | `compat/` | Node SQLite、文件、二进制、随机数、整数/浮点/集合等原实现语义 |

剩余游戏采用离线 AST 转换生成 TypeScript，并配套 Node 语义实现；生成结果已入库，运行时执行编译后的 JavaScript，不解释 Python 源码，也不代理 Python 服务。网关、后台、独立传输层及美洲野牛商户计算服务为手写 TypeScript。`tools/translate-runtime.py` 和参考导出脚本只用于迁移开发，**不属于 npm 构建依赖**。后续业务修改以 TypeScript 为准；重新生成会覆盖 `migrated/`，必须评审差异并重新验证。

## 原入口启动

需要 Node.js 24.17+；本次验证版本 24.19.0。首次在 `node/` 执行：

```powershell
npm ci
npm test
```

之后双击原 `start-server.bat` 或 `services/<名称>/start.bat`。这些入口已默认 Node；工具检测源码变化后编译。各游戏仍使用原 `service.json`、端口、`config/` 和 `data/games.sqlite3`。原脚本保存为同目录 `start-python.bat`。

仓库根目录的命令形式：

```powershell
node node/tools/start.mjs mahjong-ways2
node node/tools/start.mjs fortune-rabbit
node node/tools/start.mjs game-api
node node/tools/start.mjs gateway
node node/tools/start.mjs mock
node node/tools/start.mjs admin
```

游戏命令支持 `--port`、`--database`，不会自动启动其他游戏。大厅仍通过原端口访问各独立服务。

已有 GTT 本机环境：首次启动辅助服务时，在原私有 `sandbox.json` 旁新增 `node.json`，继续使用原商户、游戏、平台三库和 8110/8111/8112 入口，新增内部计算端口 8113。不覆盖旧配置、不重新生成商户密钥、不重置余额。先停止旧进程再启动 Node，禁止两个版本同时写同一库。网关启动器会监督其计算子进程；先启动网关，再启动后台。新增配置受现有 `services/*/data/` 忽略规则保护。

辅助命令 `admin-init`、`launch --language en`、`transactions`、`retry --operation-id <ID>`、`rtp-worker --once` 也可通过 `tools/start.mjs` 执行。显式配置使用 `--config <绝对路径>`。旧商户编号离线维护工具仍作为历史工具保留，不是运行服务。

## 新建隔离商户环境

在 `node/` 执行：

```powershell
npm run init
npm run sandbox-init
npm run buffalo
# 另开终端，分别启动：
npm run gateway
npm run platform
npm run admin
npm run rtp-worker
```

`init` 拒绝覆盖已有配置；首次管理员凭据写入私有 `runtime/admin-bootstrap.json`。`sandbox-init` 创建模拟商户并写入私有凭据文件。默认端口为网关 8210、平台 8211、后台 8212、内部美洲野牛 8213；旧环境不受影响。平台和商户后台分别为 `/`、`/merchant/`。

全部 19 款现已接入统一网关与平台/商户后台。新建模拟商户授权 1–19，钱包精度 10000，初始余额 2000.0000 USD。已有商户授权、精度、密钥和余额保持不变；平台管理员可编辑授权。详细编号、原生金额精度和接入流程见 [统一商户接入](../docs/unified-merchant-games.md)。本机游戏分别使用 `g1.localhost:8210` 至 `g19.localhost:8210`，始终打开签名启动接口返回的完整 URL。

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

- `gateway.tar.gz`：商户网关、后台、RTP worker 和美洲野牛最小启动资料。
- `buffalo-win.tar.gz`：原商户美洲野牛计算服务。
- `all-services.tar.gz`：全部 Node 运行代码、20 份服务配置、协议 schema、私有启动资料、大厅和后台。
- `frontend.tar.gz`、`infra.tar.gz`：后台前端及部署模板。
- `release.json`、包内清单：来源、文件和归档 SHA-256、服务范围、现有 S3 素材绑定；`verification.json` 由成功的独立验收生成。

运行包无需 npm 安装，也不含 Python、测试、数据库、密钥或抓包。`all-services` 不包含全部游戏图片、音效、脚本素材：部署独立游戏时，把原完整 `clients/` 合并/挂载到包内 `resources/clients/`；或用 `GTT_RESOURCE_ROOT` 指向与 `resources/` 同形的完整资源根目录。不能只用最小包宣称完整客户端已可游玩。

现有美洲野牛 S3 素材版本与 374 个文件字节继续校验绑定。其他游戏的 Node 迁移不意味着其 S3 白名单、CDN 路由已完成；当前素材发布器仍只支持美洲野牛。构建不上传 S3、不重启线上服务。

验证结果见 [VALIDATION.md](VALIDATION.md)，切换与回退见 [迁移实施](../docs/node-migration.md)。原版规则证据边界仍以各游戏文档为准；Node/Python 一致不代表新增规则得到原版抓包证明。
