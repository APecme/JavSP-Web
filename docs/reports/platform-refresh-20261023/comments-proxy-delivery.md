# DELIVERY — 第 1 项：评论同源转发

按 `docs/superpowers/plans/2026-10-23-platform-refresh.md` 第 1 节与全局约束实现。独立副本、无 Git 操作、未改动数据/凭据/生产状态，未构建 docs/demo。

> 第 2 轮返修（同源代理凭据、`configure` 验证源）见文末「返修（第 2 轮）」；文首各节的测试计数是第 1 轮结果，已被第 2 轮覆盖。

## 环境（如实说明）

- 会话中 **`/tmp/javsp-bata-validation-venv` 不存在**；系统 `python3`（3.14.4）没有 fastapi/starlette，无法跑既有 Python 测试。
- 本机 `/tmp` 不跨命令持久（验证过：上一命令写入的文件下一命令消失），因此临时 venv 建在副本内、验收后删除。
- 实际验证环境：临时 venv（Python 3.14.4）+ `fastapi 0.161.1`、`starlette 1.9.0`、`httpx 0.28.1`、`requests 2.34.2`、`PyYAML 6.0.3`、`croniter 6.2.4`、`python-multipart 0.0.32`、`pycryptodome 4.1.0`、`cryptography 50.0.2`、`packaging 26.3`、`pillow 13.0.0`、`pydantic 2.14.1`；Node v22.23.2。
- 复现方式（主代理可自行重建）：

```bash
python3 -m venv .test-venv
.test-venv/bin/pip install "fastapi>=0.115" httpx requests PyYAML croniter python-multipart \
  pycryptodome cryptography packaging pillow
JAVSP_WEB_DATA_DIR=$PWD/.verify/data .test-venv/bin/python -m unittest tests.test_comments_proxy -v
```

## 修改的文件

### 新增

| 文件 | 内容 |
| --- | --- |
| `javsp_web/comments_proxy.py` | 独立 router + 服务端请求层：上游固定为 `JAVSP_COMMENTS_URL`，逐方法/路径白名单，请求体/响应体上限、超时、并发上限，请求头允许清单、响应头白名单、错误脱敏；`upstream_base()` / `verify_base()` / `runtime_entry()` 供 runtime 使用。 |
| `tests/test_comments_proxy.py` | 19 项离线测试：本地录制型上游（`ThreadingHTTPServer`）+ 最小 FastAPI app，覆盖准入、白名单/编码绕过/方法混淆、query 限定、Cookie/Authorization/代理头隔离、上游 Set-Cookie/302 拦截、状态码与 `Retry-After`、断网/超时、请求与响应大小、非 JSON 上游、204，以及 `/api/runtime` 的 `comments_url`/`comments_verify_url`。 |
| `docs/comments-proxy.md` | 本功能的局部说明：配置、白名单表、隔离边界、验证流程、限制、验收命令。 |

### 修改（仅这 5 个共享文件）

| 文件 | 改动 |
| --- | --- |
| `javsp_web/server.py` | 第 97–98 行 `include_router(comments_proxy.router)`；删除旧的模块级 `COMMENTS_URL`（原第 103 行）；`/api/runtime`（第 324 行）改为 `**comments_runtime()`，输出 `comments_url` + `comments_verify_url`。其余不动。 |
| `javsp_web/web/assets/community.js` | `configure(url, verifyUrl)` 拆分 API 基址与验证来源（第 18–28 行）；`verify()` 增加“验证来源未配置”拒绝（第 52 行）；iframe 用 `verifyBase`（第 63 行）；消息校验 origin 改为 `verifyOrigin`，并拒绝空/超长 token（第 71 行）。 |
| `javsp_web/web/assets/app.js` | 两处 runtime 加载改为 `configure(runtime.comments_url, runtime.comments_verify_url)`（第 1204、3715 行）；影片详情打开评论时传入 `comments_verify_url`（第 2050 行）；`JavspComments.open(identifier, baseUrl, taskId, verifyUrl)` 且 base 为空时不再清空全局配置（第 3838–3841 行）。 |
| `tests/test_community_client.cjs` | fixture 扩展（记录 fetch、提供 `api`/`escapeHtml`/`AbortSignal`/节点桩、可传 base/verify）；新增 3 项：同源相对基址下数据请求保持相对 + 验证走自身 origin、相对基址缺验证来源时明确拒绝、旧单参绝对基址兼容；反例补充 token 类型/长度。 |
| `tests/test_comments_client.cjs` | harness 记录 `configure` 实参；新增 1 项：`/api/comments` + 独立验证来源分别下发、请求 URL 为 `/api/comments/api/threads/...`、`credentials:'omit'`、禁用时无请求且 section 隐藏。 |

