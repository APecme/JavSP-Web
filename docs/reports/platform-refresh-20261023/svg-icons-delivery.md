# 第 5 项：全站操作 SVG 统一 — 交付说明

独立副本：`/data12t/AutoOrder/JavSP-Web/tmp/oct23-work/svg-icons`
未使用 git，未提交、未推送、未部署；未改动原工作区与生产 `data/`。
行尾保持仓库原状（`index.html`/`login.html`/`app.js`/`ai.js`/`overrides.css`/`icons.js` 为 CRLF；
`build_demo.py`、`test_comments_client.cjs` 保持原有混合行尾；新增 `test_icons.cjs` 为 LF，与既有 LF 测试一致）。

## 1. 文件清单（相对 baseline 的实际改动行数）

| 文件 | 变更 | 说明 |
| --- | --- | --- |
| `javsp_web/web/assets/icons.js` | 新增 96 行 | 统一图标模块：`window.JavspIcons.render/refresh/names`，17 个白名单图标 |
| `javsp_web/web/index.html` | 55 行 | 35 处静态 `data-icon` 插槽（含 13 个 `close`）；`icons.js` 先于 community/app/ai 加载（第 139 行） |
| `javsp_web/web/login.html` | 1 行 | 登录页同样加载 `icons.js`（登录可用，但页面本身无符号控件） |
| `javsp_web/web/assets/app.js` | 99 行 | 新增 `javspIcon()` 助手 + 50 处动态模板改用白名单图标；展开/折叠、下载策略 caret 不再覆盖整按钮；命名规则帮助改信息图标按钮（本次返修，见 §7） |
| `javsp_web/web/assets/ai.js` | 9 行 | 发送/停止改为更新 label span（不再 `textContent` 整按钮）；历史会话 ✎/× 改图标 |
| `javsp_web/web/assets/app.css` | 2 行（+1/−1） | 命名规则帮助角标：去掉 `.naming-rule-help::before{content:'?'}`，改为 `.naming-rule-help-trigger` 按钮样式 + 13px 信息图标；`:focus` → `:focus-within`（本次返修，见 §7） |
| `javsp_web/web/assets/overrides.css` | 12 行 | `details>summary` 的 `content:"\2304"` 改为同形 mask 图标；新增 `.javsp-icon` 尺寸/间距规则 |
| `scripts/build_demo.py` | 1 行 | 资源列表加入 `icons.js`（**需主代理最终统一确认**） |
| `tests/test_icons.cjs` | 新增 388 行 | 15 个行为/安全测试（12 个原有用例 + 本次返修的 3 个命名规则帮助用例） |
| `tests/test_comments_client.cjs`、`test_scan_client.cjs`、`test_overview_actress.cjs`、`test_library_playback.cjs` | 各 1 行 | 切片 harness 补 `javspIcon: () => ''` 桩（app.js 新增全局助手后切片上下文需要） |

未修改：菜单名、详情位置、各页面布局、DOM hooks、业务 API、`community.js`（见 §5 检查结论）。

## 2. icons.js 契约

```js
window.JavspIcons.render(name, {className?, strokeWidth?}) -> string   // 受信静态 SVG，未知名字返回 ''
window.JavspIcons.refresh(root?) -> number                             // 填充 [data-icon] 插槽，返回绘制数量
window.JavspIcons.names() -> string[]
```

- 统一 `viewBox="0 0 24 24"`、`fill="none"`、`stroke="currentColor"`、`stroke-width="1.8"`、round cap/join、`aria-hidden="true" focusable="false"`。
- 白名单（17）：`close, chevron-up, chevron-down, chevron-left, chevron-right, plus, trash, pencil, refresh, send, stop, menu, folder, file, arrow-left, copy, info`。每个名字都有实际调用点（测试强制）。
- 用户文本永不进入 SVG：名字是冻结表里的字面键（`hasOwnProperty`）；`className` 仅接受 `/^[a-z0-9-]+$/i` 且丢弃 `on*`；`strokeWidth` 仅接受 1–3 数字。无 `innerHTML` 拼接调用方输入。
- 静态 HTML 写法：`<span data-icon="plus"></span>`（默认前置，`data-icon-position="after"` 追加），DOM ready 时自动填充；`data-icon-painted` 防重复。JS 未加载/加载失败时按钮文字、`aria-label`、`disabled`、`hidden` 全部照旧可用。

## 3. 已替换的操作符号（按功能）

