# GTT AWS 部署栈

> 目录已重组。当前启动命令与路径见[四目录说明](../../../../docs/project-layout.md)；本文中的旧命令保留为历史记录。

本目录取代此前直接回源公网 EC2 的简化模板。只生成配置不会创建 AWS 资源、关联实例角色、改 DNS、重启服务器或上传官网。

游戏素材迁移结果见 [GAME-ASSETS.md](GAME-ASSETS.md)：374 个与原线上字节一致的静态文件已发布到独立私有素材桶，CloudFront 正式路径已切换并通过全量 active 校验、缓存命中与匿名 S3 拒绝检查。后续边缘栈变更应基于 edge-assets-activate.json 或实际栈模板；本目录 03-edge.json 仅为首次部署/迁移前基准，不可直接覆盖当前生产路由。原应用文件保留用于回退。

当前账号首次基础栈已回滚，用户已确认两个遗留桶四项公共访问阻止全为 true。该恢复分支先按 [现有桶恢复检查](RECOVERY.md) 执行 recovery_preflight.py，再审阅 02-foundation-existing-buckets.json；不重复创建桶，也不直接重跑下述标准新建流程。

## 部署顺序

三个栈均在 **us-east-1** 创建，固定顺序如下：

| 栈名 | 模板 | 内容 |
| --- | --- | --- |
| gtt-certificate | 01-certificate.json | gttgames.com 与 *.gttgames.com 的 ACM 公有证书，DNS 验证 |
| gtt-foundation | 02-foundation.json | 两个私有 S3 桶、IAM Role/Profile、SSM Agent 配置、回源随机密钥、ALB/目标组/访问规则、CloudWatch/SNS |
| gtt-edge | 03-edge.json | 官网与业务两个 CloudFront、官网 OAC/桶策略、业务 WAF、缓存/转发策略与边缘函数 |

现有 EC2、VPC、子网、数据库和原实例安全组不纳入资源替换。foundation 在已确认的实例安全组中新增两条仅允许 ALB 访问 TCP 8080/8081 的规则，保留现有规则；管理来源和原有公网业务规则的收窄要在新入口与运维通道验收后执行。

## 第一步：证书栈

在 AWS CloudFormation 控制台选择北弗吉尼亚 us-east-1，创建标准栈，上传 01-certificate.json，栈名填写 gtt-certificate，DomainName 保持 gttgames.com。此栈没有 EC2、S3、ALB、IAM 或 CloudFront 资源。

创建后可能停留在 CREATE_IN_PROGRESS，原因是 ACM 等待域名所有权验证。在 ACM 控制台打开该证书，将 DNS 验证 CNAME 加入当前有效的权威 DNS。若 Cloudflare zone 仍 Pending，先核对委派状态，不把“添加了 Cloudflare zone”当成已接管权威解析。验证记录选 DNS-only/灰云，不删除邮件记录，不开启全域 CNAME flattening；主域名默认 flattening 可以保留。

ACM 状态变为 ISSUED 且证书栈 CREATE_COMPLETE 后，保存 Outputs 的 CertificateArn。主域名与通配域名可能共用一条验证 CNAME，以 ACM 实际给出的记录为准。保留验证记录供续期使用。这里不创建网站流量解析。

## 第二步：自动预检与基础栈

environment.json 记录了用户确认的账号、实例、VPC、两个候选子网和安全组。AWS CloudShell 使用用户当前控制台身份，或本地使用明确的临时/SSO 部署身份。部署身份需要相应 CloudFormation、ACM、EC2、ELB、IAM、S3、SSM、Secrets Manager、CloudWatch、SNS、WAF 和 CloudFront 权限；应用实例 Role 与部署身份分开，不能给应用 Role 附加 AdministratorAccess。

在已解压本目录的位置运行，只读检查身份、候选子网/可用区/路由/IGW、剩余 IP、网络 ACL、EBS 加密、实例安全组与已签发证书：

```sh
python3 cloud_preflight.py --certificate-arn ACTUAL_CERTIFICATE_ARN --parameters-output foundation-parameters.json
```

本地指定 profile 时追加 --profile PROFILE_NAME。参数输出文件使用独占创建，不覆盖既有文件。返回 review_required 或 failed 时不创建基础栈；只针对真实不满足项处理，不重复索要已确认网络截图。

