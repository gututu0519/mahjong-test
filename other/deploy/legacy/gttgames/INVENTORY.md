# GTT AWS 资源盘点

> 目录已重组。当前启动命令与路径见[四目录说明](../../../docs/project-layout.md)；本文中的旧命令保留为历史记录。

状态：2026-10-29，仅记录只读盘点结果。服务器信息来自用户在目标 EC2 运行 inventory_server.py 后提供的输出。尚未读取的 AWS 控制面设置保持待确认，不据此改安全组、DNS、IAM、磁盘或运行中的应用。

## 已确认

| 项目 | 当前值 |
| --- | --- |
| AWS 账号 | 817557336527 |
| 区域 / 实例可用区 | us-east-1 / us-east-1d |
| 实例 ID / 类型 | i-06ce52379f43882db / c7i.xlarge |
| AMI | ami-02a9cdd4e98bc3c78 |
| 弹性公网 IP | 184.195.10.174（用户提供，分配/关联 ID 待控制面确认） |
| 私网 IP | 172.31.34.87 |
| VPC | vpc-0e6c35caa56d37d51 |
| 实例子网 | subnet-01244f025cdf9591b |
| 网卡 | eni-09e1ee411d7ab09b2 |
| 实例安全组 | sg-03dcece50614afd0b |
| 架构 / 逻辑 CPU | x86_64 / 4 |
| Linux 内核 | 7.0.0-1014-aws |
| Python / Node | 3.12.3 / 18.19.1 |
| 宝塔 Nginx | 1.30.6 |
| 文件系统总量 / 剩余 | 95.82 GiB / 91.73 GiB；此数不等于已确认 EBS 卷规格或加密状态 |
| EC2 Instance Profile | IMDS /iam/info 返回 404，当前未附加实例配置文件；不据此推断账号未配置其他 SSM 管理方式 |
| SSM Agent | snap.amazon-ssm-agent.amazon-ssm-agent.service 为 active/running；AWS 控制台托管状态尚未确认 |
| 游戏网关 / 后台 / RTP worker | 三项 systemd 服务 active/running |
| 应用监听 | 127.0.0.1:8110、127.0.0.1:8112；保持本机监听 |

服务器报告的其他监听为 0.0.0.0:22、:80、:888、:28769 与 [::]:22，以及本机 DNS stub。仅凭监听表不能断言安全组允许公网访问这些端口。888 与 28769 对应的具体进程/用途待确认；当前报告没有 443 listener，不能将此前外部 TCP 连通探测当作源站 HTTPS 已部署的证据。

本次 vhost 文件名列表：0.site_total_log_format.conf、0.websocket.conf、phpfpm_status.conf、waf2monitor_data.conf。该列表未出现 GTT 域名站点文件，仍需结合宝塔站点管理和 Nginx 配置核对。

## 实例安全组入站规则

用户提供 sg-03dcece50614afd0b（launch-wizard-4）控制台截图，VPC 与目标实例一致。截图上方显示用户已成功修改规则，本表记录截图中的当前结果，不推断具体哪条在本次被修改。

| 类型 | 协议 / 端口 | 来源 | 盘点结论 |
| --- | --- | --- | --- |
| HTTPS | TCP 443 | 0.0.0.0/0 | 全网放行；本机此前报告无 443 listener，规则放行不等于已部署 HTTPS |
| 自定义 TCP | TCP 28769 | 0.0.0.0/0 | 全网放行；需确认是否为宝塔管理端口，再限定管理来源 |
| SSH | TCP 22 | 198.65.17.87/32 | 限定单个 IPv4；是否仍为当前操作者出口需在后续调整前核对 |
| HTTP | TCP 80 | 0.0.0.0/0 | 全网放行；最终应用入口按 ALB 安全组及实际 Nginx 内部端口授权 |

可见入站共 4 条，均为 IPv4。用户随后明确确认出站只有 1 条：所有流量，目标 0.0.0.0/0。因此实例安全组出站为允许所有 IPv4 流量；不据此推断子网路由、网络 ACL 或实际公网可达性。目前不调整任何规则；后续新建 ALB 来源安全组并验证运维通道后，再按最终入口方案收窄实例业务与管理端口。

## 待确认的控制面项目

### VPC 资源地图已确认

用户随后提供 VPC 详情和资源地图截图，确认 vpc-0e6c35caa56d37d51 为默认 VPC，状态 Available，IPv4 CIDR 为 172.31.0.0/16，无 IPv6 CIDR，DNS 解析和 DNS 主机名均已启用，VPC 阻止公共访问设置显示关闭。主路由表为 rtb-086967aac6b7fb55e，主网络 ACL 为 acl-006d4bf049e88e0a6。

| 可用区 | 子网 ID | 已知用途 |
| --- | --- | --- |
| us-east-1a | subnet-0f6a6017d1d739b27 | 第二 ALB 可用区候选，待容量/路由检查 |
| us-east-1b | subnet-0ca1b3ef89516a94f | 现有子网，尚未选作本项目 ALB 子网 |
| us-east-1c | subnet-0e5f0c7a590589d32 | 现有子网，尚未选作本项目 ALB 子网 |
| us-east-1d | subnet-01244f025cdf9591b | 当前 EC2 所在子网，ALB 子网候选 |
| us-east-1e | subnet-005780017cd6c391b | 现有子网，尚未选作本项目 ALB 子网 |
| us-east-1f | subnet-0b013caf86f6f8fce | 现有子网，尚未选作本项目 ALB 子网 |

