# 单游戏按版本目录交付

## 美洲野牛：按版本通过 HTTPS 加载入口

使用 `game:package -- --game buffalo-win --client-version v1.1 --service-version v1.2 --cdn-entry` 生成新版本。仅将原始根 `index.html` 加入公开对象白名单，不含玩家会话；其余 HTML、fixtures、计算规则和密钥不因本选项公开。旧版本不改写。`publish-frontend` 发布此模式时只写 `releases/<游戏>/<版本>/`，公开标记最后写入；不上传私有启动目录。其他协议适配器的原入口行为不变。

平台 JSON 可一次性配置 `frontend_cdn_origin` 为实际 HTTPS 素材域名（无路径），使清单/模板固定访问 `<origin>/releases/buffalo-win/v1.1/_gtt-manifest.json` 及同目录 `index.html`。该域名的 CloudFront 行为必须将 `/releases/*` 原样路由到私有桶根，不能重复添加 origin path。未设该项时使用版本域名的 `/_gtt-manifest.json` 和 `/_gtt-entry.html`；新版 `render-frontend-edge` 将后者映射为同版本的 `index.html`，玩家的 `/` 和 `/index.html` 仍走鉴权网关，不能整域名改为静态网站。玩家域名仍按 `frontend_origin_template` 配置 DNS/TLS 和动态/静态分流。

初次发现新版本：读取公开版本标记，用本机同游戏同协议适配资料重建并校验清单；仅当所需私有资料摘要完全匹配才登记。每次开放复核 CDN 标记及计算身份，不遍历下载图片。网关首次处理绑定会话的入口时经 HTTPS 取原始 HTML（无 token、Cookie、请求头透传，不跟随跳转），检查大小和 SHA-256，缓存原始字节，再由原适配器完成注入。缓存损坏、模板不符、协议/私有资料不兼容时拒绝，不使用其他版 HTML 顶替。共享 `frontend_releases_directory` 需可写。前端界面、素材和入口变更不要求重打平台包；变更服务端协议或规则仍需部署对应适配资料。

## 当前运行时：本地私有资料 + HTTPS 版本清单

后台与网关默认不调用 AWS CLI、不需要 EC2 读取私有 S3 的权限。发布端继续上传公开素材和 `_gtt-manifest.json`。平台读取启动资料的顺序是 `frontend_releases_directory/<release>/`、包内 `dist/data/frontend-releases/<release>/`。同名本地版本损坏应修复，不能用其他版本顶替。只有显式配置 `"frontend_private_source":"s3"` 时才启用下文所述旧版缺失回源流程。

构建独立后台或网关时可加 `--frontend-bundle <对应交付记录下的 publication-bundle>`。工具校验完整构建，仅打入清单和 `bootstrap/`，不复制公开素材。之后升级前端，也可把新的私有 `manifest.json` 和 `bootstrap/` 安装到双方共用的 `frontend_releases_directory/<release>/`，无需重打计算服务。生产仍需配置真实的 `frontend_origin_template`、DNS/TLS 和 CloudFront 版本路由；后台通过 HTTPS 读取该版本 origin 的 `/_gtt-manifest.json`，不是从公开域名下载私有启动资料。

## 当前默认命令：两项交付（格式 4）

新构建的计算 ZIP 不套 `game-<代码>/`：`package.json`、`tools/`、`config/` 直接位于归档根目录。部署时解压到独立空目录，在该目录配置实例并启动。历史带顶层目录的包仍按原清单验收。

部署为 `games/<游戏代码>/<版本>/package.json` 时，同游戏共享配置放在 `games/<游戏代码>/game.env`，进入版本目录直接执行 `npm start`。共享文件设置 `GAME_BIND`、`GAME_PORT`、`GAME_SECRET_FILE`，不要指定 `GAME_RELEASE` 或 `GAME_CONFIG`。如版本目录也有 `game.env`，优先整份使用版本目录配置（不合并）。新旧版本同时运行需不同端口，显式 `--env-file` 仍优先。

```sh
npm run game:package -- --game buffalo-win --client-version v1.0 --service-version v1.0 --assets-manifest <已校验的素材清单路径>
```

只输出 `update/game-buffalo-win/buffalo-win-client-v1.0/`（纯素材）和相邻的 `buffalo-win-serve-v1.0.zip`。计算服务自报版本、PM2 实例名与 env 示例使用计算组件版本，build-id 仅用于追溯。打包自动解包启动并核对实际身份、协议、初始状态、规则与前后端文件；校验失败撤回本次新增的交付项。

发布工具读取本次 `other/diagnostics/releases/<build-id>/publication-bundle/`，一次发布 S3 公开素材和私有启动资料，命令见同目录 `START.md`。**不要仅手工上传纯素材目录代替完整前端发布。** 服务器只收 serve ZIP，无需 client 或 `gateway-fe-*`。打包不等于已发布或已开放。

前后端版本必填，可不同次版本；异主版本拒绝。只升级前端时，保持计算组件版本，复用已验证来源 ZIP。只升级计算时保持前端版本，核对内容后复用之前的不可变清单。改变同版本内容不得覆盖。旧版目录打包命令仅作历史兼容，须额外指定 `--legacy`；历史交付读取仍支持。

## 游戏前后端版本规则