- 展开/折叠：`details>summary` 箭头改为 mask 图标；任务卡 `expandControlIcon` → `chevron-up/down`；下载「展开/收起策略」按钮改 label span + 切 caret（`data-policy-label`）。
- 关闭：`index.html` 13 处 `close` 图标（个人中心、头像选择、剧照、影片详情「关闭 ×」、各 dialog `.dialog-close`）改为图标按钮 + `aria-label="关闭" title="关闭"`；`app.js` 播放器 dialog、媒体服务器 dialog 关闭同步。
- 前后：剧照 `‹ ›`、头像分页、任务/片库/分组分页、评论分页 → `chevron-left/right`（含禁用态保留）。
- 添加：新建对话、添加影片?（原有 SVG 保留）、添加定时规则、新建预设、添加下载器、添加用户、添加分类、添加爬虫、数组项 `+`、爬虫名 `+` → `plus`。
- 删除：预设/用户/任务/剧照/下载种子/自动刮削规则/路径映射/媒体服务器/爬虫标签/配置数组项/分类项 → `trash`（纯图标按钮均带 `aria-label`+`title`）。
- 刷新：任务队列、下载管理、我的评论、立即检查、恢复内置爬虫 → `refresh`。
- 发送/停止：`发送 ↑`→`send`+`#ai-send-label`；`停止生成 ■`→`stop`+`#ai-stop-label`（`disabled`/`hidden` 语义不变）。
- 文件夹/文件：容器路径浏览器条目 `文件夹/视频` 文本 → `folder`/`file`（含 `title`）。
- 编辑/详情/复制/返回：编辑资料、编辑用户、编辑媒体服务器 → `pencil`；任务详情 → `info`；复制摘要/复制日志 → `copy`；返回分类、返回上一级 → `arrow-left`。
- 排序方向：下载表头 `↑/↓` → `chevron-up/down`（`download-sort-mark`）。
- 侧栏菜单按钮 `☰`（AI 会话列表开关）→ `menu`。
- 命名规则帮助角标 `?`（预设命名模板字段的 popover 触发器）→ `info` 图标按钮 + `aria-label`/`title`/`aria-describedby`（第 5 项审批返修，见 §7）。

## 4. 测试结果（本副本实测）

```
$ node --test tests/test_icons.cjs      -> 15 pass / 0 fail
$ node --test tests/*.cjs               -> 57 pass / 9 fail（仅 test_demo.cjs 8 + test_theme_client.cjs 1）
```

`test_icons.cjs` 覆盖：白名单结构与统一 stroke；未知/敌意名字（`__proto__`、`constructor`、`"><script>`、数组、对象）一律返回空；options 注入（引号、`onload`）；hydration 不覆盖文字/`disabled`/`aria-label`、重复调用幂等、`DOMContentLoaded` 前不绘制；`icons.js` 加载顺序（console+login）；静态 HTML 图标名白名单 + 无符号按钮 + aria-label；动态模板无字形且有 aria-label；`updateBusy` 与下载策略切换后图标仍在（DOM 语义化的 `textContent` 会清空子节点，因此可证真实丢失）；CSS 无字形伪元素。本次返修新增 3 个针对性用例（见 §7）。

9 个失败为**环境性**：本副本无 `docs/`（与 `data/`），`test_demo.cjs`/`test_theme_client.cjs` 需要 `docs/demo.html` 等生成物。已在未改动的 `baseline/` 副本上复现**完全相同**的 9 个 ENOENT 失败，故非本补丁引入。

未执行的验证（如实说明）：
- Playwright / 浏览器实测：`/tmp/javsp-oct23-browser/node_modules/playwright` 不存在，无法截图或真实渲染核对。
- Python 回归：`/tmp/javsp-oct23-venv` 不存在，系统 python3 无 `fastapi`，`tests/*.py` 未运行。
- demo 重建：`docs/` 缺失，未运行 `scripts/build_demo.py`（已把 `icons.js` 加入其资源列表）。

## 5. 仍未替换 / 有意保留（准确清单）

