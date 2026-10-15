# Big Bass Bonanza 独立服务

运行 `python -m server.run --service-dir services/big-bass-bonanza` 或双击 `start.bat`。
访问 <http://127.0.0.1:8087/>，或从 <http://localhost:8081/demo/?lang=zh> 的 Big Bass Bonanza 卡片进入。

- 服务入口 `big_bass_bonanza_client`，只装载 `big-bass-bonanza`。
- 独立配置 `config/big-bass-bonanza.json`，数据库 `data/games.sqlite3`，日志 `logs/service.log`。
- 初始积分 2000，账户、会话、局面、钱包与其他游戏服务隔离。
- PP 表单接口 `/hub-demo/ge/v3/gameService`：doInit、doSpin、doCollect。
- 原中英文横竖屏客户端资源 `clients/big-bass-bonanza/`；按游戏窗口宽高选择 desktop/mobile，大厅语言选择传入游戏，切换方向保留语言、会话与余额；保留原版规则、设置、投注、自动旋转和免费回合。
- 大厅封面来自主抓取记录 132，`https://cdn-cms.pragmaticplay.fun/slots-master/thumbs/vs10bbbonanza.webp`。

导入与更新脱敏证据：

```powershell
python tools/pp_capture/import_capture.py de27459d8d624e97af2d9609822f129f --game big-bass-bonanza
python tools/pp_capture/analyze_big_bass.py de27459d8d624e97af2d9609822f129f
```

导出工具优先读取正在录制的最新快照。当前规则、已验证样本与补抓项见 [玩法文档](../../server/games/big_bass_bonanza/README.md)。
