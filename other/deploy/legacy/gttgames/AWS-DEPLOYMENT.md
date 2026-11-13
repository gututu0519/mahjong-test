# AWS 标准化部署方案与执行顺序

> 目录已重组。当前启动命令与路径见[四目录说明](../../../docs/project-layout.md)；本文中的旧命令保留为历史记录。

状态：2026-10-29 用户确认按本文 AWS 方案执行，本项目复用一台现有 EC2。恢复栈 gtt-foundation-v2 与边缘栈 gtt-edge 均已部署；实例 Profile 已关联、SSM Online、ALB 两个目标组 healthy。四个业务域名已在 Cloudflare DNS-only 指向 AWS CloudFront，普通域名基本链路检查通过。**美洲野牛 374 个静态文件已迁入独立私有 S3，正式 CloudFront 路径全量校验通过，并实测缓存 Hit、匿名 S3 拒绝访问。** 详细发布/回退记录见 [游戏素材迁移](aws/GAME-ASSETS.md)，资源输出与历史证据见 [盘点表](INVENTORY.md)。用户尚无官网成品，主域名/www 暂保留当前解析；官网发布、CloudWatch Agent、告警接收、备份任务与恢复、Node 维护和有效会话下的完整游戏回归仍待完成，不能称整套生产验收已完成。

## 当前已确认的状态

- EC2 位于 us-east-1；用户提供的弹性公网 IP 为 `184.195.10.174`。AWS 公布的 IP 范围检查与 us-east-1 EC2 匹配。
- Ubuntu 24.04；目标机用户验证 Python 3.12.3、Node.js 18.19.1。该 Node 版本仅满足现有代码最低门槛，正式运行时的支持周期与升级验证仍需处理，不能当作已完成生产运行时维护。
- 宝塔已安装，用户能够登录。目标机盘点报告确认 Nginx 1.30.6、实例/VPC/子网/安全组 ID、本机应用监听及服务状态，详细已确认值与待确认项目见 [资源盘点表](INVENTORY.md)。安全组规则、候选 ALB 子网路由、EBS 加密及 SSM 控制面状态仍待确认。
- 发布包在 `/opt/gtt/releases/20261029-baota`，`/opt/gtt/current` 为活动版本；目标机预检已校验发布清单与素材。
- 用户验证 gtt-gateway、gtt-admin、gtt-rtp-worker 均 active；8110 健康接口返回 ok；8112 返回 HTTP 200。初始管理员已创建。
- 用户明确本项目目前只有现有服务器，因此 S3、ACM、CloudFront、ALB、WAF、实例 IAM Role 和 CloudWatch 按待创建/配置处理；不推断账号中不存在其他项目资源。
- 随后用户已完成 ACM 申请，截图确认根域名和通配域名验证成功，证书 ARN 为 arn:aws:acm:us-east-1:817557336527:certificate/5d173d56-6bc3-4e29-923e-6a9c84a6091b；后续使用此证书，其他基础设施仍待创建。
- 用户在 CloudShell 完成基础栈云预检，status=passed、warnings=[]；两个候选公有子网、路由/IGW、ACL、100 GiB 加密 gp3 磁盘、现有安全组与已签发证书均通过该步骤，基础栈参数已生成。随后 26 项 Add 变更集通过预览，但实际执行因组织 SCP 拒绝两个 S3 桶设置阻止公共访问而失败；只读预检与变更集成功均不代表写权限获准。
- 最近本地 DNS 查询显示主域名和 www 仍为旧解析，业务子域名未查询到 A 记录；NS 为 dns1/dns2.registrar-servers.com。后续执行前重新查询权威 DNS，保留已有非本项目记录。
- 本地命名 AWS profile 可以读取调用者身份，但已尝试的 CloudFormation、Route 53、CloudFront 只读操作被 AccessDenied。该 profile 是否为本项目部署身份尚未确认，没有修改 IAM 或公网资源。
- 进入盘点阶段后重新读取身份，账号 817557336527 与用户之前截图中的资源账号一致；仅按公网 IP 筛选目标实例的 ec2:DescribeInstances 调用被 UnauthorizedOperation 拒绝。没有尝试修改权限或扩大资源查询范围。服务器基础盘点可通过 inventory_server.py 读取 IMDSv2 元数据，控制面规则仍需用户控制台输出或后续确认的只读身份。

## 本轮建议架构

