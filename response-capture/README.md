# Response Capture

独立本地网页工具：输入网址，打开抓取浏览器，记录实际发生的网络请求及响应。

## 启动

Windows 双击 `start.bat`。需要 Python 3.10 或更高版本；首次运行会安装依赖。
优先使用已安装的 Edge / Chrome，否则安装 Playwright Chromium。
网页地址：http://127.0.0.1:8090

已安装依赖时，可直接运行：

```powershell
.\.venv\Scripts\python.exe app.py
```

## 使用

1. 输入完整的 HTTP / HTTPS 网址，点击“开始抓取”。
2. 在新打开的独立浏览器中登录、点击、滚动或打开新标签页。
3. 在工具网页中搜索请求、选择请求，查看响应体、响应头和请求信息。
4. 点击“停止并保存”，等待“已保存”，再下载 ZIP。

同一时间运行一个抓取任务。关闭抓取浏览器也会结束任务。每次使用独立临时浏览器会话；登录状态不会沿用个人浏览器。抓取工具只监听本机 127.0.0.1。

## 输出

`captures/<session-id>/`：

- `manifest.json`：请求清单、完整网址、方法、状态、请求和响应头、文件路径、错误说明。
- `bodies/`：浏览器解码后的响应文件及请求体；同一个网址的多次请求分别保存。
- `network.har`：浏览器网络记录，响应内容嵌入其中，停止时完成保存。
- `websockets.jsonl`：WebSocket 收发帧，二进制使用 Base64。
- `capture.zip`：首次下载时生成。

历史记录保存在本地，重启后可查看。预览最多显示 256 KiB 文本或 4 KiB 二进制内容；这不限制已保存的响应文件大小。完整文件可能很大，抓取和 HAR 导出需要相应的内存及磁盘空间。

## 边界

记录范围是此次抓取浏览器会话里实际触发、且浏览器公开给 Playwright 的请求，不会自动遍历整个网站，也不是系统级网络代理。HTTP 404/500 等响应同样保存。

未完成的长连接/SSE、下载流、跳转响应体、浏览器内部请求或被浏览器限制的响应可能无法获得完整内容；清单明确显示失败、不可用或停止时未完成。WebSocket 帧单独保存，不作为普通 HTTP 响应体。Service Worker 保持启用以兼容网站，浏览器未暴露的底层流量不保证覆盖。

没有内置登录绕过或证书校验绕过。登录凭据、Cookie、请求体与响应原文可能含敏感数据；输出仅保存在本机，分享前应检查。

## 验证

关闭 8090 上的工具服务后运行：

```powershell
.\.venv\Scripts\python.exe test_capture.py
```

使用本地测试网站验证界面抓取流程、JSON、二进制、POST、iframe、跳转、404、网络失败、WebSocket、预览、ZIP/HAR、历史恢复和移动布局。

实现依据：[Playwright BrowserContext 网络事件](https://playwright.dev/python/docs/api/class-browsercontext)。
