# GTT 商户接入服务

> 目录已重组。当前启动命令与路径见[四目录说明](../../other/docs/project-layout.md)；本文中的旧命令保留为历史记录。

默认 `start.bat` 使用 Node 独立网关，通过持久化注册表调用每款独立游戏服务，不再默认监督美洲野牛子进程。开发环境先运行 `node server/tools/start.mjs games`；服务注册和整局版本切换见 [独立游戏服务架构](../../other/docs/project/game-service-architecture.md)。旧环境继续使用原数据库与 8110 入口，私有 `data/node.json` 与原配置保留。首次创建全新环境用 [Node 初始化流程](../../other/docs/node/README.md)，下述 Python 初始化为历史回退说明。

监听 `127.0.0.1:8110`，承载商户签名 API 和 Buffalo Win 原版客户端。状态与操作记录位于本目录 `data/gtt.sqlite3`，日志在 `logs/service.log`；余额由合作平台提供。本目录配置与原 8083 服务相互独立。

首次在项目根目录执行 `python -m py.merchant.sandbox init`，然后运行 `node server/tools/start.mjs gateway`，或双击本目录 `start.bat`。还需单独启动 8111 模拟平台。

旧 `data/sandbox.json` 商户配置自动迁移到 `data/merchants.sqlite3`，旧文件另存备份，JSON 仅保留数据库路径及联调参数。通过 [管理后台](../../admin/instance/README.md) 创建商户、分配授权、停用或轮换密钥，运行中即时生效。`init` 不覆盖已有文件或重置钱包。

接口、签名、交易恢复、对账和范围见 [GTT 商户与平台钱包 v1](../../other/docs/project/gtt-merchant-wallet-v1.md)。
