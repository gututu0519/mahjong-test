# 四目录工作区

2026-11-13，按 games、gateway、admin、other 重组。本文记录目录重组；其后 Node 运行数据已迁移 PostgreSQL，见[数据库迁移记录](project/postgresql-migration.md)。游戏功能、商户入口及旧 SQLite 备份保留，未切换线上流量。

## 归属

| 原位置 | 当前物理位置 |
| --- | --- |
| `clients/<game>/` | `games/<game>/frontend/` |
| `server/migrated/py/games/<game>/` | `games/<game>/backend/engine/` |
| 单款专用 adapter 与试玩 service | `games/<game>/backend/adapters/`、`backend/services/` |
| `server/games/buffalo-win/` | `games/buffalo-win/backend/native/` |
| `services/<game>/` | `games/<game>/instance/` |
| `server/gateway/` | `gateway/src/`，后台接口迁到 `admin/backend/`，共享控制库模块到 `other/shared/control.ts` |
| `server/frontend/admin/` | `admin/frontend/` |
| 网关、后台实例 | `gateway/instance/`、`admin/instance/` |
| `server/compat/`、公共迁移代码、shared | `other/shared/` |
| `server/tools/` | `other/tooling/scripts/` |
| `server/tests/`、fixtures | `other/tests/`、`other/tests/fixtures/` |
| `py/` | `other/legacy/py/`（历史回退源码，不是当前 Node 游戏实现） |
| `docs/` | `other/docs/project/`，各游戏专用记录到 `games/<game>/docs/` |
| `deploy/`、`server/deploy/` | `other/deploy/legacy/`、`other/deploy/node/` |
| `demo/` | `other/demo/` |
| 抓取工具、HAR | `other/capture/` |
| 旧 `diagnostics/`、`server/runtime/` | `other/diagnostics/history/`、`other/diagnostics/pre-layout/runtime/` |

现有 `instance/README.md` 保留该服务的原有说明。实例内旧 `start.bat` 转发到新的游戏或业务入口。

## 命令入口

在仓库根目录执行 `npm run setup` 安装构建依赖到 `other/tooling/node_modules/`，不产生第五个顶层业务文件夹。

```powershell
npm run build
npm test
npm run games
npm run gateway
npm run admin
npm start -- buffalo-win
npm start -- mock
node other/tooling/run.mjs start rtp-worker
node other/tooling/run.mjs smoke-start
```

全新环境使用 `node other/tooling/run.mjs cli init --config <新配置路径>`，后续以 `npm start -- gateway --config <路径>` 等命令指定同一配置。模拟商户环境使用 `node other/tooling/run.mjs cli sandbox-init`；已有账号、密钥和数据库不重新初始化。

旧 Python 入口通过各游戏 `instance/start-python.bat` 或 `node other/tooling/run.mjs python -m <原模块名>` 调用。Node 日常运行不依赖 Python；Python 工具仍属历史兼容链路。

## 源码与编译产物

`other/tooling/layout.json` 明确记录每个 TypeScript 源码与发布模块路径的对应关系。源码导入已调整为四目录中的真实相对路径，可运行以下命令做独立类型检查：

```powershell
node other/tooling/node_modules/typescript/bin/tsc -p other/tooling/tsconfig.json
```

`build.mjs` 类型检查后使用 TypeScript 编译器转换模块导入，将 JavaScript 输出为已有发布契约的内部布局。这使协议 worker 的动态加载、规则资料定位及旧发布包目录契约继续工作。新增 TypeScript 文件需添加 `layout.json.modules` 映射；新增运行所需非代码文件需添加 `layout.json.files` 或明确的资源挂载。

`other/runtime/server/` 是生成的运行与打包目录，不包含需要独立维护的第二份业务源码。`other/runtime/clients/` 和 `services/` 中的目录链接分别指向真实前端和实例目录；Windows 使用 junction，Linux 使用目录符号链接。数据库、密钥、客户端素材只有一份物理来源。所有这些链接都位于被忽略的 `other/runtime/` 内，根目录不会恢复旧目录。

生成文件不作为源码编辑。重建由 `npm run build` 完成；不要使用会遍历 junction 目标的清理工具清理运行目录。正式发布包复制所需字节，不依赖开发机 junction。

`npm run layout:check` 检查顶层目录、模块登记、资源链接和已有数据库；必须先完成构建。一次性迁移审计另用 `node other/tooling/check-layout.mjs --migration`，需要本机移动清单和迁移前的 Git 基线。源码 map 指向新的真实源码目录，后台接入文档生成仍写回 `admin/config/`。

## 数据与配置

原目录通过重命名迁移，数据库与 WAL 文件一起保留。两个本机私有 JSON 配置中的旧绝对路径已更新，原值备份为同目录 `.before-layout` 文件，继续受 Git 忽略规则保护。未重置商户、密码、服务密钥、授权、开放状态或激活版本。

`restructure.mjs` 与 `finish-layout.mjs` 是本次一次性迁移记录；新检出不需要执行它们。日常操作只需 setup、build、start。移动清单在本机 `other/diagnostics/layout/moves.json`。

## 构建与验收

- 迁移前全量测试：255 项，254 通过，1 失败。
- 迁移后全量测试：255 项，254 通过，1 失败；失败项相同，为已知 Super Ace 客户端日期锁 VM 回归，未屏蔽该测试。
- 四目录源码类型检查、编译成功，现有 140 个 TypeScript 模块均纳入构建。
- 启动冒烟通过：福兔独立试玩、网关、历史内嵌计算子进程及退出清理。
- 独立发布包构建与干净解包验证通过：网关、美洲野牛、后台、RTP worker 和全部打包服务；独立游戏注册、版本路由与固定种子重试由原冒烟程序验证。
- 发布记录：`other/diagnostics/releases/gtt-node-four-domains-20261113/release.json` 与 `verification.json`。
- 美洲野牛客户端构建成功：381 个静态文件、45 个私有文件；内容摘要与迁移前已构建版本相同（`79bc8eab…`）。
- 接入文档生成一致性检查通过。
- 迁移清单核对：6,582 个原受版本管理的路径均保留；5,842 个客户端文件与 Git 原始字节逐项一致。
- 26 个本机 SQLite 数据库只读 `quick_check` 均通过；目录链接确认指向真实业务资源与实例。
- 历史 Python 入口的服务边界、美洲野牛 HTTP 流程和 PG 模块修复共 11 项回归通过。
- 本机网关 8110、后台 8112 及 19 款独立计算服务 8211–8229 已按新路径恢复启动。

这些结果不代表真实 CDN 已部署或全部游戏已完成浏览器验收。各游戏原有缺口继续以对应规则和缺口文档为准。
