# Gates of Olympus 独立试玩服务

运行 `python -m server.run --service-dir services/gates-of-olympus`，默认监听 `127.0.0.1:8085`。
从麻将服务的 `/demo/` 大厅点击宙斯「试玩」，或直接打开 `http://127.0.0.1:8085/`。
大厅在 8080 或 8081 时均可内嵌。每次从大厅进入创建独立的 2,000 虚拟积分会话，有效期 24 小时；刷新保留进度。

普通旋转、连消、倍率球、免费旋转、免费重触发、ante 投注及领取结算由本地引擎生成。
免费购买已接入，保留原版入口：100 倍普通投注购买 15 次免费旋转，支持重试和重启恢复。规则证据、派彩表及待补抓项见 [引擎说明](../../server/games/gates_of_olympus/README.md)。

- 配置：`config/gates-of-olympus.json`。卷轴与倍率权重是本地参数，不宣称等于原厂 RTP。
- 数据：`data/games.sqlite3`。保存钱包、令牌、局面、幂等结果、账本和设置。
- 日志：`logs/service.log`。与其他游戏服务的进程和数据库独立。
- 协议：`/hub-demo/ge/v3/gameService` 接受 doInit、doSpin、doCollect；也提供通用会话、状态、钱包、历史和 spin API。

资源在 `clients/gates-of-olympus/`。按游戏容器宽高选择横版/移动竖版；窗口缩放、手机旋转或全屏导致方向改变时，延迟 300ms 装载相应版本，沿用持久化会话并恢复未完成回合。
两个版本都使用已有的离线反序列化兼容分支，仅限同步反序列化调用。CSP 限制远程请求。
捕获的音频包为 MP3，HTTP 输出局部替换音频选择表达式，避免请求缺失的 OGG；磁盘原始资源不修改。

资源导入：`python tools/pp_capture/import_capture.py <capture-id>`。旋转分析使用 `tools/pp_capture/analyze_spins.py`。运行中的引擎不读取测试旋转样本。中英文桌面与移动资源已导入；大厅语言透传到启动地址，横竖屏切换保留语言与会话。中文四个语言包来自抓取 `fffa52d88f214176aacf65630c51714f`，其余 122 个资源与已有版本字节一致。中文入口 `/?lang=zh`，英文入口 `/?lang=en`，默认中文。

旧 `server.services.olympus_preview` 保留为仅展示资源的基础入口和资产处理器；正式 service.json 使用 `olympus_client`。

测试：`python -m unittest server.tests.test_olympus_engine server.tests.test_olympus_http server.tests.test_olympus_preview -v`。
