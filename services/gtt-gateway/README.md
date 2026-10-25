# GTT 商户接入服务

监听 `127.0.0.1:8110`，承载商户签名 API 和 Buffalo Win 原版客户端。状态与操作记录位于本目录 `data/gtt.sqlite3`，日志在 `logs/service.log`；余额由合作平台提供。本目录配置与原 8083 服务相互独立。

首次在项目根目录执行 `python -m server.merchant.sandbox init`，然后运行 `python -m server.merchant.sandbox gateway`，或双击本目录 `start.bat`。还需单独启动 8111 模拟平台。

旧 `data/sandbox.json` 商户配置自动迁移到 `data/merchants.sqlite3`，旧文件另存备份，JSON 仅保留数据库路径及联调参数。通过 [管理后台](../gtt-admin/README.md) 创建商户、分配授权、停用或轮换密钥，运行中即时生效。`init` 不覆盖已有文件或重置钱包。

接口、签名、交易恢复、对账和范围见 [GTT 商户与平台钱包 v1](../../docs/gtt-merchant-wallet-v1.md)。
