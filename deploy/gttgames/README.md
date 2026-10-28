# gttgames.com 部署配置

本目录准备 Linux 单机部署：Nginx 负责公网 HTTPS，两个 Python 服务只监听 loopback；Python 3.11+、Node.js 18+、systemd、Nginx、Certbot 为运行依赖。域名已写入配置，服务器公网 IP、DNS 解析和正式证书仍需在部署时配置。本目录不包含真实密码、商户密钥或生产数据库。

## 域名与服务

| 域名 | 职责 | 上游 |
| --- | --- | --- |
| `gttgames.com` | 主站预留；官网建成前 `/` 临时跳转商户入口 | Nginx |
| `www.gttgames.com` | 308 跳转主域名 | Nginx |
| `api.gttgames.com` | 仅提供 `/gtt/v1/` 商户签名接口 | `127.0.0.1:8110` |
| `play.gttgames.com` | 原版客户端、玩家会话和游戏接口 | `127.0.0.1:8110` |
| `merchant.gttgames.com` | 商户登录、接入中心、文档及 `/api/merchant/` | `127.0.0.1:8112` |
| `admin.gttgames.com` | 平台登录及 `/api/admin/` | `127.0.0.1:8112` |

启动接口在生产配置下返回 `https://play.gttgames.com/?...` 的完整地址，商户直接使用 `launch_url`。游戏 ID 保持 JSON 数字，Buffalo Win 为 `1`；商户号为 `GTT` 加六位数字。后台主账号用商户名称登录。生产配置中没有模拟商户、测试余额或 8111 钱包进程，真实商户需提供自己的 HTTPS 钱包及可选预派彩地址。

本机继续使用既有 `sandbox.json` 与 8110／8111／8112，不会因准备生产模板而改变本机商户、余额或密钥。生产根路径可识别后台类型，本机的 `/merchant/` 入口继续可用。

## 文件

- `production.json`：公开域名、可信 loopback 代理、数据库和日志目录。
- `dns-records.csv`：六项 DNS 记录模板，将 `REPLACE_WITH_SERVER_PUBLIC_IPV4` 替换为真实公网 IPv4 后再配置。IPv6 需在确认可达后另配 AAAA。
- `nginx/`：域名分流、TLS、首次签发证书的 HTTP 配置、续期重载钩子。
- `systemd/`：网关和后台进程。双方使用同一商户库与游戏库，单机各运行一个进程。
- `preflight.py`：只读检查环境、配置及客户端素材。`--template` 可在开发机执行。
- `smoke.py`：DNS／证书安装后的只读 HTTPS、入口隔离和登录前鉴权检查，不提交投注。
- `backup.py`：协调停机后的 SQLite 双库备份及完整性检查。
- `package.py`：打包代码、配置和 Buffalo 素材，排除测试、数据库、日志及其他抓取。包内有 SHA256 清单。

## 1. 准备发布包与服务器目录

原版客户端在 Git 忽略的 `clients/` 目录，部署时必须携带素材，单独克隆仓库不能完成部署。在开发机运行：

```text
python deploy/gttgames/preflight.py --template
python deploy/gttgames/package.py --output /你选择的输出目录/gtt-release.zip
```

将生成的包上传服务器。以下为新机器示例命令；已有目录／用户时检查并复用，`RELEASE_ID` 替换为版本目录名称。

```sh
sudo apt-get update
sudo apt-get install python3 nodejs nginx certbot unzip
sudo useradd --system --user-group --home-dir /var/lib/gtt --shell /usr/sbin/nologin gtt
sudo install -d -o root -g root -m 0755 /opt/gtt/releases/RELEASE_ID
sudo unzip gtt-release.zip -d /opt/gtt/releases/RELEASE_ID
sudo ln -s /opt/gtt/releases/RELEASE_ID /opt/gtt/current
sudo install -d -o root -g gtt -m 0750 /etc/gtt
sudo install -d -o gtt -g gtt -m 0700 /var/lib/gtt
sudo install -d -o gtt -g gtt -m 0750 /var/log/gtt
sudo install -m 0640 -o root -g gtt /opt/gtt/current/deploy/gttgames/production.json /etc/gtt/production.json
cd /opt/gtt/current
sudo -u gtt python3 deploy/gttgames/preflight.py --config /etc/gtt/production.json
```

后端保持监听 127.0.0.1。公网业务入口为 80／443，保留现有 SSH 管理方式；8110、8112 和数据库目录不作为公网入口。

## 2. 初始化或导入状态

新生产环境不导入本机模拟商户和钱包。创建初始平台管理员：

```sh
cd /opt/gtt/current
sudo -u gtt python3 -m server.merchant.sandbox admin-init --config /etc/gtt/production.json
```