```text
官网域名 gttgames.com / www
  → 官网 CloudFront（ACM、www 规范跳转）
  → OAC
  → 私有官网 S3 桶

业务域名 play / api / merchant / admin
  → 业务 CloudFront（ACM、默认禁止缓存、WAF）
  → play 的 /assets/*、/shared/* 与精确根静态文件路径：OAC → 私有游戏素材 S3
  → 游戏启动 HTML、会话/钱包/下注/结算和后台等动态请求：
  → HTTPS ALB（限制 CloudFront 回源、按公开 Host 分流）
  → EC2 本机 Nginx（由现有宝塔管理，适配可信代理元数据）
  → 127.0.0.1:8110 网关 / 127.0.0.1:8112 后台
  → 本机加密 EBS 上的 SQLite

EC2 离线 RTP worker → 同机数据库
一致性双库备份 → 私有备份 S3 桶
运维 → IAM Role、Systems Manager、CloudWatch 指标/告警和脱敏日志
```

这是与现有单机代码兼容的第一阶段方案，AWS 没有规定所有项目必须使用同一套产品。ALB 跨可用区部署也不使单 EC2／单 SQLite 自动具有高可用能力。首期不增加并行应用写实例，不将 SQLite 放 EFS 作为多实例共享数据库。

## 资源数量与职责

| 资源 | 本轮数量/范围 | 职责 |
| --- | --- | --- |
| EC2 | 复用现有 1 台 | 应用、SQLite、RTP worker |
| CloudFront | 2 个 | 官网分配；业务分配，后者包含四个业务域名 |
| S3 | 3 个私有桶 | 官网成品；游戏静态素材版本；状态/配置/发布备份，权限分离 |
| ALB | 1 个 | AWS 托管 TLS、Host 路由、目标组健康检查 |
| ACM | 逻辑上覆盖边缘和 ALB 两层 | 边缘证书在 us-east-1，ALB 证书同 ALB 区域；本项目均 us-east-1 时可复用满足域名覆盖要求的同一证书 |
| WAF | 计划 1 个 CloudFront 范围 Web ACL | 业务分配防护，规则先计数验证，再启用阻断 |
| IAM、SSM、CloudWatch | 按最小权限配置 | 实例身份、配置和运维入口、监控与告警 |

官网以静态成品为设计基准；官网内容尚未提供。游戏启动 HTML 仍由应用注入启动脚本；shared/**/index.js 的原模块处理现已前移到静态发布构建，374 个与原线上实际字节一致的素材经 S3/OAC/CDN 全量验证。其他本地游戏入口保持原样，本次没有宣称全部游戏已接入生产网关。

与此前方案的变化明确为：增加官网私有桶和 ALB，四个业务域名统一进入业务 CloudFront，证书统一交给 ACM；原先“两个分配直接回源公网 EC2、仅一个备份桶”不再是本轮标准化方案。

## 域名最终分配

用户当前提供 Cloudflare DNS 页面，域名已添加到 Cloudflare；注册商与权威 DNS 服务分开记录，迁入 Route 53 不是本次部署的必要前提。截图仅显示 5 条邮件 MX 与 1 条 SPF TXT，均为 DNS-only，不能据此确认网站已开橙云或 NS 委派已生效。最近本地递归查询仍返回 Namecheap NS，可能受委派状态或缓存影响，需结合 Cloudflare zone 的 Active/Pending 状态、分配的 NS 及委派查询确认。

后续按 Cloudflare 仅负责 DNS、AWS CloudFront 负责业务 CDN 的边界配置；网站 CNAME 与 ACM 验证 CNAME 均选 DNS-only（灰云），不增加 Cloudflare HTTP 代理层。Cloudflare 主域名使用 CNAME，并由其默认 apex flattening 处理；若最终仍使用 Namecheap DNS，则主域名使用 ALIAS。既有邮件记录保留，只有目标资源通过检查后才更新网站记录；目前盘点阶段不切换业务 DNS。

| 域名 | 记录类型 | 最终目标 |
| --- | --- | --- |
| gttgames.com（@） | Cloudflare CNAME（默认 apex flattening）；Namecheap 则 ALIAS | 官网分配的 cloudfront.net 域名 |
| www.gttgames.com | CNAME | 同一官网分配，由边缘跳转主域名 |
| play.gttgames.com | CNAME | 业务分配的 cloudfront.net 域名 |
| api.gttgames.com | CNAME | 同一业务分配 |
| merchant.gttgames.com | CNAME | 同一业务分配 |
| admin.gttgames.com | CNAME | 同一业务分配 |

用户业务域名不解析 EC2 弹性公网 IP。业务 CloudFront 直接以 ALB 的 AWS DNS 名称作为源站；因此无需创建 origin.gttgames.com 的公网 A 记录。保留该域名名称并不要求分配记录。

## 严格执行顺序与完成标准

