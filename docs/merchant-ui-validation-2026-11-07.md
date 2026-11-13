# 商户模式逐款浏览器验收

本轮范围：除上一轮已验收的 Buffalo Win 外，其余 18 款。续验剩余 8 款后，累计已确认 16 款进入原版主画面；Super Ace 和 Mahjong Ways 2 仍待完成浏览器验收，不能据此声称 18 款全部正常。

使用本机 8110、现有 `test` 商户 `GTT000002` 和独立玩家 `merchant-ui-check-20261107`，正常签名启动接口与商户会话，USD、固定四位商户精度。验收钱包只服务该测试玩家，余额为 USD 10,000.00。没有发起投注，网关 `game_operations` 中该玩家记录数为 0。没有创建或恢复 8210 环境，没有发布线上。

用户补充要求后，同时最多保留两个游戏页面，逐款检查并关闭；遇到工具无法关闭的页面由用户协助。已恢复测试商户原有游戏权限和全部临时游戏开关，并停止临时验收钱包。两轮恢复记录分别保存在忽略目录 `server/runtime/merchant-ui-check-snapshot.json` 和 `server/runtime/merchant-ui-check-resume-snapshot.json`，没有更改其他商户的玩家进度。

## 逐款结果

| 游戏 | 本轮结果 | 观察与剩余事项 |
| --- | --- | --- |
| Captain's Bounty | 通过 | `btt=1`、商户 operator、USD 会话；进入主盘面，余额 10,000.00，无 Demo 弹窗 |
| Fortune Rabbit | 通过 | 同上，原版主盘面及控制按钮正常显示 |
| Wild Bandito | 通过 | 同上，原版主盘面及控制按钮正常显示；未验证免费资源等其他已知缺口 |
| Tower Run Treasure Steps | 通过（启动范围） | `practice=0`、商户票据、USD 余额；原版主盘面已加载，保留首次 Go Ultra 教程。教程提示首次旋转继续，本轮没有执行旋转 |
| Great Game Serengeti | 通过 | `mode=1`、实际商户 partner、USD；关闭原版启动介绍后主盘面正常 |
| Dr Zappo | 通过 | 同上 |
| Le Vampire | 通过 | 同上 |
| Wicked Grin | 通过 | 同上 |
| Roma X 10000 | 通过 | `demo=false`、商户 SSO；完成原版 Continue/Play 启动，主盘面及商户余额正常 |
| Money Pot DELUXE | 通过 | 同上 |
| 3 Billion Vaults | 通过 | `demo=false`、实际商户 SSO；修正钱包协议中的 SC 名称后，主盘面余额、WIN、PLAY 均显示 USD，余额 10,000.00 |
| Joker's Fortune WinX | 通过 | 同上；完成原版 Continue/Play 后进入主盘面，余额 USD 10,000.00 |
| Fortune Gems 2 | 通过 | `demo=false`、实际商户 SSO、USD 上下文；原版 Continue/Play 后完整主盘面与余额 10,000.00 正常。该原版画面不显示币种文字 |
| Super Ace | 待验收 | 续验已打开 `demo=false` 商户入口；截图及重新连接超时，尚无主盘面验收结果，不能认定为通过或确定为游戏故障 |
| Big Bass Bonanza | 通过 | 商户 `accountType=R`、`demoMode=0`；修正 PP origin 和设置请求锁冲突后，原版主盘面、USD 10,000.00 正常；使用原版首次介绍偏好后重新加载确认 |
| Sweet Bonanza POP | 通过 | 同上，点击原版启动箭头后进入主盘面；USD 10,000.00，未旋转 |
| Gates of Olympus | 通过 | 同上；原版主盘面、USD 10,000.00、购买免费与 ante 入口正常显示。已复核保存的主画面截图并补记清单 |
| Mahjong Ways 2 | 待复验 | 修复 7 个公共模块返回 500 的原因；之后该页 DOM/focus 操作超时，尚不能区分客户端执行问题与浏览器控制故障，未验收到主盘面 |

16 张逐款主画面截图与无令牌的观察记录在 `diagnostics/merchant-ui-20261107/`，其中 `results.json` 只把已观察到主画面的 16 款标为通过。启动通过不代表普通投注、免费回合、购买、断线恢复等全部玩法验收完成。

## 本轮修正与证据

