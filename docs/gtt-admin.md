# GTT 管理后台 v1

后台独立监听 <http://127.0.0.1:8112/>，前端无需构建和第三方依赖。实现位于 `server/merchant/control.py`、`admin.py`、`admin.html`、`admin.css`、`admin.js`。原游戏大厅与全部独立试玩入口保留。

## 启动与首次登录

已有 `services/gtt-gateway/data/sandbox.json` 时，在仓库根目录执行：

```powershell
python -m server.merchant.sandbox admin-init
python -m server.merchant.sandbox admin
```

全新环境需先运行 `python -m server.merchant.sandbox init`。默认用户名 `admin`，支持 `--username`；随机密码写入私有 `services/gtt-gateway/data/admin-bootstrap.json`，不打印到日志或提交到 Git。已有管理账户或凭据文件时拒绝重复初始化。

网关与模拟平台仍使用 `python -m server.merchant.sandbox gateway` / `platform`，端口 8110 / 8111。升级这版代码时需要重启这两个旧进程，使其使用数据库商户目录；之后后台修改商户无需重启服务。后台可独立查看数据，恢复交易需要平台钱包可用。

## 账户、会话与权限

| 能力 | 管理员 admin | 运营 operator | 只读 viewer |
| --- | --- | --- | --- |
| 查看概览、商户配置、游戏、交易、审计 | 是 | 是 | 是 |
| 创建／编辑／停用商户、分配游戏 | 是 | 否 | 否 |
| 轮换接入及钱包密钥 | 是 | 否 | 否 |
| 恢复待处理游戏交易 | 是 | 是 | 否 |
| 创建账户、修改角色、停用、重置密码 | 是 | 否 | 否 |
| 修改本人密码、退出 | 是 | 是 | 是 |

权限由服务端逐请求验证。角色／启用状态变更、密码修改／重置会增加认证版本，立即撤销该账户全部旧会话。始终保留至少一名启用的管理员。

密码采用 PBKDF2-HMAC-SHA256、600,000 次迭代、独立随机盐，长度 12–128 字符。登录错误不区分不存在／密码错误／停用；同来源地址与用户名组合连续 5 次失败后锁定 15 分钟。Cookie 为 `HttpOnly; SameSite=Strict; Path=/`，8 小时绝对有效期、30 分钟闲置有效期；数据库仅存 Cookie token 的 SHA256。所有已登录 POST（包括查询）还需 `X-GTT-CSRF`，CSRF token 只在前端内存中保存。页面使用同源 CSP、禁止嵌套、禁用缓存，不在 localStorage 保存凭据。

## 商户维护与迁移

创建商户时，商户号由系统自动生成，无需填写；保存后在商户列表及接入凭据弹窗中显示。格式为 `GTT` 加 16 位大写十六进制字符，由后端在写事务中分配并检查唯一性，碰撞时重试，数据库主键同时保证唯一。创建 API 不接受客户端指定 `id`；修改商户时仍使用已有 `id`，商户号不可变。旧商户号、会话及历史交易保持不变。

可设置展示名称、启用状态、钱包 origin、币种及游戏授权。创建商户的币种使用下拉框，目前仅提供美元（USD），默认选中 USD；后端也仅允许新建 USD 商户，API 省略币种时默认 USD。金额精度固定为 100（美分），创建后币种不可改变。旧 DEMO 商户保留原币种、余额及流水，不自动换算或改写。钱包地址要求 HTTPS，loopback 联调可用 HTTP；不接受路径、查询、fragment、用户名密码。

创建商户和轮换密钥后，仅该次响应返回 `api_secret` / `wallet_secret`，关闭弹窗后清除凭据内容。普通查询和审计只显示密钥版本及指纹。轮换同时更换两种密钥，要求填写原因；旧密钥立即失效，合作平台需同步更新。此版没有旧密钥过渡窗口。编辑和轮换必须携带当前 `version`，避免覆盖其他操作者刚保存的设置。

旧 JSON 的 `merchants` 首次启动时使用 `INSERT OR IGNORE` 迁入 `services/gtt-gateway/data/merchants.sqlite3`，原私有文件保存为 `sandbox.before-admin.json`。迁移后 JSON 仅保存数据库路径和联调参数，不再保存密钥。重启读取数据库，不覆盖新设置；重新导入旧备份也不会覆盖同 ID 的现有商户。旧备份、初始凭据和数据库仍含敏感信息，均在 Git 忽略的本机私有目录内。

