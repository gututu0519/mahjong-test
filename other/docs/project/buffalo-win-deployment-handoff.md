# 美洲野牛部署交接：从交付包到玩家第一次旋转

**交接日期：2026-11-25。** 本文针对 `buffalo-win`（游戏 ID `1`）、同机部署的网关/后台/计算服务及当前的双 CloudFront 分配。已有环境先看第 1 节，不必重建 AWS。其他游戏可沿用版本和部署原则，但不要直接套用美洲野牛的游戏 ID、端口、HTML 发布白名单或边缘路由。

## 1. 接手时先看：用什么包，做到哪一步

| 组件 | 本次配套产物（相对仓库根目录） | 去哪里 |
|---|---|---|
| 网关 | `update/gateway/gateway-gtt-node-20261125-gateway-trial-gameinfo.zip` | EC2 网关目录。含试玩及最新 GameInfo 修复 |
| 平台管理后台 | `update/admin/admin-gtt-node-20261125-admin-trial.zip` | EC2 后台目录。含游戏目录、发布弹窗、试玩邀请 |
| 游戏前端 | `update/game-buffalo-win/buffalo-win-client-v1.1/` | 浏览器素材；已通过发布工具上传，不传到计算服务目录 |
| 游戏计算服务 | `update/game-buffalo-win/buffalo-win-serve-v1.2.zip` | EC2 的 `games/buffalo-win/v1.2/`，ZIP 根即 `package.json` |

**已确认：** 前端 `v1.1` 的 382 个公开文件已完成 S3 发布校验；业务 CDN 上的版本清单与入口 HTML 已实测 HTTP 200，HTML 摘要与清单一致。服务器曾成功启动 `buffalo-win-v1.2`。玩家域名已能访问到网关，无令牌请求返回 `401 SESSION_INVALID`；玩家域名下的 `local-auth-bootstrap.js` 已能返回 JS。

**最后的待办：部署修复版网关，用新试玩会话完成线上首局复验。** 线上曾出现 `GameInfo/Get` 或 `Spin` 失败。已本地复现并修复一处问题：试玩回合结算记录缺少规则标识，后续读取可能失败；旧记录可从对应结算响应恢复。SQLite 和独立 PostgreSQL 均通过“会话验证 → GameInfo → Spin → 再取 GameInfo”的 HTTP 回归。**尚无证据表明修复包已部署到生产或线上首局已通过**；个别 PNG 的 403 也不能算作已解决。弹性 IP 的释放与此修复无关。

## 2. 先分清四条链路

| 用途 | 入口和去向 |
|---|---|
| 管理 | `admin.gttgames.com` → 业务 CloudFront → ALB → Nginx → 后台 `8112`。`merchant.gttgames.com` 是商户工作台 |
| 商户发起正式游戏 | 商户服务端签名请求 `api.gttgames.com/gtt/v1/games/launch` → 网关 `8110` → 返回个人 `launch_url`。试玩邀请由 `play.gttgames.com/trial/<邀请>` 兑换，不能把跳转后的个人链接分享给别人 |
| 发布素材 | `play.gttgames.com/releases/buffalo-win/v1.1/…` → 业务 CloudFront → 私有 S3。`_gtt-manifest.json` 是公开版本清单，`index.html` 是未注入玩家信息的模板 |
| 玩家游玩 | `fe-v1-1-g1-g1.play.gttgames.com` → 玩家 CloudFront。首页、会话、游戏 API 回源网关；静态文件按域名改写到 S3 的对应游戏/版本。网关在会话鉴权后获取入口模板，按发布清单校验大小和 SHA-256，再注入会话。游戏操作由网关调用同机计算服务 `127.0.0.1:8211` |

`g1-g1` 是现有前端标识与域名模板组合的结果，**不要手工删掉其中一个 `g1`**。`v1.1` 是前端版本，不是计算版本。相同主版本可独立选次版本；协议变更导致两端必须一起换代时，两端升到下一主版本。

