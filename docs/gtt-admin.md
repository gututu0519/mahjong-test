# GTT 平台控制台与商户工作台

平台后台：<http://127.0.0.1:8112/>；商户工作台：<http://127.0.0.1:8112/merchant/>。前端无需构建，源码在 `server/merchant/admin.html`、`admin.js`、`admin.css`，接口与权限在 `admin.py`、`control.py`。

## 商户接入与密钥

当前所有商户统一使用 **商户号 + GTT 自动生成的 `merchant_secret`**，游戏 API、钱包和预派彩使用相同的 HMAC-SHA256 签名规则。商户不能自行指定密钥。

密钥不需要领取，也没有启用或切换签名的流程。平台管理员可在商户列表点击“查看密钥”；商户管理员可直接从侧栏“接入中心”、概览中的同名按钮进入，也可在“我的商户”查看接入凭据。直接链接为 `/merchant/#integration`。页面明确显示 `merchant_secret · 64 个字符`，可显示完整密钥、隐藏和复制；展开后的文本框换行展示全部字符，复制保持原始字符串。平台列表的 12 字符摘要明确标为“指纹”，不是接入密钥。

查看不会修改密钥或配置版本。密钥默认遮挡显示，关闭弹窗或离开凭据页面时移除相应控件，不保存到 localStorage。商户运营／只读账号仍不能读取密钥，接入页提示使用商户管理员账号。

“重置密钥”由 GTT 生成新值，需填写操作原因并提交当前配置版本。原密钥立即失效；管理员应同步更新商户服务端。创建、查看和重置响应只返回一把 `merchant_secret`，普通列表、概览、审计及交易接口不返回明文。预派彩仅配置开关与 URL，不再有单独 Token 或密钥。

按照用户确认，目前没有真实商户，全部本机商户直接统一，不保留旧版认证方式。升级时保留已经生成的统一密钥；缺失时自动生成。内部历史存储列会归一化，原领取状态清除，旧的预派彩凭据清空；商户号、玩家、游戏状态、钱包流水、商户启用状态、预派彩开关与 URL 均保留。

签名完整约定见 [商户与钱包接口](gtt-merchant-wallet-v1.md)，预派彩业务见 [预下注决策](gtt-prebet.md)。

## 接入中心与开发者文档

品牌统一使用大写 **GTT**。商户侧栏“接入中心”（`/merchant/#integration`）上方集中展示商户号、64 字符统一密钥、当前配置的 GTT API origin，以及指南／OpenAPI 下载入口。下方提供九章在线规范：接入准备、签名与验签、游戏启动、钱包回调、幂等结算、预下注决策、操作恢复、错误处理、联调验收。

文档和下载文件由 `server/merchant/integration_docs.py` 同一份结构化契约生成，包含 11 项接口的请求／响应字段、约束、JSON 示例、Python／Node.js 调用代码及固定签名测试向量。示例只使用虚构标识和专用测试密钥，不将当前商户密钥写入文档、代码块或下载文件。文档目录可键盘操作；代码支持复制；桌面采用目录与正文布局，手机使用单列和局部滚动代码／表格。

- `POST /api/merchant/integration/docs`：在线文档，需要会话、CSRF 和 `merchants.read`。
- `GET /api/merchant/integration/guide.md`：Markdown 指南附件。
- `GET /api/merchant/integration/openapi.json`：OpenAPI 3.1 JSON 附件，可导入 API 工具；HMAC 仍按指南计算。
- 平台 API 命名空间提供相同后缀，下载也需要会话及 `merchants.read`，响应禁止缓存。没有任意文件下载入口。

商户运营和只读账号可以阅读／下载文档，仍无权获取真实密钥。GTT origin 由服务配置传入；钱包与预派彩的 OpenAPI server 使用明确的示例域名，需替换为商户地址。当前本机监听、游戏接入范围、未绑定模型时 RTP 未标定、无后台自动重试和自动对账等边界在指南中如实说明。

## 开通商户后台

创建商户时自动创建主账号，使用唯一商户名称登录；初始密码与接入密钥一起展示。平台管理员可在“商户管理 → 添加成员”或“账户与权限 → 创建账户”增加绑定商户的团队成员。商户改名后主账号改用新名称和原密码，商户号与接入密钥不变。初始登录密码只在创建／重置时展示，用户可修改本人密码。这里只管理商户自身，不支持下级子商户。

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

