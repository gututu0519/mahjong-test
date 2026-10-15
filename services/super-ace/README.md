# Super Ace 接入交接（2026-10-15）

## 当前状态

**这是开发中检查点，不是已验收的可玩版本。** 用户要求换电脑，故暂停排障并提交当前工作。

已取得 JILI Super Ace（gameId 49 / fullhouse）的原版 HTML、Cocos 客户端和公共素材；已实现独立服务、生成式结算、protobuf 适配、钱包和大厅卡片。后端测试通过，但本地客户端仍卡在启动阶段，尚未完成实际旋转、购买、自动旋转、规则和记录入口的浏览器验收。大厅目录登记 playable 是现有接口接入方式，不能据此认为已验证可玩。

## 新电脑启动

在仓库根目录执行：

```powershell
git pull
python -m unittest discover -s server/tests -q
python -m server.run --service-dir services/super-ace
```

访问 `http://127.0.0.1:8088/`。也可双击本目录 `start.bat`。
大厅沿用麻将服务：`python -m server.run --service-dir services/mahjong-ways2 --port 8081`，访问 `http://127.0.0.1:8081/demo/`。
抓取工具的 `8090` 是抓取管理页面，不是新游戏端口。
服务代码只需 Python 标准库。浏览器诊断另外安装 `playwright` 并准备 Edge；可用现有 `response-capture/.venv/Scripts/python.exe`，新电脑须自行创建虚拟环境。

本服务数据在 `services/super-ace/data/`，独立 SQLite，初始余额 2000，金额精度 10000。公共钱包新增精度元数据；既有游戏仍用 100。不同精度不允许混用一个服务或数据库。

## 必须另行复制的本地资料

以下目录被 `.gitignore` 排除，**推送不会带到新电脑**：

- `response-capture/captures/d15806bcacc3496aade5a3f080feb2c6/`：原始完整抓取，包括 manifest、请求、响应和 WebSocket 数据。
- `clients/super-ace/diagnostics/`：本次排障中间文件、截图、解码脚本、补抓结果和浏览器探针。含原始试用会话信息，保持私下复制，不公开提交。
- `services/*/data/`：如要保留已有游戏余额和存档，停止对应服务后复制；不需要存档则新电脑自动新建。

原版静态资源、去标识化的登录/规则/结算 fixtures、后端代码和大厅修改已纳入提交，新电脑不需要重新抓取才能开始排障。原始抓取和诊断目录仍建议完整迁移。

## 已完成与证据

- 最新抓取会话共 2773 条记录，135 个 WebSocket 帧；原版入口 HTML 对应请求 709、1440。`fullhouse/req` 是 protobuf 加密传输，不能把旧密文直接回放给新会话。
- 导入工具：`tools/jili_capture/import_capture.py`；来源索引：`clients/super-ace/fixtures/asset-sources.json`。原版文件保持原始字节，仓库 `.gitattributes` 禁止自动换行转换。
- 使用公开 trial 启动补抓了正常旋转和购买的解码结果；去标识化样本在 `server/tests/fixtures/super-ace-spins.json`。购买样本为 0.5 基础下注、20.25 成本、23.65 总中奖，包含基础盘和 10 次免费盘。
- 原版内置教学数据在 `clients/super-ace/fixtures/DemoData.json`，用于确认金框转百搭、大 Joker 复制及免费流程。
- 生成引擎：5×4、1024 ways、原位翻牌式连消、金框变百搭、大 Joker 复制、1/2/3/5 倍率、免费双倍倍率、3 scatter 触发 10 次、免费重触发加 5 次、购买 40.5 倍、10000 倍总封顶。
- 原版符号概率、金框概率、大 Joker 复制数量分布及 RTP **未确认**；配置中的概率是本地生成参数，不是还原原版数学模型。极端封顶时逐项 award 与截断 combo 金额的一致性还需专门验证。
- 原版前端资源为英文；大厅中文/英文均可启动同一英文客户端。没有添加技术说明水印或游戏画面浮层。
- 2026-10-15 执行 `python -m unittest discover -s server/tests -q`：**72 项通过**。含 Super Ace 样本赔付、生成盘、四位金额精度、重复请求不重复扣款、重启持久化和独立钱包测试。这不代表前端已验收。

