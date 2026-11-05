# GTT 管理控制台

默认运行时已切换 Node；首次在 `node/` 安装依赖，先启动网关及计算服务，再启动后台。新建隔离环境用 `npm run init`，旧环境使用下述 8112 入口及原账号，详见 [Node 初始化与回退](../../node/README.md)。

地址：<http://127.0.0.1:8112/>。独立进程，提供管理员登录、角色权限、商户配置、游戏授权、密钥轮换、交易查询与恢复、操作审计。

首次在项目根目录执行 `node node/tools/start.mjs admin-init`，生成第一名管理员并将初始凭据保存到忽略目录 `services/gtt-gateway/data/admin-bootstrap.json`，不打印密码。已有账户时拒绝重新初始化。

运行 `node node/tools/start.mjs admin`，或双击本目录 `start.bat`。完整联调还需运行 `gateway` 与 `platform`。后台与网关共用商户数据库及游戏操作数据库，恢复操作走相同的钱包签名与幂等流程；后台不持有平台余额。日志在本目录 `logs/service.log`。

详细权限、接口、数据库迁移与范围见 [GTT 管理后台](../../docs/gtt-admin.md)。
