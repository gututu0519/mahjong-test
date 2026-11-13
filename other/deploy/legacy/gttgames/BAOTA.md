# 宝塔环境部署

> 目录已重组。当前启动命令与路径见[四目录说明](../../../docs/project-layout.md)；本文中的旧命令保留为历史记录。

2026-10-29：目标机后端已启动。用户要求统一 AWS 标准化部署，后续以 [AWS 标准化部署方案](AWS-DEPLOYMENT.md) 为准；本文保留此前上传与单机运维记录。宝塔是否保留为运维入口与当前已运行的应用分开处理，不继续按本文旧 TLS/直回源步骤配置公网域名。

服务器已安装 Ubuntu 24.04、宝塔 Linux 面板，Nginx 由宝塔安装和管理。后端沿用本目录的 systemd 服务，Python 使用 `/usr/bin/python3`，不依赖宝塔面板自身的 Python 环境。

## 上传与解压

在宝塔「文件」中新建 `/opt/gtt/uploads`，上传发布 ZIP。通过终端解压到独立的版本目录，例如：

```sh
sudo install -d -m 0755 /opt/gtt/releases/20261029-baota
sudo unzip -n /opt/gtt/uploads/gtt-release-20261029-baota.zip -d /opt/gtt/releases/20261029-baota
cd /opt/gtt/releases/20261029-baota
python3 deploy/gttgames/preflight.py --template
```

解压后当前目录应直接包含 `py/`、`clients/`、`services/`、`deploy/` 和 `release-manifest.json`。预检会验证文件 SHA256、游戏素材、运行时及域名配置；template 模式不表示官网文件、证书或 AWS 资源已部署。

## 后端服务

首次部署先创建专用运行用户、目录和配置，再初始化平台管理员。已有用户、配置或账户的服务器保留原状态并检查后复用。版本软链接与新用户示例：

```sh
sudo useradd --system --user-group --home-dir /var/lib/gtt --shell /usr/sbin/nologin gtt
sudo ln -s /opt/gtt/releases/20261029-baota /opt/gtt/current
sudo install -d -o root -g gtt -m 0750 /etc/gtt
sudo install -d -o gtt -g gtt -m 0700 /var/lib/gtt
sudo install -d -o gtt -g gtt -m 0750 /var/log/gtt
sudo install -m 0640 -o root -g gtt /opt/gtt/current/deploy/gttgames/production.json /etc/gtt/production.json
cd /opt/gtt/current
sudo -u gtt python3 -m py.merchant.sandbox admin-init --config /etc/gtt/production.json
sudo install -m 0644 deploy/gttgames/systemd/gtt-gateway.service /etc/systemd/system/
sudo install -m 0644 deploy/gttgames/systemd/gtt-admin.service /etc/systemd/system/
sudo install -m 0644 deploy/gttgames/systemd/gtt-rtp-worker.service /etc/systemd/system/
sudo systemd-analyze verify /etc/systemd/system/gtt-gateway.service /etc/systemd/system/gtt-admin.service /etc/systemd/system/gtt-rtp-worker.service
sudo systemctl daemon-reload
sudo systemctl enable --now gtt-gateway gtt-admin gtt-rtp-worker
curl --fail http://127.0.0.1:8110/health
curl --fail http://127.0.0.1:8112/health
```

初始管理员凭据保存在 `/var/lib/gtt/admin-bootstrap.json`。该文件和生产数据库不在发布包内。三个服务均由 systemd 管理，网关和后台只监听本机；AWS 安全组的业务公网入口为 80、443。

## 宝塔网站、TLS 与 CDN

Nginx 站点在宝塔中创建、配置和重载；本目录 `nginx/` 是发行版 Nginx 的独立部署参考，其中 `/etc/nginx` include、证书和日志路径，以及默认站点块，必须适配宝塔现有配置，不能直接当作宝塔站点文件导入。宝塔通常使用 `/www/server/panel/vhost/nginx` 保存站点配置，具体以面板当前版本为准。

| 宝塔站点域名 | 服务 |
| --- | --- |
| `gttgames.com` 与 `www.gttgames.com` | 官网静态成品；www 保留路径跳转主域名 |
| `api.gttgames.com` | `127.0.0.1:8110`，仅 `/gtt/v1/` 签名接口 |
| `play.gttgames.com` | `127.0.0.1:8110`，玩家及客户端接口，隔离商户签名路由 |
| `merchant.gttgames.com` | `127.0.0.1:8112`，商户后台与 `/api/merchant/` |
| `admin.gttgames.com` | `127.0.0.1:8112`，平台后台与 `/api/admin/` |

反代需保留 Host 和原始请求路径、body，覆盖 `X-Forwarded-Proto` 等代理元数据，关闭动态缓存与代理自动重试；保留现有模板中的路由隔离、登录限流、请求体限制和无查询参数访问日志。普通宝塔「全站反向代理」默认项不等于完成这些要求。配置文件需要在确认 Nginx 版本、实际站点目录和证书路径后生成，并通过宝塔的配置检查再重载。

源站证书通过宝塔的 DNS 验证申请，生产续期需配置可用的 DNS API；CDN 使用 us-east-1 的 ACM 证书。api、merchant、admin、origin 指向服务器，官网、www、play 直接按 CloudFront 最终解析配置，无需临时改为直连服务器 IP；分配与 DNS 顺序见 `CLOUDFRONT.md`。官网成品尚未提供，发布包没有虚构官网页面。当前商户钱包链路与客户端素材覆盖 Buffalo Win，其他游戏的独立试玩入口继续保留在原项目；该发布包不代表全部游戏已接入生产商户网关。
