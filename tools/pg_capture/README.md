# PG 抓取与对照工具

从仓库根目录执行下列命令。客户端资源位于 `clients/mahjong-ways2/`、`clients/buffalo-win/`；正式游戏服务仍从 `services/` 启动。

| 工具 | 命令 | 用途 |
| --- | --- | --- |
| 麻将旧样本回放 | `python -m tools.pg_capture.mahjong_ways2.serve_local --port 8081` | 独立回放抓取样本，钱包默认位于 `diagnostics/mahjong-ways2/local-spin-state.json`；可用 `--state-file` 指定隔离钱包 |
| 麻将规则分析 | `python -m tools.pg_capture.mahjong_ways2.analyze_spin --help` | 离线检查已解码的 Spin 记录 |
| 美洲野牛素材导入 | `python -m tools.pg_capture.buffalo_win.import_capture --help` | 从本机 8090 抓取服务及其响应文件导入资源，保留已有字节 |
| 美洲野牛规则分析 | `python -m tools.pg_capture.buffalo_win.analyze_rules --help` | 离线分析抓取快照 |
| 麻将 HAR 清单 | `node tools/pg_capture/mahjong_ways2/inspect-har.cjs <HAR文件>` | 输出脱敏资源清单到 `diagnostics/mahjong-ways2/har-resources.json` |

麻将旧诊断脚本和浏览器回归脚本位于 `mahjong_ways2/` 及其 `tests/`，其诊断输出统一进入 `diagnostics/mahjong-ways2/`。`restore-shared.cjs` 是显式资源还原工具，会校验来源和基线后写入资源；日常服务无需运行它。

共享模块修复与校验位于 `server/adapters/pg/client_modules.py` 和 `validate_client_module.cjs`，麻将认证元数据位于同目录的 `mahjong_metadata.py`。生产服务直接导入这些模块，不依赖旧回放引擎。

规则报告位于 `docs/mahjong-ways2-spin-interface.txt` 和 `docs/buffalo-win-rules-analysis.txt`。全量 Python 回归入口为 `python -m unittest discover -s server/tests -v`。
