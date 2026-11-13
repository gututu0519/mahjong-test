# GTT 管理控制台

> 目录已重组。当前启动命令与路径见[四目录说明](../../other/docs/project-layout.md)；本文中的旧命令保留为历史记录。

默认运行时为 Node；后台可以独立启动，并由平台管理员在“游戏服务与版本”登记游戏的内部地址、检查连接和切换新整局版本。商户后台不提供该入口和接口权限。完整本地联调先启动 `node server/tools/start.mjs games` 和网关；已有账号、配置和 8112 入口继续使用，见 [独立服务与版本管理](../../other/docs/project/game-service-architecture.md)。

地址：<http://127.0.0.1:8112/>。独立进程，提供管理员登录、角色权限、商户配置、游戏授权、密钥轮换、交易查询与恢复、操作审计。

首次在项目根目录执行 `node server/tools/start.mjs admin-init`，生成第一名管理员并将初始凭据保存到忽略目录 `services/gtt-gateway/data/admin-bootstrap.json`，不打印密码。已有账户时拒绝重新初始化。

运行 `node server/tools/start.mjs admin`，或双击本目录 `start.bat`。完整联调还需运行 `gateway` 与 `platform`。后台与网关共用商户数据库及游戏操作数据库，恢复操作走相同的钱包签名与幂等流程；后台不持有平台余额。日志在本目录 `logs/service.log`。

详细权限、接口、数据库迁移与范围见 [GTT 管理后台](../../other/docs/project/gtt-admin.md)。
