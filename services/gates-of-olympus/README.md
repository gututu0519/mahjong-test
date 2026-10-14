# Gates of Olympus 前端预览

启动：`python -m server.run --service-dir services/gates-of-olympus`，或双击本目录的 `start.bat`。
访问 <http://127.0.0.1:8085/>；麻将服务的 <http://127.0.0.1:8080/demo/> 也提供预览入口。

当前是 PP `vs20olympgate` 的英文客户端界面预览，包含启动画面、主画面、设置和规则面板。
大厅中英文界面都可打开此英文客户端。旋转、自动旋转与结算未接入；界面会提示，服务端也拒绝非初始化游戏动作。
余额 2,000 仅为初始化展示，无数据库、钱包或账本。设置按内存预览会话隔离，重启清除。
端口 8085、日志 `logs/`、客户端 `../../clients/gates-of-olympus/`，均独立于 PG 服务。

## 资源与本地适配

资源来自本机抓取 `f2e21fa2f7ee4a9daddb16f1f354bbdc`。抓取进行中也可以增量导入：

```powershell
python tools/pp_capture/import_capture.py f2e21fa2f7ee4a9daddb16f1f354bbdc
```

导入器保留静态路径并记录来源和 SHA-256，遇到静态资源版本冲突时报错。
启动页移除原站会话配置、统计脚本及跨站会话消息，使用本地随机预览令牌。
仅导入 `doInit`，不导入或回放旋转响应。原始 HAR 和完整请求保留在抓取工具目录。
`fixtures/` 不通过 HTTP 暴露。

原版组件反序列化要求签名的原站会话；本地适配仅在同步反序列化调用期间使用客户端已有的离线分支，随后恢复标志。
此兼容逻辑针对当前抓取版本，升级客户端需要重新验证。运营商 logo 脚本以空配置替代，避免加载远程大厅和统计；CSP 限制外部请求。
桌面英文资源已验证，其他语言及原生移动端资源尚未导入。

验证：`python -m unittest server.tests.test_olympus_preview server.tests.test_buffalo_preview server.tests.test_process_isolation -v`。
