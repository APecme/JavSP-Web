# DELIVERY — 第 10 项「目录监控」

工作副本：`tmp/oct23-work/directory-watch`（独立源码副本，无 `.git`，无生产 `data/` 与凭据）。
本轮只在本副本内写代码；未运行 git、未提交/推送/部署、未访问真实用户媒体、评论或生产状态。

## 1. 结论

新增独立模块 `javsp_web/directory_watch.py`（规则/观察状态持久化 + 有界轮询扫描 + 调度线程）、
管理员 router `javsp_web/directory_watch_router.py`、前端 `directory-watch.js/.css`，`server.py` 只有
include + 生命周期 glue，`index.html` 只有挂载点与 script/link。没有改 `tasks.py` 核心，没有新增生产依赖。

默认：**只提交新增或变化的文件**；保存规则那一刻已存在的文件记为基线；轮询 30 秒、稳定等待 60 秒
（5–3600 / 0–86400 有界），单次最多 20 个任务（1–100 有界）。已提交/已跳过签名持久化，重启不重复。

## 2. 精确修改文件

新增（6 个）：

| 文件 | 行数 | 作用 |
| --- | --- | --- |
| `javsp_web/directory_watch.py` | 1088 | 规则与观察状态原子持久化、扫描器、提交决策、调度线程 |
| `javsp_web/directory_watch_router.py` | 113 | 管理员 API（`/api/directory-watch/...`，全部 `require_admin`） |
| `javsp_web/web/assets/directory-watch.js` | 451 | 自动刮削页的独立「目录监控」面板 + 表单对话框（自挂载、自刷新） |
| `javsp_web/web/assets/directory-watch.css` | 110 | 面板样式，只用现有主题变量（明暗主题自动跟随，含 reduced-motion 与 900/480 断点） |
| `tests/test_directory_watch.py` | 598 | 28 个真实临时目录行为测试（含多 P、重启、并发、掉线/权限恢复） |
| `DELIVERY.md` | — | 本文件 |

修改（2 个，均为最小胶水）：

- `javsp_web/server.py:97-101`（在 `app.include_router(ai_router)` 之后）：
  ```python
  from .directory_watch_router import router as directory_watch_router
  from .directory_watch import start_scheduler as start_directory_watch_scheduler, stop_scheduler as stop_directory_watch_scheduler
  app.include_router(directory_watch_router)
  app.router.add_event_handler("shutdown", stop_directory_watch_scheduler)
  start_directory_watch_scheduler()
  ```
- `javsp_web/web/index.html`：`:16` 追加 `directory-watch.css` 链接；`:78` 在 `data-panel="auto-scrape"`
  最前面插入唯一挂载点 `<div id="directory-watch-panel" class="directory-watch-panel" data-directory-watch></div>`；
  `:147` 追加 `directory-watch.js`。既有「定时自动刮削」「下载完成自动刮削」两块 DOM 与 app.js 逻辑未动。

`javsp_web/web/assets/app.css`、`app.js`、`tasks.py`、`storage.py`、`task_store.py`、`Dockerfile`、
`JavSPWeb.spec`、`scripts/build_demo.py`、`docs/`：**未修改**。

## 3. 行为规格

规则字段（`POST/PUT /api/directory-watch/rules`）：

| 字段 | 默认 | 有界/校验 |
| --- | --- | --- |
| `path` | 必填 | 绝对路径、必须已存在且是目录（NAS/容器未挂载即拒绝并给出提示）、不能落在应用数据目录、不能与其他启用规则目录重叠 |
| `preset_id` | `default` | 必须存在（`storage.get_preset`） |
| `name` | 目录名 | ≤80 字符 |
| `enabled` | true | 暂停=不动观察状态 |
| `recursive` | true | 是否含子目录 |
| `exclude` | `[]` | ≤50 条、≤200 字符、禁止绝对路径与 `..`；按文件名或相对路径 fnmatch |
| `include_existing` | false | 首次扫描是否把已有文件也入队 |
| `poll_seconds` | 30 | 5–3600 |
| `stable_seconds` | 60 | 0–86400 |
| `max_tasks_per_scan` | 20 | 1–100（一次扫描最多提交多少任务，避免整目录批量灌队列） |