## 3. EC2：目录、配置和启动

```text
/www/wwwroot/gtt-node/
├── config/
│   ├── platform.env                  # 网关、后台共用；GTT_CONFIG_FILE 指向实际 production.json
│   ├── production.json
│   ├── postgres.json
│   └── secrets/games.key             # 各游戏共用的内部认证密钥，仅运行用户可读
├── gateway/                          # 包含网关 package.json 的目录
├── admin/                            # 包含后台 package.json 的目录
├── frontend-releases/                # 已登记的前端资料和版本缓存；运行用户需可写
└── games/buffalo-win/
    ├── game.env                      # 同游戏各版本共用
    └── v1.2/                         # 直接解压计算 ZIP，不再套 game-buffalo-win/
        ├── package.json
        ├── GAME.json
        ├── config/game.json
        └── tools/buffalo-win.mjs
```

`production.json` 以下是**合并字段示例，不是完整配置**。保留现有数据库、端口、可信代理、`client_root` 和其他运行配置：

```json
{
  "frontend_releases_directory": "/www/wwwroot/gtt-node/frontend-releases",
  "frontend_cdn_origin": "https://play.gttgames.com",
  "frontend_origin_template": "https://{release}-g{game_id}.play.gttgames.com",
  "game_service_secret_file": "/www/wwwroot/gtt-node/config/secrets/games.key"
}
```

`frontend_cdn_origin` 不带路径或末尾 `/`；`frontend_origin_template` 是玩家入口，两者不能互换。`client_root` 是磁盘路径，不填网址。新版运行时默认不直读私有 S3，**无需为网关或后台安装 AWS CLI、授予 EC2 私有桶读取权限**。已有的 `frontend_s3` 字段本身不启用旧模式；不要为解决 CDN 问题打开 `frontend_private_source=s3`。发布工具使用的 AWS 身份与服务器运行身份是两回事。

`games/buffalo-win/game.env`：

```dotenv
GAME_BIND=127.0.0.1
GAME_PORT=8211
GAME_SECRET_FILE=/www/wwwroot/gtt-node/config/secrets/games.key
```

密钥文件只含随机密钥正文；已有 `games.key` 就复用。不要把密钥、数据库密码、`X-GTT-Origin-Verify` 的值、Cookie 或 URL 的 `ops` 令牌写进仓库、截图和工单。共享 `game.env` **不要写 `GAME_RELEASE` 或 `GAME_CONFIG`**；版本和规则由包提供。同机并行运行新旧版本要分配不同端口，可在特定版本目录放其自己的完整 `game.env`。

**启动顺序：** 使用 Node.js ≥ 24.17.0，备份现网配置和数据库。若发布涉及网关和后台，先部署网关、验证后再部署后台。平台包首次启动会装依赖并执行适用的 PostgreSQL migration；试玩需包含 `0002`，不要手工清表或重置数据库。用同一运行用户，在各自包含 `package.json` 的目录执行：

```bash
python3 -m json.tool /www/wwwroot/gtt-node/config/production.json >/dev/null
# 只对本次实际更新的组件执行对应命令
(cd /www/wwwroot/gtt-node/gateway && npm start)
(cd /www/wwwroot/gtt-node/admin && npm start)
(cd /www/wwwroot/gtt-node/games/buffalo-win/v1.2 && npm start)
pm2 list
```

`npm start` 已管理 PM2，不要再套 `pm2 start npm`。配置改动后须重启读取该配置的服务；仅在后台选游戏版本不用重启。`pm2 online` 只表示进程在运行，不表示素材、钱包或游戏首局已验收。

## 4. CDN、DNS、ALB 和 Nginx：哪些设置不能混用

