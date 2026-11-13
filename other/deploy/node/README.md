# Node 部署模板目录

这里保存的是可提交、可随基础设施包发布的**部署模板**，不是本机实际运行配置。

| 模板 | 用途 | 本机运行文件 |
| --- | --- | --- |
| `platform.env.example` | 网关、管理后台、RTP worker 共用的平台配置模板 | `gateway/instance/platform.env` |
| `game.env.example` | 单款游戏、单个运行版本的配置模板 | `games/<game>/instance/releases/<release>.env` |
| `postgres.env.example` | PostgreSQL 容器首次初始化模板 | `other/deploy/instance/postgres.env` |

`.example` 表示示例，其中的占位值不能直接当作部署凭据。模板集中在这里，是因为它们与同目录的 systemd 单元和生产结构配置共同组成基础设施发布包；实际配置按所属部署实例分别存放，不在这里维护密码。

生产环境的平台配置部署到 `/etc/gtt-node/platform.env`，游戏实例配置部署到 `/etc/gtt-node/games/<game>/<release>.env`。实际 env 不提交 Git、不进入发布包，也不被前端读取。

根目录四个业务文件夹的划分保持不变。生成命令、加载优先级及部署步骤见[环境配置与部署](../../docs/project/environment-and-deployment.md)。
