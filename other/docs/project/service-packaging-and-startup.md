# 独立服务包与 npm start

## 交付边界

| 交付包 | 内容与默认服务 |
| --- | --- |
| `gateway-<build-id>.zip` | 网关、钱包、结算、协议接入及 RTP worker；默认 gateway |
| `admin-<build-id>.tar.gz` | 后台 API、平台与商户后台页面；默认 admin |
| `game-<game>-<build-id>.tar.gz` | 指定游戏的独立计算服务；默认 game |
| `mock-platform-<build-id>.tar.gz` | 独立模拟商户平台，开发环境使用 |
| `infra-<build-id>.tar.gz` | systemd 与配置示例 |

新网关包不含 `frontend/`、顶层 `clients/`、后台入口 `dist/gateway/admin.js` 或后台目录导出模块。后台和模拟平台各自独立交付；共用鉴权、商户配置、规则及协议依赖保留。

`all-services`、`buffalo-win` 等历史兼容包和 `frontend` 静态页面产物继续保留。当前命令成组构建多个独立交付物，分别取用相应压缩包。

## 美洲野牛启动资料

重复文件统一为 `gateway/resources/clients/buffalo-win/`。原根启动页、登录校验、GameInfo、Spin、规则和钱包接口保留。

仍指向当前网关包自身旧 `clients/buffalo-win/` 的配置会映射到统一目录；明确指定的外部素材挂载不会被替换。生产示例改为 `/opt/gtt-node/gateway/current/resources/clients/buffalo-win`。若同时改变安装目录，应同步修改外置结构配置。完整游戏大素材仍按原流程走 S3/CDN。

## 交付包启动

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

- 最终构建：`gtt-node-service-split-20261113-r2`，压缩包位于 `update/`。
- 新网关包的后台页面/API、顶层 `clients/` 缺席检查通过；统一资源目录存在，旧包内 client_root 配置下的美洲野牛根入口仍可打开。
- 已在干净解包目录删除网关依赖后，通过真实 `npm start` 完成补装、空 PostgreSQL 库 schema 迁移和服务启动；后台使用独立 admin 包登录成功。
- 网关、后台和独立游戏的三个阶段顺序已核对；安装失败不进入迁移，迁移失败不启动服务，均有故障注入验证。
- 全部独立计算包的进程启动、服务登记、版本路由与固定种子重试检查通过；游戏 npm 流水线另以福兔包实测。
- 源码目录的网关和福兔 `npm start` 已分别启动验证；源码网关使用新的隔离 PostgreSQL 测试库。
- PostgreSQL 全量回归 264 项，263 通过；唯一失败仍为此前的 Super Ace 客户端日期锁 VM 问题，未屏蔽测试或隐藏入口。

记录在 `other/diagnostics/releases/gtt-node-service-split-20261113-r2/verification.json`、`postgres-verification.json` 以及 `other/diagnostics/startup/`。
