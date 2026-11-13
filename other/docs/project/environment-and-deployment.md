# 按部署单元管理环境配置

最新交付已将管理后台从网关包分离，但平台进程仍共用同一份 env。各独立服务包支持 `npm start` 按依赖安装、迁移、启动顺序运行，详见[独立服务包与启动](service-packaging-and-startup.md)。

## 数量与边界

当前拓扑按以下方式管理，不按源码文件夹重复复制数据库配置：

| 部署单元 | 配置 |
| --- | --- |
| 平台应用：网关、管理后台、RTP worker | 共用一份 `platform.env` |
| 每个独立游戏计算服务的每个运行版本 | 一份 `<release>.env` |
| Docker 自建 PostgreSQL | 单独一份数据库容器初始化 env |
| 静态前端 | 不加载平台或游戏服务的 env |

19 款游戏各运行一个版本：**20 份应用/游戏 env**；加上自建 PostgreSQL 为 **21 份**。某款新旧版本并行，再增加一份游戏实例 env。使用 RDS 等托管数据库时，没有数据库容器 env。

env 数量不等于所有配置文件数量：游戏规则 JSON、平台结构配置、存储路由 JSON 和各游戏认证密钥文件仍按用途保存。

## 本机实际位置

```text
gateway/instance/platform.env                  # 平台环境参数和 PostgreSQL 凭据
gateway/instance/data/node.json                # 结构配置、存储标识和运行资料路径
gateway/instance/data/postgres.json            # schema 路由，引用 platform.env
gateway/instance/data/postgres-migration.json  # 迁移/容器/演练元信息，引用同一 env
games/<game>/instance/releases/<release>.env   # 本机计算服务实例，已生成 19 份
other/deploy/instance/postgres.env             # 数据库容器初始化配置
```

根目录不创建业务 `.env`。后台不另建一份数据库密码配置；现有平台和商户后台属于同一管理服务。

`other/deploy/node/` 中的三个 `*.env.example` 是随基础设施发布的示例模板，集中存放以便与 systemd 单元配套维护，不能当作本机运行配置。实际 env 因包含私有参数被 Git 忽略，因此在受版本管理的文件列表中主要看到这些模板。目录用途见[部署模板说明](../../deploy/node/README.md)。

模板、运行 env 和生成工具输出的参数说明统一使用中文注释；变量名、协议枚举和配置值保留原有格式。本次注释更新已逐份核对 21 个运行 env 的解析结果，全部键值保持一致。

本次已将 PostgreSQL 连接参数、平台内部认证参数和端口等移入 `platform.env`。当前运行的 `postgres.json`、`postgres-migration.json` 不再重复保存数据库连接凭据，`node.json` 不再保存平台内部密钥。商户账号和商户密钥属于业务数据，仍在 PostgreSQL。

原 JSON 保存于 `gateway/instance/data/configuration-backups/before-env-1794579824675/`。历史数据库初始化 env、迁移快照和隔离测试生成的连接配置保留在私有忽略目录中，不作为平台正式配置源。数据库、密码、游戏认证密钥和激活版本均未改变。

## 加载规则

1. 命令支持的显式 CLI 参数优先，例如 `--config`、`--env-file`，游戏的 `--port`、`--secret-file` 等。
2. 进程环境变量优先于 env 文件中的同名值。
3. env 文件优先于旧 JSON 中相应的默认字段。
4. JSON 继续保存列表、存储映射、代理配置、目录等结构化信息。

使用 Node 内置 `parseEnv`，支持引号和注释，不进行 `${VAR}` 插值。文件中的相对路径以 env **实际文件**所在目录解析，包括通过生成运行目录 junction 读取的情况。生产模板及部署生成器使用绝对目标路径，避免 systemd 注入变量和直接 `--env-file` 启动产生相对路径差异。

默认本机 `npm run gateway`、`npm run admin`、`npm run games` 自动选择 `gateway/instance/platform.env`。显式 `--config` 或 `--env-file` 不会被默认本机配置覆盖；也可以通过 `GTT_PLATFORM_ENV_FILE` 指定文件。旧完整 JSON 仍可作为兼容入口，但不再作为本机密钥维护入口。

数据库 worker 与迁移/备份工具都通过共享加载器读取连接参数。测试和演练使用显式隔离数据库目标；不会被平台的 `PGDATABASE` 替换。常规测试启动器也清除业务环境变量，防止测试占用业务端口或连接业务库。

env 不热加载。修改平台配置后重启相关平台进程；修改游戏实例配置后按服务版本发布流程检查、登记和激活。

## 平台应用部署

发布包外保留：

```text
/etc/gtt-node/platform.env
/etc/gtt-node/production.json
/etc/gtt-node/postgres.json
```

模板在 `other/deploy/node/platform.env.example`、`production.example.json` 和 `gateway/config/postgres.example.json`。安装到服务器时替换占位值，并保持 JSON 中的存储标识与路由路径一致。

核心参数包括：

```dotenv
NODE_ENV=production
GTT_CONFIG_FILE=/etc/gtt-node/production.json
GTT_PG_CONFIG=/etc/gtt-node/postgres.json
PGHOST=127.0.0.1
PGPORT=5432
PGDATABASE=gtt_new_database
PGUSER=gtt_application
PGPASSWORD=填写部署环境密码
GATEWAY_HOST=127.0.0.1
GATEWAY_PORT=8110
ADMIN_HOST=127.0.0.1
ADMIN_PORT=8112
GAME_SERVICES_MODE=remote
```