资源地图显示 6 个子网连接同一张路由表，VPC 网络连接中有 1 个 Internet Gateway。截图中 IGW ID 不完整，因此不记录推测的完整 ID。路由具体目的地/目标/状态尚不可见，不能只凭资源地图把候选子网确认为满足公网 ALB 的公有子网。各子网 CIDR、可用 IPv4 数量以及关联网络 ACL 的实际规则仍待核对。

用户随后确认该路由表有 6 个子网关联、2 条路由（其中包含 local），并明确表示这些网络条件没有问题。因此后续按用户确认网络可用推进，不继续要求路由/子网逐项截图；该确认不改写为已独立读取第二条路由、全部 CIDR 或可用 IP 数。创建 ALB 前由可用的只读部署身份自动预检选定子网和路由，发现硬性条件不满足时再处理，不因本轮盘点修改既有网络。

### 后续读取清单

| 顺序 | 内容 | 所需信息 / 读取范围 |
| --- | --- | --- |
| 1 | 管理端口核对 | 入站 4 条、出站所有流量至 0.0.0.0/0 已确认；28769 用途与当前操作者管理出口仍待确认 |
| 2 | ALB 候选子网条件 | 用户确认网络可用；采用 us-east-1d 与 us-east-1a 为候选，具体 CIDR/可用 IP/路由改为创建前自动预检，不继续索取逐项截图 |
| 3 | 网络 ACL | 实例子网与候选 ALB 子网的关联 ACL、入站/出站规则 |
| 4 | EBS / EIP | 实例关联的卷 ID、容量、类型、加密/KMS、删除行为；弹性 IP 分配/关联 ID 与目标 ENI |
| 5 | 现有 GTT AWS 资源 | CloudFront ID/aliases、官网/备份 S3、us-east-1 ACM 状态、ALB/TG、WAF、SSM Managed Node、CloudWatch；没有输出不等于没有资源 |
| 6 | DNS 与官网 | Namecheap Host Records、CAA、既有验证记录和官网成品目录/产物；当前不切换解析 |

本地现有命名 profile 对目标实例 DescribeInstances 已被 UnauthorizedOperation 拒绝。暂由用户当前控制台身份提供范围内的只读信息；不索取 AWS 长期密钥、SSH 私钥、面板密码、商户密钥或数据库原文。

## 对后续实施的影响

