# 单游戏按版本目录交付

## 当前实际磁盘结构

```text
update/game-buffalo-win/
├── buffalo-win-client-<前端版本>/
│   ├── objects/
│   ├── bootstrap/
│   └── manifest.json
└── buffalo-win-serve-<计算服务版本>/
    └── buffalo-win-serve-<计算服务版本>.zip
```

两个版本文件夹直接位于 update/game-<代码>/ 下，不在合并 ZIP 内。前端不生成 ZIP；只有 objects 内文件用于上传私有 S3，bootstrap 和 manifest 属于私有后端启动资料，不能公开整目录上传。serve ZIP 内顶层目录由来源计算包决定（通常 game-<代码>/），解压到包含 package.json 的目录后启动。

配套清单 RELEASE.json、部署说明 START.md、来源校验和、构建过程和验证记录放在 `other/diagnostics/releases/<build-id>/`，不在 update 中放日志或源码。历史平铺归档和曾生成的双组件合并 ZIP 保留，不再默认生成。

## 单游戏构建命令

```bash
npm run game:package -- --game buffalo-win --service-release other/diagnostics/releases/<服务构建号> --build-id <新交付号>
```

每次只处理一个 game。默认从该游戏当前客户端源码生成新的前端版本，不压缩前端。也可用 `--client-bundle <已有前端目录>` 复用前端版本，或 `--source <客户端源目录>` 指定构建来源。

计算包从指定发布记录读取，校验原归档、文件清单、身份、版本、协议和规则配置。服务源是 ZIP 时按字节复用，不改其中程序或版本。已有目标组件目录只有完整清单一致时才能复用；不同字节、额外文件或缺文件均拒绝覆盖。无客户端或空客户端不能宣告交付完成。

如需重新构建本款计算服务，先用单产物命令（资产清单参数沿用现有验证要求）：

```bash
npm run package -- --artifact game-buffalo-win --build-id <新服务版本> --assets-manifest <已校验素材清单>
```

该命令仅发布这一款计算 ZIP，放入其 serve 版本目录。然后 game:package 引用该发布记录补齐前端目录；不会另生成合并 ZIP。通用构建不带 --artifact 时拒绝默认批量；只有用户明确要求全量时才允许 --all。其他产物同样一次一个，例如 --artifact admin。

## 验证

```bash
npm run game:verify -- other/diagnostics/releases/<交付号>
```

先验证实际 update 中的前端目录和服务端 ZIP，再复制/解包到临时目录进行篡改拒绝测试和计算进程启动。不会修改 update 中用于上传的前端文件。校验包含来源、前后端规则/契约匹配、真实计算服务 describe、固定种子初始状态，以及仅设置监听地址、端口、密钥的 env 启动。

单独服务发布记录可先用 `node other/tooling/run.mjs smoke-release <记录目录> --archives-only` 做归档/模板检查；该检查不代表启动成功。当前交付必须继续运行 game:verify 的真实计算启动测试。

旧 kind=game-deployment-bundle 合并 ZIP 仍可用 game:verify 读取；新 kind=game-component-delivery 使用目录加服务端 ZIP。版本和文件来源均在各自发布记录里，不按目录数量推断已部署。

## 部署与范围

- 游戏身份、版本和默认 config/game.json 可从计算包读取，实例 env 可只设置 GAME_BIND、GAME_PORT、GAME_SECRET_FILE。端口按实例分配，新旧版本并行时不能重复。
- 在后台登记并激活服务和前端版本；真实 CDN 发布后，执行“检查并开放”。构建不会自动上传 S3、配置域名、登记服务、初始化钱包或开放游戏。
- 本步骤调整交付结构，仍复用现有已验证计算代码；尚未实施单游戏引擎依赖精简。前后端独立版本不要求同步升级。
- 当前从美洲野牛验证流程；不能据此宣称其他游戏已完成素材和生产验收。本地规则/协议匹配也不代替完整回合、钱包及生产 CDN 联验。
