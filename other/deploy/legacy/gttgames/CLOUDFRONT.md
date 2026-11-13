# 官网与游戏同时上线

> 目录已重组。当前启动命令与路径见[四目录说明](../../../docs/project-layout.md)；本文中的旧命令保留为历史记录。

2026-10-29：本文件记录此前两个分配直接回源 EC2 的方案。用户要求统一 AWS 标准化部署，后续以 [AWS 标准化部署方案](AWS-DEPLOYMENT.md) 为准；该建议方案采用私有官网 S3、ALB 和统一业务分配。本文旧资源数量、域名目标及执行命令不是新方案的执行依据。

资源固定按完整上线准备：1 台 Linux 服务器、2 个 CloudFront 分配、1 个私有 S3 备份桶。官网文件与游戏素材目前都在服务器；若以后迁入 S3，再为公开素材另设私有桶和 OAC。备份桶不能作为官网或游戏分配的源站。

## 分配与 DNS

| 资源 | 公开域名 | 源站 |
| --- | --- | --- |
| 官网分配 | `gttgames.com`、`www.gttgames.com` | `origin.gttgames.com:443` |
| 游戏分配 | `play.gttgames.com` | `origin.gttgames.com:443` |
| 商户 API、两个后台 | `api`、`merchant`、`admin.gttgames.com` | 直接访问服务器 HTTPS |

`origin.gttgames.com` 的 A 记录始终是服务器公网 IP，不能指向任何 CloudFront 分配，否则会形成回源循环。两个分配都保留访问者的 Host：Nginx 根据 `gttgames.com`、`www.gttgames.com` 或 `play.gttgames.com` 选择站点；源站证书覆盖这些公开域名。不能改用移除 Host 的 AllViewerExceptHostHeader 策略。

最终记录见 `dns-records.csv`。Route 53 的主域名使用 A Alias 指向官网分配，CloudFront Alias hosted zone ID 为 `Z2FDTNDATAQYW2`，EvaluateTargetHealth=false；其他 DNS 厂商需要支持根域名 ALIAS／ANAME／CNAME flattening。不能在根域名添加普通 CNAME，也不能将 CloudFront 当前解析出的 IP 填成固定 A 记录。`www` 和 `play` 使用 CNAME。模板暂不开启 CDN IPv6，不添加 AAAA。

## 证书和创建顺序

1. 确定服务器公网 IPv4、DNS 管理方式、AWS 账号及官网成品目录。官网必须有 `index.html`，安装到 `/var/www/gtt-site`，不把演示大厅当成官网。
2. 本次采用 DNS 验证源站证书：先将 `api`、`merchant`、`admin`、`origin` 四项 A 记录指向服务器 IP，官网、www 与 play 等分配准备好后直接指向 CloudFront。在宝塔创建站点，通过 DNS 验证申请覆盖公开域名的源站证书，再配置正式 Nginx 和后端服务。证书 DNS 验证不要求官网或 play 先解析服务器 IP；生产续期需同时配置可用的 DNS API 自动验证。README 中 HTTP-01 引导仅作为其他部署的可选方案，本次不采用临时直连官网／游戏域名。
3. 在 **us-east-1** 申请 ACM 公有证书，至少包含 `gttgames.com`、`www.gttgames.com`、`play.gttgames.com`；也可使用覆盖主域名和 `*.gttgames.com` 的证书。添加 ACM 提供的 DNS 验证 CNAME，保留这些记录以便自动续期，等待状态为 ISSUED。ACM 证书用于 CloudFront，Nginx 仍使用自身的源站证书。
4. 登录正确 AWS 账号，在本地验证和预览资源变更，再创建资源。以下参数中的 ARN 必须替换成真实已签发证书；命令不创建服务器、不改 DNS、不上传官网。

```sh
aws sts get-caller-identity
aws cloudformation validate-template --region us-east-1 --template-body file://deploy/gttgames/cloudformation.json
aws cloudformation deploy --region us-east-1 --stack-name gtt-production-edge \
  --template-file deploy/gttgames/cloudformation.json \
  --parameter-overrides CertificateArn=REPLACE_WITH_ISSUED_ACM_CERTIFICATE_ARN \
  --no-execute-changeset
# 检查 change set 中应只有两个 CDN 分配、两个缓存策略、一个备份桶及其 TLS 策略。
# 使用上一步返回的 change set 名称执行，勿执行不属于本次部署的变更。
aws cloudformation execute-change-set --region us-east-1 \
  --stack-name gtt-production-edge --change-set-name REPLACE_WITH_REVIEWED_CHANGE_SET_NAME
aws cloudformation wait stack-create-complete --region us-east-1 --stack-name gtt-production-edge
aws cloudformation describe-stacks --region us-east-1 --stack-name gtt-production-edge --query 'Stacks[0].Outputs'
```

