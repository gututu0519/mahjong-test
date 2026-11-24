# 独立服务包与 npm start

当前游戏交付按实际磁盘目录分开：`update/game-<代码>/<代码>-client-<前端版本>/` 放未压缩前端文件，`update/game-<代码>/<代码>-serve-<服务版本>/` 内放服务端 ZIP。配套 RELEASE.json/START.md 和验证记录留在 diagnostics；此规则替代下文历史双目录合并 ZIP 的交付说明。默认一次只构建一个指定游戏或产物；通用命令必须显式指定 --artifact，批量仅在明确要求下使用 --all。详见[单游戏组件交付](game-deployment-bundles.md)。

## 当前启动策略：已运行则重启并刷新配置

独立网关、后台、模拟平台和游戏包每次 `npm start` 都重新解析本次配置。没有同名实例时启动；已有同目录、同命名入口的实例（包括已停止/失败）则重建 PM2 进程定义并重启，以避免 restart/updateEnv 合并旧值。显式新 `--env-file`、端口等参数允许生效；同名异目录或异入口拒绝覆盖。游戏名称仍包含版本，新版本不会自动停止旧版本。

配置路径、JSON、平台 PostgreSQL 连接参数和生产域名、游戏身份/密钥等可预检查的错误，在停止旧实例前返回。实际连接、迁移、监听错误仍可能在旧实例停止后发生；这种情况下报告失败并停止新实例，不虚报成功。该行为是单实例有中断重启，不是无缝升级。当前 shell 环境变量仍按原有 `process > env file > JSON/default` 规则生效，删除文件项不会继承上次 PM2 环境，但若 shell 自身仍 export 该项须先更新或取消。共享 env 改动后各服务分别重启。

本节替代下文历史版本的重复启动直接返回、配置变化须手工删登记规则。依赖安装、迁移与等待就绪流程继续保留。

当前所有新构建的交付压缩包统一为 ZIP，按 `update/<产物名称>/<产物名称>-<build-id>.zip` 分类存放。下文历史验证记录中的 TAR.GZ 是旧版本名称，保留用于追溯，不再作为新构建格式。

## 当前默认：交付包不携带 node_modules

独立网关、后台、模拟平台和 19 款游戏包默认只交付生产 `package.json`、完整 `package-lock.json` 和程序／模板，首次执行 `npm start` 自动补装 PM2 及适用依赖，随后通过 PM2 执行迁移和服务启动。实际 env 须先准备好。npm registry 必须可访问，或 npm 缓存已具备完整依赖；安装失败返回非零，不启动 PM2 业务实例或继续迁移。已存在但不完整的 PM2 安装会尝试补装。

后台默认只有 frontend、dist、migrations、tools 四个顶层目录；安装后生成 node_modules。本节更新下文历史五目录／依赖随包的说明。其他程序功能及共享平台配置布局不变。首次维护命令（例如 admin-init）应在启动流程完成安装之后运行。

需要带依赖版本时，在原构建命令上追加 `--with-dependencies` 并选择新 build-id。该选项仍使用过滤后的生产依赖闭包，不携带开发依赖。带依赖版本不等于已通过完全离线部署验证：启动仍执行 npm 检查。历史 all-services 等兼容包交付范围维持原状。

发布记录的 `runtime_dependencies.independent_delivery` 及包内 `SERVICE.json.dependencies_bundled` 标明依赖交付方式。验证分开记录：`smoke-release` 检查交付字节后在临时解包目录安装再验证功能；`smoke-pm2-release` 从无依赖及空 npm 缓存验证游戏 npm start 的真实安装／后台启动；`smoke-install-release` 验证平台包安装及迁移失败阻断，不连接真实业务数据库，也不代表 PostgreSQL 成功迁移验收。

## 当前默认：npm start 交给 PM2 后台管理

新构建的独立网关、后台、模拟平台和游戏包使用 `npm start` → `tools/start-pm2.mjs` → PM2 → 本包命名入口。PM2 不调用 npm start，不形成启动循环。安装、迁移、监听成功后才报告后台启动成功；失败返回非零并停止本次新建进程，保留日志和失败登记。旧版包的前台行为见下面历史说明。