未新增依赖（只用既有 `requests`/`fastapi`/`starlette.concurrency.run_in_threadpool`）。未改动 `comments-service/`、`vendor/`、页面 HTML/CSS、构建脚本、demo 资产。

## 行为

- `GET /api/runtime`：启用时为 `{"comments_url": "/api/comments", "comments_verify_url": "https://<上游或独立验证域>"}`；`JAVSP_COMMENTS_URL` 显式为空/非法 → 两者均为 `""`（前端隐藏评论入口）；未设置时沿用内置默认 `https://comments.rtioo.com`（与现状一致）。`JAVSP_COMMENTS_VERIFY_URL` 可选，默认等于数据上游。
- 公开 URL 形状：`/api/comments` + 上游原路径，例如 `/api/comments/api/threads/ABC-001/comments`、`/api/comments/api/me/profile`。
- 白名单（未列出→403，路径匹配方法不符→405）：`GET api/config`、`GET/POST api/threads/{番号}/comments`、`POST api/comments/{id}/like`、`POST api/comments/{id}/reports`、`DELETE api/comments/{id}`、`POST api/identity`、`GET/POST api/me/profile`、`GET api/me/comments`、`POST api/me/logout`、`POST api/me/logout-all`、`POST api/me/pin`。
- 准入：所有转发都要求本站登录（`current_user`）；未登录 401 且不触达上游。
- 隔离：只转发 `X-User-Token`（带格式校验）、仅删除路由的 `X-Delete-Token`、固定 `Accept`/`Content-Type`/`User-Agent`；本站 Cookie、`Authorization`、`Origin`/`Referer`、`X-Forwarded-*`、`CF-Connecting-IP`、`X-Real-IP` 全部丢弃；上游 `Set-Cookie`、`Location` 及其他头不回传，3xx 一律 502。
- 上限与超时：请求体 64 KiB（流式累计，chunked 也受限；超限 413，非 JSON 415）、响应体 1 MiB（超限 502）、连接/读取 5s/10s、并发 16。
- 错误：断网 502、超时 504，固定中文提示，不含上游主机/端口/异常类型；上游 400/401/403/404/409/413/415/428/429/5xx 与数值型 `Retry-After` 原样保留，428 的 `challenge` 透传。

## 测试命令与结果

最终一轮（清理 venv 之前执行）：

```bash
# 新增功能测试
JAVSP_WEB_DATA_DIR=$PWD/.verify/data .test-venv/bin/python -m unittest tests.test_comments_proxy -v
# → Ran 19 tests ... OK

# 全量 Python（249 个旧测试 + 19 个新测试）
JAVSP_WEB_DATA_DIR=$PWD/.verify/data .test-venv/bin/python -m unittest discover -s tests -p "test_*.py"
# → Ran 268 tests, FAILED (failures=12, errors=22, skipped=1)
#   最终复核同样 34 条失败/错误，与改动前基线逐条一致：基线 Ran 249 tests，同一批 34 个失败/错误
#   （缺 selenium/cloudscraper/confz 等可选依赖、vendor JavSP 导入、扫描任务环境），逐条 diff 相同

# 前端
node --test tests/test_comments_client.cjs   # 11 pass / 0 fail
node --test tests/test_community_client.cjs  # 6 pass / 0 fail
node --test tests/*.cjs                      # pass 47 / fail 8
#   基线：51 项 42 pass / 9 fail；改动后 55 项 47 pass / 8 fail。失败集合仍为 demo 构建相关（docs/demo 未构建）
#   + 既有 AI/布局用例；其中 “old chapter bookmarks…” 在整跑中本身不稳定（单跑通过），与本次改动无关
node --check javsp_web/web/assets/app.js javsp_web/web/assets/community.js  # 语法通过
```