初始密码只写入 `/var/lib/gtt/admin-bootstrap.json`（目录 0700），不打印到服务日志。首次登录后可修改密码。已有账号时命令拒绝重复初始化。创建真实商户后，系统自动分配顺序商户号、统一密钥与商户主账号。

如需搬迁已有真实状态，先在旧环境完成顺序编号升级，协调停止旧网关／后台／RTP worker，使用 SQLite backup 导出 `merchants.sqlite3` 与 `gtt.sqlite3` 成对恢复到 `/var/lib/gtt/`，设置所有者为 `gtt:gtt`、文件模式 0600，再启动新服务。不要只搬其中一个库，也不要在线复制 `.sqlite3` 而遗漏 WAL。生产模式不运行本机 `migrate-identifiers`／模拟钱包命令。商户密钥、原密码、交易号和玩家标识随数据库保留；生产钱包／预派彩配置应指向真实商户系统。

## 3. DNS 与证书

先将 CSV 中的公网 IPv4 占位符替换为真实地址，在域名 DNS 控制台配置记录。此次准备工作没有修改 DNS。

为六个明确域名签发一张 SAN 证书，使用 HTTP-01 自动续期，不依赖 DNS 厂商插件。首次签发前只加载 HTTP 引导配置，避免正式 TLS 配置引用尚不存在的证书：

```sh
sudo install -d -m 0755 /var/www/gtt-acme
# 如果发行版启用了默认站点，先检查并取消其 default_server 链接，避免监听冲突。
sudo install -m 0644 /opt/gtt/current/deploy/gttgames/nginx/bootstrap-http.conf /etc/nginx/conf.d/gtt-bootstrap.conf
sudo nginx -t
sudo systemctl reload nginx
sudo certbot certonly --webroot -w /var/www/gtt-acme --cert-name gttgames.com \
  -d gttgames.com -d www.gttgames.com -d api.gttgames.com -d play.gttgames.com \
  -d merchant.gttgames.com -d admin.gttgames.com
```

Certbot 会要求登记邮箱和确认服务条款，由部署操作者完成。证书预期目录为 `/etc/letsencrypt/live/gttgames.com/`；不把私钥放入项目、发布包或 Git。

## 4. 安装服务与正式代理

```sh
sudo install -m 0644 /opt/gtt/current/deploy/gttgames/systemd/gtt-gateway.service /etc/systemd/system/
sudo install -m 0644 /opt/gtt/current/deploy/gttgames/systemd/gtt-admin.service /etc/systemd/system/
sudo install -m 0644 /opt/gtt/current/deploy/gttgames/systemd/gtt-rtp-worker.service /etc/systemd/system/
sudo systemd-analyze verify /etc/systemd/system/gtt-gateway.service /etc/systemd/system/gtt-admin.service /etc/systemd/system/gtt-rtp-worker.service
sudo systemctl daemon-reload
sudo systemctl enable --now gtt-gateway gtt-admin gtt-rtp-worker
sudo install -d -m 0755 /etc/nginx/snippets
sudo install -m 0644 /opt/gtt/current/deploy/gttgames/nginx/gtt-proxy.conf /etc/nginx/snippets/
sudo install -m 0644 /opt/gtt/current/deploy/gttgames/nginx/gtt-tls.conf /etc/nginx/snippets/
sudo install -m 0644 /opt/gtt/current/deploy/gttgames/nginx/gttgames.conf /etc/nginx/conf.d/
sudo rm /etc/nginx/conf.d/gtt-bootstrap.conf
sudo nginx -t
sudo systemctl reload nginx
sudo install -m 0755 /opt/gtt/current/deploy/gttgames/nginx/renew-hook.sh /etc/letsencrypt/renewal-hooks/deploy/gtt-nginx-reload
sudo install -m 0644 /opt/gtt/current/deploy/gttgames/logrotate/gtt /etc/logrotate.d/gtt
sudo certbot renew --dry-run
```

首次部署前确认发行版的 Nginx 主配置会加载 `/etc/nginx/conf.d/*.conf`，且没有其他重复的 80／443 默认站点。主站当前只把 `/` 临时跳转到商户入口；官网内容上线时替换主域名的站点块，其他子域名配置保持独立。

## 5. 验证

```sh
curl --fail http://127.0.0.1:8110/health
curl --fail http://127.0.0.1:8112/health
cd /opt/gtt/current
python3 deploy/gttgames/smoke.py --config /etc/gtt/production.json
sudo systemctl status gtt-gateway gtt-admin gtt-rtp-worker nginx
```

