# GTT 平台控制台与商户工作台

平台后台：<http://127.0.0.1:8112/>；商户工作台：<http://127.0.0.1:8112/merchant/>。前端无需构建，源码在 `server/merchant/admin.html`、`admin.js`、`admin.css`，接口与权限在 `admin.py`、`control.py`。

## 商户接入与密钥

当前所有商户统一使用 **商户号 + GTT 自动生成的 `merchant_secret`**，游戏 API、钱包和预派彩使用相同的 HMAC-SHA256 签名规则。商户不能自行指定密钥。

密钥不需要领取，也没有启用或切换签名的流程。平台管理员可在商户列表点击“查看密钥”，商户管理员可在“我的商户 → 查看 / 复制密钥”反复查看、显示／隐藏、复制同一把密钥。查看不会修改密钥或配置版本。密钥默认以密码框遮挡显示，关闭弹窗清除页面内容；不保存到 localStorage。

“重置密钥”由 GTT 生成新值，需填写操作原因并提交当前配置版本。原密钥立即失效；管理员应同步更新商户服务端。创建、查看和重置响应只返回一把 `merchant_secret`，普通列表、概览、审计及交易接口不返回明文。预派彩仅配置开关与 URL，不再有单独 Token 或密钥。

按照用户确认，目前没有真实商户，全部本机商户直接统一，不保留旧版认证方式。升级时保留已经生成的统一密钥；缺失时自动生成。内部历史存储列会归一化，原领取状态清除，旧的预派彩凭据清空；商户号、玩家、游戏状态、钱包流水、商户启用状态、预派彩开关与 URL 均保留。

签名完整约定见 [商户与钱包接口](gtt-merchant-wallet-v1.md)，预派彩业务见 [预下注决策](gtt-prebet.md)。

## 开通商户后台

平台管理员在“商户管理 → 开通后台”可创建已绑定该商户的管理员，也可在“账户与权限 → 创建账户”选择商户角色并绑定商户。初始登录密码只在创建／重置时展示，用户可修改本人密码。这里只管理商户自身，不支持下级子商户。

| 角色 | 权限 |
| --- | --- |
| 平台管理员 `admin` | 全部商户、游戏授权、密钥查看与重置、交易恢复、审计和团队管理 |
| 平台运营 `operator` | 查看商户、游戏、交易、审计，恢复待处理交易 |
| 平台只读 `viewer` | 查看商户、游戏、交易和审计 |
| 商户管理员 `merchant_admin` | 本商户资料、钱包／预派彩接入、密钥查看与重置、交易恢复及本商户团队管理 |
| 商户运营 `merchant_operator` | 本商户概览、资料、游戏、交易、审计和待处理交易恢复 |
| 商户只读 `merchant_viewer` | 本商户概览、资料、游戏、交易和审计 |

商户数据范围由服务端每次读取的 `admin_users.merchant_id` 决定，省略筛选也不能扩大范围。伪造其他商户号返回 403；交易详情和恢复同时核对商户与操作 ID，其他商户的交易返回 404。商户不能修改自身启用状态、改变币种、扩大游戏授权、创建平台账号或操作其他商户员工。权限变更、停用和密码重置撤销旧会话，至少保留一名启用的平台管理员及每个商户的管理员。

## 登录与会话

已有环境运行 `python -m server.merchant.sandbox admin`。全新环境先运行 `python -m server.merchant.sandbox init` 和 `admin-init`。初始平台管理员密码保存在私有 `services/gtt-gateway/data/admin-bootstrap.json`，不打印到日志；已有账号时不重复初始化。

平台 `/api/admin/` 使用 `gtt_admin_session`，商户 `/api/merchant/` 使用 `gtt_merchant_session`，可同时登录且互不退出。商户入口只接受绑定商户的账号。两类会话共用认证存储，但每次请求仍按账号权限限定数据范围。

密码使用 PBKDF2-HMAC-SHA256、600,000 次迭代及独立随机盐，长度 12–128 字符。连续五次失败后，同来源与用户名组合锁定 15 分钟。Cookie 为 HttpOnly、SameSite=Strict，8 小时绝对有效期、30 分钟闲置有效期；数据库只保存 token 哈希。已登录 POST（包括密钥查看）需要 `X-GTT-CSRF`，仅接受本机 Host 和同源 Origin，不开放跨域。响应禁止缓存，页面 CSP 禁止嵌套，不把凭据保存到 localStorage。

## 商户、游戏与交易