1. **侧栏开关 `‹/›` 字形**：`index.html:21` 的 `<span aria-hidden="true">&lt;</span>` 与 `app.js setSidebarCollapsed()` 里 `'>' : '<'` 的写入。属 sidebar 任务范围（240/72/56px、移动端抽屉、图标即文字），本任务不改侧栏布局。
2. **`assets/app.css:22` `.sidebar-collapsed .nav-item::first-letter{font-size:18px}`**：旧的 first-letter 假图标，**由 sidebar 任务移除**；本任务未动。
3. ~~`assets/app.css:56` `.naming-rule-help::before{content:'?'}`~~：**已在第 5 项审批返修中替换为信息图标按钮（见 §7）**，不再是保留项。
4. **`assets/play.svg` + `.library-play <img>`**：已是本地 SVG 图标（accent 底上固定白），非字形符号；替换会牵动 `cinema.css` 里 `.library-play img` 布局，为避免与页面/详情任务冲突未改。
5. **搜索图标**：`#library-search-form` 字段内已是内联 SVG；`搜索` 提交按钮仍为文字按钮。
6. **纯文字操作按钮（无图标）**：取消/保存/暂不刷新/重置/加载更多/开始刮削/浏览容器路径/选择刮削文件夹/选择视频文件/批量选择视频文件/使用默认头像/使用这个头像/不再提示/前往 GitHub/打开 Google 图片/测试连接/测试爬虫/测试连通性/立即同步/立即更新/保存设置/保存预设/保存全局策略/同步媒体库/进入/选此文件夹/选此文件/点赞/回复/举报 等。判定规则：只有“仅靠符号表达功能”或被点名的操作类才加图标，避免把补丁扩成视觉重做；这些按钮都有明确文字名，功能不受影响。
7. **`同步媒体库` 按钮**：点击后由 JS 写 `textContent='已同步'`，加图标会被抹掉，故保持纯文字（未改其状态反馈逻辑）。
8. **`app.js` 中重复定义的 `taskCard`**：783、829 行两份旧实现被 1926 行的定义覆盖（死代码）。第三份已加图标；两份死代码的“删除”按钮仍无图标（停止按钮已加）。未删除死代码——属无关重构。
9. **既有内联 SVG 未迁移到 icons.js**：`.github-star-invite-close`、`comment-help summary`、`overviewSelectionIcon`、`artworkPlaceholder`、`.theme-toggle`、`avatar-pencil`、`lc-stat-icon` 等（本来已是 SVG，不改以免扩大 diff）。
10. **CSS 掩码的 chevron 路径**：`overrides.css` 里 `details>summary::after` 的 data-URI 与 icons.js 的 `chevron-down` 是同一形状但两处维护（注释已标注同步要求）。
11. **正常文本中的箭头/单位未机械替换**：`方向键 ← → 切换`、`docs.html ↗`、`1920×1080`、`·` 等。
12. **视觉验收未做**：无浏览器，未见真实渲染；`.javsp-icon` 尺寸/间距按现有 CSS 约定（`.button svg`/`.icon-button svg` 16px，其余 1em + `margin-inline-end:.35em`）推定。
13. **`aria-live`/状态文案**：`停止生成`→`正在停止…`、`发送`→`提交中…` 仍走 label span，未改文案。

## 6. 给主代理的合并提示

- **加载顺序**：`index.html` 在 `theme.js` 之后、`markdown-it.min.js` 之前插入 `icons.js`；`login.html` 同样在 `theme.js` 后。任何页面若重排脚本，请保持 `icons.js` 在 `community.js`/`app.js`/`ai.js` 之前。
- **AI 面板 id 契约**：`#ai-send-label`、`#ai-stop-label` 由 `ai.js` 更新文案；`#ai-send`/`#ai-stop` 本身不再被整体 `textContent` 覆盖。若页面任务重写 AI 面板，请保留这两个 span（或同步改 `ai.js updateBusy`）。
- **下载策略按钮**：`#download-policy-toggle` 内含 `[data-icon="chevron-down"]` + `[data-policy-label]`，`app.js setDownloadPolicyExpanded` 依赖二者。
- **CSS 位置**：`overrides.css` 只改了两处——`details>summary::after` 规则（第 415 行，同形替换）与文件末尾追加的 `.javsp-icon` 三条规则；与页面/侧栏任务在同一文件的改动应能三方合并。
- **demo 资源列表**：`scripts/build_demo.py` 的 `assets` 已含 `icons.js`（单行）。本任务未生成 `docs/`；合并后请在集成工作区 `python scripts/build_demo.py`，`demo.html` 会自动带上 `assets/icons.js`，`overrides.css` 中的 `.javsp-icon` 规则也随之生效。
- **新增测试**：`tests/test_icons.cjs`；另外 4 个既有测试各加 1 行 `javspIcon` 桩，否则 app.js 切片会 `ReferenceError`。
- **命名规则帮助（本轮返修）**：`app.js namingRuleHelp()` 输出 `.naming-rule-help` 容器 + `.naming-rule-help-trigger` 按钮 + `.naming-rule-popover`；popover/hint 的 `id` 由配置路径派生（`naming-rule-popover-<字段路径>`、`naming-rule-hint-<字段路径>`）。若页面/sidebar 任务调整预设表单结构，只需保留 `.naming-rule-control` 包裹与这三个类名，`:hover`/`:focus-within` 展开逻辑即可继续生效。
- **PyInstaller**：`JavSPWeb.spec` 以目录方式打包 `javsp_web/web`，`icons.js` 自动包含；`server.py` 的 `ASSET_VERSION` 由 assets 目录哈希生成，会随新文件自动变化，无需手工登记。