1. **盘点与记录**：读取实际 EC2 ID、VPC、子网、两个可用区、实例 Role、安全组、EBS 加密状态、Nginx 版本/配置，以及现有 AWS 资源和 DNS。核对部署账号及所需权限。保存当前应用配置、服务状态与一致性备份。不会因为重新规划而删除实例、密钥或数据库。
2. **形成可复现配置**：以 CloudFormation 维护新增资源，区分网络/身份、存储、入口三个层次；参数引用既有 VPC、子网及实例。输出域名、资源 ID、目标组等信息；执行前检查 change set。部署权限与应用实例 Role 分开。旧 cloudformation.json 只有简化边缘资源，不是本文完整模板，不能继续作为完整标准化模板部署。
3. **证书与存储**：ACM 申请 gttgames.com、*.gttgames.com，DNS 验证记录添加到现有 DNS 服务并保留。配置两个私有 S3 桶、加密、版本控制和必要生命周期；官网桶只授权指定 CloudFront OAC。备份桶单独授权实例 Role 的限定前缀。建立官网发布版本和回滚规则。
4. **源站适配与 ALB**：创建 ALB 与目标组，配置 Nginx 对应的内部入口和健康检查。ALB 只能访问约定的 Nginx 端口，8110/8112 继续只监听 loopback。Nginx 按可信 ALB 的转发信息向本机应用传递 HTTPS、公开 Host 和真实玩家 IP；现有模板中的 $scheme 不能直接照搬到 ALB 终止 TLS 的 HTTP 下游。对请求 body/路径、Cookie、HMAC、Host 及跨域检查做真实链路测试。
5. **创建两个 CloudFront 分配**：官网源站为普通私有 S3 REST 桶与 OAC；业务源站为 ALB，保留访问者 Host。默认 CachingDisabled + AllViewer，仅经验证的公共素材路径可缓存且 MinTTL=0、尊重 no-store/private；错误缓存为 0。ALB 入站限定 CloudFront 源站前缀列表，Listener 同时校验随机回源头，默认拒绝不匹配请求。ALB 健康检查到 EC2 走其安全组授权链路。按目标 ALB/区域支持情况检验 TLS 与路由参数后再部署。
6. **监控、备份和发布验证**：配置应用/实例/ALB 异常与磁盘告警、RTP worker 心跳、备份失败告警和恢复演练；使用应用一致性的双库备份，不以在线裸复制或任意时刻 EBS 快照冒充跨库一致性备份。完整 URL 中含玩家令牌，ALB/CloudFront/WAF 等日志需按字段处理敏感信息，未验证脱敏前不打开完整请求日志。验证发布、校验和回滚流程。
7. **上线验收后切 DNS**：先在验证域名或本机解析覆盖下完成 TLS、两类后台登录、商户隔离、会话、余额、普通/购买免费、完整整局、钱包幂等与故障恢复、缓存隔离测试，再切六个公开域名。通过后收紧 EC2 公网业务端口，只保留已确认的受限运维入口；宝塔用作运维工具，不承担公网业务 TLS。不能在 SSM 可用性未确认前移除现有 SSH/面板入口。

WAF、ALB、CloudFront、S3 等费用需在完整模板生成时按区域和用量列出，本文不提供未核实的总价。用户已确认采用该方案，目前只做盘点，不据此立即创建收费资源。

## 现有代码的生产边界

- 数据库为 SQLite。迁移 RDS PostgreSQL／MySQL 需要适配存储层、事务、唯一约束/幂等、回合与预派彩计划恢复、RTP worker、迁移和回滚，并验证既有商户/玩家状态；不能只修改连接字符串。完成后才规划多实例、跨可用区故障切换和自动扩缩容。
- 当前商户生产网关的完整钱包链路只接入 Buffalo Win。项目中的其他独立游戏入口和素材继续保留，尚未接入生产商户网关的部分需逐款完成适配与验收；不能把单款网关部署成功说成全部游戏已上线。
- 单机首次运行检查已完成，AWS 入口、证书、发布流水线、备份任务、监控和真实商户钱包联调尚未完成。
- 旧发行包中的 README/BAOTA/CLOUDFRONT 流程是此前单机方案，不包含本文完整架构。后续按明确版本生成新基础设施与应用发布包，不让用户混用不一致的说明。

## 官方依据

- [CloudFront OAC 与私有 S3](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html)
- [限制 ALB 仅接受 CloudFront 回源](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/restrict-access-to-load-balancer.html)
- [CloudFront 和源站的证书要求](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/cnames-and-https-requirements.html)
- [SQLite 适用范围及多服务器数据库边界](https://sqlite.org/whentouse.html)
- [Cloudflare 与其他 CDN 的代理边界](https://developers.cloudflare.com/dns/proxy-status/use-cases/)
- [Cloudflare 主域名 CNAME flattening](https://developers.cloudflare.com/dns/cname-flattening/set-up-cname-flattening/)