商户号由系统分配，为 `GTT` 加 16 位大写十六进制字符，创建 API 不接受指定 ID。名称、钱包 origin、启用状态和游戏授权可配置；新商户目前仅支持 USD、100 美分精度，已有币种不可修改。钱包地址要求 HTTPS，loopback 联调允许 HTTP；不接受路径、查询、fragment 或用户名密码。

商户钱包链路当前接入 Buffalo Win，其他游戏原试玩入口保留。目标 RTP 仍为未标定，不提供未经验证的百分比设置。

交易中心可按商户、玩家、游戏、状态、操作 ID 分页查询。扣款、派彩使用整数美分与商户币种显示。详情只展示标准请求、已提交结果和元信息，不暴露候选状态、随机种子或未来牌面。

只允许恢复 prepared／debited 操作，必须填写原因。恢复复用原候选结果、操作及钱包交易号，不重新抽取结果。商户停用或授权撤销后，管理员／运营仍可恢复已受理的待处理操作；后续新游戏请求需有效启用状态及授权。当前没有自动重试线程或手工退款按钮。

概览最近七天按 UTC 日期统计已完成的游戏操作，包含续列／免费步骤，不等同于付费局数。金额仅累计 settled 的扣款和派彩，并按币种分别汇总；玩家按商户与身份去重。数据来自实际业务数据库，不填充演示曲线。

## 后台 API

所有 POST 使用 JSON，最大 16 KiB，拒绝重复键、NaN、Infinity 和 URL 查询参数。`me` 为 GET，其他接口为 POST；商户入口使用相同后缀并强制限定本商户。

| 后缀 | 主要字段 | 权限 |
| --- | --- | --- |
| `login` / `me` / `logout` | 登录字段或会话 | 登录／本人 |
| `overview` / `merchants/list` | 可选筛选 | merchants.read |
| `merchants/create` | name, enabled, wallet_url, currency, games，可选 pre_payout | merchants.write |
| `merchants/update` | id, version 及商户字段 | merchants.write |
| `merchants/profile` | id, version, name, wallet_url, pre_payout | profile.write |
| `merchants/signing/view` | id；可重复返回当前 merchant_secret，无领取状态 | keys.rotate |
| `merchants/signing/rotate` | id, version, reason；重置统一密钥 | keys.rotate |
| `merchants/rotate` | id, version, reason；同样重置唯一商户密钥 | keys.rotate |
| `games` | 无 | games.read |
| `transactions/list` / `detail` | 商户、玩家、状态、操作 ID 及分页 | transactions.read |
| `transactions/retry` | merchant_id, operation_id, reason | transactions.retry |
| `prebet/list` | merchant_id, player_id, limit | transactions.read |
| `audit` | actor, action, target, before_seq, limit | audit.read |
| `users/list` / `create` / `update` / `reset` | username, role, merchant_id, enabled 等 | users.manage |
| `password` | current_password, new_password | 本人 |

旧的领取、签名激活、分开预派彩凭据接口已移除，调用返回 404。密钥查看、重置等记录操作者、对象、原因及指纹，审计不记录明文。

## 数据与验证

- 商户配置、账号、会话、统一密钥及审计：`services/gtt-gateway/data/merchants.sqlite3`。
- 玩家游戏状态与操作：`services/gtt-gateway/data/gtt.sqlite3`。
- 模拟平台钱包：`services/gtt-mock-platform/data/platform.sqlite3`，后台不直接改余额。
- 本机演示账号：`merchant-demo`，登录密码保存在私有 `services/gtt-gateway/data/merchant-demo-bootstrap.json`。
- 数据库、备份和日志保存在 Git 忽略目录，升级前使用 SQLite 备份。

运行 `python -m unittest server.tests.test_gtt_admin server.tests.test_gtt_prebet server.tests.test_gtt_merchant -q`。开发浏览器验证脚本为忽略目录 `diagnostics/gtt_console_ui_qa.py`，使用临时数据库，验证反复查看／复制、重置、权限、桌面及手机布局，不对现有钱包做测试扣款。

2026-10-28 验收：53 项接入专项及全项目 240 项回归通过。浏览器验证重复查看同一密钥、显示／隐藏、复制、重置后立即使用、无领取／激活／旧版配置入口、团队隔离和六个手机页面。实际 2 个本机商户已直接统一，现有统一密钥、商户配置、游戏授权和预派彩开关／URL 保留；8110／8111／8112 已更新，实测统一签名、钱包余额查询、重复查看及移除接口返回 404。截图保存在 `diagnostics/gtt-console-v2/merchant-single-key.png` 和 `merchant-single-key-mobile.png`。

当前服务固定监听本机。接入费、自动对账报表、数学 RTP 标定和公网部署仍属独立后续工作。
