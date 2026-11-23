# 特殊玩法维护表监督流程

本目录将“抓到候选”与“接入已验收”分开处理。抓取检测器只判断保存下来的协议样本；只有完整抓取证据、当前实现、真实本地界面验收和登记专项测试全部通过，更新器才允许把登记的一个 `❌` 改为 `✅`。

当前登记的 7 个缺项都没有真实完成的整套验收材料，其专项测试路径也只是登记位置，不能据此宣称已经支持。当前应保持 `pending`，不修改这些单元格。PP、TaDa 尚无对应功能解码器的项目继续等待；麻将购买的报价证据未确认时最多为候选。该流程不会补造证据、自动实现玩法或用合成测试替真实玩法打勾。

## 启动与状态

在仓库根目录运行：

```powershell
node other/tooling/feature-maintenance/watch.mjs --capture-url http://127.0.0.1:8090 --interval-ms 10000 --once
node other/tooling/feature-maintenance/watch.mjs --capture-url http://127.0.0.1:8090 --interval-ms 10000
```

常驻进程不逐轮输出控制台日志，状态写入 `other/diagnostics/feature-maintenance/status.json`。捕获 API 只读轮询，不开始或停止录制。每次最多使用一个 watcher；锁文件为该诊断目录中的 `.watch.lock`。正常 `SIGINT` / `SIGTERM` 退出会清理自己创建的锁。旧 PID 存在或无法确认归属时保留锁，不结束任何旧进程；确认 PID 已退出后才清除对应旧锁。

`--once` 正常检查结束返回退出码 `0`，即使所有登记玩法仍为 `pending`。抓取 API 失败、顶层处理异常或来源验证错误返回非零；异常原因仍写入本地状态文件。

抓取工具自动创建的子进程可使用内部参数 `--parent-pipe`：父进程向 stdin 写固定 `stop\n` 或关闭管道，watcher 会停止下一轮并等待当前表格更新完成后退出。Windows 父进程不能用 `terminate()` 代替这个入口，否则可能在更新事务中途强制截断。手动常驻启动不需要此参数。

该诊断目录属于本地私有产物，不应提交。记录包含候选、验收文件、测试日志和表格更新备份。watch 只保留登记游戏的必要 game-api 元数据：会话编号、脱敏启动 URL 以及请求的 `id/url/method/state/status/mime/body/request_body`；URL 删除查询参数，不复制请求头、响应头、Cookie 或 Authorization。普通素材请求不参与变化检测。没有功能候选时不另存详情快照；有候选才保存内容摘要寻址的脱敏快照。原始请求体只保留在既有 capture 目录，通过摘要引用，不再复制。

状态或文件缺失、解码失败、Excel 占用、测试失败都会保持 `pending` 并给出原因。关闭 Excel 后可在下一次轮询重试。相同输入的已通过专项在同一 watcher 进程内复用已核验结果；代码、资源、证据或验收文件改变后会重新检查。进程重启不直接把旧的布尔声明当作新执行结果。

监督入口 `verify.mjs` 自身发生变化时必须重启本窗口的 watcher；旧进程会拒绝为未加载的新代码摘要生成报告。固定验证器模块按内容摘要加载，其执行版本也在生成报告前重新核对。

## 登记条件

`features.json` 决定允许变更的准确游戏、玩法名称、工作表和单元格。每项必须登记：

- `verifier` 固定为 `other/tooling/feature-maintenance/verifiers/integrated-feature.mjs`。
- `test_files` 是 `other/tests/feature-maintenance/*.test.mjs` 中该玩法的固定专项测试路径。文件尚不存在就不能通过。验证器没有任意命令或 shell 参数入口。
- `implementation_roots` 至少覆盖该游戏的 `backend`、`frontend`、`instance/config`。验收必须绑定这些目录内的全部文件，而不是只挑一个没有变化的文件；影响该玩法的共享代码也应加入登记目录范围。
- 当前 `gateway/config/game-readiness.json` 中相同游戏编号、code、玩法名称的 `implementation` 必须为 `included`。这只是必要条件，单独修改它不会触发打勾。

`capture_sources` 另外登记原始抓取来源，和本地UI验收来源严格分开。当前只确认启动来源 `https://sdstest.ink` 与 PG API 来源 `https://api.mmga1.com`；没有确认的 PP/TaDa 来源不自动放行。本机接口、未知域名或不匹配的来源即使能解码也不能当原始厂商证据。已有捕获会话启动路径是 `/`，因此不擅自要求只能从 `/game` 启动。

最终验收还必须等该次捕获正常停止并保存 `manifest.json`。验证器核对完成状态、原始启动 origin/path，以及每个证据文件在原始 manifest 中对应的可信 HTTPS game-api 成功请求。录制进行中没有 manifest 时保留候选并等待，不停止抓取，也不最终打勾。

专项测试应按对应玩法实际断言触发条件、连续状态、金额与钱包、结束状态、重复请求和刷新恢复，并读取 `GTT_FEATURE_ACCEPTANCE_PATH`、`GTT_FEATURE_CANDIDATE_PATH` 指向的验收输入。不要用空测试、总为真的断言或无关游戏测试代替该功能验收。验证器固定执行当前 Node 的 `--test --test-reporter=tap`，要求实际测试数量大于零、退出码为零，且没有失败、取消、跳过或 TODO。

