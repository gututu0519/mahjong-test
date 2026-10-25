# GTT 商户与平台钱包接口 v1

本规范对应 `server/merchant/` 的可运行实现，首款接入 Buffalo Win。GTT 生成游戏结果，合作平台拥有玩家账户和余额。平台钱包、GTT 游戏记录、原本的 8083 试玩服务使用三个独立数据库；GTT 商户服务不创建本地积分钱包。

## 本机启动和验收

在项目根目录首次执行：

```powershell
python -m server.merchant.sandbox init
```

此命令创建 `services/gtt-gateway/data/sandbox.json`，生成独立的接口密钥和钱包密钥，不覆盖已存在的配置。该文件被 Git 忽略。默认商户 `demo-platform`、玩家 `demo-player`、DEMO 币种和 2000 初始积分。平台启动时只补建不存在的测试账户，重启不重置余额。

分别在两个终端启动：

```powershell
python -m server.merchant.sandbox platform
python -m server.merchant.sandbox gateway
```

- 模拟平台：<http://127.0.0.1:8111/>，查看平台余额、创建中英文游戏会话、查看钱包交易。
- GTT 接入服务：`http://127.0.0.1:8110`，承载签名 API 和原版 Buffalo Win 客户端。
- 原大厅和 8083 Buffalo 试玩继续使用原来的服务与钱包。
- GTT 配置：`services/gtt-gateway/config/buffalo-win.json`，独立复制的规则配置。
- GTT 数据：`services/gtt-gateway/data/gtt.sqlite3`。
- 平台钱包：`services/gtt-mock-platform/data/platform.sqlite3`。
- 日志：各自服务目录下的 `logs/service.log`。

可在命令行创建游戏链接、查看 GTT 操作记录或恢复一笔待处理操作：

```powershell
python -m server.merchant.sandbox launch --language en
python -m server.merchant.sandbox transactions
python -m server.merchant.sandbox retry --operation-id <操作ID>
```

`--config` 可指定另一份联调配置。端口可用 `--port` 覆盖，同时应更新配置中的 `gateway_origin` 和后台商户的 `wallet_url`，两端必须一致。旧 JSON 商户配置自动迁入 `data/merchants.sqlite3`；此后通过 [GTT 管理后台](gtt-admin.md) 创建商户、分配游戏和维护密钥，运行中即时生效。玩家仍由平台账户系统建立。当前模拟页只展示指定的 `sandbox_merchant` / `sandbox_player`。

## 身份、金额及签名

商户、玩家、操作、交易、回合标识使用 1–128 位 ASCII 字母、数字和 `_ . : -`。同一 `player_id` 在不同商户下是不同玩家；玩家标识由平台给出，不接收密码、真实姓名或其他非必要个人资料。

金额一律为整数 `amount_minor`，当前 `minor_unit=100`，示例 1500 表示 15.00。币种必须与商户配置一致。模拟平台只提供 DEMO 积分。禁止浮点数、布尔值、负数和超过 `9,000,000,000,000,000` 的金额。GTT 页面余额通过平台回调取得，不以浏览器上报金额为准。

平台 → GTT 使用 `api_secret`；GTT → 平台钱包使用另一把 `wallet_secret`。两种请求均使用 POST、`Content-Type: application/json`，无 URL 查询参数。JSON 不允许重复字段、NaN 或 Infinity；请求体最多 16 KiB。

签名头：

| 字段 | 内容 |
| --- | --- |
| `X-GTT-Merchant` | 商户号 |
| `X-GTT-Timestamp` | 10 位 Unix 秒时间戳，允许前后 300 秒偏差 |
| `X-GTT-Nonce` | 每个请求重新生成的 16–64 位随机 ASCII 字母、数字、`_`、`-` |
| `X-GTT-Signature` | 以下 HMAC-SHA256 的小写十六进制结果 |

签名原文是以下五项以 LF 换行连接，末尾没有额外换行：

```text
POST
/gtt/v1/games/launch
<timestamp>
<nonce>
<SHA256(实际请求体原始字节)的小写十六进制>
```

对该原文的 UTF-8 字节使用对应方向密钥计算 HMAC-SHA256。请求方可任意排版 JSON，但签名必须使用实际发送的原始字节。接收方使用恒定时间签名比较，并将已使用 nonce 持久化；nonce 重用返回 `AUTH_REPLAY`。交易重试使用**新时间戳、新 nonce、新签名、相同交易号及相同业务参数**，不能重复发送同一份签名头。

Python 参考代码可复用 `server.merchant.common.signed_headers`；生产平台应按规范独立实现。密钥仅在服务端保存，不放入浏览器、游戏链接、日志或仓库。钱包回调只允许 HTTPS，或本机联调的 loopback HTTP；不跟随重定向。

