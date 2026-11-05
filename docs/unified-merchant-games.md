# 19 款游戏统一商户接入

更新：2026-11-05。全部游戏已接入 Node 网关和平台/商户后台，原独立服务入口保留。本次为本机接入验证，没有发布到线上或更新 S3。

## 本机测试

| 入口 | 地址 |
| --- | --- |
| 模拟商户钱包与游戏选择 | http://127.0.0.1:8211/ |
| 平台管理后台 | http://127.0.0.1:8212/ |
| 商户管理后台 | http://127.0.0.1:8212/merchant/ |
| 商户签名 API | http://127.0.0.1:8210/gtt/v1/ |

本次测试使用私有 `node/runtime/config.json`，与既有 8110 环境及各独立游戏数据库隔离。管理员账号见 `node/runtime/admin-bootstrap.json`；模拟商户账号、商户号和密钥见 `node/runtime/merchant-demo-bootstrap.json`。不要提交这些文件。

模拟商户已授权全部 19 款，初始余额为 2000.0000 USD，钱包精度 10000。打开模拟平台，选择游戏，点“创建游戏会话”，再点“打开游戏”。投注后回到模拟平台刷新余额和交易，也可在后台交易中心按游戏查询。

首次安装后，在 `node/` 执行 `npm ci`、`npm run build`。新环境执行 `npm run init`、`npm run sandbox-init`，已有配置不能重复初始化。四个终端分别运行：

```powershell
node tools/start.mjs gateway --config runtime/config.json
node tools/start.mjs platform --config runtime/config.json
node tools/start.mjs admin --config runtime/config.json
node tools/start.mjs rtp-worker --config runtime/config.json
```

网关启动器会启动并监督美洲野牛内部计算子进程。其他游戏协议 worker 按首次访问启动，无须先启动 18 个旧独立端口。当前后台进程和日志在 `node/runtime/local-all-games-logs/`。

## 授权与接入流程

1. 平台管理员创建商户，配置钱包 origin、金额精度和游戏授权；系统自动分配商户号、登录账号与签名密钥。
2. 商户实现 `/wallet/v1/balance`、`debit`、`credit`、`refund` 及交易查询等现有钱包接口，原签名规则不变。
3. 商户服务端签名调用 `POST /gtt/v1/games/list`，获取获授权游戏。`wallet_compatible` 表示钱包精度是否足够。
4. 调用 `POST /gtt/v1/games/launch`，传入数字 `game_id`、`player_id` 和语言；启用预派彩时还需 `external_username`。
5. 浏览器直接打开返回的完整 `launch_url`。每款游戏使用自己的 origin 和绑定游戏的短期会话。
6. 原客户端协议经网关转接原 Node 协议适配器。统一网关保存确定性计算、钱包扣款/派彩、整局状态与幂等结果。
7. 商户使用原交易查询/重试接口对账；平台或商户后台查询交易。停用或撤销授权后，后续游戏请求被拒绝，已受理的待结算操作可由有权限的运营人员恢复。

## 固定游戏编号

编号沿用原 `server/merchant/identifiers.py`，不能重排。商户 API 使用数字编号，内部和原独立入口保留 slug。

| ID | 游戏 | 原生精度 |
| --- | --- | --- |
| 1 | buffalo-win | 100 |
| 2 | captains-bounty | 100 |
| 3 | fortune-rabbit | 100 |
| 4 | wild-bandito | 100 |
| 5 | tower-run-treasure-steps | 100 |
| 6 | great-game-serengeti | 100 |
| 7 | dr-zappo | 100 |
| 8 | le-vampire | 100 |
| 9 | wicked-grin | 100 |
| 10 | roma-x-10000 | 10000 |
| 11 | money-pot-deluxe | 10000 |
| 12 | 3-billion-vaults | 10000 |
| 13 | jokers-fortune-winx | 10000 |
| 14 | fortune-gems2 | 10000 |
| 15 | super-ace | 10000 |
| 16 | big-bass-bonanza | 100 |
| 17 | sweet-bonanza-pop | 100 |
| 18 | gates-of-olympus | 100 |
| 19 | mahjong-ways2 | 100 |

## 金额、状态和部署约定

钱包精度创建后不可更改。接入全部游戏使用 10000；原精度 100 的商户保持旧金额语义，可以使用原生精度 100 的游戏。原生 100 的引擎投注与派彩在回调时精确乘以 100，原生 10000 的游戏直接使用商户单位；不对钱包实际金额取整。两位小数客户端只展示到分，不展示不足一分的余额部分。结果的 `wallet` 和 `minor_unit` 使用游戏原生单位，`settlement` 明确记录商户钱包单位，后台交易金额也使用商户钱包单位。美洲野牛 RTP 报表按游戏原生精度 100 聚合。

商户、玩家、游戏共同确定状态与历史。原协议缓存仅存放在独立的 `merchant-protocols/<游戏>.sqlite3` 镜像中，权威账务与游戏状态保存在网关数据库。钱包回调超时后以同一交易号恢复，不重新开奖，也不重复扣款。协议 worker 重启后从权威账务同步镜像。

已有美洲野牛 RTP 功能保留，四位钱包也使用相同模型选择和整局绑定。其他游戏没有新增未经标定的 RTP 模型；后台美洲野牛 RTP 页面只表示该游戏。商户预派彩开关适用于全部游戏，限制以实际付费整局为基数，普通、免费、续列和收奖按各款已有状态机处理。优先匹配原区间，最多搜索 3000 个完整合法候选；未命中时选择已搜索结果中不超过上限的最高派彩，允许低于原下限。不会向上取档或修改引擎派彩；没有合法下档时才返回 `PREBET_RANGE_UNREACHABLE`，不扣款。有限搜索不等于全局数学穷举，实际取档及搜索范围写入决策 resolution。

本机使用 `g1.localhost:8210` 至 `g19.localhost:8210`，保留原客户端根路径 API 和素材地址，Cookie 按主机隔离。支持 localhost 子域的浏览器无需修改 hosts。旧两位钱包的美洲野牛入口继续使用原网关地址。

生产需显式配置 `game_origins`（slug 到 HTTPS origin 的映射），代理到统一网关并保留 Host、Origin 和可信代理头；每个游戏使用不同 origin。完整素材保持独立发布，网关最小包只带必要协议/启动资源，需挂载完整资源树或配置经验证的 CDN 路由。旧独立 `services/<游戏>/start.bat`、原端口和数据目录保持可用；它们继续使用独立会话和钱包，不会自动变为商户钱包入口。

本次未完成 19 款浏览器全流程视觉验收、生产 HTTPS/CDN 验收或数学模型重新认证。原抓取证据缺口及补抓要求继续以各游戏规则文档和 `game-validation-and-resource-gaps.md` 为准。


2026-11-05 规则修正：用户确认 `[-1,0]` 表示必输、整局零派彩（上限 0 倍），包括免费、续列及收奖，不再具有“不限制”特殊含义。与 `[0,0]` 的合法派彩集合相同；找不到合法零派彩整局时保持不扣款，不放宽区间。已冻结的回合保留原结果，新计划使用修正后的规则。