- 平台配置可自动读取包根 `platform.env` 或同级 `config/platform.env`，也支持 `GTT_PLATFORM_ENV_FILE`、`--env-file` 和原 `/etc/gtt-node/platform.env`。显式指定优先；不读取 `.example` 作为实际配置。
- 游戏配置支持 `GAME_ENV_FILE`、包根 `game.env`、部署根 `config/games/<代码>/<版本>.env`，每款游戏的 PM2 名称包含代码及版本。不同版本须使用不同端口。
- 锁定的 PM2 客户端包含在包内，并连接同一用户的 PM2_HOME（默认 ~/.pm2）；缺少依赖时补装。不自动调用全局安装或切换 root/www。可在包根运行 `npx --no-install pm2 list`、`npx --no-install pm2 logs <名称>`。
- 重复执行 npm start 会先预检查配置，再重启同目录同入口实例并刷新本次参数和环境；已停止/失败实例也按此处理。同名异目录/异入口拒绝覆盖，端口冲突不会自动杀其他进程。旧包若仍提示已运行即返回，需升级到 restart-env 版本。
- 保留 `npm run start:foreground -- --env-file <路径>` 和直接命名脚本的三阶段前台流程。宝塔直接管理脚本及 systemd 不嵌套后台启动器；systemd 模板改为 start:foreground。一次性 RTP 操作用 `npm run start:foreground -- rtp-worker --once`。
- 后台运行不等于开机自启，验证运行后由部署者显式管理 PM2 保存和开机启动。
- 平台实际密码、密钥仍仅存于实际 env；游戏子进程不携带平台数据库凭据。配置模板及 ecosystem 示例继续提供显式 env 参数。

## 交付边界

### 精简后台包（2026-11-14）

`gtt-node-admin-slim-20261114-r2` 的独立后台包顶层仅包含 `frontend/`、`dist/`、`migrations/`、`node_modules/`、`tools/` 五个目录。根目录的 env/JSON/PM2 示例、服务清单、依赖锁与 START.md 继续保留。服务器外部的共用 `config/` 不变。

后台启动使用独立 `admin/backend/cli.ts`；包内 `dist/cli.js` 保留 `admin` 和 `admin-init` 兼容命令，PM2 和三阶段启动不变。构建器遍历后台实际 JS 导入依赖，并明确纳入 PostgreSQL worker/迁移运行器，不再复制全体游戏和其他服务。`dist/data/` 保存后台需要的 SQL、游戏目录、readiness、RTP 模型和基础配置、接入指南；路径由 `SERVICE.json.data_directory` 和 `runtimeData()` 解析。包内没有 `resources/`、顶层 `config/` 或迁移后的各款完整游戏引擎。少量共用值转换、随机数及模型管理辅助模块仍需保留，不能当作整套游戏计算引擎删除。

精简包面向当前独立 remote 游戏服务部署：服务登记、版本切换、交易查询和重试、RTP 策略/任务/发布、商户和用户权限以及前端版本管理入口继续保留。后台创建 RTP 任务，计算由独立 worker/游戏服务承担。旧 embedded 拓扑仍使用完整兼容部署，不以缺失引擎的精简包替换它。源码的嵌入式引擎加载改为按需进行，源代码与完整兼容包的引擎仍保留。

维护依赖清单时，变量路径加载及 Worker 入口须显式登记并验证；不能仅凭静态导入闭包认定所有运行资料都不需要。

| 交付包 | 内容与默认服务 |
| --- | --- |
| `gateway-<build-id>.zip` | 网关、钱包、结算、协议接入及 RTP worker；默认 gateway |
| `admin-<build-id>.zip` | 后台 API、平台与商户后台页面；默认 admin |
| `<game>-serve-<服务版本>.zip` | 指定游戏的独立计算服务；位于其 serve 版本目录，默认 game |
| `mock-platform-<build-id>.zip` | 独立模拟商户平台，开发环境使用 |
| `infra-<build-id>.zip` | systemd 与配置示例 |