## 平台 → GTT

所有 `/gtt/v1/` 接口要求商户签名。

| 路径 | 请求 JSON | 成功结果 |
| --- | --- | --- |
| `/gtt/v1/games/list` | `{}` | 本商户已启用游戏、引擎和规则版本 |
| `/gtt/v1/games/launch` | `{"player_id":"demo-player","game_id":"buffalo-win","language":"en"}` | 游戏链接、到期时间、平台余额、币种 |
| `/gtt/v1/transactions/list` | `{"after_seq":0,"limit":100}` | 本商户游戏操作，含状态、对应钱包交易号和已结算结果 |
| `/gtt/v1/transactions/retry` | `{"operation_id":"..."}` | 恢复同一操作或返回已保存结果 |

列表 `limit` 为 1–100，按 `seq` 升序，以末条 `seq` 作为下一页 `after_seq`；不同商户互不可见。恢复接口返回 404 时，不披露另一个商户是否存在该操作。

启动前 GTT 向平台查询玩家余额，平台不存在的账户不能启动游戏。`launch_url` 为 GTT 服务上的相对地址，平台拼接可信的 GTT origin；不要对外分享链接中的短期会话凭据。会话有效期 24 小时，绑定商户、玩家和游戏，同一身份的多次进入恢复同一游戏状态。

GTT 继续兼容原版 Buffalo GameInfo / Spin 协议，购买仍使用 `fb=2`。浏览器只持有游戏会话，不能调用签名商户接口或直接修改平台钱包。通用 Spin 也可使用 Bearer 游戏会话请求 `/api/v1/games/buffalo-win/spin`，携带 `Idempotency-Key` 和 `{"previous_sid":"0","bet":{"coin_minor":2,"level":1,"buy_free":true}}`。

`/api/v1/sessions` 和原试玩的匿名 launch 不在此服务中发放游客余额，需走签名商户启动；原本各试玩服务不受影响。

## GTT → 平台钱包

以下接口是平台应实现的契约，模拟平台已实现；全部要求对应商户的 `wallet_secret` 签名。共同字段是 `player_id`、`currency`、`minor_unit`。

| 路径 | 追加字段 | 含义 |
| --- | --- | --- |
| `/wallet/v1/balance` | 无 | 读取平台玩家余额 |
| `/wallet/v1/debit` | `transaction_id`, `round_id`, `amount_minor` | 扣除一次投注或免费购买成本 |
| `/wallet/v1/credit` | 同上及 `reference_id` | 向对应投注回合发放奖金 |
| `/wallet/v1/refund` | 同上及 `reference_id` | 撤销尚无成功派奖的原扣款，或建立取消标记 |
| `/wallet/v1/transactions/get` | `transaction_id` | 查询指定玩家的交易，未知交易返回空列表 |
| `/wallet/v1/transactions/list` | 可选 `limit` | 查询指定玩家最近 1–100 条交易 |

例如基础投注 0.20、75 倍购买的扣款请求：

```json
{"player_id":"demo-player","currency":"DEMO","minor_unit":100,"transaction_id":"<operation_id>:debit","round_id":"<round_id>","amount_minor":1500}
```

成功余额对象：

```json
{"data":{"player_id":"demo-player","currency":"DEMO","minor_unit":100,"balance_minor":198500},"error":null}
```

成功变动对象额外返回 `transaction_id`、`status:"applied"`、`amount_minor`、`applied_minor`、`balance_before_minor`。`balance_minor = balance_before_minor ± applied_minor` 必须成立。扣款和派奖的 `applied_minor` 必须等于请求金额；退款可能为 0，表示没有找到已成功扣款，但已阻止原交易迟到扣款。错误、畸形或不一致的成功响应被视为结果未知，不能据此再次生成结果或换交易号重扣。

平台须在同一数据库事务中完成余额更新和去重记录。同一商户下交易号全局唯一，不能因不同玩家或操作类型复用；相同参数重试返回原始结果，参数不同返回 `TRANSACTION_CONFLICT`。不足余额的拒绝也持久化，同一交易号不能在之后余额充足时突然扣款。

一笔 GTT 游戏操作对应最多一笔扣款 `operation_id:debit` 和一笔派奖 `operation_id:credit`。续列与免费不再扣款；免费和续列的派奖 `reference_id` 指向最初付费回合的 `round_id:debit`。购买免费同样适用，平台不应将每次续列当作新投注。

