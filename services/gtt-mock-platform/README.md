# GTT 模拟合作平台

默认 `start.bat` 已切换 Node。已有环境继续使用原三库；新建环境在 `node/` 执行 `npm run init`、`npm run sandbox-init`，使用隔离端口 8210–8213。下文 Python 初始化仅为历史回退流程；当前启动和构建见 [Node 使用说明](../../node/README.md)。

监听 `127.0.0.1:8111`，提供独立的玩家钱包、签名回调和本机联调页面。平台钱包位于本目录 `data/platform.sqlite3`，重启不会重置既有余额；该数据库与 GTT 和原试玩服务隔离。

项目根目录首次执行 `python -m server.merchant.sandbox init`，然后运行 `node node/tools/start.mjs mock` 或本目录 `start.bat`。另行启动 GTT 接入服务后，打开 <http://127.0.0.1:8111/> 创建游戏会话、打开 Buffalo Win，再刷新查看平台账单。

页面由平台服务端签署 GTT 启动请求，浏览器拿不到商户密钥。模拟页仅操作私有配置指定的测试玩家。

完整契约和验收步骤见 [GTT 商户与平台钱包 v1](../../docs/gtt-merchant-wallet-v1.md)。