完整模板还包含平台内部密钥、公共域名和客户端版本域名模板。TLS 支持 `PGSSLMODE=disable|require|verify-full`，自定义 CA 使用 `PGSSLROOTCERT`。本机现有端口仍为 **15432**，不因示例中的 5432 改变。

网关、后台和 RTP worker 共用下面的环境文件，网关与后台各自在自己的交付目录使用 npm start：

```ini
EnvironmentFile=/etc/gtt-node/platform.env
ExecStart=/usr/bin/npm start
```

RTP worker 在网关包目录使用 `npm start -- rtp-worker`。网关与后台工作目录分别为 `/opt/gtt-node/gateway/current` 和 `/opt/gtt-node/admin/current`；模板开放版本目录的依赖安装写权限，并提供 `/var/cache/gtt-node-npm` 缓存目录。

也可执行 `npm start -- --env-file /etc/gtt-node/platform.env`；手工维护入口 `node dist/cli.js ...` 保留，但不包含完整安装/迁移流水线。配置文件须允许实际运行账号读取，例如以 `gtt-node` 为所有者、权限 0600；不要放进应用版本目录。使用容器环境变量直接注入时，可省略 env 文件，并删除 JSON 中的 `env_file` 指针，保留 `GTT_CONFIG_FILE`、`GTT_PG_CONFIG` 等必要变量。

平台和游戏文件按 Node/systemd 的引号规则解析。容器应用可以挂载文件后传给上述应用 `--env-file` 参数，或直接注入未附带引号的变量值；Docker 自身的 `--env-file` 不采用同一套引号解析规则。数据库容器的独立初始化 env 使用 Docker 格式。

## 游戏实例配置与滚动发布

每个实例只有自己需要的参数：

```dotenv
GAME_ID=fortune-rabbit
GAME_RELEASE=本次构建号
GAME_CONFIG=/opt/gtt-node/games/fortune-rabbit/本次构建号/config/game.json
GAME_BIND=127.0.0.1
GAME_PORT=8313
GAME_SECRET_FILE=/etc/gtt-node/secrets/fortune-rabbit.key
```

批量生成 19 份配置，不手工复制：

```powershell
npm run game:env -- --all --release <构建号> --base-port 8311 --output other/diagnostics/game-envs/<构建号>
```

单款示例：

```powershell
npm run game:env -- --game fortune-rabbit --release <构建号> --port 8313 --output other/diagnostics/game-envs/<构建号>
```

生成结果是 `<输出目录>/<game>/<release>.env`，部署到 `/etc/gtt-node/games/<game>/<release>.env`。可指定 `--host`、`--install-root`、`--secret-root`，单款也可指定 `--game-config`、`--secret-file`；这些是目标服务器的绝对路径。生成器拒绝覆盖已有实例配置，也不生成或轮换认证密钥。

游戏 systemd 模板读取对应 `%i.env`，在独立版本目录执行 `npm start -- --game-id <game> --release %i`。新旧实例必须使用不同端口。先启动、检查并在平台登记新版本，再切换新整局；旧版本的未结束整局清零后才停止旧进程。

计算服务只接收游戏和必要 OS 环境变量；本机游戏启动器不会把平台 env 指针、PG 密码、数据库配置路径或其他平台凭据传给计算子进程。游戏 env 中出现 PG 或平台配置项会被拒绝。独立试玩入口仍属于有钱包/存档的开发链路，使用平台数据库配置，与无钱包计算服务区分。

## PostgreSQL 容器配置

`other/deploy/instance/postgres.env` 对应数据库容器初始化，模板为 `other/deploy/node/postgres.env.example`，只包含 `POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB`。

修改这里的 `POSTGRES_PASSWORD` 不会改变已有数据库用户密码。应用实际连接参数以 `platform.env` 为准；本次没有重建容器或数据库。

## 构建与验证

- 实际 `.env` 和 `*.env` 被 Git 忽略，示例 `*.env.example` 可以提交。
- 发布构建拒绝把实际 env 文件放入归档，只发布示例和生成工具。
- 网关包携带 `tools/render-game-env.mjs`，也可在部署端生成配置。
- `npm run config:check` 检查本机配置布局；追加 `-- --migration` 可核对与本次迁移前备份的连接、密码和端口一致性。以后主动修改密码或端口时，不使用历史一致性选项作为健康判断。
- 新增 6 项环境配置测试通过；完整 PostgreSQL 回归 262 项中 261 通过，唯一失败仍为已有 Super Ace 日期锁 VM 问题。
- 已验证网关、后台共用一个 env 连接独立新 PostgreSQL 库，独立游戏包使用自己的版本 env 启动；原有干净解包和游戏服务冒烟通过。
- RTP worker 已在干净解包环境中通过同一平台 env 运行一次；env 模式初始化也不会将平台内部密钥另存入 JSON。
- 最终产物与检查记录：`other/diagnostics/releases/gtt-node-env-20261113-r3/` 的 `release.json`、`verification.json`、`postgres-verification.json`；本机配置迁移核对见 `other/diagnostics/environment/configuration-verification.json`。
- 本机网关 8110、后台 8112 及 19 款计算服务 8211–8229 已按新配置恢复；签名请求及源 SQLite 封存校验通过。

此处实现并验证的是配置加载和部署产物，没有执行线上服务器部署。