1. 三款 PG 均缺少 `shared/4528468aab/` 下的 `93111cc830.11720.png`、`9d112f7e32.69cdf.png`、`28f911ed51.9a259.png`，浏览器返回 404 后反复加载。先检查现有 31 份抓取清单，未找到这些路径的成功响应；原 `static.eajzzxhro.com` 补取返回 403，随后从已有最新抓取使用的原 CDN `s5.mmga1.com` 成功取得同路径文件。检查 PNG 签名，记录长度、SHA-256 和源 URL，各游戏的 `fixtures/merchant-mode-assets.json` 保存逐项来源。恢复后上述三款均已进入主画面，没有关闭原入口或使用占位图片。
2. Node 的模块修复函数将 `$1'.+$';` 作为字符串替换模板，其中 `$'` 被 JavaScript 解释为原文后缀，导致麻将模块生成无效脚本。改用函数返回替换内容；7 个实际麻将公共模块初始化检查通过，修复结果与现有 Python `repair_source` 的同一模块 SHA-256 一致。没有将后续浏览器超时认定为已经解决。
3. 两款 JILI 的重定向仍带 `currency=SC`，商户入口现在用已认证商户币种替换该字段。续验确认仅改 URL 不够：原版 `GameInfoAck.WalletInfo` 的 `currencyName`、`currencySymbol` 仍为 SC。现在按每次已认证请求的商户币种填写这两个显示字段，保留捕获的协议钱包编号 80、原协议路径与玩法配置；独立入口不提供商户币种，原行为保留。两款原版主画面均已确认显示 USD 10,000.00。19 款入口测试增加两款原生 GameInfo 解码断言，覆盖币种、余额及钱包编号。
4. Big Bass 的浏览器配置直接显示 `datapath` 和 `gameService` 为 `http://127.0.0.1:8110/...`，与 `g16.localhost` 游戏 origin 不同。PP 商户 HTML 的这两个字段现在使用配置的游戏 origin，包括生产 HTTPS；三款均有相关回归断言，浏览器均已进入主盘面。
5. PP 原生 `saveSettings.do` 先打开写事务再解析玩家；商户玩家同步另用 SQLite 连接写入镜像，造成锁冲突和 500。现在进入原生处理器前先同步已认证会话，后续同请求使用已同步快照。三款 PP 原生 POST 设置请求均增加 200、空正文回归断言；空 JSON 响应不再被强行解析。原版介绍与设置入口保留。

本次最终源码的全套 241 项 Node 测试通过（241 passed、0 failed）。日志为 `server/runtime/merchant-ui-resume-tests.log`。运行服务已加载当前构建，8110 健康检查返回 200。

本轮补入原版图片，线上应用与静态素材仍需按构建规则配套生成新版本，不能沿用旧素材清单或视作已上线。

## 验收中断与下一步

初轮浏览器出现 focus、DOM snapshot 超时及会话重置，完成 10 款。续验在最多两个游戏页的限制下完成另外 6 款；打开 Super Ace 后截图与连接超时。用户最后澄清此前只是收起浏览器面板，并未点 × 关闭游戏标签，因此工具仍列出 Buffalo Win 和 SuperAce。后台页曾短暂恢复，但新验收页无法附着；没有成功创建第三个游戏页。尝试 Chrome 备用验收时，Windows Computer Use 无法可靠确定当前 URL，强制结束本轮操作。继续前需真正关闭上述两个游戏标签。没有将这些工具故障推断为游戏已通过，也没有确定为某个游戏的代码故障。

恢复浏览器控制后，每次最多打开两个游戏页，只需继续 Super Ace 和 Mahjong Ways 2：重新签名启动并确认正式模式标记、钱包及原版主画面，保存截图。麻将需额外核查模块请求、脚本执行与登录初始化；Super Ace 需先采集实际失败请求或执行栈，不能仅因工具超时修改其版本相关域名适配。

已有非启动阻塞的缺失响应仍记录在 `results.json`：Tower promotions、部分 favicon；JILI 邮件列表 `/rankingservice/user/GetMailList`；Joker `/sss-jf2/JILI_NEW.png`；Sweet Bonanza POP `/gs2c/promo/active/`。平台附加功能与资源应先核对已有最新抓包，再补抓邮件列表/邮件打开、活动与奖励操作的请求响应；图片需核对实际请求路径和来源。没有隐藏这些入口或伪造成功响应。
