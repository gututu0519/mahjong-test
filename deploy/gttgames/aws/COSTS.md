# 基础栈费用核对

2026-10-29，参考 AWS 官方公开按需定价，区域 us-east-1，按每月 730 小时估算，不扣账户优惠额度且未计税。这里只估算本次基础栈的部分持续费用，不是整套项目月费或费用上限。

| 项目 | 单价假设 | 月估算 |
| --- | --- | --- |
| 1 个 ALB 本体 | 0.0225 美元/小时 | 16.425 美元 |
| ALB 公网 IPv4 | 按 2 个，每个 0.005 美元/小时 | 7.30 美元 |
| 1 个 Secrets Manager 回源密钥 | 0.40 美元/月 | 0.40 美元 |

上述精确小计为 24.125 美元，按分四舍五入约 **24.13 美元/月**。实际 ALB IPv4 数量可能随扩展变化。

另计 ALB LCU、S3 容量/请求/历史版本、CloudWatch 指标/告警/日志、SNS、Secrets Manager API 与适用的数据传输费用。现有 EC2、EBS 与弹性公网 IP 的费用不在上述小计内；后续 edge 栈的 CloudFront、边缘函数与 WAF 也不在其中。基础栈不预留 LCU，不创建 NAT Gateway、新 EC2、数据库实例或完整访问日志采集链路。

当前变更集 26 项全部 Add，符合两项条件参数保持默认的基础栈：未填 NotificationEmail，不创建邮件订阅；EnableBackupMonitoring=false，不创建每日备份指标告警。仍会创建其余 8 项基础监控告警。邮箱、CloudWatch Agent 与备份任务需要按后续步骤配置，不能认为模板创建完成即告警接收和备份已全部可用。

首次执行已回滚。后续复用两桶的恢复模板在相同默认条件下预计为 24 项 Add（仍需 AWS 变更集核对），减少的是桶资源创建，不减少实际存储的两个桶。旧栈将 /gtt/gtt-foundation/application 日志组和 OriginSecret-3CjWVoPBBpHN-ywmJXT 标记 DELETE_SKIPPED，物理状态和数据量尚待直接服务核对。新恢复栈创建独立日志组与密钥，因此若旧密钥仍有效且未计划删除，按上述单价额外约 0.40 美元/月；旧日志实际存储费按用量另计。旧资源不在新栈约 24.13 美元的部分费用小计内。

来源：

- [ALB 定价](https://aws.amazon.com/elasticloadbalancing/pricing/)
- [公网 IPv4 定价](https://aws.amazon.com/vpc/pricing/)
- [Secrets Manager 定价](https://aws.amazon.com/secrets-manager/pricing/)
