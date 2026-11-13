# 复用首次失败栈留下的两个私有桶

2026-10-29 用户已确认 gtt-foundation 为 ROLLBACK_COMPLETE，下面两个 us-east-1 桶均存在，且四项桶级 PublicAccessBlock 均为 true：

- 官网：gtt-foundation-websitebucket-5q89fgxgjfpz
- 备份：gtt-foundation-backupbucket-gkey3lhv1ajm

失败是显式写入 PublicAccessBlock 的 API 被组织 SCP 拒绝，不能据此推断现有桶的保护已关闭，也不能据桶存在认定其他配置已完成。当前不再另建桶，不修改四项保护，不重复申请 ACM，不修改原实例或 DNS。

## 当前只执行只读检查

把恢复包上传 CloudShell 后执行以下命令。脚本只读取调用身份、失败栈状态/资源清单、两个桶的区域/预期拥有者/公共访问阻止/版本控制/加密/所有权/生命周期/桶策略存在性。它不读取对象或密钥，不打印桶策略原文，不修改资源，不创建变更集。

```sh
unzip -n /home/cloudshell-user/gtt-aws-recovery-20261029.zip -d /home/cloudshell-user/gtt-aws-recovery &&
python3 /home/cloudshell-user/gtt-aws-recovery/recovery_preflight.py
```

输出 status=review_required 时保留完整输出，先处理实际缺项或读取权限。AccessDenied 不能按“没有配置”处理。not_confirmed_deleted_resources 是待核对清单，不保证这些物理资源仍存在；尤其要追踪可能保留的日志组和 Secrets Manager 密钥，核对前不自动删除或重建它们。此检查通过也不表示部署写权限、组织 SCP 或全部生产验收已经通过。

## 后续恢复模板的边界

02-foundation-existing-buckets.json 是单独的恢复变体，标准 02-foundation.json 仍保留四项保护配置。恢复变体以 ExistingWebsiteBucketName、ExistingBackupBucketName 引用已核验的同账号同区域私有桶，保持 IAM 的备份路径授权、ALB、SSM、监控和各输出名称。它不创建 AWS::S3::Bucket，不写 PublicAccessBlock、版本控制、加密、所有权或生命周期；这些现有桶配置属于外部管理，今后由只读检查和单独维护流程核验，不宣称已经导入 CloudFormation。两个桶未来的删除与配置变更不能通过删除该新栈完成。

恢复栈仍管理备份桶的 RequireTLS 策略；官网桶的 TLS 与 OAC 读取策略仍由边缘栈管理，因此首次检查遇到任何已有桶策略都要求审阅，不能直接覆盖。官网桶继续私有，只授予指定 CloudFront 分配读取权限。foundation-existing-buckets-parameters.json 记录此前核验的基础参数与两个桶名，供检查通过后审阅变更集使用；参数文件存在不表示桶检查或资源创建已完成。

ROLLBACK_COMPLETE 的旧栈保留诊断记录。待桶完整配置、其他遗留资源及最新资源预检通过后，拟采用新栈名 gtt-foundation-v2 创建变更集，避免删除旧栈或与旧日志组名称冲突；不要直接对旧栈执行 UPDATE。后续边缘栈 FoundationStackName 必须指定实际成功的新基础栈名。当前恢复包没有自动执行或删除命令，需先审阅检查结果与新变更集。

该路径利用已经具备安全配置的私有桶，不修改组织策略，也不关闭安全保护；后续其他动作若再被组织策略拒绝，按实际拒绝项交由组织管理员处理。

## 已收到的恢复检查结果

2026-10-29 用户在 CloudShell 执行检查，status=passed、issues=[]，两桶全部检查为 true、errors=[]。版本控制、AES256 加密、强制桶拥有者、四项公共访问阻止及全桶 7 天中止未完成上传均已确认，两个桶均无桶策略。旧栈标记保留两个桶、/gtt/gtt-foundation/application 日志组和 OriginSecret-3CjWVoPBBpHN-ywmJXT 密钥；后两者还没有直接服务读取结果，不当作已删除。

下一阶段先创建 gtt-foundation-v2 / gtt-foundation-recovery 变更集预览，使用本目录的 02-foundation-existing-buckets.json 与 foundation-existing-buckets-parameters.json。默认条件下预计 24 项 Add、不含 AWS::S3::Bucket，仍会管理备份桶 TLS 策略并给原实例安全组新增 ALB 来源的 8080/8081 授权。预览不执行资源创建。新栈将使用自己的日志组和回源密钥，旧日志/密钥继续留在遗留清单，核对后再安排清理；若旧密钥实际存在且尚未计划删除，应计入额外存储费用。尚未提交或执行新变更集。

用户随后提交该恢复变更集，返回 CREATE_COMPLETE / AVAILABLE、Reason=null，24 项全部 Add，与模板预期一致，没有新建桶或 EC2 实例替换。变更集 ID 为 22242733-d438-41e9-82e3-71b5fba35ed4，栈 ID 为 34e4f990-d3c7-11f1-b4de-0edd9a39b38d，账号与区域均吻合。已完成预览审阅，下一步执行该变更集；资源创建结果仍待用户提供。实际部署写权限仍以资源事件为准。