## 7. 第 5 项审批返修（本轮唯一的改动）

审批意见：命名规则帮助角标 `?` 属于靠符号表达功能的可聚焦控件，不能以"不是按钮"为由保留。本轮只改这一处，其余原样。

### 7.1 改动（2 个文件，4 处）

**`javsp_web/web/assets/app.js` — `namingRuleHelp()`（第 332-338 行，+3 行）**

```diff
 function namingRuleHelp(targetPath) {
   const variables = NAMING_RULE_VARIABLES.map(...).join('');
-  return `<span class="naming-rule-help" tabindex="0"><span class="naming-rule-popover">...</span></span>`;
+  const suffix = String(targetPath || '').replace(/[^a-z0-9]+/gi, '-').replace(/^-+|-+$/g, '').toLowerCase();
+  const popoverId = `naming-rule-popover-${suffix}`;
+  const hintId = `naming-rule-hint-${suffix}`;
+  return `<span class="naming-rule-help"><button class="naming-rule-help-trigger" type="button"
     aria-label="查看可用命名变量" title="查看可用命名变量" aria-describedby="${hintId}">${javspIcon('info')}</button>
     <span class="naming-rule-popover" id="${popoverId}" role="group" aria-label="可用命名变量">…</span></span>`;
 }
```

（diff 中 `return` 一行按可读性折行展示，源码仍为单行；变量列表 `${variables}` 与提示语 `<small id="${hintId}">` 均原样保留。）

- 角标本体：`javspIcon('info')`（白名单内已存在的 `info`，24px viewBox、`currentColor`、`aria-hidden`），不再有任何 `?` 文字。
- 真实 `<button type="button">`：可聚焦、可被辅助技术识别为按钮；`type="button"` 保证不会提交预设表单。
- 可访问名称/说明：`aria-label="查看可用命名变量"` + `title` 同文案 + `aria-describedby` 指向原提示语 `<small>`（"点击变量会插入到当前模板的光标位置。"），因此屏幕阅读器能读到名称与用法，而不需要展开视觉 popover。
- popover 原样保留：`<strong>可用命名变量</strong>`、变量列表按钮、提示语文本、`data-insert-naming-variable` / `data-naming-target` 属性全部未动；popover 容器补 `id` + `role="group"` + `aria-label`，使其内部 14 个变量按钮有分组语义（触发器用 `aria-describedby` 关联提示语，未用 `aria-expanded`，因为展开由 CSS `:hover/:focus-within` 驱动，写死 expanded 状态会失真）。
- id 由配置路径派生（`summarizer.path.basename_pattern` → `naming-rule-popover-summarizer-path-basename-pattern`），同一页面多个命名模板字段互不冲突。

**`javsp_web/web/assets/app.css` 第 56 行（+1/−1 行，仍是单行压缩格式）**

```diff
-.naming-rule-help{position:relative;flex:0 0 22px;width:22px;height:22px;border:1px solid var(--accent-border);border-radius:50%;background:var(--accent-soft);color:var(--accent-text);cursor:help}
-.naming-rule-help::before{content:'?';position:absolute;inset:0;display:grid;place-items:center;font-weight:700;font-size:12px}
-.naming-rule-help:hover .naming-rule-popover,.naming-rule-help:focus .naming-rule-popover{...}
+.naming-rule-help{position:relative;display:inline-flex;flex:0 0 22px;width:22px;height:22px}
+.naming-rule-help-trigger{display:grid;place-items:center;width:100%;height:100%;padding:0;border:1px solid var(--accent-border);border-radius:50%;background:var(--accent-soft);color:var(--accent-text);cursor:help}
+.naming-rule-help-trigger .javsp-icon{width:13px;height:13px;margin-inline-end:0}
+.naming-rule-help:hover .naming-rule-popover,.naming-rule-help:focus-within .naming-rule-popover{...}
```