已有命名 profile 时，为每条命令增加 `--profile PROFILE_NAME`。更新已有 stack 时等待 `stack-update-complete`。模板不申请 IAM 管理权限，不给备份桶添加公开读权限；执行者仍须具备创建相关资源的权限。

5. 等待两个 CloudFront 分配状态都为 Deployed。用 stack outputs 替换 CSV 中两个分配域名，将 `@`／`www` 指向官网分配、`play` 指向游戏分配，其他记录保持指向服务器。源站 TLS 已提前准备好，切换后不会因回源域名再次经过 CDN。
6. 运行 README 中的 smoke.py，再执行下面的 CDN 专项验收，最后启用日常备份上传。备份目录和上传身份由生产运维配置；模板只创建加密、版本控制、阻止公开访问并要求 TLS 的桶，不声称已建立自动备份。

## 缓存与请求转发

| 链路 | 缓存 | 请求转发 |
| --- | --- | --- |
| 官网静态内容 | 默认 300 秒，最小 0，最大 7 天，尊重源站 no-store/private | Host 参与缓存键；不转发 Cookie 和查询参数 |
| 官网 ACME challenge | CachingDisabled，错误缓存 0 | AllViewer，保留 Host 和路径 |
| 游戏默认行为 | CachingDisabled，错误缓存 0 | AllViewer，完整转发查询参数、Cookie、Authorization 和其他访问者请求头 |
| 游戏 `/assets/*`、`/shared/*` | 默认 1 天，最小 0，最大 7 天，尊重 no-store/private | Host 和全部查询参数参与缓存键；不转发 Cookie |

游戏入口 `/`、`index.html`、本地登录脚本、会话、余额、投注和原版 `/web-api/`、`/game-api/` 均走默认不缓存行为。不会按全站扩展名模糊缓存，避免动态响应被当成静态素材。当前修复过的 shared/index.js 返回 no-store，因此仍不会被缓存。API 与后台未经过 CloudFront；HMAC 的请求路径和原始 body 保持不变。CloudFront 动态行为允许的完整方法集合由 AWS 接口要求决定，源站继续限制实际业务方法。

两个分配均设置 HTTPS 回源、连接尝试一次，不设置自定义错误页／200 替换。所有可配置错误的 ErrorCachingMinTTL 为 0，避免把短暂认证失败或服务故障缓存。游戏分配不启用访问日志或实时日志，因为原版启动 URL 的查询参数携带玩家令牌；后续接日志必须先验证脱敏。Nginx 的原有无查询参数访问日志继续使用。

官网与 play 的 HTTPS 站点均提供 `/.well-known/acme-challenge/`；官网分配为该路径单独禁用缓存。切换后执行 `certbot renew --dry-run` 验证真实 CDN 路径，源站证书需在过期前完成续期。若证书已过期，HTTPS 回源会失败，应先修复源站证书再恢复流量。

## 上线验收与待提供信息

- 官网根路径返回真实官网 200；`www` 保留路径和查询参数跳转主域名，不再跳商户后台；两个后台独立登录。
- 官网和游戏响应包含 `Via`／`X-Amz-Cf-Id` 等 CDN 标记；同一普通素材重复 GET 出现 Hit 和 Age；声明 no-store 的资源不要求 Hit。
- 带两个不同玩家会话分别读取余额，重复请求不出现缓存 Hit／Age，余额不串用；普通投注、购买免费和重试按既有钱包验收流程执行。
- 校验源站收到正确的公开 Host、查询参数和认证头；源站只信任本机 Nginx 代理，不扩大后端可信地址范围。
- 两个分配不记录完整启动 URL；源站 play 访问日志不含会话令牌；模拟钱包 8111 不进入生产。
- 官网更新后可按需清除官网分配缓存；游戏素材更新时按变更路径清除游戏分配缓存，不把 CDN 清除当成会话重置。

当前缺少已确认的服务器 IP、可用于此项目的 AWS 登录、DNS 提供方及官网成品文件。仓库模板准备与本地验证不能证明 AWS 已创建资源或公网已上线；正式证书、DNS 切换、CDN 端到端与备份恢复验收必须在目标环境完成。

## 官方依据

- [CloudFront 的自定义域名及 us-east-1 证书](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/cnames-and-https-procedures.html)
- [保留全部访问者头的 AllViewer 策略](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-managed-origin-request-policies.html)
- [HTTPS 回源证书与 Host 匹配](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-https-cloudfront-to-custom-origin.html)
- [缓存键与源站请求策略](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/understanding-how-origin-request-policies-and-cache-policies-work-together.html)