- 用户在 AWS CloudShell 执行 cloud_preflight.py 后提供完整输出：status=passed、warnings=[]，已生成 foundation-parameters.json，读取身份账号为 817557336527。已保存报告于本机忽略目录 diagnostics/aws-preflight-20261029.json，并将不含密钥的基础栈参数记录在 aws/foundation-parameters.json。该步骤未修改 AWS 资源。
- 本次控制面输出确认：us-east-1d 子网 subnet-01244f025cdf9591b 的 CIDR 为 172.31.32.0/20、4084 个可用 IPv4；us-east-1a 子网 subnet-0f6a6017d1d739b27 的 CIDR 为 172.31.0.0/20、4087 个可用 IPv4。两者均通过 rtb-086967aac6b7fb55e 的 active 0.0.0.0/0 路由指向已附加 IGW igw-069cedff13815b609。
- 网络 ACL acl-006d4bf049e88e0a6 为默认 ACL；入/出 IPv4 第一条规则均为 100 allow all，32767 为末尾 deny。现有安全组规则与此前记录一致。
- EBS 卷 vol-07e44d82886c2f88a 为 gp3、100 GiB、Encrypted=true；KMS ARN 为 arn:aws:kms:us-east-1:817557336527:key/f82b6c2c-2c89-438c-938c-a3ea5737ef1e。实例控制面 InstanceProfile 为空。CloudFront 源站托管前缀列表为 pl-3b927c52。
- 基础设施仍未创建；下一阶段先创建 gtt-foundation 的 CREATE 变更集，核对服务端校验、资源增量与费用项后才执行。原实例、数据库、DNS 与既有运维入口保持当前状态。
- 用户随后在 CloudShell 运行 validate-template 成功，AWS 返回 CAPABILITY_IAM，接着成功提交 CREATE 变更集。变更集 ARN：arn:aws:cloudformation:us-east-1:817557336527:changeSet/gtt-foundation-initial/ee5434ec-4c60-4218-94e4-6620e7cab629；栈 ARN：arn:aws:cloudformation:us-east-1:817557336527:stack/gtt-foundation/0e0cb2c0-d3c4-11f1-ac94-0affc131550f。尚未收到 describe-change-set 的最终状态/清单，也尚未执行 ExecuteChangeSet。
- 用户随后提供 describe-change-set 输出：Status=CREATE_COMPLETE，ExecutionStatus=AVAILABLE，Reason=null，26 项全部 Add，与模板在默认条件下的资源集一致，没有 Remove/Modify 或 EC2 实例资源。GatewayIngress/ConsoleIngress 虽作为 Add 资源显示，执行时会给现有实例安全组新增 ALB 来源的 TCP 8080/8081 两条授权，保持旧管理规则。尚未收到 ExecuteChangeSet 或资源创建完成结果。费用核对见 aws/COSTS.md。
- 用户执行创建后提供控制台截图，gtt-foundation 显示 ROLLBACK_IN_PROGRESS。创建已失败并进入自动回滚，底层 CREATE_FAILED 原因待查询，不推断为权限、额度、ALB 或模板错误。当前不重复 ExecuteChangeSet、不删除栈、不重新初始化应用。修复前还需核对已创建/回滚/Retain 的资源，避免遗留桶、日志或密钥被重复创建后失去追踪。
- 用户随后提供失败事件：2026-10-29T18:16:34.787Z BackupBucket、18:16:35.023Z WebsiteBucket 均因 s3:PutBucketPublicAccessBlock 被 Organizations SCP 显式拒绝。调用身份 arn:aws:iam::817557336527:user/aws；策略 ARN arn:aws:organizations::734130320423:policy/o-jgkzt3731v/service_control_policy/p-rpz4cfcf。失败桶物理名分别为 gtt-foundation-backupbucket-gkey3lhv1ajm、gtt-foundation-websitebucket-5q89fgxgjfpz。其余所贴失败原因为 Resource creation cancelled，是连带取消，不能认定各自另有权限问题。SCP 内容、条件、组织管理员归属未知；暂停后续基础栈重试与边缘部署，保留全部桶安全配置，先核对允许的部署方式、回滚结果与遗留资源。已有只读预检与变更集未验证实际写权限。
- 用户随后明确没有组织管理权限，并提供 S3 桶列表截图：上述两个 gtt-foundation 桶均仍存在于 us-east-1，创建时间分别为 2026-10-29 14:16:34、14:16:35 EDT，与失败事件吻合。由模板执行创建到桶后，后续安全配置动作失败；列表存在不能证明公共访问阻止、版本控制、加密、所有权、生命周期等完整配置已成功。此前建议另建两个手动桶过早，当前先读取这两个现有桶配置和栈最终状态，不要求重复创建。截图另有 cf-templates-97sz5i8g50w7-us-east-1，未检查内容或生命周期，不对该桶执行修改/删除。
- 用户随后提供只读命令结果：gtt-foundation 已 ROLLBACK_COMPLETE；两个遗留桶的 BlockPublicAcls、IgnorePublicAcls、BlockPublicPolicy、RestrictPublicBuckets 全部为 true。无需重新设置四项保护。新准备的 aws/02-foundation-existing-buckets.json 引用这两个现有桶，不创建或更改桶配置；尚未提交/执行。aws/recovery_preflight.py 将读取桶完整配置与旧栈资源摘要，先核对配置缺项/桶策略冲突/其他遗留资源，再决定新恢复栈变更集。版本控制、加密、所有权、生命周期和其他遗留资源仍未收到目标账号读取结果；不能把本次 BPA 成功读数扩展为完整部署成功。详见 aws/RECOVERY.md。
- 用户上传恢复包并提供 recovery_preflight.py 完整输出：status=passed、issues=[]、两桶 errors=[]。两桶均为当前账号 us-east-1、全部 BPA=true、Versioning=Enabled、AES256 SSE-S3、BucketOwnerEnforced、全桶 AbortIncompleteUploads=7 天，无额外生命周期规则且无桶策略。旧栈资源摘要保留四项 DELETE_SKIPPED：两个上述桶、日志组 /gtt/gtt-foundation/application、回源密钥 arn:aws:secretsmanager:us-east-1:817557336527:secret:OriginSecret-3CjWVoPBBpHN-ywmJXT；日志/密钥尚未逐项直接读取其物理状态。只读报告归档 diagnostics/aws-recovery-preflight-20261029.json。下一步提交新栈 gtt-foundation-v2 的 gtt-foundation-recovery CREATE 变更集预览，默认条件下预计 24 项 Add，无 AWS::S3::Bucket；恢复栈将创建独立日志组和回源密钥，旧日志/密钥保留追踪、核对后安排清理，不在预览时删除。尚未收到该新变更集提交/预览或执行结果。
- 用户随后提供恢复变更集：arn:aws:cloudformation:us-east-1:817557336527:changeSet/gtt-foundation-recovery/22242733-d438-41e9-82e3-71b5fba35ed4；新栈 arn:aws:cloudformation:us-east-1:817557336527:stack/gtt-foundation-v2/34e4f990-d3c7-11f1-b4de-0edd9a39b38d。Status=CREATE_COMPLETE、ExecutionStatus=AVAILABLE、Reason=null，24 项全部 Add，与复用版默认资源集吻合，无 AWS::S3::Bucket、无 EC2 实例替换。BackupBucketPolicy 会为现有备份桶添加 TLS 要求；GatewayIngress/ConsoleIngress 会给原实例安全组新增仅允许 ALB 的 8080/8081 授权。变更集审阅通过，可进入执行；尚未收到执行或栈创建完成结果。
- 用户随后执行恢复变更集并提供 gtt-foundation-v2 的 CREATE_COMPLETE 与 16 项 Outputs，已保存 aws/foundation-v2-outputs.json。ALB DNS 为 gtt-fo-LoadB-1UAP5uxaLR4S-2096295513.us-east-1.elb.amazonaws.com，ALB SG 为 sg-052c0213ec35d6a83；Profile 为 gtt-foundation-v2-InstanceProfile-YtSBp4ypOBlM，内含 Role gtt-foundation-v2-InstanceRole-SEITTr9OZXcM。网关 TG gtt-fo-Gatew-M0AUSGVCG6AF/cc99c7c3a282285c，后台 TG gtt-fo-Conso-RMBU0D963CBT/1c93320440368bde。新日志组 /gtt/gtt-foundation-v2/application、新 Agent 参数 /gtt/gtt-foundation-v2/cloudwatch-agent 与新回源密钥 ARN 已记录，未读取密钥原文。基础栈完成不等于 Profile 已关联或目标健康；下一步手动关联现有 EC2 的 Profile 并核对 SSM Online，再配置 Nginx。尚未收到角色关联、两个 TG healthy、CloudFront/官网/DNS 或监控/备份任务验收结果。旧日志/密钥仍留在遗留资源清单，不在本步删除。
- 用户随后提供 CloudShell 截图，多次以 InstanceIds=i-06ce52379f43882db 查询 us-east-1 的 SSM managed node 均返回 []。尚不能据此认定 Profile 已关联、Agent 正常注册或组织已允许 SSM 写操作；也没有证据归因于 Nginx/应用。下一步读取 EC2 实际 IamInstanceProfile，结合原盘点已确认的 snap.amazon-ssm-agent.amazon-ssm-agent.service，对该 Agent 单独重启并检查运行状态；不重启 EC2 或游戏服务。必要时再按实际错误检查 Agent 日志、IAM/SCP 或 SSM 出站连通性，不重复索取已确认网络截图。
- 用户随后提供实际读取结果：EC2 的 IamInstanceProfile.Arn 为 arn:aws:iam::817557336527:instance-profile/gtt-foundation-v2-InstanceProfile-YtSBp4ypOBlM，关联正确；SSM 返回该实例 PingStatus=Online、AgentVersion=3.3.4793.0，实例身份关联与 SSM 在线检查通过。未提供 Agent 重启命令结果，不推断是否重启过。已由 render_nginx.py 生成 diagnostics/releases/gtt-alb-20261029.conf 待上传 EC2，当前进入 Nginx 8080/8081 端口、既有配置和目标文件冲突检查，尚未确认安装/重载或两个目标组 healthy。
- 用户在 EC2 执行 ss 过滤 8080/8081，仅返回表头，确认检查时两端口无监听；/www/server/nginx/sbin/nginx -t 对 /www/server/nginx/conf/nginx.conf 返回 syntax is ok / test is successful。下载配置与已验证生成器逐字一致，SHA-256=f1b6ceca36470b2ac2694642d27c8da7be1f27a57b25bffad3d77d061f682e51。进入安装新 vhost → 语法检查 → graceful reload → 本机两入口健康检查的阶段，缺少源文件或已有目标配置时停止，失败语法检查时移出本次新增配置，不覆盖既有站点。尚未收到上传文件确认、安装/重载或健康检查结果。
- 首次安装因源文件尚未上传而在写入前停止；用户随后上传并重跑安装，提供两次 Nginx 语法检查成功与重载后两入口健康结果：127.0.0.1:8080/health 返回 gtt-gateway status=ok、HTTP 200，127.0.0.1:8081/health 返回 gtt-admin status=ok、HTTP 200。8080 的第一次 curl 连接被拒绝后通过既有重试成功，与重载监听切换阶段相符，未出现最终健康检查失败。配置已安装到 /www/server/panel/vhost/nginx/gtt-alb.conf，本机 Nginx 到两后台健康链路通过；ALB 两个目标组的实际 TargetHealth 仍待 CloudShell 读取，不以本机 HTTP 200 代替 ALB 健康验收。
- 用户随后读取网关 TG：i-06ce52379f43882db:8080 State=unhealthy、Reason=Target.Timeout、Description=Request timed out。后台 TG 命令已贴出但结果尚未收到，不能认定 8081 同样超时。继续核对真实 ALB/实例安全组入出站、Nginx 监听地址与 Ubuntu/宝塔主机防火墙；本机 200 不等于远端路径通畅，模板中的安全组声明也不能代替实际规则。暂不部署 edge 或切 DNS，不放宽 8080/8081 至公网，不修改游戏服务/数据库。
- 用户随后补齐两组查询：网关 8080 与后台 8081 的 Target 均为 i-06ce52379f43882db，均 unhealthy / Target.Timeout / Request timed out。两端口的共同 ALB→EC2 路径优先排查，但尚不能断言主机防火墙或安全组已被确认是原因。已请求的两个实际安全组规则、当前 ss 监听地址、ufw 状态与 iptables filter 规则尚未收到；等待这些诊断输出后进行有证据的修复。
- 用户最新终端附件 f9fe9401-3398-4d62-b744-ad1fd142c4fc/已粘贴的文本.txt 确认：Nginx 正在 0.0.0.0:8080/8081 监听；UFW active，默认 deny incoming，iptables INPUT DROP；ufw-user-input 仅放行既有 20/21/22/80/443/888/8888/28769/39000:40000，没有 8080/8081，也没有其他允许 ALB 来源的规则。loopback 在 ufw-before-input 中允许，解释了本机 200 与远端丢弃可同时存在。已确认主机防火墙为实际阻断点之一，AWS 两个安全组实际读取结果仍未收到。根据此前控制面确认的 ALB 子网 us-east-1a=172.31.0.0/20、us-east-1d=172.31.32.0/20，下一步仅新增这两个来源到本机 172.31.34.87 TCP 8080:8081 的 UFW 允许规则，保留防火墙与其他规则，之后重查 ALB 健康。UFW 按子网 CIDR 识别来源，AWS SG 仍须仅允许 ALB SG；不把子网放行误写为主机防火墙识别了 ALB SG。规则执行与目标恢复尚待确认。
- 随后用户从 CloudShell 查询两个目标组，8080、8081 均 State=healthy、Reason=null，ALB→EC2→本机两应用的健康链路验收通过。未提供 UFW 新规则列表或实际 AWS 安全组输出，因此不据健康结果扩展声称已完成全部防火墙规则审计。当前推进 gtt-edge / gtt-edge-initial CREATE 变更集预览，显式 FoundationStackName=gtt-foundation-v2、DomainName=gttgames.com、PriceClass=PriceClass_All、WafManagedRulesMode=COUNT；参数另存 aws/edge-parameters.json。预计 10 项 Add（2 CloudFront、OAC、2 缓存策略、来源请求策略、2 函数、WAF、官网桶策略），尚未提交/执行边缘栈，也未切换 DNS 或上传官网成品。
- 用户随后提交边缘变更集并收到 ARN：arn:aws:cloudformation:us-east-1:817557336527:changeSet/gtt-edge-initial/eebad0a9-33a1-4185-ab34-a282cc7a4700；栈 ARN：arn:aws:cloudformation:us-east-1:817557336527:stack/gtt-edge/407e0ae0-d3cb-11f1-9bba-12ffcd982a93。当前仅确认 create-change-set 接受请求，尚未收到 wait 结束或 describe-change-set 的最终状态/10 项清单，不能声称已通过预览或已创建 CloudFront/WAF，暂不执行变更集。
- 用户随后提供 gtt-edge-initial 最终预览：Status=CREATE_COMPLETE、ExecutionStatus=AVAILABLE、Reason=null，10 项全部 Add，逻辑资源与已验证 03-edge.json 完全一致：AssetOriginPolicy、BusinessDistribution、BusinessWaf、GameAssetCache、ViewerIpFunction、WebsiteBucketPolicy、WebsiteCache、WebsiteDistribution、WebsiteFunction、WebsiteOac。变更集审阅通过，下一步执行该变更集；WAF 为 COUNT，FoundationStackName 显式指向 gtt-foundation-v2，无 DNS 资源或应用/数据库修改。执行会增加 CloudFront 与 WAF 相应用量/规则费用，不能把基础栈的部分费用小计作为整套月费。尚未收到 ExecuteChangeSet、栈完成或边缘链路验收结果。
- 用户随后执行边缘变更集并提供 gtt-edge CREATE_COMPLETE 和五项 Outputs，已保存 aws/edge-outputs.json：业务 CloudFront E3RCHQALSXUQDV / ds4bqnhfevccf.cloudfront.net；官网 CloudFront E1N2M7RKXRR940 / df79mrkarlfs7.cloudfront.net；业务 WAF ARN arn:aws:wafv2:us-east-1:817557336527:global/webacl/BusinessWaf-LK6wQlKsFfcJ/dc8866a6-defa-4d26-9e29-9b4b91d3afb3。两个基础设施栈已完成，但公网业务链路仍待验收，DNS 未切换。
- 用户通过异步问题明确“还没有”官网成品。项目本地初步检索仅找到游戏客户端/试玩大厅/抓取工具页面，没有已确认的正式品牌官网。根域名和 www 暂保留当前解析，不能用占位页冒充官网成品或宣布官网上线；官网内容需另行确认并实现/提供。业务四个子域名的切换也必须先完成边缘验证。
- 本机尝试通过 curl.exe --connect-to 将四个业务正式域名连接新 CloudFront，均在 TLS 握手阶段失败（schannel 错误35 / HTTP 000）；随后以 Python SSL 验证 admin.gttgames.com 的原始 SNI 直连相同分配也得到 SSLEOFError，未得到 HTTP 响应。两种检查均保持证书校验，没有改 DNS、绕过 TLS 校验或读取私密数据。这尚不足以确定 AWS 配置故障，需从用户 CloudShell 复核正式域名 + connect-to 的响应，再区分本机网络限制与边缘配置问题；本机检查不能记录为 passed。
- 用户随后从 CloudShell 通过原正式域名的 curl --connect-to 两轮验证：admin/merchant 的 /deployment.json 均 HTTP 200，portal 分别正确且三个公开 URL 均为既定 HTTPS 域名；api 的 POST /gtt/v1/games/list 空凭据返回 AUTH_INVALID / HTTP 401；play 的 GET /api/v1/wallet 无会话返回 SESSION_INVALID / HTTP 401。四项基本 TLS/Host/边缘函数/ALB/应用路由与未认证拒绝检查通过；未验证真实登录、签名商户调用、完整游戏回合、缓存隔离或客户端访问地区的可用性，不宣称全部生产验收完成。当地本机 TLS 失败仍不能记为已恢复。
- 此后本机 Resolve-DnsName 查询根域 NS 返回 arturo.ns.cloudflare.com 与 nelly.ns.cloudflare.com，已观测到 Cloudflare NS，替代此前 Namecheap NS 的旧查询快照；Cloudflare 控制台 zone Active 状态及其他递归解析器仍未独立读取。下一步在 Cloudflare 为 play/api/merchant/admin 添加或更新同名业务 CNAME 到 ds4bqnhfevccf.cloudfront.net，DNS-only 灰云，TTL 自动，根域/www、邮件及 ACM 验证记录保持当前配置。业务 DNS 尚待用户执行并回传，不能据 connect-to 测试认定 DNS 已切换。
- 用户随后提供 Cloudflare DNS 截图，四个业务子域均 CNAME、DNS-only、TTL 自动，目标在截图中截断；邮件和 ACM CNAME 仍可见，未看到根域/www 网站记录。实际查询 merchant/api/play CNAME 均为 ds4bqnhfevccf.cloudfront.net；admin 初次本机 Resolve-DnsName 仍报 NXDOMAIN，但 Google DNS 与 Cloudflare DoH 随后均返回 admin.gttgames.com CNAME 到同一正确分配（Status=0、TTL=300），不能据本机一次 NXDOMAIN 断言配置错误。
- 切换后本机以普通 URL（无 connect-to、不关闭证书校验）请求：merchant /deployment.json=200，portal=merchant，Cache-Control=no-store，响应带 CloudFront Via/X-Cache；api POST /gtt/v1/games/list=401 AUTH_INVALID；play /api/v1/wallet=401 SESSION_INVALID。三项通过。admin 的普通请求与再次 connect-to 均仍出现 schannel 35 / HTTP 000，未取得 HTTP 响应；原因尚未确定，不能直接断言只是缓存、证书配置错误或网站故障。CloudShell 在切换前已两次验证 admin connect-to 200，但切换后普通域名的 admin 验证仍需补充，同时由用户浏览器确认登录页可达。DNS 四条已配置，不等于全部客户端可用或真实登录/游戏业务验收完成。
- 用户随后从 CloudShell 直接请求 https://admin.gttgames.com/deployment.json（不使用 connect-to）得到 HTTP 200、portal=admin、既定 HTTPS URL 正确，并反馈网页可以打开。admin 普通域名在该环境的 DNS/TLS/回源基本检查通过；此前本机环境的 TLS 失败没有新的本机测试结果，不据此认定所有网络客户端问题已解决。实际账户登录、商户签名请求和完整游戏回合仍未验收。
- 用户询问 S3 目前未用上的原因。明确当前部署只完成两桶基础设施/访问配置，尚无官网成品上传，且一致性备份定时任务与上传/恢复演练尚未接入。业务游戏客户端与素材仍由 EC2 应用处理，CloudFront 缓存指定素材路径；实时数据在 EC2 本机 SQLite。不能把已建官网/备份桶表述为已有官网内容、已有自动备份，或宣称游戏素材已经迁到 S3。未读取对象清单，不据此断言桶内绝对无对象。
- 用户随后明确授权游戏静态素材迁移到独立 S3/CloudFront，并说明本机已有 AWS 配置可上传。已读取本机 profile 列表，只有 sds-test；默认无凭据，显式 sds-test STS 确认账号 817557336527、IAM 用户 gututu。该身份 S3 可用，但 cloudfront:GetDistribution 与 cloudformation:DescribeStacks 分别被 identity-based policy 未授权拒绝，因此边缘栈继续使用用户已有 CloudShell 身份操作，未尝试扩大权限或读取密钥。
- 从线上已安装 gtt-release-20261029-baota.zip 的校验清单构建美洲野牛静态产物，模块处理器与包内源码逐字匹配，shared/**/index.js 预先运行同一 prepare_module 与 Node 初始化校验；覆盖 assets/shared 和 31 个根目录静态文件，排除 fixtures、HTML 入口及非静态开发文件。发布 ID 2e8b417be6a438768bc4，374 个文件、38,302,587 字节。原客户端和所有其他本地游戏入口没有修改。
- 本机身份成功创建专用桶 gtt-game-assets-817557336527-us-east-1（此前 HeadBucket=404），以 S3 默认全开公共访问保护方式创建并读回核验；未调用被 SCP 拒绝的 PutPublicAccessBlock，也未放宽保护。已核验 us-east-1、四项 BPA 全 true、BucketOwnerEnforced、AES256、版本控制 Enabled、全桶 7 天中止未完成分段上传。桶配置由发布工具管理，尚未导入 CloudFormation；计划 OAC/桶策略由现有 gtt-edge 管理。
- 已将 374 个对象上传 releases/buffalo-win/2e8b417be6a438768bc4，逐个用 S3 返回 SHA-256、长度、MIME、缓存头和元数据核验通过，全部完成后提交 _gtt-manifest.json；清单 SHA-256 56e389e7a8fbe1d22576332cbbf2a1279928c8f3722d8e2231a0158288e2375f。匿名 S3 对象 GET 实测 403。回执 diagnostics/releases/gtt-game-assets-2e8b417be6a438768bc4/upload-receipt.json。
- 同一 374 文件经普通 HTTPS 从现有 play.gttgames.com 下载，SHA-256/长度/兼容 MIME 全部与构建产物一致，verify-baseline.json=passed。新迁移 10 项测试加原 Nginx 入口 4 项测试通过；prepare/activate 两份 CloudFormation 模板经 cfn-lint us-east-1 检查无错误/警告。当前 CloudFront 完全未改、业务仍走原素材源站。
- 迁移分为 prepare（Add OAC、S3 缓存策略、游戏域名函数、素材桶策略，Modify 现有 BusinessDistribution 增加 S3 源站和 /__gtt-assets-check/* 校验路径）与 activate（完整 CDN 校验通过后只修改 BusinessDistribution 的正式静态路由）。精确 root 路径加 assets/shared 合计 34 个行为；动态默认行为、后台、官网分配、DNS、ALB/EC2 及数据库保留。CloudShell 操作脚本在创建变更集前核对实际栈/模板/账号/分配/已提交 S3 清单与对应全量验证报告。尚未提交 prepare 变更集、配置 OAC 或切正式素材路径，详见 aws/GAME-ASSETS.md。
- 用户随后上传素材迁移包并在 CloudShell 执行 asset_change_set.py prepare，返回 submitted=true、executed=false、phase=prepare。变更集 gtt-assets-prepare-2e8b417be6a4，ARN arn:aws:cloudformation:us-east-1:817557336527:changeSet/gtt-assets-prepare-2e8b417be6a4/cbfbb0f1-ea06-41f6-959e-2bc3b5051bbb，目标为既有 gtt-edge / 407e0ae0-d3cb-11f1-9bba-12ffcd982a93。脚本前置栈/账号/分配/原模板一致性、S3 已提交清单校验和全量基线报告核对通过后才提交。当前仅确认已接受创建变更集，尚待最终 describe-change-set 预览与执行；不据 submitted=true 认定 OAC 或 S3 正式回源已生效。
- 用户随后提供 prepare 最终预览：CREATE_COMPLETE / AVAILABLE，Reason=null。Modify BusinessDistribution、Replacement=False；Add GameAssetFunction、GameAssetsBucketPolicy、GameAssetsOac、GameS3Cache，准确为预期 4 Add / 1 Modify，无 Remove 或其他变更。预览审阅通过，下一步 ExecuteChangeSet，等待 gtt-edge UPDATE_COMPLETE（本阶段为 UPDATE），随后用 game_assets.py verify --phase probe 全量校验；尚未收到执行、更新完成或探针结果，正式素材路径仍未切换。
- 用户随后执行 prepare，等待 UPDATE_COMPLETE 后运行全量 probe，返回 status=passed、phase=probe、release=2e8b417be6a438768bc4、manifest_sha256=56e389e7a8fbe1d22576332cbbf2a1279928c8f3722d8e2231a0158288e2375f、checked=374、errors=[]、tls_validation=true。七项路由检查均符合预期：admin/merchant deployment 200，API 空凭据与游戏钱包无会话 401，admin/merchant/api 访问同一素材校验路径 404。确认 S3 OAC 经业务 CloudFront 的全量校验路径与域名隔离通过，正式素材路径尚未切换。下一步 asset_change_set.py activate 提交变更集，预期仅 BusinessDistribution Modify / Replacement=False；尚未提交或执行 activate。
- 用户随后执行 asset_change_set.py activate，返回 submitted=true、executed=false、phase=activate；变更集 gtt-assets-activate-2e8b417be6a4，ARN arn:aws:cloudformation:us-east-1:817557336527:changeSet/gtt-assets-activate-2e8b417be6a4/a4eba270-877d-47c0-a81c-2c30d36b2455，仍指向既有 gtt-edge 栈。脚本对应的当前 prepare 模板、S3 清单与全量 probe 报告守卫检查已通过；尚未收到最终预览状态或资源清单，activate 尚未执行，正式路径未确认切换，不重复提交该变更集。
- 用户随后提供 activate 的最终预览：Status=CREATE_COMPLETE、ExecutionStatus=AVAILABLE、Reason=null，唯一变更 BusinessDistribution Modify / Replacement=False，与预期完全一致。已核对通过，下一步执行 activate，等待 UPDATE_COMPLETE，再使原先走缓存的 /assets/*、/shared/* 失效，等待失效完成，运行 verify --phase active 全量验证正式 URL。31 个根静态路径此前用默认禁缓存行为，因此首次切换只需对原有两个素材前缀失效。尚未收到执行、缓存失效或正式路径验证结果，不认定迁移完成。
- 用户随后执行 activate → 等待 UPDATE_COMPLETE → 创建并等待静态缓存失效 → active 校验，返回 passed / active、release=2e8b417be6a438768bc4、manifest_sha256=56e389e7a8fbe1d22576332cbbf2a1279928c8f3722d8e2231a0158288e2375f、checked=374、errors=[]、tls_validation=true。两个后台 /deployment.json=200，API 空凭据/游戏无会话=401，admin/merchant/api 请求根素材 /0aa2dd1614.bda0d.png 均 404。确认正式素材路径切到目标 S3 发布版本；缓存失效 ID 未单独返回，但后续命令链成功执行验证，未推测 ID。
- 本机进一步读取同一正式 PNG 两次，HTTP 200，目标发布元数据正确，X-Cache 从 Miss from cloudfront 转为 Hit from cloudfront、Age=1，Cache-Control=public, max-age=300, s-maxage=86400；匿名 S3 对象 GET=403。回执 diagnostics/releases/gtt-game-assets-2e8b417be6a438768bc4/post-activation-check.json。美洲野牛本次静态素材迁移验收完成，EC2 原文件保留回退；启动 HTML 与认证/钱包/下注/结算接口仍回源 ALB/EC2。有凭据的真实游戏启动、音效与完整回合还未执行，不声称所有游戏/整套生产上线验收已完成。后续 CloudFront 维护必须基于 active 模板或实际栈，不能直接用原始 03-edge.json 覆盖回旧路由。
- 用户询问截图中三个桶用途，已通过 sds-test 对四个已知桶执行只读 ListObjectsV2 分页盘点（未下载任何备份内容）。cf-templates-97sz5i8g50w7-us-east-1 当前 1 个对象、874 字节，键 2026-10-29T174140.551Z96a-01-certificate.json；备份桶当前对象数 0；官网桶当前对象数 0；新游戏素材桶当前 375 个对象、38,460,620 字节，为 374 素材与发布清单，均在既定版本前缀下。盘点归档 diagnostics/aws-s3-bucket-inventory-20261029.json。没有执行账号级全桶枚举，不据此断言账号总桶数只有四个；对象数指当前版本列表，未枚举历史版本。
- 用户随后询问可删除的桶（并未明确授权执行删除）。对 cf-templates-97sz5i8g50w7-us-east-1 列举对象版本，只有该 874 字节模板的 null 版本，没有删除标记或其他历史版本；下载归档至 diagnostics/aws-template-archive/01-certificate-20261029.json，SHA-256 50b6630e09aa7948d09a80a1164095a3c1e9955a5c668e4caf608ef18393d8f8，与仓库 01-certificate.json 逐字相同，仅一个 ACM Certificate 资源。已知应用/源站链路不使用此模板桶，可列为归档后清理候选；备份桶、官网桶均仍有部署引用/规划用途，游戏素材桶正在使用，应保留。归档清单 diagnostics/aws-template-archive/inventory.json 标记 deleted=false，没有删除任何对象/桶、栈或证书。
- 用户询问商户能否正常接入。当前确认域名、TLS、CDN/ALB/应用基本路由和未认证拒绝、游戏静态加载链路通过；项目接入文档实现 HMAC 商户 API、启动前查询外部权威钱包、扣款/派奖/退款/交易查询及幂等恢复，当前商户游戏链路范围为 Buffalo Win（game_id=1）。隔离测试已有成功签名启动/余额和会话检查，但未使用真实部署商户执行线上签名目录/launch、商户钱包回调、实际游戏整局、故障重试与对账。只能称已具备开展接入联调的网络/接口基础，不能宣布正式商户上线验收通过；自动备份/恢复与告警接收也仍待完成。未创建或修改任何正式商户、玩家、凭据或资金记录。

- 用户完成证书步骤，提供 ACM 截图显示 gttgames.com 与 *.gttgames.com 验证成功、证书已颁发，并提供完整 ARN：arn:aws:acm:us-east-1:817557336527:certificate/5d173d56-6bc3-4e29-923e-6a9c84a6091b。账号和区域与本项目相符，后续基础栈使用该 ARN，不重复申请证书。CloudFormation 证书栈最终状态尚未单独提供；源站/边缘实际关联与链路验证尚未执行。

- 用户明确回复 GTT 目前“只有一个服务器”，因此本项目 ACM、CloudFront、S3、ALB、WAF 等按待新建资源处理；现有 EC2 与其应用/数据复用，不推断整个账号没有其他项目资源。已开始准备 aws/ 下的三阶段 CloudFormation 栈，尚未在目标账号创建。

- 用户随后提供 Cloudflare DNS 页面：当前可见 6 条 MX/TXT 邮件记录，全部 DNS-only。未看到网站 A/CNAME 或橙云记录，不能据截图认定网站已由 Cloudflare HTTP 代理。最近递归 NS 查询仍为 dns1/dns2.registrar-servers.com，仅作观测，Cloudflare 权威委派是否生效待 zone 状态及进一步查询确认。DNS 托管采用 Cloudflare 时网站和 ACM 验证记录统一 DNS-only，CDN 仍为 AWS CloudFront；主域名记录类型改用 Cloudflare CNAME/apex flattening。

- 可复用现有实例及三个后端进程；不需要因本次盘点重装系统或清空数据库。
- 创建 ALB 前先确认两个可用区的公有子网和路由，不能仅凭当前单个 EC2 子网开始创建。
- 实例身份、S3 备份与监控权限尚未配置/验收；Agent 在运行不等于已接入 Systems Manager。
- 后续业务入口、TLS 代理元数据和健康检查适配尚未执行，当前只完成应用本机运行验证。
- Node 18.19.1 满足既有最低版本检查；上线前应单独完成受维护 LTS 版本升级与客户端模块处理回归，不在盘点期间直接升级。

架构与执行顺序见 [AWS 标准化部署方案](AWS-DEPLOYMENT.md)。