| 项目 | 已用配置 / 核对点 |
|---|---|
| DNS 与证书 | Cloudflare 中 `play` 指向旧业务分配，`*.play` 指向新玩家分配，均为「仅 DNS」。保留 ACM 的 DNS 验证记录。`*.gttgames.com` 不覆盖 `版本.play.gttgames.com`；玩家分配在 `us-east-1` 使用 `*.play.gttgames.com` 证书，ALB 的 `HTTPS:443` 也附加该 SNI 证书 |
| 业务分配 `E3RCHQALSXUQDV` | `/releases/*` → `game-releases-root`（S3 桶根、源路径空）。保留原先绑定历史前缀的 `game-assets` 和旧路径，不要直接改旧源。`/trial/*` 必须动态回源网关、禁缓存，不能让不同访客收到同一会话跳转 |
| 玩家分配 `EJSTMAFRMLH6Q`，`gtt-player-entry` | 默认 `(*)` → ALB，HTTPS:443，`CachingDisabled`、`AllViewer`，允许包含 **POST** 的方法。部署在查看器请求阶段的 `gtt-player-version-router` 要保留真实 `X-GTT-Client-IP` 并按游戏/版本分流。首页和动态 API 的 Host、会话参数要保留 |
| 玩家静态行为 | S3 源实际 ID 是控制台「源名称」，本次为 `gtt-game-assets-817557336527-us-east-1.s3.us-east-1.amazonaws.com`，**不是旧分配的 `game-releases-root`**。静态请求把 `/shared/…` 等改写到 `/releases/buffalo-win/v1.1/…`；不向 S3 转发浏览器 Host、Cookie 或认证信息。已确认有效的单脚本行为使用 S3 源、`GET, HEAD`、无源请求策略及同一查看器函数 |
| 静态覆盖范围 | 除 `/local-*.js` 外，还需核对 `/shared/*`、`/assets/*` 和根目录带哈希的素材（本版可匹配 `/??????????.?????.*`）。**一条 JS 成功不代表所有行为已部署成功**。不要把首页 `/` 或 `/web-api/*`、`/game-api/*` 路由到 S3 |
| S3 | 桶 `gtt-game-assets-817557336527-us-east-1` 保持私有、启用 OAC。桶策略保留 TLS 限制，允许上述**两个分配的 ARN**读取 `releases/buffalo-win/*`，不是授予公共读取或全桶权限 |
| ALB | 优先级 `10`：Host 为 `play.gttgames.com`、`api.gttgames.com` **或** `*.play.gttgames.com`，**并且**匹配回源验证标头，转到网关目标组。后台使用独立规则；默认固定 `403` 保留。目标组默认端口显示 `8080`，但**此环境有意把实际注册目标端口设为 `80`**，以 Targets 列表为准 |
| 宝塔 Nginx | 正式 `80` 玩家入口配置在 `/www/server/panel/vhost/nginx/node_gateway.conf`。其 `server_name` 需包含 `*.play.gttgames.com`，保留原域名，向 `8110` 转发时保留原 Host。`gtt-alb.conf` 中的 `8080` 测通不能代替验证正式 `80`。不要删 Host、回源标头、可信代理或 HTTPS 检查 |

**安全交接待办：** 回源验证值曾出现在排障截图中。轮换时先让 ALB 同时接受新旧值，再更新两个分配的 ALB 源，待部署完成、验证通过后撤销旧值。不要复制旧截图中的值。

## 5. 发布和验收：以一次完整回合为终点

1. **已有版本不要重建覆盖。** 新版本只打指定游戏；打包命令、`--cdn-entry` 和完整 `publication-bundle` 用法见[单游戏交付](game-deployment-bundles.md)。发布端上传到不可变前缀，验证素材，最后写公开标记。计算 ZIP 不上传 S3。协议资料摘要兼容时，更新前端无需重打后台和网关；协议不兼容时不能只改版本号。
2. **先验公开素材。** 浏览器或 `curl` 检查以下地址。清单要返回本游戏、本版本；入口和脚本应返回正确内容，而不是带 `200` 的错误页面：
   - `https://play.gttgames.com/releases/buffalo-win/v1.1/_gtt-manifest.json`
   - `https://play.gttgames.com/releases/buffalo-win/v1.1/index.html`
   - `https://fe-v1-1-g1-g1.play.gttgames.com/local-auth-bootstrap.js`