改动前的失败清单与改动后逐条一致（Python 34 条、Node 同一集合），没有为了通过而修改旧断言；只按新语义扩展了两个 JS harness（记录 `configure` 实参、可传 base/verify）。

## 关键取舍

1. **URL 形状用透明镜像**（`/api/comments` + 上游原路径，故出现 `/api/comments/api/...`）：保持与 comments-service 文档一致的单一路径词汇，且旧单参 `configure('https://comments.<domain>')` 直连模式仍完全可用。若把前缀“吃掉”上游 `/api`，路径更短但会破坏单参直连兼容，故不采用。
2. **验证页面不转发**：Worker `verifyHuman()` 会比对 `result.hostname` 与 `TURNSTILE_HOSTNAME`（默认 `comments.rtioo.com`）。把验证 HTML 放到站点域名渲染会让 hostname 变成站点域，验证必然失败。因此 `comments_verify_url` 与数据 base 分离，iframe 直连验证域，前端校验 origin/source/nonce/action/token。
3. **失败关闭**：上游未配置、非法、缺 scheme 一律禁用而不是半可用；相对基址但无验证来源时 `verify()` 明确报“验证服务未配置”，避免加载必然失败的页面。
4. **默认上游保留**：不设置环境变量时仍指向内置生产地址（现状行为），只有显式空值才禁用；这一点在文档与 runtime 中都能看到。
5. **不伪造转发头**：不设置 `CF-Connecting-IP`/`X-Forwarded-For`。代价是上游按 IP 的限流聚合成服务器出口 IP；收益是不可被用户伪造来源、也不绕过上游风控。
6. **并发上限而非本地按用户限流**：本地限流会与上游配额叠加且难以校准，容易出现误伤；只加 16 路并发闸门防止连接爆炸，风控仍由上游负责。
7. **请求体流式读取**：即使没有 Content-Length 的 chunked 请求也不能无限缓冲。
8. **CSRF 边界不变**：仍依赖 `HttpOnly` + `SameSite=Lax` 会话 Cookie（与站点其他写接口一致），未引入新 token，也没有加基于 Host/Origin 的强校验（反代下 Host 可能与 Origin 不一致，风险大于收益）。
9. **登录即准入**：评论读接口也要求本站登录；与现状一致（评论 UI 只在登录后的应用内出现）。

## 未解决项与限制

1. **上游 IP 限流聚合**：经代理后上游看到服务器出口 IP，按 IP 的读/写配额由全部站点用户共享（按评论身份维度的配额仍独立；上游线程缓存 15s 可吸收重复读取）。要改变这一点需要上游侧为该部署单独配置限流或用独立出口；本功能刻意不伪造 CF 头、不放宽风控。
2. **第三方直连依赖**：数据经服务器，但验证 iframe 与 `challenges.cloudflare.com` 脚本仍由浏览器直连；网络受限环境下验证无法完成，评论不可用。
3. **非 JSON 上游响应无法诊断**：Cloudflare 拦截页等非 JSON 内容统一脱敏为 502，不保留原因。
4. **评论服务侧未改**：`comments-service/worker` 不在本项范围。若使用独立验证域，上游 `TURNSTILE_HOSTNAME` 必须允许该域，否则验证仍失败。
5. **没有本地按用户限流**：单账号高频操作仍由上游限制，可能因共享出口 IP 影响其他用户（见第 1 条）。
6. **demo/文档构建未执行**：按分工由主代理统一构建。旧 demo 若未提供 `comments_verify_url`，绝对基址下会自动回退为同一来源，相对基址下验证会明确报未配置。
7. **既有环境缺口**：全量 Python 仍有 34 项改动前就存在的失败（可选依赖缺失、扫描任务环境），Node 仍有 demo 构建相关失败；均与本项无关，未掩盖也未放宽断言。