网关、后台和模拟平台通过 `MerchantDirectory` 每次读取最新记录，不缓存密钥与授权。停用商户会阻止新的签名 GTT 接入及游戏请求；移除游戏授权会阻止后续启动和旋转。已有状态继续保存，重新启用可继续。

商户钱包链路首批接入 Buffalo Win。其他 18 款游戏的原试玩入口和资源仍在，尚未统一接入这条钱包链路。游戏目标 RTP 为 `null / not_calibrated`，后台不提供未经标定的百分比设置。

## 交易查询与恢复

平台预派彩可在商户编辑中配置；交易中心提供“预下注决策”查询。GTT 接入方向、区间、购买免费基数和重试规则见 [GTT 预下注决策](gtt-prebet.md)。

按商户、玩家、游戏、状态、操作 ID 查询，以 `seq` 降序游标分页；界面每页 25 条，API 上限 100。扣款与派彩分别按商户币种显示，两位小数、与平台钱包 1:1 对应，无汇率、兑换比例或额外派彩系数。例如 `1500` 最小单位显示 `15.00 USD`，平台入账同为 `15.00 USD`。概览最近交易、交易详情摘要和恢复确认页使用同一金额格式，采用整数运算避免大额分币误差。旧 DEMO 交易继续标记 DEMO，不改写为 USD。内部流水和钱包协议仍使用整数最小单位，后台 API 补充 `currency` / `minor_unit`；若商户记录缺失则返回 null，页面明确显示原始最小单位，不猜测币种。详情仅返回标准请求、已提交结果与元信息，不暴露内部随机种子、候选下一步状态或密钥。操作 ID 输入支持 `:debit` / `:credit` 后缀。

只允许恢复 `prepared` / `debited`，须填写 4–300 字原因。后台先持久化申请审计，再调用原 `MerchantService.retry`，最后记录成功或失败。复用候选结果、操作 ID 和钱包交易 ID，不重新抽取结果、不手工改余额。已完成／已拒绝的交易返回 `NOT_PENDING`，不能通过恢复变更终态。

商户停用或游戏授权移除后，管理员和运营仍可恢复**已受理**的待处理交易；只有后台恢复路径允许停用商户。模拟钱包继续接受正确签名的结算。真实平台须保留相应结算权限；若钱包拒绝或离线，操作保留待处理并记录失败，修复后再恢复。尚未开始的后续免费旋转仍需启用商户及游戏权限。此版没有自动重试线程、手工派彩、取消／退款按钮。

## 后台 API

统一前缀 `/api/admin/`，使用 `{data,error}` 信封。不接受 URL 查询参数，JSON 最大 16 KiB，拒绝重复 key、NaN、Infinity；仅接受本机 Host 及同源 Origin，不开放跨域。

| 方法与后缀 | 主要请求字段 | 权限 |
| --- | --- | --- |
| POST `login` | username, password | 无会话 |
| GET `me` | 无 | 会话 |
| POST `overview` | 无 | merchants.read |
| POST `merchants/list` | 无 | merchants.read |
| POST `merchants/create` | name, enabled, wallet_url, currency, games，可选 pre_payout；返回 merchant.id，不接受指定 id | merchants.write |
| POST `merchants/update` | id, name, enabled, wallet_url, currency, games, version，可选 pre_payout；已有币种不可改变 | merchants.write |
| POST `merchants/rotate` | id, version, reason | keys.rotate |
| POST `games` | 无 | games.read |
| POST `transactions/list` | 可选 merchant_id, player_id, game_id, status, operation_id, before_seq, limit | transactions.read |
| POST `transactions/detail` | operation_id，可选 merchant_id | transactions.read |
| POST `transactions/retry` | merchant_id, operation_id, reason | transactions.retry |
| POST `prebet/list` | 可选 merchant_id, player_id, limit；只读预下注决策，不返回未来结果 | transactions.read |
| POST `audit` | 可选 actor, action, target, before_seq, limit；精确匹配 | audit.read |
| POST `users/list` | 无 | users.manage |
| POST `users/create` | username, role | users.manage |
| POST `users/update` | username, role, enabled | users.manage |
| POST `users/reset` | username | users.manage |
| POST `password` | current_password, new_password | 本人会话 |
| POST `logout` | 无 | 本人会话 |