- **作用域与编号**：按游戏分别管理客户端（`client`）和计算服务（`serve`）。两端首次发布均为 `v1.0`，格式为 `v主版本.次版本`。同一主版本内，两端的次版本独立递增；只更新一端，另一端保留原版本。同一端已发布的版本号不得覆盖或重新分配。
- **同主版本是兼容承诺**：任意 `v1.x` 客户端都必须能配任意 `v1.x` 计算服务，包括新客户端配旧服务、旧客户端配新服务。例如前端 `v1.2` 配后端 `v1.0` 有效。如果前端必须依赖后端新增接口才能运行，就不能作为 `v1.2` 发布；应将两端作为新一代从 `v2.0` 起发。两端同日更新但仍可独立替换，不必升主版本。
- **后台配对**：前端和计算服务分别选择版本，不要求次版本相等；不同游戏或不同主版本不得配对。主版本相同不替代认证、实际协议、启动资料及 CDN 等[开放检查](game-opening-checks.md)。
- **交付与追溯**：面向部署人员只交付一个前端目录和一个后端 ZIP，例如 `buffalo-win-client-v1.1/` 与 `buffalo-win-serve-v1.0.zip`。构建时间、Git 提交、校验和及内部 build-id 记入发布清单，不充当组件版本号。
- **旧版过渡**：美洲野牛启用新编号时，之前的交付版本作废，不得改名为 `v1.0` 或用于新会话；保留历史记录及未结束回合的恢复结算能力。

后台在「独立游戏服务 → 选择前后端版本」按游戏提交一对版本，校验计算服务在线身份、前端资源和两条路由修订后，在同一个事务中切换。旧单端切换接口也必须配对当前另一端。前端清单的 `component_version`（前端构建参数 `--component-version v1.0`）是展示与兼容版本；`release` 仍用于唯一标识构建和固定 CDN 地址。计算版本取认证服务实际报告的 `release`。无正式组件版本的旧构建仅供历史查看，不据其文件名推断版本。游戏构建编号、交付结构迁移及线上旧版停用尚需单独实施。

## 按游戏和版本自动读取（新前端发布流程）

在生产模式下，同一游戏的每个前端版本只发布一次。`releases/<游戏>/<v主.次>/` 放公开素材；`private/frontend/<游戏>/<v主.次>/` 放私有 `bootstrap/` 和完整 `manifest.json`。计算服务不读取这些文件。现有目录交付和旧前端版本仍可沿用原路径。

**平台一次性配置**：网关和后台使用更新后的程序、AWS CLI v2、可写的本地前端版本缓存目录，以及平台 JSON 中同一份配置：

```json
{
  "frontend_s3": {"bucket":"gtt-game-assets-817557336527-us-east-1","owner":"817557336527","region":"us-east-1"},
  "frontend_origin_template":"https://{release}-g{game_id}.play.gttgames.com"
}
```

域名为示例，必须与实际版本域名的 DNS、通配证书及 CloudFront 分配相符。部署更新后的 `render-frontend-edge.mjs` 生成的边缘函数一次，其后按版本自动路由；不按版本修改边缘配置。运行身份需 `s3:GetObject` 读取所需 `private/frontend/` 和 `releases/` 对象；CloudFront OAC 只允许读取所需 `releases/`。发布工具检查私有桶保护并拒绝授权范围超出 `releases/` 的桶策略，服务端读取权限使用 IAM 身份策略，不公开私有前缀。

**每次前端更新**（示例 `buffalo-win/v1.0`）：

```sh
npm run frontend:build -- --game buffalo-win --remote-version v1.0
node other/tooling/run.mjs publish-frontend <上一步输出的完整bundle目录> --bucket gtt-game-assets-817557336527-us-east-1 --owner 817557336527
```

使用发布工具而不是手工上传：逐对象校验，最后写入私有清单作为完成标记；同版本不覆盖，重试用原 bundle。后台「游戏客户端版本 → 按版本读取 S3」输入游戏与版本，检查 CDN 后在「独立游戏服务」配对。后台和网关会在需要时从固定路径下载并验证私有文件，缓存可分开，不需手传 `gateway-fe-*`，也不用上传 `client` 到服务器。登记、检查失败不变更现有组合；历史构建不会自动变成 `v1.0`。

## 原目录交付的实际磁盘结构

```text
update/game-buffalo-win/
├── buffalo-win-client-<前端版本>/
│   └── <直接上传 S3 的所有素材，保留相对路径>
└── buffalo-win-serve-<计算服务版本>/
    ├── buffalo-win-serve-<计算服务版本>.zip
    └── gateway-<前端版本>/
        ├── bootstrap/
        ├── manifest.json
        ├── install-delivery-frontend.mjs
        └── START.md
```

格式 3：client 目录的全部内容可直接上传到清单指定的私有 S3 前缀，不再套 `objects/`。serve ZIP 解压到包含 package.json 的目录后启动。网关私有资料不放进计算 ZIP，不上传 S3。两个交付目录并排时，按随包 START.md 执行 `node <serve>/gateway-<前端版本>/install-delivery-frontend.mjs <网关安装器路径> <实际前端版本存储根目录>`；脚本自动组合资料并调用现有网关安装器逐文件验证。单独构建前端使用的完整 bundle 和历史格式 2 交付保持原格式。

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
