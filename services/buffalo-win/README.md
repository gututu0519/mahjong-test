# Buffalo Win 独立服务

在仓库根目录启动：

```powershell
python -m server.services.buffalo_demo
```

也可以双击本目录 `start.bat`，或者运行 `python -m server.run --service-dir services/buffalo-win`。
服务监听 127.0.0.1:8083；主大厅依旧由 8080 的麻将服务提供。启动两项服务后，访问 <http://localhost:8080/demo/?lang=zh#games>，选择「美洲野牛 → 试玩」。

## 已实现

- 独立会话、2,000 初始虚拟积分、SQLite 持久化钱包与逐笔账本。
- 普通旋转、扩展符号计数、新增列、倍率递增、结束时统一结算。
- 3 个免费符号奖励 10 次免费旋转，每多 1 个加 2 次；免费内可重触发，最后一次免费也可续奖。扩展符号变百搭，倍率在免费功能内保留。
- 第 1 列不生成百搭；2/3/4 格堆叠分别扩展为 3–4/4–6/5–8 个符号；新增卷轴同样支持堆叠及原版表现字段，无本地 8 列截断。
- 原版 v2 JSON 协议适配：登录、GameInfo、Spin、钱包；刷新后可继续未完成的回合。
- 重复请求幂等、并发重复请求只结算一次、过期状态拒绝、余额不足回滚、回合内锁定投注。
- 大厅从后端取得游戏链接，再在 iframe 内运行。

目前中文客户端资源可用。英文接入进行中：原版启动页、主游戏英文资源和英文赔付表资源已从会话 `8a704656ec204d4899533712d6a8d7b1` 导入，英文规则和免费功能仍待补齐验证；按用户要求，大厅已开放英文测试入口；交互及免费功能验证仍在进行。进度见 `clients/buffalo-win/fixtures/english-capture-status.json`。可运行 `python -m tools.pg_capture.buffalo_win.import_capture <会话ID>` 从正在抓取的会话增量导入静态资源，脚本保留既有资源并在版本冲突时停止。原版赔付表、规则面板及 GameRule 接口已从抓取会话 `09637ea7151b461fbc04eee29b8678d5` 恢复；19 个静态资源的来源、响应行号与 SHA-256 见 `clients/buffalo-win/fixtures/restored-original-help-assets.json`。保留原版 UI、图片和文字，没有自制帮助面板。历史面板尚未接入；服务端 JSON 历史接口可用。

引擎 1.1.0 已按抓取的原版中英文说明对齐上述规则。来源为 `clients/buffalo-win/89240957a6.15d79.json`、`clients/buffalo-win/cbff7a4b9e.67a15.json`，客户端继续使用原版面板。GameRule 中的 96.75% 是捕获的原版元数据，不是本地引擎的理论 RTP；客户端保持不显示 RTP 的配置。

## 规则与本地参数

确定性结算参见 `docs/buffalo-win-rules-analysis.txt`。引擎的中奖位置、加权符号数、续列判断和派奖与 789 条离线响应一致（中文 403 条、英文 386 条）。英文脱敏用例 `rule-cases-en.json` 来自会话 `8a704656ec204d4899533712d6a8d7b1`，保留响应行号以追溯。运行服务不会读取这些旋转样本，每一步都由新随机种子生成结果。

本服务配置：`config/buffalo-win.json`。随机权重、堆叠概率、扩展块概率和合法范围内的大小分布仍为本地演示设定，不能代表原厂概率或理论 RTP。只要最右列继续中奖或含免费符号就新增卷轴；每次请求只推进一步，不强制插入中性列。

免费奖励在当前旋转的续列全部结束后统一判断，公式为 `10 + 2 × (免费符号数 - 3)`，不足 3 个不奖励。重触发追加剩余次数和总次数，保留倍率与累计奖金，不重复扣款；新一步清零当步新增次数字段。重触发使用原版说明中的同一奖励公式，但当前捕获没有完整重触发响应，其协议计数通过本地状态、适配器及持久化测试验证。配置校验锁定规则常量；改变规则需要更新实现及版本。新回合自动使用新 ruleset_id，已有未完成回合仍拒绝跨规则版本继续；升级时不清空钱包和历史。

所有金额使用整数分，积分无现金价值。引擎不含充值、提现或支付功能。

## 服务隔离与接口

本目录独立拥有 `service.json`、`config/`、`data/games.sqlite3` 和 `logs/service.log`，不使用麻将服务的数据库或账号。运行数据和日志被 Git 忽略。

- `POST /api/v1/games/buffalo-win/launch`，JSON `{ "language": "zh" }`。
- `POST /api/v1/sessions`；`GET /api/v1/wallet`；`GET /api/v1/history`。
- `GET /api/v1/games/buffalo-win/state`。
- `POST /api/v1/games/buffalo-win/spin`，Bearer token、Idempotency-Key，JSON `{ "previous_sid": "0", "bet": { "coin_minor": 30, "level": 2 } }`。
- 兼容接口：`/game-api/buffalo-win/v2/GameInfo/Get` 和 `/game-api/buffalo-win/v2/Spin`。

客户端的请求仅指向本地服务；原版公开 API 域名描述符只用于旧客户端初始化。认证模板已清理原始用户和令牌。采集原文、分析脚本与 fixtures 均不对 HTTP 开放。

前端资源来自本机捕获会话 ae59ed3f3b5044a0ac6ab404a23a724d，来源及 SHA-256 见 `clients/buffalo-win/fixtures/asset-sources.json`。大厅封面来自 `clients/buffalo-win/2d6aa03a40.9854e.jpg`。

旧命令 `python -m server.services.buffalo_preview` 仅保留为无结算的前端排查工具，与正式服务使用同一端口，不能同时启动。

## 验证

```powershell
python -m unittest discover -s server/tests -v
```

Buffalo 专项测试覆盖 789 条离线样本重算、204 派奖实例、完整免费流程、3/4/5 个免费符号奖励、最后一次免费重触发、倍率保留、堆叠数量范围、新增列堆叠、12 列延伸、持久化与并发重试、HTTP 登录与启动，以及跨服务隔离。测试中的固定结果注入只用于隔离测试，没有提供给正式服务的控制接口。