密码使用 PBKDF2-HMAC-SHA256、600,000 次迭代及独立随机盐，长度 12–128 字符。连续五次失败后，同来源与用户名组合锁定 15 分钟。Cookie 为 HttpOnly、SameSite=Strict，8 小时绝对有效期、30 分钟闲置有效期；数据库只保存 token 哈希。已登录 POST（包括密钥查看）需要 `X-GTT-CSRF`，本机模式仅接受本机 Host 和同源 Origin；生产模式校验配置域名、可信 loopback HTTPS 代理及同源 Origin，不开放跨域。响应禁止缓存，页面 CSP 禁止嵌套，不把凭据保存到 localStorage。

## 商户、游戏与交易

商户号由系统分配，为 `GTT` 加六位数字，从 `GTT000001` 按顺序递增，编号不回收、不复用，创建 API 不接受指定 ID。名称、钱包 origin、启用状态和游戏授权可配置；新商户目前仅支持 USD、100 美分精度，已有币种不可修改。钱包地址要求 HTTPS，loopback 联调允许 HTTP；不接受路径、查询、fragment 或用户名密码。

商户钱包链路当前接入 Buffalo Win，其他游戏原试玩入口保留。RTP 中心支持平台默认、商户及玩家目标与实际返还率；只有通过验证并发布的模型可配置。操作与统计口径见 [RTP 模块](gtt-rtp.md)。

交易中心可按商户、玩家、游戏、状态、操作 ID 分页查询。扣款、派彩使用整数美分与商户币种显示。详情只展示标准请求、已提交结果和元信息，不暴露候选状态、随机种子或未来牌面。

只允许恢复 prepared／debited 操作，必须填写原因。恢复复用原候选结果、操作及钱包交易号，不重新抽取结果。商户停用或授权撤销后，管理员／运营仍可恢复已受理的待处理操作；后续新游戏请求需有效启用状态及授权。当前没有自动重试线程或手工退款按钮。

概览最近七天按 UTC 日期统计已完成的游戏操作，包含续列／免费步骤，不等同于付费局数。金额仅累计 settled 的扣款和派彩，并按币种分别汇总；玩家按商户与身份去重。数据来自实际业务数据库，不填充演示曲线。

## 后台 API

所有 POST 使用 JSON，最大 16 KiB，拒绝重复键、NaN、Infinity 和 URL 查询参数。`me` 为 GET，其他接口为 POST；商户入口使用相同后缀并强制限定本商户。

| 后缀 | 主要字段 | 权限 |
| --- | --- | --- |
| `login` / `me` / `logout` | 登录字段或会话 | 登录／本人 |
| `integration/docs` | 在线接入文档，无真实凭据 | merchants.read |
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
- 本机演示主账号使用商户名称 `demo-platform` 登录，登录密码保存在私有 `services/gtt-gateway/data/merchant-demo-bootstrap.json`。
- 数据库、备份和日志保存在 Git 忽略目录，升级前使用 SQLite 备份。

运行 `python -m unittest server.tests.test_gtt_admin server.tests.test_gtt_prebet server.tests.test_gtt_merchant -q`。开发浏览器验证脚本为忽略目录 `diagnostics/gtt_console_ui_qa.py`，使用临时数据库，验证反复查看／复制、重置、权限、桌面及手机布局，不对现有钱包做测试扣款。

2026-10-28 验收：53 项接入专项及全项目 240 项回归通过。浏览器验证重复查看同一密钥、显示／隐藏、复制、重置后立即使用、无领取／激活／旧版配置入口、团队隔离和六个手机页面。实际 2 个本机商户已直接统一，现有统一密钥、商户配置、游戏授权和预派彩开关／URL 保留；8110／8111／8112 已更新，实测统一签名、钱包余额查询、重复查看及移除接口返回 404。截图保存在 `diagnostics/gtt-console-v2/merchant-single-key.png` 和 `merchant-single-key-mobile.png`。

后端服务固定监听本机；已准备生产域名与 HTTPS 反向代理配置，实际公网部署见部署说明。接入费、自动对账报表仍属独立后续工作。RTP 已实现完整回合统计、模型标定和版本绑定，尚不代表第三方数学认证。

2026-10-28 接入中心验证：新增测试执行 Python／Node.js 固定签名向量，检查 OpenAPI 引用、接口覆盖、鉴权下载、无真实密钥和只读权限；浏览器验证九章目录、11 项接口、代码复制、两种附件下载及桌面／390px 手机布局。截图为 `diagnostics/gtt-console-v2/merchant-integration-center.png`、`merchant-integration-signatures.png`、`merchant-integration-mobile.png`。