## 当前阻塞及继续排查

`clients/super-ace/local-adapter.js` 在 SystemJS 注册 `WASM-` 模块时替换登录和请求边界：W → `/jili/login`、c → `/jili/command`、b → `/jili/custom`。`/jili/custom` 尚未实现，不能宣称平台附加功能已完成。ack 1/0/2/4/36 已适配；无支持的命令明确报错。

注意 SystemJS factory 必须显式两个参数 `(publish, context)`；框架检查函数 length。单项导出的返回值也必须保留，不能统一改成对象导出返回值。当前适配器已修正这两点。

仍然出现 `TypeError: A.apply is not a function`，随后原版 generator 异常循环，浏览器截图超时。暂停 JS 后确认公共脚本在本地启动时执行了删除内置对象属性的分支：

- 文件 `astarte2/3.6/web-mobile/src/chunks/bundle.0c125.js`（单行）。
- `M82` 在列约 705888 执行 `delete W1u[P8G[C1T]]`，首个观察目标为 Element.prototype 的 constructor；随后会破坏 Function/JSON 等。
- 调用链：M82 → H3R → 匿名函数 → l4lMvcD → V8t4G.w4f → 模块 execute。
- `H3R` 还安排大量字符串分配的定时分支。仅替换 delete 语句不足以修复启动。
- 这是已确认的环境防护分支；**触发条件是否为域名、来源校验或其他检测尚未完全查清**。公开 trial 原地址能正常运行，本地地址失败。
- 曾实验取消全局 fetch/XHR/src/window.open 包装、取消 WASM 模块 hook、去 CSP；尚无成功本地启动结果。不要把这些实验结论写成已修复。
- 最后实验只在 Playwright 路由中将 `H3R();` 替换为等长 `0    ;`（`diagnostics/local_guard.py`）；被用户中断前尚无成功结果。**原版素材和生产服务没有应用此实验补丁。**

最小复现：`python tools/jili_capture/check_local.py`，需先启动 8088 并创建 `clients/super-ace/diagnostics/`。完整诊断目录包含 `pause.py`、`break.py`、`delete.py`、`local_guard.py`、`interactive_probe.py`；迁移后可继续，但不能依赖旧机器仍运行的浏览器/PID/8764 诊断端口。

下一步先解决公共脚本初始化，再检查登录模板、info schema 和 spin protobuf 与原版运行时是否真正兼容。之后实际点击验证正常下注、连消、金框/大 Joker、购买和免费再触发、自动旋转、横竖屏、刷新/重启余额、记录与规则入口；补齐大厅 `demo:ready` 消息（当前未接）、检查 `/history` 返回结构和平台附加请求。当前服务器仍保留原版规则/记录等入口的适配意图，不允许通过隐藏功能绕过缺失实现。

## 主要文件

- `server/games/super_ace/engine.py`、`config.json`：生成式规则和本地参数。
- `server/adapters/jili/wire.py`、`super_ace_schema.json`、`super_ace.py`：protobuf 和原版消息适配。
- `server/services/super_ace_demo.py`：8088 HTTP 服务、原版资源、登录和命令路由。
- `clients/super-ace/local-adapter.js`：客户端协议边界及本地 URL 适配。
- `server/tests/test_super_ace.py`：后端测试。
- `tools/jili_capture/`：素材导入、原型分析及诊断脚本。部分分析脚本固定了本次抓取 ID，属于开发工具。
- `demo/`、`server/services/local_demo.py`：JILI 分类、Super Ace 卡片和独立服务跳转。

换电脑后可直接告诉下一位代理：先读本文件，按项目 AGENTS.md 保留原版功能，继续解决 Super Ace 本地启动，不要从旧密文回放或隐藏功能开始。