签名与提交：签名 = 相对路径 + `size` + `mtime_ns`。文件必须在 `stable_seconds` 内签名不变才提交；
提交前把同一目录、同一 `javsp.multipart.media_identity` 的**已知**兄弟分 P 一起放进 manifest，
交给现有 `tasks.create_tasks(..., source="directory_watch", input_files=[...])`，因此多 P 聚合规则与
手动多选扫描完全一致。提交/跳过（低于预设最小文件大小等）都写入 `committed` 签名，重启或再次扫描不会重复提交。
已有任务仍在 `queued`/`running` 时，对同一分组的变化只记「等待现有任务完成」，不重复入队。

跳过项：临时/未完成下载后缀（`.!qb .part .partial .tmp .crdownload .download .downloading .aria2 .!ut .bc! .td .filepart .opdownload .incomplete`、`.tmp.` 中间段、`.` 开头的隐藏文件）、非视频后缀、
预设 `scanner.ignored_folder_name_pattern`（默认 `^\. ^#recycle$ ^#整理完成$ ^#不要扫描$`）、
预设输出目录名（由 `summarizer.path.output_folder_pattern` 的字面前缀推导，默认 `#整理完成`）、应用数据目录子树。
目录符号链一律不跟随（配合 `(st_dev, st_ino)` 访问集合，循环结构不会卡死），文件符号链跟随目标签名。

状态机（`status.state`）：`ok` / `initializing` / `disabled` / `offline`（根目录不可访问，保留已提交签名）/ `error`（预设缺失、权限或读取失败）。
`status` 还带 `pending`（等待稳定/等待现有任务）、`committed`、`submitted_total`、`skipped_total`、
`last_scan_at`、`last_submitted_at`、`last_error`、`message`（中文可读原因）。

API（全部 `require_admin`，非管理员 403）：

- `GET /api/directory-watch/rules` → `{rules, limits, scheduler}`
- `POST /api/directory-watch/rules`（201）/ `PUT /rules/{id}`（部分更新）/ `DELETE /rules/{id}`（404）
- `POST /rules/{id}/pause|resume|scan|reset`

持久化：`data/directory-watch-rules.json`、`data/directory-watch-state.json`，写入走「同目录临时文件 → `fsync` → `os.replace` → 目录 `fsync`」，
损坏 JSON 自动回退为空状态，不留 `.tmp` 残留（有测试）。

## 4. 关键取舍

1. **基线在保存规则时建立，而不是首次扫描时**。保存请求里做一次目录遍历（FastAPI 线程池，不持任何锁），
   把当前文件记为 `baseline`。这样「保存后 30 秒内掉进来的文件」不会被误判成已有文件；离线/权限失败时
   基线不写入，首次扫描会重试。代价：保存一个超大库的规则时这一个请求会慢一些（已记录，见未解决项）。
   替代方案（首次扫描建基线）会让创建后到首次扫描之间到达的文件永久漏刮，已否决。
2. **提交（`create_tasks`）不在模块锁内**。扫描分两段：短临界区算签名与持久化 → 无锁调 `create_tasks` →
   短临界区提交结果。因此 NAS 上慢速扫描不会阻塞管理员 API（有回归测试把 `_submit` 卡住，断言 `pause` 接口仍在 5 秒内返回）。
3. 复用 `javsp.multipart.group_files/media_identity` 的思路判断分组，改用 `tasks._preset_config_data`
   取 scanner 配置（未改 `tasks.py`）；若 vendor 不可用则退化为「每个文件单独提交」，不阻断主流程。
4. **修改规则即重新建立基线**（换目录/换预设/改排除都会重置观察状态），避免改预设后整库重刮；
   `暂停/恢复` 不动观察状态（有测试）。
5. 结束条件用 `generation` + `enabled` 双重校验：扫描中途暂停或编辑规则，会在下一个提交前中止并记
   「规则已修改或暂停，已停止本次提交」（有测试）。