## 候选与真实界面验收

watch 自动保存的候选结构为：

```json
{
  "version": 1,
  "session_id": "抓取会话编号",
  "source": {
    "detail": {"path": "仓库内脱敏详情路径", "sha256": "实际文件摘要"},
    "capture_root": "other/capture/response-capture/captures/抓取会话编号",
    "detector": {"path": "other/capture/response-capture/feature_evidence.py", "sha256": "实际检测器摘要"}
  },
  "result": {"version": 1, "session_id": "抓取会话编号", "features": []}
}
```

`features` 保存对应检测结果。验证器固定重新执行 Python 检测器，对照输出、原始文件摘要和全部协议检查，不能仅把 JSON 的 `status` 改成 `evidence_complete`。

功能接入后，先在本地真实客户端完成入口、功能触发、结果、刷新以及恢复，保留可辨认的截图或录像与相应接口响应文件，再创建：

`other/diagnostics/feature-maintenance/acceptance/<功能id中非字母数字下划线横线替换为下划线>.json`

格式如下。示例中的文字是占位说明，不能直接作为有效验收：

```json
{
  "version": 1,
  "kind": "integrated-feature-acceptance",
  "synthetic": false,
  "feature": {"id": "登记id", "game_id": 4, "game_code": "wild-bandito", "name": "免费旋转"},
  "capture": {
    "session_id": "对应完整抓取会话",
    "candidate": {"path": "对应候选JSON路径", "sha256": "实际摘要"}
  },
  "implementation": [{"path": "完整实现快照中的每一个文件", "sha256": "实际摘要"}],
  "ui": {
    "record": {"path": "真实UI操作记录JSON", "sha256": "实际摘要"},
    "attachments": [{"path": "对应PNG截图或MP4/WebM录像", "sha256": "实际摘要"}]
  },
  "created_at": "有效ISO时间"
}
```

`implementation` 使用 `verify.mjs` 导出的 `snapshot(root, implementation_roots)` 获取，按路径排序。UI 操作记录需要：

- `version: 1`、`kind: "local-ui-record"`、`synthetic: false`、`feature_id`、`game_code`、`capture_session_id`。
- `implementation_sha256` 为 `hash(canonical(implementation))`，绑定执行该次 UI 验收的源码和资源版本。
- `started_at`、`finished_at` 和 `browser: {name, version}`。
- `network: {path, sha256}` 指向真实接口记录。
- `events` 按时间至少依次包含 `navigate`、`trigger-feature`、`observe-result`、`reload`、`observe-restored`。每项包含 `at`、`action`、`artifact`；`artifact` 必须对应上面的附件。`navigate` 还包含 `url`；触发、结果、恢复事件包含 `request_id`，关联实际接口响应。

接口记录格式为 `version: 1`、`kind: "local-ui-network"`、`feature_id`、`game_code`、`origin` 和 `records`。每个 record 包含唯一 `request_id`、`at`、`url`、`method`、`response_status: 200`、`response_body: {path, sha256}`。响应文件必须实际存在且非空。它与 UI 操作必须属于同一本地 origin、同一验收时间段。

只接受 `http://127.0.0.1`、`localhost`、`[::1]` 或项目统一网关的 `g<数字>.localhost` 地址。记录 URL 时移除查询参数与用户凭据，避免留下启动令牌。截图必须有完整 PNG 结构且至少 320×240；录像须具备相应媒体结构。哈希、文件结构及时间线检查提供可追溯性，不等于自动识别画面是否表现了目标玩法；录入验收材料时仍须如实完成界面流程，并由玩法专项测试验证实际协议与结算语义。

单独生成报告可运行：

```powershell
node other/tooling/feature-maintenance/verify.mjs --feature "登记id" --candidate "仓库内候选JSON路径" --acceptance "仓库内验收JSON路径"
```

缺任何条件都只返回 `pending`。通过后生成严格的 `version/status/feature/target/workbook_sha256/evidence/implementation/validation/created_at` 报告；其中保留实际测试 TAP、stderr 和执行记录的摘要。测试完成后还会重新校验所有输入，避免测试期间变动造成过期结论。

## 工作簿更新与重复执行

watch 仅把完整验证器产生的报告交给 `updateWorkbook({root, reportPath})`。更新器独立检查登记身份、目标位置、全部证据与实现摘要、当前 readiness、工作簿基线和 Excel 锁；成功后只改变登记的单格，保留备份和回执，并同步工作簿摘要。相同报告重复执行不再写表；旧 hash 或不完整材料不能跳过验证。当前没有真实通过项，因此不会修改现有缺项标记。

## 框架测试

```powershell
node --test other/tooling/feature-maintenance/tests/pipeline.test.mjs
```

这些测试在系统临时目录创建明确标记 `synthetic: true` 的协议、UI产物、源码和测试文件。它们只证明监督门禁的程序行为，包括完成、不完整、过期 hash、附件替换、skip、测试中变更、无证据轮询及互斥锁；不写真实工作簿，不证明 7 项玩法已经实现或验收。生产 CLI 不开放合成通过开关。
