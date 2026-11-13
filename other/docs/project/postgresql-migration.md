# PostgreSQL 数据迁移

## 当前实际状态

2026-11-13 已在本机完成迁移并恢复服务。目标是**新创建的数据库**，没有复用或覆盖其他项目的数据库。

| 项目 | 当前值 |
| --- | --- |
| 数据库 | `gtt_20261113121637` |
| 版本 | PostgreSQL 17.11 |
| 本机地址 | `127.0.0.1:15432` |
| Docker 容器 | `gtt-postgres-20261113121637` |
| 独立持久卷 | `gtt-postgres-20261113121637-data` |
| 应用连接凭据 | `gateway/instance/platform.env`，私有、受 Git 忽略 |
| 存储路由 | `gateway/instance/data/postgres.json`，引用上述 env，不再重复保存密码 |
| 启用标记 | `gateway/instance/data/database-active.json` |
| 网关配置 | `gateway/instance/data/node.json` 的 `postgres_config` 指向上述文件 |

容器只映射本机地址，设置 `unless-stopped` 重启策略。启动应用前需启动 Docker Desktop；必要时运行 `docker start gtt-postgres-20261113121637`。密码由 `platform.env` 统一维护，迁移工具也读取同一份环境配置；`postgres-migration.json` 保留容器和演练元信息。详见[环境配置与部署](environment-and-deployment.md)。

网关、平台后台、商户后台及 19 款独立计算服务已经恢复。签名目录请求成功，新的防重放 nonce 已验证写入新 PostgreSQL；切换前封存的 84 个 SQLite/WAL 文件保持字节一致。此次未部署 AWS 或切换线上环境。

## 迁移范围与隔离

总计迁移并校验 **42 个命名空间、345 张源表、3,270 条记录**：

- `control`：账号、权限、商户、密钥、开放状态、游戏和客户端版本注册、路由、审计。
- `game`：玩家、会话、整局、钱包操作、幂等计算、预派彩、RTP 策略与统计、版本绑定。
- `mock`：现有模拟商户钱包。
- `demo_<game>`：19 款独立试玩和通用 API，各自隔离余额、玩家及存档。
- `protocol_<game>`：19 款原客户端协议镜像，保留历史和缓存恢复信息。

历史 `before-*` 文件及 `backups/` 下旧备份未混入当前业务数据。它们与原运行 SQLite 文件均保留。按类型建立的 schema 模板可能包含尚未使用的空表；345 是实际迁移的源表数量。

原配置中的 `merchant_database`、`game_database`、各游戏 `data/games.sqlite3` 等路径现在作为存储路由标识，映射到明确的 PostgreSQL schema。启用 PostgreSQL 后，不通过这些路径打开 SQLite 读写业务数据；未知路径明确报错。新客户端版本的协议镜像在受控协议目录下，通过相同的版本化 migration 建立隔离 schema。

## Migration 实现

- 基线结构：`other/migrations/postgres/0001-baseline.json`，仅含结构，无业务行或账号密钥。
- 事件触发器：`other/migrations/postgres/0001-game-events.sql`。
- 不可变基线执行器：`other/shared/database/migrations.ts`。
- 迁移登记与执行顺序：`other/shared/database/runner.ts`。
- 已应用版本和校验和：`gtt_meta.schema_migrations`。
- 每个源库的快照摘要、导入结果与完成时间：`gtt_meta.imports`。

迁移使用 PostgreSQL advisory lock，schema 变更与版本记录在事务内提交。已应用版本校验和不匹配时拒绝继续；已有但未经管理的同名 schema 不会被覆盖。后续结构升级必须新增 migration 模块、登记 runner 和构建映射，不能改写 0001；当前没有自动逆向 `down`，需要按业务数据兼容性编写前向修复或独立回退方案。

应用启动中的旧建表调用在 PostgreSQL 模式仅检查所需表，缺少 migration 时失败。新增列不通过临时 `ALTER TABLE` 绕过迁移。

## 数据迁移流程与校验

1. 先备份运行 SQLite 到隔离演练快照，在独立 PostgreSQL 演练库导入并运行业务回归。
2. 停止本机网关、后台、游戏启动器及其子进程，停止业务写入。
3. 使用 SQLite backup API 获取最终一致快照；最终导入要求快照记录停写确认。
4. 在新目标库执行 migration，逐 namespace 导入。导入遇到非空且未登记来源的目标表时拒绝覆盖；不同来源快照不能重复灌入同一 namespace。
5. 保留原主键、外键、密码哈希、密钥、交易、JSON 字节、未结束回合和版本绑定。修复 identity sequence，保留源 `sqlite_sequence` 高水位。
6. 导入期间停用事件派生触发器，避免补造历史事件；导入完成后验证外键并恢复触发器。
7. 按主键排序，对源表和 PostgreSQL 表逐列规范化，核对记录数和 SHA-256。导入完成记录与业务数据在同一事务提交。
8. 完成全量校验后修改启用配置、恢复服务，再验证真实签名请求落入 PostgreSQL。