## 整合提示

- 仅这 5 个共享文件需要三方合并：`javsp_web/server.py`、`javsp_web/web/assets/app.js`、`javsp_web/web/assets/community.js`、`tests/test_comments_client.cjs`、`tests/test_community_client.cjs`；新增文件直接拷入即可。
- 已按原文件逐行保留 CRLF/LF 混排（`file` 校验与原始一致），`diff -u` 只剩本功能相关行，便于按基线合并。
- 副本内测试产物（`.test-venv/`、`.verify/`、`__pycache__/`）已全部删除，仓库目录只剩源码。
- `docs/comments-proxy.md` 为局部说明；若主代理已有统一文档结构，可移动位置，不影响代码。

---

# 返修（第 2 轮）：同源代理凭据 + `configure` 验证源

主代理验收发现严重漏项：`comments_proxy` router 已改为 `Depends(current_user)`（本站会话 Cookie 准入），但前端两处评论请求仍是旧直连时代的 `credentials: 'omit'`，真实浏览器不会附带本站 Cookie，同源代理必然 401。本轮只改此副本，未改原工作区、未委托、无提交/部署、未动 `docs/` 与 demo。

## 1. 失败测试先行（先红后绿）

先在 `tests/test_community_client.cjs`（6 → 12 项）与 `tests/test_comments_client.cjs`（11 → 13 项）补写行为测试，确认红：

| 新增/改写用例 | 断言 | 改前结果 |
| --- | --- | --- |
| 同源相对 base（`/api/comments`）发同源凭据 | `init.credentials === 'same-origin'`（数据请求仍为相对 URL、`referrerPolicy: 'no-referrer'`） | 失败（`'omit'`） |
| 绝对外域 legacy base 不泄漏本站 Cookie | `init.credentials === 'omit'`；绝对同源 base 才是 `same-origin`；协议相对 `//host` 为 `omit` | 部分失败（`requestInit` 不存在） |
| options 不能覆盖安全决策 | `requestInit(url, {credentials:'include', referrerPolicy:'unsafe-url'})` 仍返回 `same-origin`/`no-referrer` | 失败（无该点） |
| 无页面 origin 时不猜同源 | 无 `location` 时绝对 base 一律 `omit` | 失败 |
| `configure(base)` 同 base 不清验证源 | 已配 `verify='https://comments.example'` 后 `configure('/api/comments/')`，`verify()` 仍可完成 | 失败（被清成相对 base → “验证服务未配置”） |
| 切换 base 不带旧 origin | `configure('/api/other-comments')` 后 `verify()` 拒绝；错误 origin 的 message 被丢弃，新 origin 通过 | 通过（回归保护） |
| 空 base 语义 | `requireIdentity()` 拒绝“评论服务未启用”，且 0 次 fetch；`verify()` 同样拒绝且不建 iframe | 失败（用例 setup 缺 `init()`，修正后通过语义不变） |
| app.js 层（真实 `community.js` 决策） | 相对 base 的读/写请求 `credentials: 'same-origin'`，绝对 base 读/写仍 `'omit'`，均 `referrerPolicy: 'no-referrer'` | 失败（`'omit'`） |

## 2. 改动（仅 4 个文件）

