# Wild Bandito

启动：`start.bat`，或在仓库根运行 `python -m server.run --service-dir services/wild-bandito`。

- 端口：8100；独立配置：`config/wild-bandito.json`；独立数据库：`data/games.sqlite3`。
- 大厅：`http://127.0.0.1:8080/demo/?lang=zh`；通过大厅创建独立试玩会话。
- 原版英文客户端：普通旋转、连消、金框转 Wild、递增倍率、规则、赔付表、自动旋转、投注与历史记录；免费已按公开规则实现，待原版免费样本复核。
- 不重放抓取结果，不改原资源字节，不在游戏中添加技术提示。

免费结算已通过 12 组真实 HTTP/二进制模拟（3/4/5 Scatter、零中奖、再触发及最后一次再触发），包含重试和服务重启恢复。运行 `python -m tools.pg_capture.simulate_wild` 可复核，临时数据不进入 8100 钱包。

原版免费画面仍缺 4 个资源包，CDN 返回 403，完整 UI 尚未跑通；详细文件清单在规则文档中。免费后端模拟通过不代表缺失的界面资源已恢复。

证据、规则及补抓操作见 `docs/wild-bandito-rules.md`。