新网关包不含 `frontend/`、顶层 `clients/`、后台入口 `dist/gateway/admin.js` 或后台目录导出模块。后台和模拟平台各自独立交付；共用鉴权、商户配置、规则及协议依赖保留。

`all-services`、`buffalo-win` 等历史兼容包和 `frontend` 静态页面产物继续保留。当前命令成组构建多个独立交付物，分别取用相应压缩包。

## 美洲野牛启动资料

重复文件统一为 `gateway/resources/clients/buffalo-win/`。原根启动页、登录校验、GameInfo、Spin、规则和钱包接口保留。

仍指向当前网关包自身旧 `clients/buffalo-win/` 的配置会映射到统一目录；明确指定的外部素材挂载不会被替换。生产示例改为 `/opt/gtt-node/gateway/current/resources/clients/buffalo-win`。若同时改变安装目录，应同步修改外置结构配置。完整游戏大素材仍按原流程走 S3/CDN。

## 交付包启动

### 包内配置模板

独立平台包根目录提供 `platform.env.example`、`production.example.json`、`postgres.example.json`，采用 `/www/wwwroot/gtt-node/config/` 公共配置方案；复制到该目录后分别去掉 `.example`，填写实际连接、密钥和域名。网关、后台及 RTP worker 共用同一份实际平台配置。部署目录不同需同步修改模板内路径，已有配置不得用示例覆盖。

每款独立游戏包提供 `game.env.example`，包含其游戏代码和该次构建版本，规则路径按 `/www/wwwroot/gtt-node/games/<游戏代码>/<版本>/config/game.json` 生成。实例端口和密钥文件由部署时指定，同机实例不能复用监听端口；游戏示例不带平台数据库参数。

所有独立包提供 `ecosystem.config.example.cjs`：复制为包根目录下的 `ecosystem.config.cjs`，核对 env 路径和 Node 解释器后，通过 `pm2 start ecosystem.config.cjs` 启动。`cwd: __dirname` 固定到包根目录，`args` 显式传入 env；详细准备、避免重复实例和健康检查步骤见包内 `START.md`。仅修改宝塔显示名称不代表已应用参数，须核对实际 PM2 进程配置。

独立包统一使用自身名称的入口：网关 `tools/gateway.mjs`，后台 `tools/admin.mjs`，模拟平台 `tools/mock-platform.mjs`，游戏 `tools/<游戏代码>.mjs`（例如 `tools/mahjong-ways2.mjs`、`tools/fortune-rabbit.mjs`）。`npm start` 自动调用对应入口，`SERVICE.json.entry_point` 记录入口路径。PM2 工作目录选择包根目录，启动文件选择该入口；游戏 env 仍按独立版本实例提供。

网关构建器现提供 `tools/gateway.mjs` 命名入口，网关包的 `npm start` 指向它；该入口导入原 `tools/start-service.mjs`，保留依赖安装、迁移、启动流程及参数透传，原入口继续有效。PM2 可选择 `tools/gateway.mjs`，运行目录仍为网关包根目录，并显式传入 `--env-file <实际 platform.env 路径>`。此变更需新构建包才会包含；旧包可在 `tools/` 下新增内容为 `import './start-service.mjs';` 的 `gateway.mjs`，作为服务器侧补丁记录，不修改历史交付压缩包。

在解压后的各服务包根目录执行 `npm start`。默认角色由 `SERVICE.json` 声明，也可指定配置：

```bash
# 网关包或独立后台包
npm start -- --env-file /etc/gtt-node/platform.env
# 独立游戏包
npm start -- --env-file /etc/gtt-node/games/fortune-rabbit/<release>.env
# 网关包中的 RTP worker
npm start -- rtp-worker --env-file /etc/gtt-node/platform.env
```

顺序固定为：