| 文件 | 改动 |
| --- | --- |
| `javsp_web/web/assets/community.js` | 新增 `requestCredentials(target)`：相对/同源目标 → `'same-origin'`；绝对跨域 → `'omit'`（仅当 `location.origin` 证明同源时才 `same-origin`，无 `location` 时不猜）。新增 `requestInit(target, options)`：`{ ...options, credentials, referrerPolicy: 'no-referrer' }` —— 展开在**前**，options 不可能覆盖。`service()` 改用 `requestInit(url, options)`。`configure()` 改为：有新 verify 参数就用它；无 verify 且 base 未变则**保留** runtime 给的验证源；base 变了则回退到新 base（不带旧 origin）。导出 `requestCredentials`/`requestInit`。 |
| `javsp_web/web/assets/app.js` | `JavspComments.request()` 只做 URL 组合，安全项委托给 `window.JavspCommunity.requestInit(url, options)`，`signal`/`headers` 仍在其后覆盖；删除硬编码 `credentials: 'omit'`。其余（页大小、回复、分页、挑战重试、`open()` 空 base 早退）未动。 |
| `tests/test_community_client.cjs` | fixture 支持显式空 `base` 与 `pageOrigin`（注入页面 `location`）；新增 6 项（见上表）。 |
| `tests/test_comments_client.cjs` | harness 载入真实 `community.js` 取其 `requestInit`/`requestCredentials`（其余仍用桩），使 app.js 的凭据行为走真实决策而非复制规则；新增 2 项。 |

未改：`javsp_web/comments_proxy.py`（router 的 `Depends(current_user)`、流式限长请求体、响应体上限、`_comment_action` 保留 slash 均原样）、`server.py`、`docs/`、demo、`comments-service/`、`vendor/`。无新增运行时依赖。

## 3. 决策与边界

1. **凭据由“目标是否同源”决定，不由调用方决定**。同源代理必须带 Cookie（`same-origin`）；绝对外域保持 `omit` + `no-referrer`，旧单参直连模式行为不变。
2. **不可覆盖**：`requestInit` 的展开顺序是唯一防线，`credentials`/`referrerPolicy` 永远写在 `options` 之后；两个 fetch 都只经过它。新增用例直接以 `{credentials:'include'}` 攻击该顺序。
3. **不猜同源**：绝对 base 只有在浏览器上下文能证明 `new URL(base).origin === location.origin` 时才用 `same-origin`，否则 `omit`（Node/无 `location` 环境即走此分支），失败方向偏保守（401 而非泄漏）。
4. **`configure` 的验证源生命周期**：`configure(base)`（同 base、无 verify）为“更新而不清空”——runtime 下发的验证域得以保留；base 变更则旧 origin 一并丢弃，避免把旧验证域当成本 base 的验证源。
5. **空 base**：`configure('')` 即关闭评论服务 —— `service()` 抛“评论服务未启用。”且不发请求，`verify()` 同样拒绝且不创建 iframe；`JavspComments.open(name,'')` 早退、section 保持隐藏（原有行为，现由用例固定）。
6. **保留项**：验证消息校验仍是 origin + `event.source` + nonce + action + token 类型/长度；iframe 仍用独立的 `verifyBase`；同源相对 base 下 iframe 走绝对验证域。请求体流式限长、`_comment_action` 的 slash 未触碰。

## 4. 真实浏览器验证（本机 Chromium，非自动化套件）

环境：`~/.cache/ms-playwright/chromium-1248`（Chromium，headless）+ `playwright-core`（装在临时目录、验收后删除；未写入 requirements）。脚本保留在 `tests/manual/browser-comments-credentials.cjs`（名字不匹配 `node --test` 的发现模式，不影响自动化套件；运行方式见文件头注释：需 `PW_CHROME`、可写的短 `TMPDIR`、`NODE_PATH` 指向 playwright-core）。

本地起三个 HTTP origin 跑**线上同一份** `community.js`，站点侧代理按 router 语义“无 `javsp_session` Cookie 即 401”：

