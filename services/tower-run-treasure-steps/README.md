# Tower Run Treasure Steps

启动：`python -m server.run --service-dir services/tower-run-treasure-steps`，或双击 `start.bat`。

中英文原版客户端：<http://127.0.0.1:8099/?lang=zh>、<http://127.0.0.1:8099/?lang=en>。大厅位于 <http://127.0.0.1:8080/demo/?lang=zh>，提供 Play’n GO 筛选和试玩入口。

服务仅绑定 127.0.0.1；数据库 `data/games.sqlite3`、日志 `logs/` 独立持久化且不提交。初始余额 2000。普通旋转、消除补牌、Bob 分面额进度、Wild Rift、Dimensional Multiplier、宝藏室金币/钥匙/箱子和 GO Ultra 已实现。刷新重播待结算局，不重复扣款或派奖。

引擎 1.1.0 已按新增原站实录补齐开箱符号 14 与独立动画组；支持同转多钥匙、新箱与钥匙同转、倒计时和钥匙同转、满盘及多奖封顶，开箱后的生命恢复与最终汇总分步发送。新局使用修正后的展示协议；更新前已保存的待结算局保留原结果及结算金额。

详细规则、证据、随机权重边界与补抓项见 [规则文档](../../docs/tower-run-treasure-steps-rules.md)。原版客户端展示 RTP 不代表本地模型，原版概率尚未恢复。
