# Sweet Bonanza POP 独立服务

运行 `python -m server.run --service-dir services/sweet-bonanza-pop`，或双击本目录 `start.bat`。
访问 <http://127.0.0.1:8086/>，也可从麻将服务 `/demo/` 大厅进入。

- 入口：`sweet_bonanza_pop_client`，只装载 `sweet-bonanza-pop`。
- 配置：`config/sweet-bonanza-pop.json`；数据：`data/games.sqlite3`；日志：`logs/service.log`。
- 账户、钱包、会话、局面、设置与其他服务独立；初始积分 2000。
- PP 协议 `/hub-demo/ge/v3/gameService`；支持 doInit、doSpin、doCollect。
- 客户端：`clients/sweet-bonanza-pop/`，原版设置、规则、投注、旋转与自动旋转入口保留，不添加实现状态浮层。

当前抓取包含英文 desktop 包，本地直接加载该包，窄窗口使用原客户端自身布局。中英文大厅均可进入英文游戏；未声称支持中文或独立 mobile 包，等待补抓后接入。
未改写原始资源；启动脚本设置本地会话与英文，关闭 DEMO 水印标记；同步反序列化使用与宙斯相同的兼容方式。

普通消除、免费、倍率、免费追加已有实测证据。POP 中奖结算已有本地实现，专用动画字段仍待原响应校准；封顶与恢复的原版响应也待补抓。完整边界见 [引擎文档](../../server/games/sweet_bonanza_pop/README.md)。

导入新抓取：`python tools/pp_capture/import_capture.py <capture-id> --game sweet-bonanza-pop`。
中途抓取继续进行不会影响此服务；运行时不访问远端或抓取工具。