```json
{
  "cookieInBrowser": ["javsp_session"],
  "legacyBehavior":      { "status": 401 },                                  // 旧策略 credentials:'omit' 打同源代理 → 401（复现漏项）
  "sameOrigin":          true,                                               // configure('/api/proxy', origin) + requireIdentity → 200
  "verification":        "browser-proof",                                    // 同源验证域 iframe 往返成功
  "crossOriginVerification": "browser-proof",                                // 数据走相对代理、验证走另一 origin（生产形状）成功
  "verificationAfterBaseSwitch": "评论验证服务未配置，请刷新页面后重试。",      // 切 base 无 verify → 旧 origin 已丢弃
  "verificationAfterSameBaseReconfigure": "browser-proof",                    // 同 base 再 configure(base) → 验证源保留
  "seenSite":   [ { "cookie": "" }, { "cookie": "javsp_session=s3cret" } ],    // 第一行=旧 omit 复现，第二行=新代码
  "seenLegacy": [ { "cookie": "" } ],                                        // 绝对外域 /api/me/profile：无本站 Cookie
  "seenOmission":[ { "method":"OPTIONS", "cookie":"" }, { "method":"GET", "cookie":"" } ],
  "pageErrors": []
}
```

`seenOmission` 是“同主机不同端口”（仍是跨 origin，但 Cookie 按主机匹配、不按端口）：若客户端仍带凭据，该服务必然收到 `javsp_session`；实际预检与 GET 都没有，证明 `omit` 真的生效，而不是仅靠 Cookie 主机隔离“看起来没带”。

如实说明两点：
- 该 harness 里验证 iframe 的导航请求遇到了同主机 Cookie（`/verify` 记录到 `javsp_session`）。这是 `127.0.0.1` 不同端口共享主机的测试假象：Cookie 按主机下发，iframe 导航的凭据由浏览器默认策略决定，前端无接口可关断。生产 `comments_verify_url` 是不同域（`comments.rtioo.com` 或独立验证域），本站 Cookie 不会被发送；这不是本次代码引入的泄漏面，也没有新增可设置项。
- 本次浏览器验证没有起真实 FastAPI 应用（本机无 fastapi 环境），代理端点由“Cookie 否则 401”的等价桩代替。真实本站 Cookie + 本地上游的端到端验收仍由主代理用 `/tmp/javsp-oct23-venv/bin/python` 完成。

## 5. 测试结果（准确输出）

```bash
node --test tests/test_community_client.cjs   # 12 pass / 0 fail
node --test tests/test_comments_client.cjs    # 13 pass / 0 fail
node --test tests/*.cjs                       # 63 tests, 55 pass, 8 fail
node --check javsp_web/web/assets/app.js javsp_web/web/assets/community.js  # 通过
```

- 全量 8 项失败全部是 `docs/` 未构建导致（本副本 `docs/` 仅有 `comments-proxy.md`，没有 `demo.html`/`demo-seed.js`/`assets/theme.css`）：`tests/test_demo.cjs` 7 项 `ENOENT docs/...`、`tests/test_theme_client.cjs` 1 项 `docs/demo.html` 缺失。这 8 项失败都在读取不存在的 `docs/` 构建产物（`ENOENT`/`docs/demo.html`），与本轮改动的 `app.js`/`community.js` 无关；未放宽任何断言。
- Python 侧本轮未跑：`comments_proxy.py` 无改动，本机无 fastapi/starlette（`/tmp/javsp-oct23-venv` 在本环境不存在）；补跑方式见上一节命令（`.test-venv` 方案）。
- 未使用 Playwright 的 Python 包；浏览器验证为临时 `playwright-core` + 已缓存 Chromium，产物已删除（`.pw-verify/`、`.npm-cache/`、`/dev/shm/pwv*` 均不存在）。

## 6. 整合提示（本轮）

- 需要合并的文件增加 0 个运行时文件：仍是 `javsp_web/web/assets/app.js`、`javsp_web/web/assets/community.js` 与两个 JS 测试；`tests/manual/browser-comments-credentials.cjs` 为可选手工验收脚本（不参与自动化），可直接丢弃。
- 合并后请确认 `community.js` 与 `app.js` 同版本上线：`app.js` 现在依赖 `window.JavspCommunity.requestInit`（此前已依赖 `headers()/withChallenge()`），若只更新其中一个会报 `requestInit is not a function`。