3. **后台 → 游戏目录 → 发布管理。** 选前端 `v1.1`、计算 `v1.2`。第一次连接计算服务填 `http://127.0.0.1:8211`，后台从服务器文件读取共享密钥。点「检查并发布」：认证计算服务、核对实际版本/协议/适配摘要并通过 HTTPS 查公开标记。常规开放不重新下载全部素材。全部通过才在事务内切换和开放；失败不改变原组合。
4. **后台 → 游戏目录 → 试玩 → 立即试玩。** 分享邀请，不分享含 `ops` 的个人地址。邀请限已开放版本；每次兑换独立会话和余额，试玩不调用真实商户钱包。测试顺序：入口 HTML → 启动 JS → `verifyOperatorPlayerSession` → `GameInfo/Get` → 第一次 `Spin` → 再次 `GameInfo/Get`。后三个协议响应应为 HTTP 200、`err: null`，并核对余额变化、重复请求不重复扣款。
5. **记录结果再交接。** 记下包名、前后端版本、时间、失败接口的路径/状态码及脱敏错误。不以试玩通过代替正式商户签名启动、扣款、派彩和未结回合恢复验收。回退优先切回已验证的兼容配对；保留旧实例和被回合绑定的版本，不回滚玩家数据库来代替应用回退。

## 6. 常见现象速查

| 现象 | 先查哪一跳 |
|---|---|
| 玩家域名 NXDOMAIN 或 TLS 连接失败 | 查实际版本域名的公网 CNAME、CloudFront 备用域名、证书层级；不要因为普通 `play` 素材可访问就判定玩家域名可用 |
| CloudFront 502 | 区分 ALB 回源 TLS 与 `FunctionValidationError / invalid value for origin rewrite`；后者核对函数引用的**本分配**源 ID |
| `403 Forbidden` 纯文本 / Nginx HTML / JSON `HOST_REJECTED` | 分别核对 ALB 转发条件、Nginx 站点及可信标头、实际进入的 Node 服务和 Host。正文是线索，不是单凭状态码定责 |
| 不带 `ops` 访问玩家 `/` 得到 `401 SESSION_INVALID` | 这是正常无令牌结果，表明域名请求已到会话校验；用新邀请继续验收 |
| JS 返回 `503 application/json`，浏览器报 MIME 错误 | 若错误码为 `FRONTEND_CDN_REQUIRED`，是静态请求走了网关。对比**玩家域名下原路径**和**业务域名下带版本前缀路径**；不要把 JSON 错误响应强改成 JS 类型 |
| S3 XML `403 AccessDenied` / `404 NotFound` | 核对该分配的 OAC 和桶策略、真实对象键、是否重复拼 origin path、是否把玩家 Host 转给 S3。旧 `private/frontend/...` 的 `403` 不等于新版必须给 EC2 增加权限 |
| 会话验证 `POST` 返回 403 HTML，游戏提示地区限制 | 先核对动态行为是否允许 POST，看响应正文。地区提示是游戏内置通用文案，不是地理封锁的证据 |
| `GameInfo/Get` 或 `Spin` 返回 `500 GAME_UNAVAILABLE` | 核对网关包是否含 `trial-gameinfo` 修复。看网关日志中 `[protocol-worker]` 的阶段和栈；不要先重配 CloudFront。另查缺失 PNG 是否真的列入当前版本清单 |

**本地证据：** 仓库根目录下 `other/diagnostics/releases/gtt-node-20261125-buffalo-cdn-entry/` 有发布清单、验证与 S3 回执；网关包对应 `gtt-node-20261125-gateway-trial-gameinfo/`。这些是构建/发布记录，不是线上经营验收报告。进一步阅读：[环境与部署](environment-and-deployment.md) · [开放检查](game-opening-checks.md) · [后台与试玩](gtt-admin.md)。
