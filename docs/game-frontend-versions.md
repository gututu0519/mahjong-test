# 游戏客户端前端版本

本功能管理游戏启动页、JS、图片、音效及配套启动资料，不管理平台/商户后台自身的前端版本。平台后台入口为“游戏前端版本”（`http://127.0.0.1:8112/#frontends`）；商户后台不展示此入口，接口也拒绝商户账户。

## 自动版本与切换

每次构建自动生成 `fe-<UTC毫秒时间>-<内容摘要8位>-<随机6位>`。不接收手填前端版本号；相同内容重复构建也会产生不同构建号，内容摘要仍相同。清单记录逐文件大小、SHA-256、MIME、处理前校验和、兼容处理状态、源码提交及工作区 dirty 状态。

平台登记时从服务器已安装的构建读取版本与清单。检查通过后，可切换新会话或回退到已检查版本。已打开的游戏固定使用原版本域名、静态资源和启动资料，不强制刷新；新启动链接使用当前版本。前端按会话绑定，后端计算按整局绑定，两者使用相同的客户端协议契约进行兼容检查。此能力不是向正在执行的 JS 里替换代码。

旧版本及其会话关系持久化到控制库和游戏库。网关重启后保持绑定。“标记停用”禁止再次激活，不删除旧文件或终止旧会话；当前版本不能直接停用。没有激活前端版本的游戏继续使用既有入口。

后端构建号也默认自动生成。独立游戏包启动时从 `GAME.json` 读取发布号；平台登记服务时通过已认证的 `/v1/describe` 自动读取，无需再填写发布版本。

## 本地构建与操作

在 `server/` 执行：

```powershell
npm run frontend:stage -- --game buffalo-win
```

命令编译 Node 工具、构建游戏客户端，并安装到 `services/gtt-gateway/data/frontend-releases/<自动版本>/`。输出包含版本和实际路径，不登记、不激活。然后在平台后台选择“登记构建”→“检查素材”→“切换新会话”。本地检查验证文件字节，不代表已验证生产 CDN。

需要分开构建和安装时：

```powershell
npm run frontend:build -- --game buffalo-win
node tools/install-frontend.mjs <构建目录> --destination <网关数据目录/frontend-releases>
```

产物位于 `diagnostics/releases/frontend-<游戏>-<自动版本>/`：

| 路径 | 用途 |
| --- | --- |
| `objects/` | 可以上传私有 S3 的游戏静态文件 |
| `bootstrap/resources/` | 网关所需启动 HTML、注入依赖、协议资料、配置模板与规则资料，仅部署到后端 |
| `manifest.json` | 静态与私有文件的完整配套清单，不直接作为公开 CDN 清单 |
| `DEPLOY.txt` | 对应版本的部署信息 |

只扫描明确允许的静态目录和已识别的根目录静态文件；fixtures、抓取记录、账号数据、日志及浏览器配置不作为静态素材发布。构建不会删除原始客户端。旧应用包、当前应用包与此客户端版本包分别保留。

## 生产发布

1. 构建并保留完整客户端版本包。将版本包安装到配置的 `frontend_releases_directory`，不要替换旧目录。网关应用包自带 `tools/install-frontend.mjs`、`tools/publish-frontend.mjs` 与 `tools/render-frontend-edge.mjs`，安装时显式传入服务器数据目录。
2. 使用 AWS CLI 凭证发布静态部分：`node tools/publish-frontend.mjs <构建目录> --bucket <私有桶> --owner <12位AWS账号>`。发布器先验证阻止公开访问、BucketOwnerEnforced、版本控制及加密；逐文件校验后以条件写入上传不可变对象，最后写入经过过滤的公开清单。不会上传 `bootstrap/`，不会覆盖内容不同的已有对象，不执行清理或自动修改 CloudFront。
3. 为版本域名准备 DNS、TLS 与 CloudFront 路由。生产配置例为 `frontend_origin_template: "https://{release}-g{game_id}.play.example.com"`；版本号和游戏编号位于同一个域名标签，可使用 `*.play.example.com` 证书。网关/反向代理须接收这些 Host，并保留 Host 转发。配置模板只是示例，不是已部署地址。
4. 为版本域名使用独立 CloudFront 分发，保留原业务分发与入口。私有 S3 源使用 OAC，源路径必须为空；静态请求由 viewer-request Function runtime 2.0 路由到 `/releases/<游戏>/<自动版本>/<原路径>`。HTML、API、WebSocket 仍访问网关源，保留查询、Cookie 和鉴权。使用转发 viewer Host 的源请求策略，动态缓存 MinTTL 为 0，并遵循应用的 no-store 响应。静态对象采用一年 immutable 缓存。
5. 在平台登记已安装构建，执行生产“检查素材”，逐项请求版本 CDN 并核对大小和 SHA-256；再验证启动、语言、图片音效、普通/免费/购买回合与恢复，最后切换新会话。回退选择已保留的兼容版本，不覆盖或失效旧版本对象。

边缘函数通过 `node tools/render-frontend-edge.mjs <配置JSON> <新的输出JS路径>` 生成。配置字段为 `host_suffix`（例如 `.play.example.com`）、`assets_origin_id`、`assets_domain`、`dynamic_origin_id`、`dynamic_tls_name`；这些值必须来自实际分发与源，不能使用示例覆盖现有生产配置。生成器不部署分发或证书。

AWS 的源选择支持和限制见 [CloudFront origin helpers](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/helper-functions-origin-modification.html)；条件写入和校验和参数见 [S3 PutObject](https://docs.aws.amazon.com/cli/latest/reference/s3api/put-object.html)。CloudFront Test API 不验证实际源切换，必须在部署后验证真实请求。

## 验证边界

自动化覆盖：重复构建自动编号、私有文件排除、文件篡改拒绝、平台/商户权限、检查前激活拒绝、版本切换与回退、旧会话和资源跨网关重启保持、错误版本会话拒绝、模拟 S3 不覆盖及公开清单过滤、边缘函数路由与鉴权保留。

已为美洲野牛实际构建并本地安装，包含 381 个静态文件与 45 个私有启动资料文件，尚未激活用户环境的版本路由。其余 18 款已配置目录规则，仍需分别完成浏览器、资源覆盖和生产 CDN 验收，不能把统一构建能力当作所有游戏已完成素材迁移。

本次未上传真实 S3、未部署 CloudFront/DNS/TLS、未切换线上流量。原有 Super Ace 客户端日期锁 VM 回归问题单独记录在 `server/VALIDATION.md`，不属于前端版本切换已解决项。
