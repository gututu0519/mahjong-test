# Mahjong Test

仓库包含两个独立项目：

```text
mahjong-test/
├── Mahjong Ways 2/    # 麻将游戏资源和本地模拟服务
└── response-capture/  # 浏览器请求与响应抓取工具
```

## Mahjong Ways 2

双击 `Mahjong Ways 2/start.bat`，或者在仓库根目录运行：

```powershell
python ".\Mahjong Ways 2\serve_local.py"
```

访问 <http://localhost:8080/?mock=1>，启用本地模拟登录。

赔付表和规则使用抓取到的原版面板、图片与样式，`GameRule/Get` 从本地
`fixtures/game-rule.json` 返回抓取的规则元数据。资源来源及校验值见
`Mahjong Ways 2/fixtures/restored-original-help-assets.json`。

本地 Spin 已接入原客户端的二进制协议：按顺序循环回放 12 个已抓取的完整回合，
包括未中奖、中奖和连续消除。下注档位会同步换算奖金，连消只在首转扣款，
请求重试不会重复结算。页面显示“本地样本回放 · 模拟余额”；这是抓取样本演示，
不是生产随机数或赔率引擎，未覆盖的免费旋转和购买奖励功能不做模拟。

模拟余额从 2000 开始，连同回合进度保存在 `Mahjong Ways 2/diagnostics/local-spin-state.json`，
刷新页面或重启服务后可继续。多个标签页共享这一份本地钱包；出现旧回合提示时刷新同步。
需要重新开始时，停止麻将服务并删除该状态文件，再重新启动。
开发验证可用 `--port 8081 --state-file diagnostics/test-wallet.json` 隔离测试钱包。

## 抓取工具

双击 `response-capture/start.bat`。首次启动会自动创建 Python 虚拟环境并安装依赖。
访问 <http://127.0.0.1:8090>，输入网址开始抓取，在新打开的浏览器里操作目标网站，停止后下载 ZIP。

详细使用方式和抓取边界见 [抓取工具说明](response-capture/README.md)。

两个服务使用不同端口，可以同时运行。需要 Python 3.10+；麻将模块修复还需要 Node.js。抓取工具优先使用本机 Edge / Chrome。

抓取数据、虚拟环境、诊断文件和运行日志只保留在本机，不提交到 Git。
