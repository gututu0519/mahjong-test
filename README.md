# Mahjong Test

仓库包含两个独立项目：

```text
mahjong-test/
├── mahjong/           # 麻将游戏资源和本地模拟服务
└── response-capture/  # 浏览器请求与响应抓取工具
```

## 麻将

双击 `mahjong/start.bat`，或者在仓库根目录运行：

```powershell
python .\mahjong\serve_local.py
```

访问 <http://localhost:8080/?mock=1>，启用本地模拟登录。

## 抓取工具

双击 `response-capture/start.bat`。首次启动会自动创建 Python 虚拟环境并安装依赖。
访问 <http://127.0.0.1:8090>，输入网址开始抓取，在新打开的浏览器里操作目标网站，停止后下载 ZIP。

详细使用方式和抓取边界见 [抓取工具说明](response-capture/README.md)。

两个服务使用不同端口，可以同时运行。需要 Python 3.10+；麻将模块修复还需要 Node.js。抓取工具优先使用本机 Edge / Chrome。

抓取数据、虚拟环境、诊断文件和运行日志只保留在本机，不提交到 Git。
