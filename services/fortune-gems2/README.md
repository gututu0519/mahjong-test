# TaDa Fortune Gems 2 接续记录

更新：2026-10-15。按用户要求暂停实现，保存当前代码，明天继续。

**当前是开发检查点，尚未打通可试玩流程。** 独立服务 8089 可启动，原客户端能显示介绍页并加载到 100%，但开始按钮没有出现。尚未接入大厅，横竖屏完整交互、旋转及轮盘动画均未通过浏览器验收。不要将服务启动成功或后端既有测试通过描述为本游戏已经完成。

## 明天从这里继续

1. 启动 8089，先解决介绍页停在 100% 的启动回调，再检查真实点击开始是否登录并请求 game info。不要强行隐藏介绍页或手动设置完成标记来绕过启动流程。
2. 核对本地 `GameApp` 登录状态、公共 `m_readyCb` 调用路径、GameView 初始化和 life-service 握手依赖。最后一次观察的具体状态见下节。WebSocket 被 CSP 拦截是现存问题，尚不能认定就是卡点原因。
3. 普通旋转打通后验证 Extra Bet、普通轮盘和额外倍率轮盘。优先查最新抓取中的规则和额外轮盘证据，补齐 `MultShowArray`、`LightOnPos`，核实 symbol 0 / wild 赔率。
4. 添加专项后端测试：真实样本逐线结算、protobuf 编解码、钱包扣款/中奖、相同 key 重试、非法下注、round-end 不重复扣款。然后做原客户端端到端验收。
5. 用 390×844、横屏和运行中旋转方向检查布局、开始按钮、下注、Extra Bet、自动旋转、中奖/轮盘动画、规则、记录、关闭返回、同会话刷新及余额一致性。用户已补抓竖版，必须查最新会话，不能按旧快照判断缺少素材。
6. 验收后接入大厅 TaDa 厂商筛选、第七张卡片及封面，补 `server/services/local_demo.py` 的 catalog、launch 和封面白名单。目前大厅仍是原来的六款。

## 当前卡点及排障证据

最初公共脚本在 localhost 触发保护分支，进入十亿次循环。导航前开启 CDP Debugger、加载 3 秒后 pause，定位调用链为 `v$L → L3H → V4BhcNw → h2eSW.X61 → execute`。

- `astarte2/3.6/web-mobile/src/chunks/bundle.fb6e5.js`：`h2eSW.m_4.V4BhcNw`；循环位置单行列约 775504。
- `astarte2/3.6/web-mobile/assets/other/index.ad23f.js`：`R7xpx.C3jL.V4BhcNw`。
- `local-adapter.js` 只在 loopback 域名下，通过一次性 Function.prototype 属性 setter 适配这两个谓词，保留调用方十六进制奇偶编码。原始混淆脚本没有修改。更新上游版本时必须重新定位名称和逻辑。
- 加入该适配后不再卡死，介绍页可显示；补充 `/api-documents/` 静态路径白名单后，banner 的 plist/png 不再 404，加载由 98% 到达 100%。

最后一次本地浏览器观察（1100×800）：

- `IntroView.IsDataReady() === true`，`CheckTasks() === true`。
- `m_nowProgress ≈ 100`，`m_maxProgress ≈ 100`，`m_isBottombarFinished === true`。
- `m_sceneNode.active === true`，`Btn_Playing.worldScale` 的 x/y 仍为 0。
- `m_barChangeAnim` 有 `Clip_Intro_LoadingToButton`，时长 0.8333 秒，state 存在但没有播放。
- `APP.IsLoaded() === true`，但 `APP.m_loginSuccess === false`、`m_preLoaded === true`、`m_loginBody === null`。
- `GameView` 在前一次检查中 `m_isLogin`、`m_isGetGameInfo`、`m_isBottombarFinished` 均为 false。
- `IntroView.Init` 注册公共 ready callback；callback 才会播放 LoadingToButton 动画。需要查清谁应触发它。
- 控制台没有 pageerror；有原版 Normal 字体 OTS 警告，以及连接 `wss://uat-wbslot-fd.tsohlacol.com/lifeservice/ws2` 被本地 CSP 拦截的错误。当前 launch 的 `domain_gs=localhost` 被原代码反转/拼成上述域名，不能继续使用原远端连接。
- 早先原站诊断浏览器也曾停在 100%，手动触发 transition 出现 getState 返回 null；后续本地检查确认 LoadingToButton clip 存在，不要把早先结果直接当成本地缺失素材结论。

本地适配器 `demo:ready` 目前依赖 ack 1 返回，触发时机偏早，尚未用于大厅；应改为真实画面就绪后通知。`/tada/custom` 尚未实现。平台邮件、活动及 life-service 也没有本地业务实现；原入口未隐藏。

## 已保存的实现

- `clients/fortune-gems2/`：164 个原版静态文件、素材来源索引、去标识化 login/info fixtures、本地适配脚本和简版规则页。
- `tools/tada_capture/import_capture.py`：从抓取导入静态 allowlist；正在录制、没有 manifest 时读取 8090 snapshot。只导入静态文件，来源 URL 去 query。
- `server/adapters/tada/fortune_gems2_schema.json`：从原客户端提取的公共及游戏 protobuf 定义。
- `server/adapters/tada/fortune_gems2.py`：W 登录、ack 1 info、2 notice、0 spin、4/36 查询最后回合；复用现有 protobuf codec 和事务钱包。
- `server/games/fortune_gems2/`：3×3 五线、wild、第四倍率列、Extra Bet 与轮盘的本地生成引擎草稿；不是原版数学模型。
- `server/services/fortune_gems2_demo.py`、`services/fortune-gems2/`：8089 独立服务、独立配置和数据库；已登记 catalog 和启动入口。
- `server/tests/fixtures/fortune-gems2-spins.json`：60 个去标识化真实公共 trial 样本，25 普通、35 Extra Bet，含一个普通轮盘样本，没有额外倍率轮盘样本。

