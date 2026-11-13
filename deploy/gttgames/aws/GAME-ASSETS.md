# 游戏素材迁移到私有 S3

后续构建的产物划分、配套版本与发布顺序遵循 [构建与发布规则](../../../docs/build-and-release.md)。本页保留已完成迁移与现有工具的执行记录。

本次用户授权将游戏静态素材迁到独立 S3，通过现有业务 CloudFront 加载。首批严格使用已部署的 gtt-release-20261029-baota.zip 中的美洲野牛文件，不改原版功能、游戏 UI、游戏入口、会话或结算；其他本地游戏入口保留。

**状态：正式素材路径已切换，374 个文件全部通过 active 验证，CDN 缓存命中和 S3 匿名拒绝均已实测。** 后续实际游戏画面、音效与完整回合验收仍需在有效商户会话下完成。

## 当前完成的工作

- 本机 AWS profile sds-test 为账号 817557336527 的 IAM 用户 gututu，可访问 S3；默认 profile 无凭据，该命名身份没有 CloudFront GetDistribution 和 CloudFormation DescribeStacks 权限。CloudFront 栈操作继续由已有 CloudShell 身份执行，不要求给实例角色扩大部署权限。
- 从已安装发布包导出 374 个文件，总计 38,302,587 字节；覆盖 assets、shared 以及根目录图片/JSON/样式/脚本。排除 fixtures、HTML 入口与非静态开发文件。shared/**/index.js 使用与线上发布包一致的 prepare_module 预处理并通过 Node 校验。启动 HTML 继续由 EC2 注入启动脚本，动态 API 保持原链路。
- 发布 ID：2e8b417be6a438768bc4。独立桶 gtt-game-assets-817557336527-us-east-1，区域 us-east-1。对象前缀 releases/buffalo-win/2e8b417be6a438768bc4。
- 桶创建和上传已由本机身份完成；四项 Block Public Access 全部 true，BucketOwnerEnforced，SSE-S3 AES256，版本控制 Enabled，全桶 7 天中止未完成分段上传。没有调用 PutPublicAccessBlock、没有添加公共 ACL/策略或关闭保护。当前桶的配置由发布工具维护和核验，尚未导入 CloudFormation；新 OAC 和桶策略现已由既有边缘栈管理。
- 374 个 S3 对象逐个核对 ContentLength、服务器返回的 SHA-256、MIME、Cache-Control 和发布元数据；全通过后才写入 _gtt-manifest.json。它的 SHA-256 为 56e389e7a8fbe1d22576332cbbf2a1279928c8f3722d8e2231a0158288e2375f。
- 同一份 374 文件通过普通 HTTPS 从现有 play.gttgames.com 逐个下载，与导出文件 SHA-256/长度/兼容 MIME 比对全部通过。没有使用真实玩家凭据或修改线上数据。
- 正式素材路径现已回源私有 S3，EC2 原素材和服务保留用于回退；HTML 启动入口和动态 API 保持原 ALB/EC2 链路。后续维护应从 edge-assets-activate.json 或当前实际栈模板出发；03-edge.json 和 edge-rollback.json 是迁移前基准，不能当作当前线上模板直接覆盖。

## 执行记录

- 用户已在 CloudShell 执行 prepare，提交变更集 gtt-assets-prepare-2e8b417be6a4，UUID cbfbb0f1-ea06-41f6-959e-2bc3b5051bbb，executed=false。守卫检查已通过，当前待 AWS 最终变更集预览；还未执行 prepare、probe 或 activate。
- 用户随后提供最终预览 CREATE_COMPLETE / AVAILABLE、Reason=null：四项 Add 和 BusinessDistribution Modify、Replacement=False，与预期一致。已核对通过，下一步执行并等待 UPDATE_COMPLETE，然后全量 probe；尚未收到这两步结果，activate 未提交。
- 用户随后执行 prepare 并在等待 UPDATE_COMPLETE 后完成全量 probe：374 文件全通过、errors=[]、TLS 校验开启、发布 ID/清单 SHA-256 匹配；两个后台 portal 200、无凭据 API/钱包 401，三个非游戏域名访问校验素材均 404。准备阶段及 S3 OAC 实际回源验证通过，下一步提交 activate 变更集；正式路径仍未切换。
- 用户随后提交 activate，返回变更集 gtt-assets-activate-2e8b417be6a4 / a4eba270-877d-47c0-a81c-2c30d36b2455，submitted=true、executed=false。当前等待最终 AWS 预览，尚未执行、清缓存或验证正式路径。
- 用户随后提供最终预览 CREATE_COMPLETE / AVAILABLE，Reason=null，只有 BusinessDistribution Modify / Replacement=False。正式切换变更集已核对通过，下一步执行并等待更新完成、清除原素材前缀缓存、验证正式路径；这些步骤结果仍待确认。
- 用户随后执行 activate、等待 UPDATE_COMPLETE、创建并等待两条旧素材前缀缓存失效，再运行 active 验证：status=passed、phase=active、checked=374、errors=[]、TLS 校验开启，发布 ID 与清单 SHA-256 匹配。两后台配置 200、未认证 API/钱包 401、非游戏域名访问根素材 404。S3 元数据和文件 SHA-256 确认正式 URL 已使用目标 S3 发布版本。
- 本机进一步抽查正式 PNG URL，连续访问从 Miss from cloudfront 转为 Hit from cloudfront，Age=1，Cache-Control=public, max-age=300, s-maxage=86400，x-amz-meta-gtt-release=2e8b417be6a438768bc4；匿名 S3 对象 GET 仍返回 403。记录见构建目录 post-activation-check.json。未读取生产凭据或执行有认证的下注/结算，不把静态迁移验收扩展为全部游戏业务验收完成。