1. **依赖安装**：`npm install --omit=dev --ignore-scripts --no-audit --no-fund`，依据包内 `package.json` 与 `package-lock.json` 安装生产依赖。已有依赖可复用，缺失依赖会补装；不执行第三方安装钩子。
2. **适用迁移**：平台服务持有迁移锁，执行并校验 PostgreSQL 路由配置中的版本。独立计算游戏没有玩家数据库，此阶段校验游戏身份、规则、端口和密钥，明确报告无需数据库迁移，不接收平台 PG 凭据。
3. **启动服务**：只有前两步成功才加载服务并监听端口。

安装或迁移失败返回非零状态并停止后续步骤。迁移不会重新导入 SQLite、清空数据或重置账号密码。Node.js 需要 24.17.0 或更新版本，并安装 npm；首次安装、缺失依赖或缓存不足时需要可用的 npm registry。

数据库服务和 JSON/env 配置须预先准备。正式平台 `npm start` 要求明确的 PostgreSQL 路由，不会因缺少配置而创建 SQLite 业务库，也不负责新建 PostgreSQL 容器或数据库。完成迁移后，首次管理员可从后台包运行 `node dist/cli.js admin-init --env-file /etc/gtt-node/platform.env`。

包内 `START.md` 提供操作说明。维护时可分别运行 `npm run migrate` 和 `npm run serve`；原 `node dist/cli.js ...` 入口在适用包和历史兼容包中保留。

## 源码目录入口

源码入口在安装阶段额外编译 TypeScript：

```powershell
# 仓库根目录默认网关
npm start
npm start -- admin
# 也可进入 gateway/、admin/ 或 games/<game>/ 直接 npm start
npm --prefix gateway start
npm --prefix admin start
npm --prefix games/fortune-rabbit start
# 独立试玩，区别于无钱包计算服务
npm --prefix games/fortune-rabbit run demo
npm start -- fortune-rabbit
```

源码依赖集中安装在 `other/tooling/node_modules/`。`npm run games` 是开发用的 19 个计算服务启动辅助器，生产逐个运行版本实例。原 `.bat` 与 `node other/tooling/run.mjs` 调试入口保留。

## Linux 部署

网关与后台各自拥有独立版本目录/current 指针：`/opt/gtt-node/gateway/current/`、`/opt/gtt-node/admin/current/`。游戏仍在 `/opt/gtt-node/games/<game>/<release>/`。

systemd 模板使用 `npm start`，RTP worker 为 `npm start -- rtp-worker`。平台进程共用 `/etc/gtt-node/platform.env`，游戏实例各自使用版本 env。运行账号必须能写入相应版本目录中的依赖、安装锁和 npm 缓存；模板配置了 `ReadWritePaths` 与 `/var/cache/gtt-node-npm` 缓存目录，解压后也须授予运行账号文件权限。新旧游戏版本使用不同端口，待旧整局结束后停止旧实例。

压缩包只放在根目录 `update/`，发布清单及验证记录保留在 `other/diagnostics/releases/<build-id>/`。实际 env、密钥和业务数据不随包发布。本次没有执行线上部署。

## 本次验证

美洲野牛实际目录交付 `gtt-node-buffalo-folders-20261117-r2`：本次仅构建 game-buffalo-win 计算产物（服务版本 gtt-node-buffalo-20261117），并校验复用前端 fe-20261117151146182-79bc8eab-fb6c46。实际 update/game-buffalo-win 下有 client 文件目录和 serve ZIP 目录，不生成前端 ZIP 或合并 ZIP。单产物清单只包含一个服务归档；未指定目标、目标无效或 --all/--artifact 冲突均拒绝。单服务归档检查、目录/清单检查、临时解包实际计算服务及协议/规则验证通过，未进行生产 S3/CDN 发布。Windows 下 RELEASE.json 与 release.json 不能共存，因此新组件交付只保存一份标准 RELEASE.json，读取器兼容历史小写文件。