## 已核实协议与未核实规则

游戏归属按实际启动链确认为 **TaDa**：`tadagaming.com/PlusTrial/223/en-us` → LoginTrial → `casino-wbgame.tadagaming.com/fgp/`，gameId 223、skin 1。引流页面标题中的 JILI 不作为本次客户端厂商归属依据。

- WASM System 模块 `chunks:///WASM-6233a0e2.js`，W 登录、c 命令、b custom。HTTP `/fgp/req` 是加密协议，旧密文不能直接回放给新会话。
- 公共 info 的下注档位为 0.2 / 0.4 / 0.6 / 1 / 2 / 4 / 8 / 10 / 20 / 40 / 80 / 100 / 120 / 160 / 200，初始币 2000，精度 10000。
- Extra Bet 为基础下注的 1.5 倍。SpinReq `extraSpin: {}`（Index 默认 0）已实测成功；Index 1 原站返回 ret 324。
- 五线顺序为中、上、下、左上至右下、左下至右上。符号 0..6 为普通，7 为 wild；8..13 表示 1/2/3/5/10/15 倍，14 普通轮盘，15 额外轮盘。
- 实际样本确认 symbol 1..6 的基础赔率分别为 1 / 1.6 / 2 / 2.4 / 3 / 4 倍；`AwardDataVec.Win` 已包含第四列倍率，不能再乘一次。
- 轮盘档位顺序来自 GameInfoData：`[1000,10,1,30,5,50,200,8,100,3,20,15]`。真实普通轮盘样本中基础下注 0.2、WheelOdd 8、WheelMult 1、WheelWin 1.6，另有 LineWin 0.2，总中奖 1.8。

尚未核实或未完成：

- 配置中的 symbol 0 = 0.4 倍、wild = 5 倍目前是推断，需查原规则或真实中奖样本。
- `MultShowArray` / `LightOnPos` 当前为空；额外轮盘需要的倍率分布、亮灯位置和动画契约未确认。
- `max_win_multiple=15025` 是当前草稿假设；GameInfo.MaxOdd=15000 的含义和总封顶边界仍需进一步核实，不能认为已还原。
- 所有符号权重、stack/轮盘概率和 RTP 都是未还原项。官网与本次捕获版本存在规则差异，不要将官网新版本直接套用。
- 公共 freeSpinList 的 `free` 字段在原 encoder 诊断时触发保护，schema 尚缺该字段；当前 empty freeSpin 不等于平台赠送免费旋转已实现。
- 刷新/断线后动画恢复、round-end/未展示回合语义还未验证；4/36 目前仅返回最后结算，不重复扣款。
- 简版 `/rules` 和本地账本 `/history` 不是原版完整规则/历史网页，逐步回放未实现。

## 启动与资料位置

在仓库根目录执行：

```powershell
python -m server.run --service-dir services/fortune-gems2
```

访问 `http://127.0.0.1:8089/`。大厅 8080、游戏 API 8082、其他独立游戏 8083/8085/8086/8087/8088、抓取工具 8090 沿用现有服务。明天先检查 `/health` 和监听端口，避免重复启动。不要覆盖 `services/*/data/`。

原始抓取会话：`26eac198ccb74d698186778efab172a2`。保存位置 `response-capture/captures/<session>/`。截至本次暂停仍在 recording；最后一次重新导入仍为 164 个静态文件。**不要停止用户的录制会话**，继续前通过 `/api/sessions` 和 `/api/sessions/<id>` 读取最新状态。不要在日志、文档或提交中输出带 ops/ssoKey/token 的 URL。

以下本地资料被 `.gitignore` 排除，不随 Git 推送，换电脑需私下复制：

- `response-capture/captures/26eac198ccb74d698186778efab172a2/`：完整 HTTP / WebSocket 抓取。
- `clients/fortune-gems2/diagnostics/`：截图、解码结果、CDP 探针及原始 trial 数据，可能含临时会话凭据。
- `services/*/data/`、`services/*/logs/`：钱包/存档及日志。

诊断目录里 `local_host.py` / `local_drive.py` / `local_scopes.py` 用本地 CDP 9232，`live_host.py` / `drive.py` / `scopes.py` 用原站 CDP 9231；运行需 `response-capture/.venv/Scripts/python.exe`，系统 Python 没有 playwright。调试主机不是正式服务。`local-console.json`、`local-feature-decoded.json`、`readiness.json`、`anim.json`、`reloaded.png` 保存最后卡点证据。

`decode.cjs` / `main.decoded.js` / `fgp-proto.json` 可查游戏协议；`schema.js` 可追踪公共 protobuf。混淆 scope 里的同名变量在不同模块并不相同，读取一个 scope 会覆盖 `window.__scope` 同名项；不要用错误 decoder 的结果作证据。卡死后再 attach CDP 往往无法响应，`debug-new.py` 的“导航前启用 Debugger 再 pause”才是已验证办法。

## 同批其他改动

Super Ace 核心试玩与启动修复已完成，浏览器验证和剩余平台功能见 [Super Ace 文档](../super-ace/README.md)。按用户要求，大厅“星际宝石”“幸运七号”占位卡片及对应筛选/样式已移除。这些改动与本 TaDa 开发检查点一同保存。

提交前运行 `python -m unittest discover -s server/tests -q`：**75 项全部通过**（40.089 秒）。另按来源索引核对 164 个静态文件与抓取响应逐字节一致。Fortune Gems 2 尚无专项测试，既有测试通过不能代替该游戏验收。