## 为什么分两次更新边缘栈

第一次 prepare 增加 OAC、静态缓存策略、游戏域名函数、桶策略及一个 S3 源站，并仅增加 /__gtt-assets-check/* 校验路径。既有静态路径和全部动态路径保持现状。桶策略只授权现有业务分配 E3RCHQALSXUQDV 读取 releases/buffalo-win/*，且要求 TLS；业务分配显式依赖该桶策略，使源站启用前权限已安装。

第二次 activate 在完整校验路径检查通过后，把 /assets/*、/shared/* 和清单中 31 个根目录静态文件的精确路径切到 S3。根目录 HTML、认证、钱包、下注、商户 API、后台仍回源 ALB。当前模板含 34 个缓存行为，在 AWS 文档所列默认 75 个的配额内；实际更新仍需 AWS 服务端确认。

静态 S3 缓存策略不转发 Host、Cookie、Authorization 或查询参数；OAC always 签名。函数先检查 Host=play.gttgames.com，再将校验前缀移除并清空查询参数。其他业务域名访问静态路径仍返回 404，避免把同一分配上的后台路由变成公开 S3 入口。S3 对象浏览器缓存 300 秒，CDN 缓存最多 86400 秒；切换后需清除旧静态缓存并重新验证。

## CloudShell：当前只提交 prepare 变更集

上传 gtt-game-assets-migration-20261029.zip 后：

```sh
unzip -n /home/cloudshell-user/gtt-game-assets-migration-20261029.zip -d /home/cloudshell-user/gtt-game-assets-migration &&
python3 /home/cloudshell-user/gtt-game-assets-migration/asset_change_set.py prepare
```

脚本先验证当前账号、边缘栈状态、分配 ID、当前栈模板与原模板完全一致、S3 四项保护及已提交清单 SHA-256、全量线上基线报告，再提交 UPDATE 变更集。只保留既有栈参数并追加三个素材参数，不读取 CloudFront 的回源密钥原文。不自动执行，也不修改 DNS。

预计变更：Add GameAssetsOac、GameS3Cache、GameAssetFunction、GameAssetsBucketPolicy，Modify BusinessDistribution 且不替换；不改其他既有资源。返回的变更集名预计 gtt-assets-prepare-2e8b417be6a4，实际以脚本输出为准。审阅 DescribeChangeSet 后再执行。

## prepare 部署成功后

```sh
python3 /home/cloudshell-user/gtt-game-assets-migration/game_assets.py verify --manifest /home/cloudshell-user/gtt-game-assets-migration/manifest.json --phase probe
```

该检查通过 /__gtt-assets-check/* 下载全部 374 文件，核对 SHA-256、长度、MIME、缓存头与 S3 发布元数据；再检查两个后台 portal、未认证 API/钱包及其他域名访问素材的隔离。全部通过才写出 verify-probe.json，之后可提交 activate 变更集：

```sh
python3 /home/cloudshell-user/gtt-game-assets-migration/asset_change_set.py activate
```

activate 预计只有 BusinessDistribution Modify，不应替换分配或修改动态默认行为。仍先审阅变更集，再执行。

## activate 部署成功后

先清除现有两条素材路径的旧 CDN 缓存（它们此前已走 CloudFront 缓存，根目录静态路径此前使用默认禁缓存行为）：

```sh
aws cloudfront create-invalidation --region us-east-1 --distribution-id E3RCHQALSXUQDV --paths '/assets/*' '/shared/*' --no-cli-pager
```

记录返回 ID，等待 invalidation-completed 后运行：

```sh
python3 /home/cloudshell-user/gtt-game-assets-migration/game_assets.py verify --manifest /home/cloudshell-user/gtt-game-assets-migration/manifest.json --phase active
```

需要再确认实际游戏启动、图片/音效和完整游戏回合，不能用未认证请求或文件比对宣称全部游戏业务验收通过。本次是同一客户端版本的素材迁移；未来升级客户端须另行处理老会话的版本路径兼容，不能直接删旧发布前缀。

## 回退

EC2 原素材与服务都保留，edge-rollback.json 为部署前的原边缘栈模板。可运行 asset_change_set.py rollback 提交只恢复业务原路由的 UPDATE 变更集，审阅后执行，再清除 /assets/*、/shared/* 旧缓存；若正式静态路由已缓存根文件，还需为清单里的根文件清缓存。回退模板会移除本次 OAC、素材策略/函数/缓存策略，但不会删除外部素材桶或任何发布对象。若策略被手动改过，脚本的模板一致性检查将停止，需要先审阅实际差异。

## 后续本机构建与上传

game_assets.py build --archive 已部署发布包 --output-parent 输出目录 生成内容寻址的不可变版本，发布器在上传前验证所有本地字节，已存在对象校验不一致时拒绝覆盖。不使用 sync --delete。publish_game_assets.py 需要 boto3，可安装在独立工具环境；显式使用 --profile sds-test。首次缺少写权限会停止，避免对整批文件重复尝试被拒绝的操作。

凭据由本机 AWS 配置读取，不写入脚本、ZIP、对象元数据或终端输出。构建目录、上传回执、验证结果位于忽略目录 diagnostics/releases/gtt-game-assets-2e8b417be6a438768bc4。

依据：

- https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html
- https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/DownloadDistValuesCacheBehavior.html
- https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/cloudfront-limits.html