完整游戏包版本 `gtt-node-buffalo-full-20261117-r2`：美洲野牛 ZIP 根目录包含 `buffalo-win-client-fe-20261117151146182-79bc8eab-fb6c46/`、`buffalo-win-serve-gtt-node-game-components-20261117/`、RELEASE.json 和 START.md。已验证归档与组件文件校验、游戏身份、前端/服务端规则配置一致、契约一致、错误身份/契约/资源篡改/资源缺失拒绝，实际启动计算服务后检查版本和契约及固定种子初始状态。计算实例仅提供地址/端口/密钥 env，身份、版本和规则路径使用包内默认。源独立计算包的新 `-serve-` 命名版本 gtt-node-game-components-20261117 也通过全归档解包验证。前端自动构建和复用已有前端目录两条路径均已运行；完整包不代表生产 CDN、钱包或全部玩法验收，不宣称完成单游戏引擎依赖精简。见 [完整游戏包说明](game-deployment-bundles.md)。

开放部署检查版本 `gtt-node-opening-checks-20261117`：后台 ZIP 默认四目录、42 个服务端 JS 模块。新开放接口采用检查任务/轮询/确认流程，前端兼容性、私有资料和生产 CDN 清单资源校验通过后才能开放，检查期间或确认前切换版本会拒绝；关闭及旧回合恢复保留。首页目录、登记服务、激活数量分别统计。专项源码测试与全归档干净解包验证通过，解包测试额外验证无登记服务时不能通过管理 API 开放、目录不冒充部署数量。详见 [开放检查规则](game-opening-checks.md) 及该版本诊断目录。生产 CDN 分支使用受控响应测试，未执行真实生产 CDN 或 PostgreSQL 端到端验收。

自动重启及刷新配置版本 `gtt-node-restart-env-20261116`：26 个 ZIP 已构建，默认独立包不带依赖。`pm2-verification-env-clean.json` 在隔离 PM2_HOME/空 npm 缓存中验证 PID 更新、同路径 env 端口与密钥更新、配置项删除恢复默认、显式新 env 路径、去除当前调用环境变量后不沿用旧进程/守护进程值、错误预检查保留原进程、stopped/errored 恢复、同名异目录拒绝及其他版本名称隔离、安装/监听失败不宣告成功。`install-verification.json` 覆盖平台三个包的安装与迁移失败阻断（拒绝握手的隔离 TCP 端点，并非真实 PostgreSQL 迁移成功）；`verification.json` 为全归档解包与服务功能冒烟。未执行 Linux 宝塔或真实 PostgreSQL 完整启动验收。

统一 ZIP 版本 `gtt-node-zip-20261116`：全部 26 个新归档采用真正的 ZIP 编码，后台位于 `update/admin/admin-gtt-node-zip-20261116.zip`（304203 字节），保留默认四目录和首次启动安装依赖规则。校验覆盖 ZIP 干净解包、归档与文件 SHA-256、22 个独立包的依赖安装、后台初始化/管理 API/接入导出和独立游戏服务冒烟，见该版本目录 `verification.json`；没有新增生产 PostgreSQL 迁移成功验收结论。历史 TAR.GZ 读取兼容继续保留。

2026-11-15 默认无依赖交付版本：`gtt-node-install-on-start-20261115`，26 个归档已生成；其中 22 个独立服务包均未携带 node_modules。后台四目录包为 273773 字节。`verification.json` 在校验交付字节后为 22 个临时解包实例安装依赖，再通过原有服务及后台功能检查。`pm2-verification.json` 通过空缓存、离线安装失败不启动、恢复联网自动安装 PM2、游戏后台启动及健康检查；`install-verification.json` 通过网关/后台/模拟平台无依赖安装和迁移失败阻断。后者使用隔离拒绝握手的 TCP 端点，没有完成真实 PostgreSQL 成功迁移，不可表述为生产数据库验收通过。

可选带依赖版本 `gtt-node-install-on-start-20261115-bundled-r2` 通过 `--with-dependencies` 构建并通过干净解包与功能验证；不代表完全断网部署已验证。最初 bundled 构建在压缩阶段超时，无成功 release.json，仅保留诊断中间产物；以 bundled-r2 为准。日常部署优先选择无 bundled 后缀的默认版本。