接着人工验证平台管理员登录、创建商户、商户名称登录、密钥／文档下载、授权游戏 1 启动，返回链接必须使用 `https://play.gttgames.com/`。在商户测试账户上联合验证普通投注、免费流程、钱包幂等、响应丢失及原操作恢复。当前商户钱包链路仍仅 Buffalo Win，RTP 中心已提供完整整局统计、90%／96% 模型与商户／玩家目标设置，模型为统计验证而非第三方理论认证；其他游戏接入状态沿用原项目记录。

后台使用 `__Host-` 会话 Cookie（Secure、HttpOnly、SameSite=Strict、Path=/、无 Domain）；商户和平台会话分别绑定各自域名。生产后端只信任 loopback 代理，校验明确域名、HTTPS 转发标记和同源 Origin，Nginx 覆盖客户端传入的代理头。API 与 play 及两类后台的路径均做隔离，商户请求签名路径和请求体不重写，不开启代理自动重试。

## 6. 日志、备份与回滚

应用日志在 `/var/log/gtt/`，Nginx 访问日志使用不含查询参数、Referer、Cookie、签名头或请求体的格式。玩家访问的查询参数含会话凭据，因此 play 站点关闭 Nginx 错误日志，只保留状态码、无查询的路径及耗时；网关日志继续脱敏会话令牌。HSTS 初始为一天，确认所有入口及续期正常后再评估延长。

升级之前在维护窗口停机并备份成对状态：

```sh
sudo systemctl stop gtt-rtp-worker gtt-admin gtt-gateway
cd /opt/gtt/current
sudo python3 deploy/gttgames/backup.py --config /etc/gtt/production.json --services-stopped
# 记录输出目录，并保留当前 release 链接。随后切换到已校验的新 release。
sudo systemctl start gtt-gateway gtt-admin gtt-rtp-worker
```

备份包含商户密钥和密码哈希，目录 0700、文件 0600，按内部备份策略保存。代码回滚可停机切回之前的 `/opt/gtt/current`；若发生数据库结构变更，使用对应版本的双库备份恢复，不能把单库或旧状态直接覆盖在线数据库。恢复时连同配置及 WAL／SHM 生命周期协调处理，先停止服务、确认备份完整性，再启动并验证。

## 参考

- [Nginx 反向代理](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)
- [Nginx TLS](https://nginx.org/en/docs/http/ngx_http_ssl_module.html)
- [Nginx 日志格式](https://nginx.org/en/docs/http/ngx_http_log_module.html)
- [Let's Encrypt 验证方式](https://letsencrypt.org/docs/challenge-types/)
- [systemd 执行环境](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html)

## 本次本地验证记录

已在隔离临时数据库与测试证书下运行 Nginx 1.30.6：语法检查、TLS SNI／证书校验、域名分流、两个后台根路径登录、Secure Cookie 隔离、签名路径／body 保持、完整 play 链接、HTTPS 玩家余额和投注、原版客户端 GameInfo、访问日志无会话令牌均通过。测试浏览器的原版设备提示通过其“Continue to Game”入口继续，没有修改或隐藏提示。该验证不代表已修改公网 DNS、签发正式证书或部署目标 Linux。systemd 验证仍需在目标 Linux 上执行。

## 客户端素材待补记录

HTTPS 浏览器验证在原版设备兼容性检查阶段观察到以下已有素材缺失：`/3c3f748b3f.c9ac6.png`、`/009dacbcef.9f20d.png`、`/b13b8b6217.55f12.png`，以及 `/shared/service-worker/sw.js`、`/favicon/favicon.ico`、`/favicon/favicon-48.png`。这些请求返回 404；继续原版入口后游戏客户端和 GameInfo 正常加载。没有为绕过缺失而删除入口、隐藏原版提示或使用其他游戏的未验证素材替换。

已检查现有 Buffalo 素材目录、根目录 `original.har`／`official-audio.har`，并搜索 `response-capture/captures` 中已有 HAR，未找到三个 PNG 的对应捕获记录。后续补抓操作是：打开原版 Buffalo Win 启动页及设备兼容性检查页，保存上述图片、favicon 和 service worker 的完整请求／响应，再核对版本与引用路径后恢复素材。当前发布包携带已有捕获素材及校验清单；本次部署验证覆盖已列出的接口、页面入口和游戏初始化，素材完整性验收继续跟踪这些条目。

## RTP 标定服务

`gtt-rtp-worker` 无公网监听，与网关共用游戏数据库，只执行离线模拟。默认 2 个计算子进程、低优先级和 CPU 配额；标定成功先保存待发布模型，不自动改变商户目标。原有商户模式与目标配置在首次升级时保留；所有商户自主配置 RTP，无需平台授权。完整统计、验证口径与操作步骤见项目 `docs/gtt-rtp.md`。生产后台「模型与标定」可检查心跳和真实任务进度；只有通过验证并发布的模型才能用于目标配置。
