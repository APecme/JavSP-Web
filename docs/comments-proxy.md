# 评论同源转发（F09）

浏览器不再直接请求评论服务：公开评论与评论身份 API 统一走本站 `/api/comments/*`，由服务端
`javsp_web/comments_proxy.py` 转发到固定的上游。Cloudflare 人机验证页面仍留在验证域，不经过本站转发。

## 配置

| 环境变量 | 说明 |
| --- | --- |
| `JAVSP_COMMENTS_URL` | 上游评论服务地址，仅由服务端决定。未设置时沿用内置默认 `https://comments.rtioo.com`；显式设为空字符串即彻底禁用评论（`comments_url` 与 `comments_verify_url` 均为 `""`，前端隐藏评论入口）。非法值（非 http/https、带账号密码、带 query/fragment）同样视为禁用。 |
| `JAVSP_COMMENTS_VERIFY_URL` | 可选。验证页面的来源，默认等于 `JAVSP_COMMENTS_URL`。仅在该来源与数据源不同（例如独立验证域）时才需要设置。 |

`GET /api/runtime` 返回：

```json
{"comments_url": "/api/comments", "comments_verify_url": "https://comments.rtioo.com"}
```

`comments_url` 永远是同源相对路径，前端在其后拼接上游路径，例如
`/api/comments` + `/api/threads/ABC-001/comments` = `/api/comments/api/threads/ABC-001/comments`。

## 允许转发的方法与路径

上游路径按“前缀 + 原路径”透明镜像，逐条白名单校验；未列出的路径一律 403，路径匹配但方法不匹配返回 405。

| 方法 | 路径 |
| --- | --- |
| GET | `/api/comments/api/config` |
| GET / POST | `/api/comments/api/threads/{番号}/comments` |
| POST | `/api/comments/api/comments/{id}/like` |
| POST | `/api/comments/api/comments/{id}/reports` |
| DELETE | `/api/comments/api/comments/{id}` |
| POST | `/api/comments/api/identity` |
| GET / POST | `/api/comments/api/me/profile` |
| GET | `/api/comments/api/me/comments` |
| POST | `/api/comments/api/me/logout` |
| POST | `/api/comments/api/me/logout-all` |
| POST | `/api/comments/api/me/pin` |

禁止：`/api/admin/*`、用户在路径中携带完整 URL、`..` / 百分号编码逃逸、非白名单方法、任意 query。
番号只接受 `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`，评论 ID 重新按整数规范化，query 仅允许 `before`、`limit`
（1–18 位数字，按固定顺序重写）。

## 边界与隔离

- 准入：所有转发请求都要求本站登录会话（`Depends(current_user)`），未登录返回 401，且不会触达上游。
- 请求头：只转发 `X-User-Token`（评论身份 token，格式校验失败 400）、`X-Delete-Token`（仅评论删除路由）、
  固定 `Accept`/`Content-Type` 与固定 `User-Agent`；本站 Cookie、`Authorization`、`Origin`/`Referer`、
  `X-Forwarded-*`、`CF-Connecting-IP`、`X-Real-IP` 一律丢弃，也不构造任何伪造转发头。
- 响应头：只保留状态码、JSON 内容与数值型 `Retry-After`；上游 `Set-Cookie`、`Location` 及其他头不回传，
  上游 3xx 直接按 502 处理，不跟随跳转。
- 上限：请求体 64 KiB（超限 413，非 JSON 415），响应体 1 MiB（超限 502），连接/读取超时 5s/10s，
  同时最多 16 个上游请求。
- 错误：网络失败 502、超时 504，均为固定中文提示，不含上游主机、端口或异常类型；上游状态码
  （400/401/403/404/409/413/415/428/429/5xx）与 `Retry-After` 原样保留，428 的 `challenge` 字段原样透传。

## 验证流程

`JavspCommunity.configure(url, verifyUrl)` 拆分为“数据 API 基址”和“验证来源”：

- 数据请求：`comments_url`（同源相对路径）+ 上游路径，`credentials: 'omit'`、`referrerPolicy: 'no-referrer'`。
- 验证 iframe：`${comments_verify_url}/verify#action=…&nonce=…`，直接加载验证域页面。
- 回传校验：`event.origin` 必须等于验证来源的 origin、`event.source` 必须是该 iframe、`type` 为
  `javsp-verification`、nonce 与 action 必须匹配、token 必须是非空且不超过 4096 字符的字符串。
- 旧的单参调用 `configure(url)` 仍可用：验证来源回退为同一个绝对地址；若只给相对基址而没有验证来源，
  `verify()` 会明确拒绝（“评论验证服务未配置”），而不是加载一个必然失败的页面。

验证页面不能转发：评论服务在 `siteverify` 时比对 `hostname`（Worker 中 `TURNSTILE_HOSTNAME`，默认
`comments.rtioo.com`）。如果把验证 HTML 放到本站域名下渲染，Turnstile 返回的 hostname 会变成站点域名，
验证必然失败。因此本站只代理数据接口，验证页面保留在验证域。

## 已知限制

1. 数据接口经服务器转发，但验证 iframe 与 Turnstile 脚本（`challenges.cloudflare.com`）仍由浏览器直连
   第三方；网络受限环境下验证可能无法完成，此时评论不可用。
2. 上游看到的来源地址是本站出口 IP：上游按 IP 的限流（读请求限流、评论/点赞/举报的 IP 维度配额）会由全部
   本站用户共享，而按评论身份维度的限流仍然独立。上游的评论线程缓存（15s）会吸收重复读取。我们不伪造
   `CF-Connecting-IP` 或任何转发头来绕过该限制，也不放宽上游风控；如果确实需要更细的粒度，应在上游为该
   部署单独配置限额或使用独立出口。
3. 上游若返回非 JSON（例如 Cloudflare 拦截页），代理只能给出脱敏的 502，无法区分具体原因。
4. CSRF 边界与站点其他写接口一致：`HttpOnly` + `SameSite=Lax` 会话 Cookie，未额外引入 CSRF token。
5. 本站登录被注销后评论立即不可用（准入在代理层），这是有意的行为。

## 验收

```bash
python -m unittest tests.test_comments_proxy -v   # 19 项：白名单/隔离/超时/大小/状态码/运行时配置
node --test tests/test_community_client.cjs       # configure 拆分、相对基址、nonce/action/source
node --test tests/test_comments_client.cjs        # 同源 base + 验证来源分别下发
```