静态文件仅允许 `/`、`/admin.js`、`/admin.css`；`/health` 无需认证。日志不记录请求体、Cookie、密码或密钥；审计记录操作者、时间、类型、对象、结果及不含凭据的配置变化。

## 数据归属与范围

- `services/gtt-gateway/data/merchants.sqlite3`：商户配置、密钥、账户、会话、登录限制及审计；三个进程共用。
- `services/gtt-gateway/data/gtt.sqlite3`：玩家游戏状态、候选结果及操作；后台恢复通过相同服务结算。
- `services/gtt-mock-platform/data/platform.sqlite3`：平台余额与钱包交易，后台不直接写入。
- `services/gtt-admin/logs/service.log`：后台进程日志。

当前仅为本机后台，不直接暴露公网；尚无 HTTPS 终止、MFA、企业身份集成、跨机器部署、外部不可变审计存储或加密密钥托管。本机 Cookie 因 HTTP 不带 Secure，密钥数据库与备份依赖本机文件访问保护。对外部署需先补齐这些运行条件。

接入费计费、账单、自动对账差异报表、数学 RTP 标定和商户规则版本绑定仍是后续工作。

## 验证

```powershell
python -m unittest server.tests.test_gtt_admin server.tests.test_gtt_merchant -v
python -m unittest discover -s server/tests -v
```

后台专项覆盖登录锁定、会话过期／撤销、密码哈希、Cookie／CSRF／Origin／Host、三类角色越权、一次性密钥、运行中授权更新、密钥轮换、版本冲突、参数验证、停用商户后的幂等恢复、失败审计、交易隔离与分页、末名管理员保护、静态文件访问范围和旧配置迁移。

2026-10-25：后台与商户专项 18 项通过，全项目 205 项通过。浏览器验收与截图记录在 `diagnostics/`。

2026-10-25 USD 币种调整：后台与商户专项 20 项通过，覆盖新建商户仅接受 USD、默认 USD、USD 钱包启动及扣款、旧 DEMO 数据兼容和新环境初始化。浏览器已确认创建表单仅有“美元（USD）”选项，截图 `diagnostics/gtt-merchant-usd.png`。

2026-10-25 商户号自动生成：后台与商户专项 21 项通过，包括后端分配商户号、拒绝指定 ID、碰撞重试及耗尽回滚、并发唯一性、审计目标一致性和生成商户的钱包全流程。浏览器已确认商户号字段不可填写、显示“保存后自动生成”，截图 `diagnostics/gtt-merchant-auto-id.png`。

2026-10-25 商户币种金额显示：后台与商户专项 22 项通过，验证 USD 派彩 `20400` 美分与平台实际入账相等（204.00 USD）、混合 USD / DEMO 查询及详情、概览币种一致，以及缺失商户记录时不猜测币种。另通过 10 项前端金额校验，覆盖 0、1 分、99 分、整元、普通派彩和金额上限附近，均无浮点分币误差。浏览器已验收交易列表和详情摘要，截图 `diagnostics/gtt-transactions-currency.png`。

2026-10-25 按用户明确要求，将本机 `demo-platform` 从 DEMO 一次性迁移为 USD，金额按 1:1 保留：玩家余额为 `167720` 美分，即 `1677.20 USD`。同步更新该商户 1 个平台账户、5 笔钱包交易的请求／回执币种，以及 2 个游戏扣款回执；20 条游戏记录、局面、交易号、密钥和金额保持不变。普通后台编辑的币种不可变约束仍保留，此次不开放通用换币功能。迁移前的三个数据库备份位于私有忽略目录 `services/gtt-gateway/data/before-usd-20261025T150837127229Z/`，审计操作为 `merchant.currency.migrate`。已在副本验证迁移幂等、5 笔钱包交易重试不重复扣款／派彩、20 条已结算游戏操作重试结果一致，并通过真实服务余额查询及签名启动验证。此前关于旧 DEMO 数据不自动转换的规则仍适用于其他未明确迁移的历史商户。