预检通过仅代表上述已读取的资源条件满足，不代表部署写权限、Organizations SCP、权限边界或服务额度均已验证；validate-template 和成功生成变更集也不验证所有资源创建权限。组织成员账号在执行前应由组织管理员核对部署动作及适用策略。2026-10-29 首次执行已确认 SCP p-rpz4cfcf 显式拒绝 s3:PutBucketPublicAccessBlock，导致两个桶失败、基础栈进入回滚。模板设置四项桶级阻止公共访问均为 true；保留这些配置，由组织管理员确认允许的部署身份或经审核的策略调整，不能靠新增 IAM Allow 覆盖 SCP Deny。重试前先核对回滚状态与 Retain 遗留资源。

使用 02-foundation.json 与上述参数创建 gtt-foundation change set，检查新增资源及对现有安全组的两条授权后执行。控制台要求确认 IAM 资源创建能力。NotificationEmail 填运维收件地址并完成 SNS 邮件确认；留空时会有告警规则与主题，但没有邮件接收人。EnableBackupMonitoring 首次保持 false，直到备份任务安装、恢复演练及指标验证完成。

基础栈创建期间 ALB 目标可能尚未健康，因为 EC2 Nginx 的 8080/8081 入口还没安装，这不等于应用数据库需要重新初始化。基础栈输出包括网站/备份桶、ALB DNS、目标组、实例角色/Profile、Agent 配置参数和 SNS 主题。

## 既有实例的关联与适配

1. 在 EC2 的“操作 → 安全 → 修改 IAM 角色”中，选择基础栈输出的 InstanceProfileName；该下拉框实际列出实例配置文件，模板分别创建的 Role 与 Profile 名称不同。当前成功栈为 gtt-foundation-v2，Profile 为 gtt-foundation-v2-InstanceProfile-YtSBp4ypOBlM，内含角色 gtt-foundation-v2-InstanceRole-SEITTr9OZXcM。先复核当前仍未附加其他角色，已有角色时不自动替换。此首次关联是既有外部实例的操作记录，不声称由 CloudFormation 自动接管整台实例。确认 Systems Manager 中实例 Online 后再考虑调整旧运维入口。
2. 把 render_nginx.py 上传服务器的 /opt/gtt/uploads，并生成独立配置：

```sh
python3 /opt/gtt/uploads/render_nginx.py --domain gttgames.com --output /opt/gtt/uploads/gtt-alb.conf
```

3. 确认 8080/8081 没有其他监听。首次将新配置安装到 /www/server/panel/vhost/nginx/gtt-alb.conf，使用 /www/server/nginx/sbin/nginx -t 检查，再通过宝塔重载。存在同名配置时先保存旧版本，不直接覆盖。检查失败不重载，并移出本次新增的配置文件恢复可检查状态。
4. 新配置不更改已有 80/443 站点，不修改数据库、后台账户或 systemd 应用。8080 入口代理 8110，8081 入口代理 8112。各端口默认站点仅给 ALB 健康检查访问 /health；公开 Host 下不开放健康接口。Target Group 均为 healthy 后再创建边缘栈。
5. HTTPS 在 ALB 终止，Nginx 只在已通过 ALB 访问约束的链路上向应用标记 https；保留公开 Host、原始 body/路径、Cookie 和认证头。边缘函数覆盖 X-GTT-Client-IP，ALB 限制 AWS CloudFront 源站前缀并校验随机回源头，Nginx 以该受保护客户端 IP 计限流和转发。不能放开 8080/8081 公网来源。

主机防火墙需与 AWS 安全组分开核验。当前服务器 UFW active / 默认拒绝入站，原规则没有 8080/8081，本机 loopback 健康正常不能证明 ALB 可达。已确认本次 ALB 子网 a=172.31.0.0/20、d=172.31.32.0/20；对当前实例可增加以下两条规则，只允许两个子网到实例私网 IP 的应用入口，不改变既有管理规则：

```sh
sudo ufw allow proto tcp from 172.31.0.0/20 to 172.31.34.87 port 8080:8081 comment 'GTT ALB us-east-1a'
sudo ufw allow proto tcp from 172.31.32.0/20 to 172.31.34.87 port 8080:8081 comment 'GTT ALB us-east-1d'
sudo ufw status verbose
```

UFW 不识别 AWS 安全组身份，上述来源范围是 ALB 子网；AWS 实例安全组仍需限定 SourceSecurityGroupId 为实际 ALB SG。更换子网/实例私网地址后需同步审阅这些规则。当前规则待用户执行，执行后必须重新读取两个目标组的健康状态；若继续 Timeout，再核对已请求的实际 AWS 安全组规则。

