# GTT

项目按四个业务目录组织：**games、gateway、admin、other**。当前 Node 运行数据已通过保留数据的迁移切换到 **PostgreSQL 17**；原 SQLite 文件作为切换前备份保留。

## 目录

```text
games/<game>/
  frontend/       原版客户端、图片、音效、启动注入和 fixtures
  backend/        本游戏引擎、专用协议适配和试玩服务
  instance/       service.json、config/、本机私有资料、旧库备份与 logs/
  docs/           本游戏规则与抓取记录（已有记录的游戏）
  start.bat       单款独立试玩入口
gateway/
  src/            鉴权、会话、游戏路由、钱包、结算与恢复
  config/         公共配置模板与数据库结构
  instance/       网关私有配置、数据库路由、迁移快照与日志
  start.bat
admin/
  frontend/       平台控制台与商户工作台
  backend/        后台接口与目录导出
  config/         接入文档和 OpenAPI
  instance/       后台实例配置与日志
  start.bat
other/
  shared/         公共运行库、跨游戏协议和数据模型
  tooling/        构建、启动和发布工具
  tests/          自动化测试与测试 fixtures
  deploy/         Node 和历史基础设施模板
  docs/           项目级文档与验证记录
  demo/           试玩大厅
  mock-platform/  商户钱包模拟平台
  game-api/       独立通用 API 实例
  capture/        抓取工具与 HAR 资料
  legacy/         历史 Python 源码和回退入口
  diagnostics/    诊断、历史产物和新构建
  runtime/        自动生成的运行目录，不是源码维护位置
update/           仅存放带版本号的交付压缩包
```

`.git/` 为 Git 元数据。素材、私有配置和迁移备份保留在所属业务目录中；当前玩家状态、交易和后台配置存放在 PostgreSQL。运行目录通过内部链接读取资源。

## 安装与启动

环境配置按部署单元管理：本机平台应用共用 `gateway/instance/platform.env`，游戏计算实例使用 `games/<game>/instance/releases/<release>.env`，数据库容器配置单独存放。根目录不放业务 `.env`。详见[环境配置与部署](other/docs/project/environment-and-deployment.md)。

需要 Node.js **24.17.0 或更新版本**。所有命令在仓库根目录运行：

```powershell
npm run setup
npm run build
```

现有商户环境分别启动三个终端，npm 入口按“安装依赖并编译 → 迁移 → 启动”执行：

本机 PostgreSQL 位于独立 Docker 容器中，启动应用前需确保 Docker Desktop 和数据库容器运行。连接信息与迁移记录见[PostgreSQL 迁移说明](other/docs/project/postgresql-migration.md)。

```powershell
npm run games
npm run gateway
npm run admin
```

- 平台后台：<http://127.0.0.1:8112/>
- 商户后台：<http://127.0.0.1:8112/merchant/>
- 网关：<http://127.0.0.1:8110/>
- `games` 启动现有 19 款独立计算进程，默认端口 8211–8229。
- 全新环境需要初始化；已有环境不要重新初始化或覆盖私有配置，详见[目录与启动说明](other/docs/project-layout.md)。

在根目录或 `gateway/` 中执行 `npm start` 默认启动网关；`admin/` 中启动后台；`games/<game>/` 中启动该游戏的独立计算服务。游戏目录中的 `npm run demo` 启动独立试玩，原根目录 `npm start -- <game>` 试玩入口也保留。

单款独立试玩可以双击 `games/<game>/start.bat`，或运行：

```powershell
npm start -- mahjong-ways2
npm start -- fortune-rabbit
npm start -- mock
```

麻将试玩及大厅：<http://127.0.0.1:8080/>、<http://127.0.0.1:8080/demo/>。各游戏端口见各自 `instance/service.json`。

## 构建、测试与发布

```powershell
npm test
npm run test:postgres
npm run db:status
npm run docs:check
npm run frontend:build -- --game buffalo-win
npm run frontend:stage -- --game buffalo-win
npm run package -- --assets-manifest <已经验证的素材清单绝对或相对路径>
node other/tooling/run.mjs smoke-release <发布产物目录>
```

应用、独立游戏计算服务、客户端静态资源、基础设施分别构建。新的应用交付压缩包放在根目录 `update/`：网关为 `gateway-<build-id>.zip`，后台独立为 `admin-<build-id>.tar.gz`，其他包为 `<包名>-<build-id>.tar.gz`。版本号默认自动生成，也可通过 `--build-id` 指定，已有版本禁止覆盖。构建中间目录、`release.json` 和验证记录保留在 `other/diagnostics/releases/<build-id>/`；该目录不是压缩包交付目录。客户端静态资源构建仍在诊断发布目录内生成对象和清单。

新网关包已移出后台页面与接口，重复的顶层 `clients/` 合并到 `resources/clients/`。网关、后台及独立游戏包解压后均可 `npm start`，详见[独立打包与启动](other/docs/project/service-packaging-and-startup.md)。

后台仍支持新整局切换后端版本、新会话切换客户端版本，生产部署状态以各文档记录为准。根目录 `AGENTS.md` 为保留在本机的协作约定，由 Git 忽略。

## 文档

- [独立服务包、npm start 流水线与部署目录](other/docs/project/service-packaging-and-startup.md)

- [目录重组、开发入口、兼容运行目录和验收结果](other/docs/project-layout.md)
- [PostgreSQL 迁移、备份和验证记录](other/docs/project/postgresql-migration.md)
- [平台与游戏实例环境配置、部署模板和生成命令](other/docs/project/environment-and-deployment.md)
- [构建与发布规则](other/docs/project/build-and-release.md)
- [独立游戏服务与整局版本切换](other/docs/project/game-service-architecture.md)
- [游戏客户端版本](other/docs/project/game-frontend-versions.md)
- [平台与商户后台](other/docs/project/gtt-admin.md)
- [游戏待验证与素材缺口](other/docs/project/game-validation-and-resource-gaps.md)

目录重组后的 PostgreSQL 数据迁移已在本机完成，未部署线上流量。Super Ace 客户端日期锁 VM 回归为迁移前已有问题，在 PostgreSQL 回归中仍失败，未屏蔽该测试。