精简后台最终版本 `gtt-node-admin-slim-20261114-r2`：26 个归档完成构建，后台有 41 个服务端 JS 模块。干净解包、五目录布局、独立管理员初始化及重复初始化拒绝、平台/商户页面、登录、overview/商户/用户/审计/交易/预派彩/RTP/游戏查询、接入文档及游戏目录导出、19 款独立游戏服务登记和激活通过，见 `verification-admin-final.json`。选定源码回归覆盖环境配置、19 游戏远程计算、服务注册权限及模型导入校验；未执行全量回归。PostgreSQL/npm start 完整流水线未复验：本机 Docker Desktop Linux engine 不可用；本版验证不代表真实 PostgreSQL 或 Linux 宝塔部署已验收。最初无 r2 的尝试存在网关打包遗漏，使用 r2 最终归档。

2026-11-14 PM2 后台启动最终交付版本：`gtt-node-pm2-start-20261114-r2`。使用锁定 PM2 7.1.2，26 个归档通过干净解包和原有服务冒烟；独立福兔包在隔离 PM2_HOME 下通过 npm start 后台启动、版本 env 自动发现、带鉴权健康检查、重复启动 PID 不变、同名配置冲突拒绝、缺配置失败、端口占用失败停止、依赖锁缺失失败停止和游戏子进程凭据隔离。测试停止并清理了隔离守护进程。结果见该版本目录的 `verification.json`、`pm2-verification-final.json`。未执行本版 PostgreSQL 完整启动流水线或 Linux 宝塔端到端验收。早期 `gtt-node-pm2-start-20261114` 含 PM2 上游示例文件，归档检查未通过，不作为最终交付使用；以 r2 为准。

2026-11-14 配置模板版本：`gtt-node-config-templates-20261114`，已生成 26 个分类归档。干净解包校验验证了独立包根目录模板、游戏身份及版本、平台 JSON/env 路径对应关系、PM2 cwd/args、命名入口和归档文件校验，并通过原有服务冒烟。记录位于 `other/diagnostics/releases/gtt-node-config-templates-20261114/verification.json`。本版没有新增 PostgreSQL 启动流水线或服务器宝塔部署通过的结论；实际配置由部署时填写。

2026-11-14 命名入口版本：`gtt-node-named-entry-20261114`，26 个归档按产物分类交付到 `update/<产物名称>/`。网关、后台、模拟平台和 19 款游戏均已使用自身名称入口及对应 `npm start`；干净解包、入口映射、归档及逐文件校验、原有服务冒烟通过。此次 PostgreSQL/npm start 流水线复验因本机 PostgreSQL 端口拒绝连接、Docker engine 不可用而受阻，不能沿用下述旧版本结果作为本版已通过结论。详见该版本诊断目录中的 `verification.json` 和 `postgres-verification-blocked.md`。

- 最终构建：`gtt-node-service-split-20261113-r2`，压缩包位于 `update/`。
- 新网关包的后台页面/API、顶层 `clients/` 缺席检查通过；统一资源目录存在，旧包内 client_root 配置下的美洲野牛根入口仍可打开。
- 已在干净解包目录删除网关依赖后，通过真实 `npm start` 完成补装、空 PostgreSQL 库 schema 迁移和服务启动；后台使用独立 admin 包登录成功。
- 网关、后台和独立游戏的三个阶段顺序已核对；安装失败不进入迁移，迁移失败不启动服务，均有故障注入验证。
- 全部独立计算包的进程启动、服务登记、版本路由与固定种子重试检查通过；游戏 npm 流水线另以福兔包实测。
- 源码目录的网关和福兔 `npm start` 已分别启动验证；源码网关使用新的隔离 PostgreSQL 测试库。
- PostgreSQL 全量回归 264 项，263 通过；唯一失败仍为此前的 Super Ace 客户端日期锁 VM 问题，未屏蔽测试或隐藏入口。

记录在 `other/diagnostics/releases/gtt-node-service-split-20261113-r2/verification.json`、`postgres-verification.json` 以及 `other/diagnostics/startup/`。