## 顺序编号与已有商户迁移

GTT 对接游戏编号在 `server/merchant/identifiers.py` 显式分配：Buffalo Win 为 1，其余已登记游戏按顺序保留编号，后续只追加、不重排。编号登记不代表已经开通钱包链路，授权目录仍只列实际接入游戏。引擎代码与原版客户端路径保留，GTT 接口与后台展示使用数字 ID；启动的 `game_id` 不接受字符串、布尔值或浮点数。

商户号为 `GTT000001` 至 `GTT999999`，由持久化计数器在写事务中顺序分配；并发创建不重复，删除后不复用。商户名称须唯一，用于商户主账号登录，商户号用于接口请求头。团队成员继续使用独立登录名。已有主账号保留密码和用户 ID；主账号角色／停用变更时仍须保留其他启用管理员。

升级已有环境时先停止 8110／8111／8112，再运行 `python -m server.merchant.sandbox migrate-identifiers`。该命令备份三库及改变的私有配置，使用 SQLite 附加数据库和 DELETE 超级日志事务更新主键、外键、会话、nonce、游戏状态、操作、钱包、退款取消、预派彩、审计作用域及 JSON 中的商户元信息。不会改动玩家标识、钱包金额、业务交易号、游戏结果或 merchant_secret。提交后恢复 WAL。映射记录在 `merchant_id_migrations`，重跑不再次编号；接口不接受旧商户号作为别名。

联调配置的 `sandbox_merchant` 和私有登录文件同步更新。此前没有管理员的商户会补建主账号，初始密码只写入私有 `merchant-GTTxxxxxx-bootstrap.json`；命令输出仅包含编号映射、备份路径和凭据文件路径，不输出密码或密钥。启动服务前可用三个数据库的 `PRAGMA foreign_key_check` 检查关联完整性。

2026-10-28 顺序编号验收：64 项接入专项回归通过；补充验证主账号资料在同一事务中返回正确登录名，6 项相关回归通过。已对本机数据库副本演练并完成实际迁移：`demo-platform → GTT000001`，`GTTBAECD72516D4C449 → GTT000002`（商户名称 `test`）。原 20 条操作、全部既有游戏状态、余额、密钥和账号密码保持一致，三库外键检查通过。两个商户均已按名称登录，数字游戏 1 启动成功，旧商户号验签失败。已有 `test` 商户此前没有账号，补建凭据位于私有 `services/gtt-gateway/data/merchant-GTT000002-bootstrap.json`。后台、商户页、游戏目录和接入文档桌面／手机浏览器验证通过，截图为 `diagnostics/gtt-console-v2/merchant-number-profile.png`、`merchant-numeric-game-id.png`、`merchant-number-integration.png`、`merchant-number-mobile.png` 和 `platform-sequential-merchants.png`。

## 生产域名与 HTTPS 部署

正式配置和操作步骤见 [gttgames.com 部署目录](../deploy/gttgames/README.md)。`merchant.gttgames.com` 根路径识别为商户工作台，`admin.gttgames.com` 根路径识别为平台控制台，通过只含公开信息的 `GET /deployment.json` 配置入口和跳转。相反后台的 API 在域名边界返回 404；生产会话名增加 `__Host-` 前缀，并设置 Secure、HttpOnly、SameSite=Strict、Path=/，不设置 Domain。Nginx 覆盖代理头，后端只信任 loopback 代理，并以真实客户端 IP 执行已有登录限流。

生产配置分开指定 API origin 和 play origin，文档、Markdown、OpenAPI 示例和启动响应同步使用配置地址；本机开发保留相对游戏链接和原会话。生产服务从 `/var/lib/gtt` 读取两库，日志写 `/var/log/gtt`，不加载模拟商户、不启动 8111。原版游戏客户端素材不在 Git 中，发布工具会携带必要素材并生成 SHA256 清单，同时排除数据库、日志、测试与私有抓取。

本次使用隔离临时数据库和本机测试证书验证了 Nginx 1.30.6 配置、HTTPS 代理、两类后台登录、Secure Cookie、跨域拒绝、签名原文不变、完整 play 链接、玩家余额／投注和原版客户端 GameInfo。测试未修改公共 DNS、未签发真实证书、未向公网部署。systemd 单元已准备，需在目标 Linux 机器执行 `systemd-analyze verify` 后安装。
