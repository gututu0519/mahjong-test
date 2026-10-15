# Super Ace 接入交接（2026-10-15）

## 当前状态

**客户端启动已修复，主游戏流程可试玩；平台附加功能仍未全部接入。**

JILI Super Ace（gameId 49 / fullhouse）保留原版 HTML、Cocos 界面、素材及动画，使用独立生成引擎、protobuf 适配和持久化钱包。2026-10-15 在 Edge 实际验证了启动、普通旋转、购买后 10 次免费旋转及连消播放、自动旋转启动/停止、规则与记录入口、刷新后余额恢复、手机尺寸显示以及大厅嵌入。平台邮件、活动、自定义命令等尚未验收，详见下方边界。

## 新电脑启动

在仓库根目录执行：

```powershell
git pull
python -m unittest discover -s server/tests -q
python -m server.run --service-dir services/super-ace
```

访问 `http://127.0.0.1:8088/`。也可双击本目录 `start.bat`。
大厅沿用麻将服务：`python -m server.run --service-dir services/mahjong-ways2`，访问 `http://127.0.0.1:8080/demo/`。
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
- 修改前全量后端基线 **72 项通过**；本次 Super Ace 引擎与 HTTP 回归 **7 项通过**。新增验证原始脚本逐字节返回、连接探测不创建账户、不泄露会话，以及非空记录页和返回导航。
- `response-capture/.venv/Scripts/python.exe tools/jili_capture/check_local.py` 通过：真实客户端启动、旋转、自动旋转、规则/记录打开与返回、同会话刷新不多扣款、390×844 显示。无 JavaScript 页面异常，页面余额与账本一致；脚本不替换浏览器响应，也不注入测试牌面。
- 手动浏览器验证购买：基础下注 0.5、扣款 20.25；10 次免费盘完整播放，示例最终中奖 20.25，界面余额与账本均为 1999.5。此为本次随机结果，不是固定回放。大厅加载到 100% 后发出 `demo:ready`，遮罩正常退出。

## 启动修复与运行适配

`clients/super-ace/local-adapter.js` 在 SystemJS 注册 `WASM-` 模块时替换登录和请求边界：W → `/jili/login`、c → `/jili/command`、b → `/jili/custom`。`/jili/custom` 尚未实现，不能宣称平台附加功能已完成。ack 1/0/2/4/36 已适配；无支持的命令明确报错。

注意 SystemJS factory 必须显式两个参数 `(publish, context)`；框架检查函数 length。单项导出的返回值也必须保留，不能统一改成对象导出返回值。当前适配器已修正这两点。

原先的 `TypeError: A.apply is not a function` 和 generator 卡死来自公共脚本的原站域名检查。暂停 JS 后确认：

- 文件 `astarte2/3.6/web-mobile/src/chunks/bundle.0c125.js`（单行）。
- `M82` 在列约 705888 执行 `delete W1u[P8G[C1T]]`，首个观察目标为 Element.prototype 的 constructor；随后会破坏 Function/JSON 等。
- 调用链：M82 → H3R → 匿名函数 → l4lMvcD → V8t4G.w4f → 模块 execute。
- `H3R` 还安排大量字符串分配的定时分支。仅替换 delete 语句不足以修复启动。
- 检查函数 `V8t4G.V97.l4lMvcD` 读取当前 hostname，127.0.0.1 不匹配原站表；另一份 `assets/other/index.22b2c.js` 存在相同检查 `w3CK8.r3L3.l4lMvcD`。
- 直接改 `H3R` 或函数文本会进一步触发源码完整性保护。因此没有修改这两份原始脚本，也没有应用上次交接的临时文本补丁。
- `local-adapter.js` 仅在 localhost / 127.0.0.1 / ::1 下，用两个一次性属性 setter 在对应配置初始化时适配域名谓词，保留调用方的十六进制奇偶编码。安装完成立即移除 setter；浏览器检查验证 `Function.prototype` 上没有残留。版本变更时必须重新验证这两处绑定，不能盲用旧名称。
- 原客户端基于 IP 生成 `uat-history.0.0`，导致 `new URL()` 抛错；在 URL 构造和 iframe 资源边界映射到本地规则/记录页，使页面加载与 postMessage 的 origin 一致。已有规则页、记录页新增返回按钮，使用原客户端 `CloseWebView` 事件关闭。
- Cocos 用 `style.textContent` 写入字体地址，已在该边界映射为本地 HTTP，修复 HTTPS 字体请求失败。连接监测访问无凭据 `/fullhouse/` 时，仅对 `Sec-Fetch-Dest: empty` 返回 204，不创建账户；正常页面访问仍校验会话。
- 大厅跨端口且不发送 referrer，加载完成通知不包含任何会话信息；接收端继续校验消息来源窗口和 origin。

浏览器回归命令见上文。截图与诊断输出在 `clients/super-ace/diagnostics/`，不提交；原始抓取字节仍按 `.gitattributes` 保持不变。

## 尚未完成及补抓项

- `/jili/custom`、`/rankingservice/user/GetMailList` 和平台 life-service WebSocket 没有本地业务实现。邮件请求仍为 404，远端 WebSocket 被 CSP 拦截；不影响已验证的旋转/结算，但不能称为完整平台还原。原入口未隐藏或禁用。补抓邮件列表、打开邮件、活动、奖励领取和自定义命令的请求/响应后再实现，不能伪造成功响应。
- 原版完整规则/记录网页样式及逐步回放仍未还原；当前入口打开仓库已有的规则文本/素材页面和本地账本表格。
- 极端封顶时逐项 award 与截断 combo 金额的一致性、免费再触发、购买多份后中途刷新、未播完动画的恢复，以及真实手机浏览器横竖屏切换仍需专项验证。已验证的刷新恢复是已结算回合余额，不等于恢复动画播放位置。
- 原始完整 Super Ace 抓取 `d15806bcacc3496aade5a3f080feb2c6` 尚未复制到这台电脑；现有去标识化 fixtures 和静态资源足以运行本次修复。需要补齐以上平台功能时，先迁移或重新抓取对应证据。

## 主要文件

- `server/games/super_ace/engine.py`、`config.json`：生成式规则和本地参数。
- `server/adapters/jili/wire.py`、`super_ace_schema.json`、`super_ace.py`：protobuf 和原版消息适配。
- `server/services/super_ace_demo.py`：8088 HTTP 服务、原版资源、登录和命令路由。
- `clients/super-ace/local-adapter.js`：客户端协议边界及本地 URL 适配。
- `server/tests/test_super_ace.py`：后端测试。
- `tools/jili_capture/`：素材导入、原型分析及诊断脚本。部分分析脚本固定了本次抓取 ID，属于开发工具。
- `demo/`、`server/services/local_demo.py`：JILI 分类、Super Ace 卡片和独立服务跳转。

后续工作先读本文件并运行浏览器回归，再按上述补抓项继续；不要重复应用已失败的源码文本修改，也不要隐藏未实现的原版入口。
