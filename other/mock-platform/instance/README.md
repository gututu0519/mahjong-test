# GTT 模拟合作平台

> 目录已重组。当前启动命令与路径见[四目录说明](../../docs/project-layout.md)；本文中的旧命令保留为历史记录。

默认 `start.bat` 已切换 Node。已有环境继续使用原三库；新建环境在 `server/` 执行 `npm run init`、`npm run sandbox-init`，统一使用 8110–8113 和 `services/gtt-gateway/data/node.json`，已有环境不可重复初始化。下文 Python 初始化仅为历史回退流程；当前启动和构建见 [Node 使用说明](../../docs/node/README.md)。

监听 `127.0.0.1:8111`，提供独立的玩家钱包、签名回调和本机联调页面。平台钱包位于本目录 `data/platform.sqlite3`，重启不会重置既有余额；该数据库与 GTT 和原试玩服务隔离。

项目根目录首次执行 `python -m py.merchant.sandbox init`，然后运行 `node server/tools/start.mjs mock` 或本目录 `start.bat`。另行启动 GTT 接入服务后，打开 <http://127.0.0.1:8111/> 创建游戏会话、打开 Buffalo Win，再刷新查看平台账单。

页面由平台服务端签署 GTT 启动请求，浏览器拿不到商户密钥。模拟页仅操作私有配置指定的测试玩家。

完整契约和验收步骤见 [GTT 商户与平台钱包 v1](../../docs/project/gtt-merchant-wallet-v1.md)。