退款必须核对原交易玩家、币种、回合和金额，不能跨商户、跨玩家退款；已经成功派奖的回合不允许用此简单退款接口撤销。一次扣款最多成功退一次。若原扣款尚未到达，必须先持久化原交易号的取消标记，之后迟到的扣款返回 `TRANSACTION_CANCELED`。GTT 游戏流程不会在超时后自动退款；此阶段提供退款契约和模拟实现，人工取消工作流后续另行接入。

## 错误与恢复

商户及钱包接口统一为 `{"data":null,"error":{"code":"...","message":"..."}}`，成功时 `error:null`。原版游戏兼容接口继续使用其原有 `dt/err` 报文。

| HTTP / code | 处理 |
| --- | --- |
| 401 `AUTH_INVALID` | 商户、签名、时间戳无效，核对配置 |
| 409 `AUTH_REPLAY` | 重新生成 nonce 和签名 |
| 403 `GAME_FORBIDDEN` | 商户未启用该游戏 |
| 409 `INSUFFICIENT_BALANCE` | 已明确拒绝，游戏状态不推进 |
| 409 `TRANSACTION_CONFLICT` / `IDEMPOTENCY_CONFLICT` | 同一标识对应不同参数，停止该冲突请求 |
| 409 `STALE_STATE` | 读取最新游戏状态 |
| 409 `OPERATION_PENDING` | 先恢复该玩家游戏的待处理操作 |
| 503 `WALLET_UNCERTAIN` | 保留操作及交易号，重试或查询恢复 |

GTT 操作状态为 `prepared → debited → settled`，无扣款步骤可直接从 `prepared → settled`；明确拒绝扣款为 `rejected`。GTT 在调用平台前先保存完整候选游戏结果和下一步状态，不提前发布新局面。确认扣款后保存其回执，确认派奖后才提交游戏状态；同一玩家游戏存在待处理操作时不接受另一笔新操作。HTTP 超时、丢失响应、进程重启都从保存的结果继续，不重新抽取牌面。

玩家读取状态时会尝试恢复待处理操作，也可由平台调用签名 retry 接口。当前恢复由请求触发，没有后台定时工作线程；平台停机时待处理记录保留，平台恢复后重试。仍使用原始规则版本的候选结果，重试不要求重算该版本引擎。

平台余额是真实来源。GTT 操作结果内的钱包前后余额是各回调时的快照；若平台同时发生其他交易，不应将 GTT 某次操作两个快照当作平台全局余额连续性证明。对账应逐一匹配商户、玩家、回合、交易号、金额与终态。

## RTP 配置与本阶段范围

游戏目录返回 `target_rtp:null, rtp_status:"not_calibrated"`。当前配置沿用已有 Buffalo 本地权重，尚未标定 RTP，不提供一个未经验证的百分比。后续商户可绑定经过计算、仿真和版本验证的游戏配置；总体实际 RTP 需要按已结算投注与派奖统计，并明确未结束回合的口径。

本阶段已实现数据库多商户配置、密钥、授权和隔离，签名协议，平台钱包联调，Buffalo 原客户端启动及交易恢复。管理后台已实现登录及三类角色、商户维护、游戏授权、密钥轮换、交易查询／恢复和审计，端口 8112，见 [管理后台说明](gtt-admin.md)。停用商户及撤销游戏授权会阻止后续游戏请求；管理员／运营仍可恢复已受理的待处理交易，模拟钱包接受其有效签名。接入费计费、自动对账差异报表、后台重试线程及其他游戏的商户接入仍属后续工作；本机服务固定监听 loopback。

## 验证

```powershell
python -m unittest server.tests.test_gtt_merchant -v
```

覆盖签名篡改、nonce 重放、过期签名、商户禁用与游戏权限、JSON 参数检查、同名玩家跨商户隔离、并发钱包重试、退款及迟到扣款、完整 25 步购买免费回合、双方账单金额核对，以及“平台已扣／已派，但响应丢失或畸形”后的重启恢复。固定抓取牌面仅在离线测试中注入；运行服务使用随机生成引擎。

2026-10-25 验收：全项目 193 项回归通过，补充后的商户专项 7 项通过，包括 GTT 并发重试只生成一次结果、余额不足不推进以及启动凭据日志脱敏。浏览器从模拟平台签名创建会话后，原版英文客户端完成一次购买免费：平台初始 2000.00，购买扣款 450.00，10 次免费累计派奖 133.20，游戏及平台最终余额均为 1683.20。GTT 保存 19 步已结算游戏操作；平台账本为 1 笔扣款、3 笔派奖，金额一致。该本地随机回合仅用于接口联调，不能用于推断 RTP。验收截图为忽略目录 `diagnostics/gtt-platform-wallet.png`。