6. 后台调度：单守护线程 `directory-watch`，每规则按自身 `poll_seconds` 到期触发，per-rule 非阻塞锁保证同一规则
   不并发扫描；`stop(timeout)` 置事件并 join，`server.py` 通过 Starlette `shutdown` 钩子停止（有集成测试）。
   NAS 兼容：只用 `os.scandir`+`stat` 的轮询，无 inotify/看门狗依赖，无新生产依赖。
7. 观察记录上限 `MAX_COMMITTED_ENTRIES=20000`：超过上限时只清理「本次扫描中已不存在」的记录，离线时不会触发清理。
8. 前端完全自挂载：`directory-watch.js` 自己渲染面板与 `<dialog>`，用 `MutationObserver` 监听
   `[data-panel="auto-scrape"]` 的 `class` 变化按需加载，可见时每 15 秒静默刷新；因此 **app.js 零改动**。
   删除/重置为两次点击确认（不引入新的 app.js 依赖），Escape/焦点由原生 `<dialog>` 负责。

## 5. 测试

环境事实（如实报告）：

- 题目给出的 `/tmp/javsp-bata-validation-venv/bin/python` **不存在**；系统 `python3`（3.14.4）里没有 fastapi 等项目依赖。
- 本副本内另建 venv（`.venv`，交付前已删除）并按 `requirements.txt` 安装：
  `python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt`
  （`slimeface` 在 Python 3.14 上构建失败，与本次功能无关；`pretty-errors`、`cloudscraper`、`selenium` 单独安装后全绿）。
- 运行用户 uid=1000（非 root），所以权限失败用例是真实 `chmod 000` 验证，不是 mock。

新增测试（先写失败测试，再实现；首轮 22 个用例 15 失败，最终 28 个全绿）：

```
.venv/bin/python -m unittest tests.test_directory_watch -v
Ran 28 tests in 7.6s
OK
```

覆盖：新增文件需稳定窗口、持续写入不提交、多 P 聚合为单任务、迟到分 P 与已提交兄弟合并、已有文件基线
（含 `include_existing` 对照）、子目录/recursive/排除模式、临时后缀与 `#整理完成`/`#recycle`/隐藏目录排除、
数据目录不被吞入、变化文件仅在旧任务结束后再提交、单次提交上限、重启不重复、离线保留状态并恢复、
权限失败上报并恢复、暂停立即停提交、扫描中途暂停中止、缺预设阻断、跳过项不重复尝试、并发扫描只建一个任务、
提交不持模块锁、目录符号链循环不卡死、状态文件损坏恢复、调度线程扫描并干净停止、router CRUD/校验/重叠/权限、
`index.html` 挂载点、`server.py` include+shutdown 集成。

全量回归（同一 venv，逐模块；全部 OK）：

```
test_ai 53 / test_ai_scrape 13 / test_ai_translation 20 / test_ai_web 13 / test_app_update 21 /
test_auth_sessions 9 / test_avatar_assets 2 / test_config_access 6 / test_config_validation_messages 7 /
test_cookiecloud_sync 6 / test_cover_progress 2 / test_dify_... 4 / test_directory_watch 28 /
test_download_cache 2 / test_error_messages 7 / test_library_catalog 18 / test_login_security 13 /
test_media 9 / test_multipart 21 / test_organization_log 22 / test_profile 4 / test_scrape_logging 21 /
test_task_scans 24(skip 1) / test_task_store 31 / test_updater 7   → 全 OK
```

Node：

```
node tests/test_web_client.cjs          passed
node tests/test_ai_translation_client.cjs passed
node tests/test_comment_markdown.cjs    ok # fail 0
node tests/test_comments_client.cjs     ok # fail 0
node tests/test_community_client.cjs    ok # fail 0
node tests/test_cookiecloud_client.cjs  passed
node tests/test_film_detail_ux.cjs      ok # fail 0
node tests/test_library_playback.cjs    passed
node tests/test_mount_batch_client.cjs  passed
node tests/test_overview_actress.cjs    ok # fail 0
node tests/test_scan_client.cjs         passed
node tests/test_demo.cjs                # fail 8   ← 环境性：本副本没有 docs/ 目录（ENOENT docs/demo-seed.js、docs/assets/theme.css）
node tests/test_theme_client.cjs        # fail 1   ← 环境性：docs/demo.html 不存在；其余 9 项（含 login/console 主题引导顺序）通过
node --check javsp_web/web/assets/directory-watch.js  → 通过
```