导入以 namespace 为事务边界。中断后可对**同一快照**重试，已完成部分必须再次通过数据校验；不会删除源库或重复插入已完成数据。`verify` 不导入数据，只核对已有导入结果；应用产生新业务数据后，不能再把它与切换前快照逐行相等当作正常运行条件。

最终快照：`gateway/instance/data/postgres-snapshots/20261113131431833-c645d5/`。

最终校验记录：

- `other/diagnostics/postgres/gtt_20261113121637-import-1794575685990.json`
- `other/diagnostics/postgres/gtt_20261113121637-verify-1794575687203.json`
- `other/diagnostics/postgres/live-verification.json`

## 常用命令

在项目根目录运行：

```powershell
npm run db:status
npm run db:migrate
npm run test:postgres
npm run gateway
npm run admin
npm run games
node other/tooling/database/cutover.mjs check-source
node other/tooling/database/cutover.mjs backup
```

再次执行迁移演练时，使用新的演练库和快照，不覆盖已启用库：

这里的 `db:snapshot` 读取保留的 SQLite 源库，用于重演历史迁移；当前 PostgreSQL 的备份使用 `cutover.mjs backup`。

```powershell
node other/tooling/database/new-trial.mjs
npm run db:snapshot -- --trial
npm run db:import -- --trial --snapshot <演练快照目录>
npm run db:verify -- --trial --snapshot <演练快照目录>
```

`--writes-paused` 只应在已经停止全部写入时用于正式快照，不能用它把运行中的跨库快照标成一致快照。新环境需先准备 PostgreSQL 和私有连接配置，再执行 migration；`db:migrate` 会为固定业务存储建立 schema。直接使用发布包时设置 `GTT_PG_CONFIG`，或在网关配置中提供 `postgres_config`；配置模板见 `gateway/config/postgres.example.json`。

## 备份与回退

切换前的 SQLite 原文件、最终快照及 `node.json.before-postgres` 均保留；数据库数据位于独立 Docker volume，不能删除容器卷作为重建操作。

已经生成 PostgreSQL 自定义格式备份：`gateway/instance/data/postgres-backups/gtt_20261113121637-1794575699334.dump`。后续通过 `cutover.mjs backup` 生成新备份；恢复应先在另一个新数据库使用 `pg_restore` 演练并校验，再切换连接。

新库已经接受签名请求写入。直接恢复旧 SQLite 配置会遗漏新写入，不能作为无损回退。历史 Python 源码和 SQLite 测试仍保留，但不自动与 PostgreSQL 双写，也不能直接作为切换后的业务回退运行时。

## 验证结果与边界

- PostgreSQL 上运行原有全部 255 项测试：254 通过，唯一失败为迁移前已有的 Super Ace 日期锁 VM 回归。
- 新增独立连接并发读改写及失败事务回滚测试通过；原有跨控制/结算库原子回滚在 PostgreSQL schema 间验证通过。
- 19 款原协议、独立试玩、商户钱包、免费与购买回合、幂等重试、旧库恢复、服务版本和客户端版本测试通过。
- 发布包已携带 `pg` 生产依赖和 migration；干净解包启动网关和后台，使用另一个新 PostgreSQL 库登录成功，确认未创建 SQLite 业务数据库。
- 最终发布验证产物：`other/diagnostics/releases/gtt-node-postgres-20261113-r2/`，包含 `release.json`、`verification.json` 和 `postgres-verification.json`；此包未部署线上。
- 原 SQLite 兼容测试和历史工具继续保留；PG 专项测试使用独立 `gtt_test_*` 数据库，不连接当前业务库。

当前保留同步数据库调用接口，由专用 worker 执行 PostgreSQL I/O，连接池固定事务连接。事务使用跨进程 advisory lock 保留原 SQLite `BEGIN IMMEDIATE` 的串行边界，跨 schema 事务按固定顺序加锁。此阶段完成了数据库和数据迁移，**尚未完成全异步调用链或多网关高可用改造**，不把数据库可远程连接等同于已通过分布式网关验收。

专项测试和演练数据库以 `gtt_test_*`、`gtt_package_*`、`*_trial*` 区分，均与当前业务库隔离；失败演练也保留用于追溯，未通过删库或修改已应用校验和来伪装成功。