- 视觉规格不变：22×22 圆形、`--accent-soft` 底、`--accent-border` 边、`cursor:help`；图标 13px 居中（覆盖 `.javsp-icon` 的 `1em` 与 `margin-inline-end:.35em`）。
- `.naming-rule-help` 退化为纯定位容器（`display:inline-flex`），popover 的 `position:absolute;right:0;top:calc(100%+8px)` 与 `@media(max-width:560px)` 内的重定位规则完全不受影响。
- `:focus` → `:focus-within`：键盘 Tab 到按钮即可展开，继续 Tab 可进入变量按钮，行为与原先 `tabindex="0"` 的 span 一致（且现在有可见焦点环：`cinema.css` 的 `button:focus-visible`）。
- 第 57 行 `.naming-rule-control:hover .naming-rule-popover{display:grid}`（整行 hover 也展开）保留未动。

### 7.2 本轮未动（明确边界）

- **sidebar 一律没碰**：新 sidebar 代理的内联 SVG 与本改动无交集（`naming-rule-help-trigger` 是新类名，不复用 `.icon-button`），`index.html`、`app.js setSidebarCollapsed()`、`app.css:22` 的 `.sidebar-collapsed .nav-item::first-letter` 均未改。
- 未删除任何旧代码：`namingRuleHelp` 的变量列表、提示语、`<strong>` 标题、`data-insert-naming-variable` 点击处理（`app.js:1719`）原样；其余 50 处图标已由主代理整合，本轮未重跑、未回改。
- 未安装/升级任何依赖，未重跑全量环境（无 Playwright、无 Python venv，见 §4）。
- 未改其他独立副本（`baseline/`、`sidebar/`、`review/` 等），未 git 提交、未推送、未部署。
- 未扩大业务重构：只改 `namingRuleHelp()` 与对应的 3 条 CSS 规则。

### 7.3 新增的针对性测试（`tests/test_icons.cjs`，+3 用例）

| 用例 | 断言要点 |
| --- | --- |
| `the naming-rule help is an info icon button with a name, a popover and insert actions` | 用真实 `icons.js` 渲染 `namingRuleHelp('summarizer.path.basename_pattern')`：按钮体只有共享 SVG（`class="javsp-icon"`、`aria-hidden`），去掉 SVG 后按钮内**无任何文字字形**；不再有 `tabindex="0"`；`type="button"`、`aria-label`、`title`、`aria-describedby` 指向同名 `id`；popover 保留固定 `id` + `role="group"` + `aria-label`，标题与提示语文本未改；每个变量仍是 `data-insert-naming-variable="{token}"` + `data-naming-target="<字段路径>"`，数量与变量表一致 |
| `naming-rule variable buttons still insert into the field at the caret` | 提取 `app.js` 的点击插入分支实跑：token 替换选区（`x{num}y` 选中 `y` → `x{num}{actress}`）、光标落在 token 之后、字段重新聚焦、派发 `input` 事件（表单 dirty 逻辑不受影响） |
| `naming-rule help CSS drops the "?" pseudo-element and keeps the popover on hover and focus` | `app.css` 不再含 `.naming-rule-help::before` 与 `content:'?'`；`.naming-rule-help` 仍是定位上下文；`.naming-rule-help-trigger` 保留圆形外观、`.javsp-icon` 13px；`:hover` 与 `:focus-within` 两条展开规则都在 |

实测结果：

```
$ node --test tests/test_icons.cjs   -> 15 pass / 0 fail
$ node --test tests/*.cjs            -> 57 pass / 9 fail（仍为既有 test_demo 8 + test_theme_client 1 的 docs/ ENOENT）
$ node --check javsp_web/web/assets/app.js -> OK
```

### 7.4 遗留风险（如实说明）

- **未做浏览器视觉验收**（本副本无 Playwright）：13px 图标在 22px 圆内的居中、popover 在两个新 id 下的定位均按 CSS 推定，合并后请在有浏览器的环境点开任一命名模板字段确认。
- **`icons.js` 未加载时的降级**：本按钮与其余纯图标按钮一致，没有文字回退，`icons.js` 加载失败时会显示空圆但仍可聚焦、仍有 `aria-label`（此前 `?` 由 CSS 生成则不会消失）。若主代理要求更保守，可加 `javspIcon('info') || '<span aria-hidden="true">?</span>'`。
- **`aria-expanded` 未使用**：展开状态由 CSS 驱动，未写 `aria-expanded`，避免静态值与实际可见性不一致；若后续改为 JS 点击开关 popover，需要同步补 `aria-expanded`。