`test_demo.cjs` / `test_theme_client.cjs` 的失败与本次改动无关（本副本按任务要求不含 `docs/`、无 demo 构建），
未通过改断言规避。未做浏览器实机验收（无浏览器环境），UI 交互留待主代理按计划第 3 项统一验收。

## 6. 主代理需要做的整合动作

1. `server.py`、`index.html` 的改动已经在本副本内完成，三方整合时按上面 `§2` 的两处 diff 合入即可；
   如果整合后 `server.py` 里 `include_router` 段被其它功能改动，请保持我的 4 行在其附近（顺序不影响）。
2. **docs/demo（由主代理统一构建）**：`scripts/build_demo.py:18` 的 `assets` 列表需要补
   `'directory-watch.js', 'directory-watch.css'`；`tests/test_demo.cjs:27` 的资产一致性列表同理。
   否则 `demo.html` 会引用不存在的资产。
3. **未新增依赖**：`requirements.txt` / `Dockerfile` / `JavSPWeb.spec` 不需要改动（`javsp_web/web` 整目录已打包，
   `ASSET_VERSION` 会自动把新资产纳入哈希）。
4. UI 验收建议：自动刮削页 → 顶部新面板；新增规则（选目录/预设/间隔/稳定等待/排除/处理已有）→ 保存后立即显示
   「已建立基线」；投放文件后按「立即扫描」看状态从「等待稳定」到「已提交」；暂停/恢复、重置观察状态、
   删除（两次点击）都要与既有「定时自动刮削」卡片视觉一致；1440/1024/390/320 与明暗主题需实机过一遍。
5. 文档（`docs/`）需要补一节「目录监控」说明：默认只处理新增/变化、稳定等待含义、临时文件与输出目录跳过、
   NAS 轮询（无事件通知）、重启不重复、暂停与重置的差别。本轮未写 docs。

## 7. 未解决项与已知限制

1. **保存规则会在请求内遍历一次目录**（建立基线）。超大库 + 慢速 NAS 时该次 `POST/PUT` 可能耗时数秒；
   遍历不在任何锁内、也不在事件循环里，但会占用一个线程池 worker。若主代理认为不可接受，可改为
   「保存时只记 `created_ts`，首次扫描建基线」，代价是创建后到首次扫描之间到达的文件算作已有文件。
2. **「立即扫描」接口是同步的**：慢速挂载时该 HTTP 请求会一直等到扫描结束（事件循环不受影响）。
   需要的话可改成 202 + 后台线程 + 前端轮询 `status`。
3. **规则编辑要求目录当前可访问**：离线时无法改名字/预设等字段（只能暂停/恢复/删除）。这是为了避免保存一个
   永久失效的路径，但离线期改配置的诉求未覆盖。
4. **增量分 P**：第 1 段先到会被当作独立任务提交，第 2 段后到时按「与已提交兄弟合并」再提交一次同一影片
   （不会重复提交第 2 段，但同一影片会被刮两次）。建议把「稳定等待」设成大于分 P 之间的间隔。
5. `include_existing=true` 首次扫描会把整库当候选，虽然受 `max_tasks_per_scan` 与稳定窗口约束，但仍是一次性大提交，
   UI 已用提示说明。
6. 状态文件按提交分组整体重写（`fsync` 后 `os.replace`），大批量提交时是 O(n) 次写；超大库可考虑改为按 rule 分文件或
   sqlite（本轮未做，避免引入新的存储层）。
7. 未实现「原生事件（inotify/ReadDirectoryChangesW）」加速，按计划只做 NAS 兼容轮询。
8. 未做浏览器自动化验收；`.js` 只做了语法检查与元素 id/接口名的静态交叉核对。
9. 运行整套 Python 测试会在副本根目录生成 `data/`（既有测试行为）；我已删除该目录与 `.venv`、`__pycache__`，
   交付副本不含任何运行产物或凭据。