用户随后执行恢复变更集，gtt-foundation-v2 已 CREATE_COMPLETE，16 个 Outputs 保存于 foundation-v2-outputs.json。成功复用了两桶，ALB、安全组、目标组、角色/Profile、SSM 配置与监控资源已创建。当前进入 EC2 关联 Profile → 验证 SSM Online → 安装/校验 Nginx 8080/8081 → 验证两个目标组 healthy 的阶段；这些主机适配/健康状态尚未验收。边缘栈必须显式使用 FoundationStackName=gtt-foundation-v2；CloudFront/WAF、官网上传、DNS 切换、CloudWatch Agent、备份任务与恢复演练尚未完成。

随后用户确认 EC2 关联 Profile ARN 正确，SSM 返回 i-06ce52379f43882db PingStatus=Online、AgentVersion=3.3.4793.0。角色与 SSM 连接步骤完成，下一步为 EC2 内的 Nginx 检查/安装；原 SSH 和宝塔入口继续保留到后续运维与业务验收。

用户随后确认 8080/8081 空闲且原 Nginx 配置检查成功，上传 gtt-alb-20261029.conf 并安装到 /www/server/panel/vhost/nginx/gtt-alb.conf。新配置检查通过且重载后，本机两个新入口分别返回网关、后台健康 JSON 和 HTTP 200；首次 8080 连接拒绝后自动重试成功。当前推进 ALB 的两个目标组 TargetHealth 检查，尚未确认 ALB healthy；边缘栈仍待此检查通过后创建。

两个目标组随后均返回 unhealthy / Target.Timeout。主机实查确认 Nginx 监听 0.0.0.0:8080/8081，UFW active / 默认拒绝入站，缺少这两个端口放行，iptables 规则与该状态一致；这是已确认的主机阻断点。当前补充两条仅允许 ALB 已确认子网到实例私网 8080:8081 的 UFW 规则，命令见 README；不停止防火墙，不放行公网，不更改 Nginx/应用。规则尚待用户执行，ALB 恢复结果待确认，实际 AWS SG 规则尚未收到；若修复后继续超时再核对它们。

随后用户重新查询两组目标健康：8080=healthy、8081=healthy，Reason 均为 null，ALB 回源健康链路通过。当前准备 gtt-edge / gtt-edge-initial CREATE 变更集预览，显式指定 FoundationStackName=gtt-foundation-v2，WAF 先 COUNT、PriceClass_All；预计 10 项 Add，尚未提交或执行。复用恢复包中已上传的 03-edge.json，无需重复上传；CloudShell 参数在命令中显式传入，避免使用模板中旧栈名默认值。官网内容和 DNS 仍未发布/切换。

随后 gtt-edge-initial 的预览返回 CREATE_COMPLETE / AVAILABLE、Reason=null、10 项全部 Add，与模板资源吻合。变更集 UUID eebad0a9-33a1-4185-ab34-a282cc7a4700，栈 UUID 407e0ae0-d3cb-11f1-9bba-12ffcd982a93，已核对通过。下一步 execute-change-set 并等待 gtt-edge CREATE_COMPLETE，保存五项 Outputs；尚未收到执行结果，不能声称分配可用。执行不切 DNS，完成后仍需官网内容发布、临时解析下的业务回归和最终切换。

用户随后执行并确认 gtt-edge CREATE_COMPLETE，五项 Outputs 保存于 edge-outputs.json。业务分配 ds4bqnhfevccf.cloudfront.net，官网分配 df79mrkarlfs7.cloudfront.net；DNS 尚未切换。用户明确尚无官网成品，根域名/www 保留当前解析。本机以原域名 SNI + connect-to 进行的业务测试尚未成功（TLS 握手失败、无 HTTP 响应），下一步由 CloudShell 复核，不能把栈成功当作端到端链路已通过。CloudWatch Agent、备份、Node 运行时维护、告警接收与正式业务回归仍待后续处理。

CloudShell 随后两轮 connect-to 检查均通过：管理与商户 portal 配置返回 200，商户 API 与游戏钱包无凭据分别返回预期 AUTH_INVALID / SESSION_INVALID 的 401。基本业务 TLS 和回源路由通过，真实认证业务与完整游戏回合仍待验证。本机 DNS 查询已观测 NS 为 arturo.ns.cloudflare.com、nelly.ns.cloudflare.com；下一步在 Cloudflare 添加/更新四个业务子域 CNAME 到 ds4bqnhfevccf.cloudfront.net，全部 DNS-only，根域/www 等官网成品准备好后再切。尚未收到 DNS 修改结果或普通域名访问验证。

用户随后提供四个业务 CNAME 均 DNS-only 的截图。公共 DNS 查询确认四个名称指向正确业务分配；admin 本机初次查询仍 NXDOMAIN，但 Google 与 Cloudflare DoH 均返回正确 CNAME。普通 URL 测试已确认 merchant 200、api 401、play 401，证书校验保持开启；admin 本机仍 TLS 握手失败，原因未定，尚需 CloudShell 普通域名与用户浏览器复核，不把 DNS 设置成功扩展为所有客户端访问成功。主域名/www 仍等待官网成品。

用户随后在 CloudShell 用普通 admin 域名请求 /deployment.json 返回 200、portal=admin，反馈网页可打开，补齐该环境的普通域名基本检查。真实账号登录与游戏回合仍待验收。当前 S3 官网成品与备份任务尚未接入，两桶创建成功仅代表基础设施准备完成；游戏页面/素材仍回源 EC2，CloudFront 按策略缓存素材，SQLite 仍在 EC2。

参考：https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/troubleshooting.html
