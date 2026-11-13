# 商户客户端启动模式检查

> 目录已重组。当前启动命令与路径见[四目录说明](../project-layout.md)；本文中的旧命令保留为历史记录。

2026-11-07。范围为当前 Node 商户网关的全部 19 款游戏；独立游戏服务和大厅的试玩入口保留，不更改其账号、钱包或启动语义。本次不发布线上应用或 S3 素材。

后续逐款浏览器验收累计确认其余 18 款中的 16 款，Super Ace 和 Mahjong Ways 2 仍待完成；期间补入 PG 图片并修正麻将模块、JILI 原生钱包币种、PP 地址配置及设置请求锁冲突。逐款结果、截图位置、工具中断与剩余操作见 [浏览器验收记录](merchant-ui-validation-2026-11-07.md)。HTTP 回归不替代两款剩余游戏的画面验收。

## 已确认的问题与修正

| 厂商及游戏 | 原商户链路遗留 | 商户模式 |
| --- | --- | --- |
| PG：Buffalo Win、Captain's Bounty、Fortune Rabbit、Wild Bandito、Mahjong Ways 2 | 统一 launch 带 mock=1、btt=2；前四款脚本强制 btt=2、ot=local-demo；麻将只在 mock=1 时注入会话传输，并使用本地模拟登录响应 | 商户启动不带 mock，五款均 btt=1，operator/会话/玩家/币种/余额绑定已验证商户；麻将保留必要的二进制 GameInfo 桥接，不走模拟登录校验 |
| JILI/TaDa：Super Ace、Fortune Gems 2、Joker's Fortune WinX、3 Billion Vaults、Money Pot Deluxe、Roma X 10000 | 本地处理器重定向时补回 demo=true、loginFrom=trial、ssoKey=local | 认证后的商户重定向 demo=false，去掉 trial 来源，SSO key 使用当前会话；后续协议请求仍由商户钱包结算 |
| Hacksaw：Wicked Grin、Le Vampire、Dr Zappo、Great Game Serengeti | 重定向 mode=2、partner=demo、固定 EUR，并用 disableddemotext 隐藏试玩文字 | mode=1，partner 与币种来自实际商户；移除隐藏文字开关；认证账户及实时余额来自商户会话 |
| PP：Gates of Olympus、Sweet Bonanza POP、Big Bass Bonanza | 通用 launch 外层带 mock=1，但原客户端配置已经是 accountType=R、demoMode=0、showRealCash=1 | 移除外层 mock；保留原有账号模式配置和商户钱包接口；hub-demo 是现有静态/协议路径名，不据此认定为试玩模式 |
| Play'n GO：Tower Run Treasure Steps | launcher 模板 practice=1、空 ticket；登录协议回包固定 DEMO 币种 | 商户 HTML practice=0、ticket 绑定当前会话；登录协议使用实际商户币种和玩家 |

PG 美洲野牛客户端 `assets/main/index.719d7.js` 的原始字符串表还原后，`isDemo()` 明确比较 `cs_Launch.betType === '2'`。四款 Hacksaw 的 `casino/hacksaw-casino.min.js` 均有 `case 1: return "live"; case 2: return "demo"`。Tower 的 `fixtures/launcher.html` 明确包含 `practice: 1`。这些是客户端代码/模板证据，不把缺少的原站真钱抓包写成已完成验证。

## 会话与协议约束

- 网关完成 Host、Origin、签名启动会话和游戏归属校验后，才向商户 HTML 注入会话上下文。不能仅凭客户端 query 声明就取得商户钱包。
- PG 商户请求接受 btt=1；四款原来只接受 2 的适配器按服务端商户上下文切换校验，独立服务仍使用原值。旧 btt=2 投注在商户会话中拒绝，不通过隐藏弹窗或改翻译字符串绕过。
- PG 登录保留客户端必需的 `oj` 账号元数据；五款的可见 WebView 帧率兼容脚本也接受已认证的商户上下文，不再以 `mock=1` 作为唯一启用条件。
- 商户 iframe 的同源 fetch/XHR 使用当前会话凭据；WebSocket 使用同源会话参数，重定向保留 ops。跨源请求不附加凭据，不依赖第三方 Cookie。
- 原客户端数学展示、动画、历史及玩法入口保留。PG 美洲野牛的购买免费权限保持原配置；余额和结算继续通过商户钱包，不创建匿名试玩账户。

## 验证与发布边界

最终 241 项 Node 回归通过。检查包含 19 款商户 launch、实际重定向参数、最终 HTML、PG 商户登录响应、原始协议投注与去重结算，确认 PG 的试玩 btt=2 被拒绝；另验证五款 PG 的原独立启动行为、商户 WebView 帧回调、跨源凭据隔离、三款 PP 原生设置 POST 和两款 JILI 原生钱包币种。商户接入规范与下载示例已更新到 v1.14.0。

美洲野牛已在本机 8110 的商户会话中完成浏览器启动验收：`btt=1`、商户 operator、实际账号币种和余额，登录后进入主画面，无 Demo Mode 弹窗，购买入口保留。仅操作启动与原版验证通知，未发起投注。验收截图保存在 `diagnostics/merchant-mode-buffalo-win.jpg`。

浏览器验收另发现正式模式加载的 7 张原版图片未导入，导致登录完成后停留在加载画面。先核对最新抓取 `1979cf39544d4c4c8b86d6e3ac0e036f`，请求 513–519 均为成功响应，已按原路径恢复到 `clients/buffalo-win/shared/2fd142260e/`，逐项检查 PNG 签名和捕获长度，记录 SHA-256、来源与请求号。详见 `clients/buffalo-win/fixtures/merchant-mode-assets.json` 和合并后的 `asset-sources.json`；没有用占位图或关闭原功能绕过。

本次修改五款 PG 的启动注入和帧率兼容脚本，并恢复美洲野牛 7 张素材。客户端静态素材若发布线上，必须按构建规则生成新素材版本并绑定配套应用，不能沿用旧脚本字节的素材清单；尚未构建或上传该新版本。其余厂商的商户模式在后端响应边界处理，原静态资源字节保留。

HTTP/协议回归不代替全部 19 款浏览器视觉验收；不同浏览器和生产 HTTPS/CDN 的启动、刷新恢复仍需分别验收。缺少的玩法抓包和资源继续见各游戏规则及资源缺口文档。