## 第三步：边缘栈与官网

创建 gtt-edge，FoundationStackName 显式填实际成功的基础栈名：当前为 gtt-foundation-v2，不能沿用模板默认的旧失败栈 gtt-foundation；DomainName 填 gttgames.com。模板通过 exports 引用已建资源，PriceClass 默认为全部节点；业务 WAF 首次以 COUNT 观测，SampledRequests 关闭，尚未启用完整请求日志。通过协议与业务回归后再将 WafManagedRulesMode 改为 BLOCK。

官网成品上传基础栈的 WebsiteBucketName，必须有 index.html。上传使用限定的网站发布身份，实例备份角色没有官网写权限。官网桶保持私有，由指定 CloudFront OAC 读取，www 在边缘保持路径与查询参数跳转主域名。游戏启动 HTML 仍由应用处理；美洲野牛 shared/**/index.js 已在素材构建时预处理并通过 S3 提供，详见 [素材迁移记录](GAME-ASSETS.md)。不能将未处理的客户端目录复制为官网。

业务分配包含 play、api、merchant、admin 四个域名，默认 CachingDisabled + AllViewer；只缓存 /assets/*、/shared/*，Host 和全部查询参数在素材缓存键中，MinTTL=0，尊重 no-store/private；自定义请求策略将经边缘覆盖的客户端 IP 转发给源站，但不把它放入素材缓存键。动态错误不缓存，不把错误响应替换成 200。ALB/CloudFront/WAF 完整访问日志保持未启用，应用与 Nginx 日志按无查询参数方式收集。

CloudFront 部署完成并完成临时解析覆盖下的验收后，在 Cloudflare 为 @、www 添加指向官网分配的 CNAME，为 play、api、merchant、admin 添加指向业务分配的 CNAME，全部 DNS-only。@ 使用默认 apex flattening，ACM 验证记录不 flatten。无需创建指向 EC2 的网站 A 记录或 origin 域名。

## 监控、备份与回滚

关联实例 Role 后，按 AWS 官方文档安装签名校验过的 CloudWatch Agent，用基础栈输出 AgentParameterName 中的配置启动。配置提供内存、根盘、RTP 进程数量，以及已脱敏的两个应用日志和 Nginx 无查询参数日志；CPU、实例状态和 ALB 目标健康告警由基础栈创建。RTP 进程数量监控不等于任务进展心跳，后者仍使用应用中的 worker 状态核验。Agent 未安装/启动前，不把内存和磁盘告警当作已经可用。

备份桶、角色与可选失败告警已提供，定时备份任务尚未自动启用。需确定维护窗口，协调停止 gtt-rtp-worker、gtt-admin、gtt-gateway，执行现有 backup.py --services-stopped 生成一致性双库与配置副本，恢复服务，再用实例 Role 上传到备份桶 backups/ 前缀。恢复演练成功后，启用每日任务并将 BackupSuccess 指标（GTT.Backup，InstanceId 维度，成功 1/失败 0）接入告警；启用 EnableBackupMonitoring 后缺少每日指标也会告警。不在未确认窗口时自动停止业务做备份。

应用继续使用带校验清单的版本目录和 current 链接回滚。数据库变更时协调停服务并成对恢复，不能仅回滚一个库。删除栈时按 edge → foundation → certificate 的依赖顺序，两个桶、回源密钥和日志设置 Retain，遗留资源由运维清单追踪，不自动清空。

## 验证与费用边界

本地验证包含 cfn-lint、实际 Nginx 与隔离应用的健康检查、HTTPS 代理标记、Host/命名空间隔离、Secure Cookie、HMAC 启动和余额接口，以及边缘函数的 Node.js 事件测试。服务端 CloudFormation validate-template、账号额度/权限、ALB/CloudFront 实际链路和 CloudWatch Agent、S3 发布/恢复仍需目标 AWS 账号验收；本地通过不代表 AWS 资源已创建或官网已上线。

创建基础栈和边缘栈前，按实际流量估算 ALB 小时/LCU、公网 IPv4、CloudFront 流量/请求、S3 容量/请求/版本、WAF ACL/规则/请求、Secrets Manager、CloudWatch 指标/日志/告警，以及现有 EC2/EBS 的费用。模板没有给出未经核实的固定月费，也没有预开完整请求日志或额外服务器。

官方依据：

- https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html
- https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/restrict-access-to-load-balancer.html
- https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/attach-iam-role.html
- https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Install-CloudWatch-Agent.html
