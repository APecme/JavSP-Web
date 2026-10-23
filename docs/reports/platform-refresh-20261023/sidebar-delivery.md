# 第 4 项 左侧导航 — 交付说明

独立副本：`/data12t/AutoOrder/JavSP-Web/tmp/oct23-work/sidebar`（无 `.git`、无生产 data）。未修改原仓库或其他副本，未提交、推送、部署，未生成 `docs/demo`，未委托其他代理。

## 文件清单

| 文件 | 变更 |
| --- | --- |
| `javsp_web/web/index.html` | 仅改侧栏结构与资源引用：`aside.sidebar` 增加 `id="sidebar"`、`aria-label`、`aria-controls`；8 个现有 `data-view` 项改为「inline SVG 图标 + `.nav-item-label` 文字」，保留原 ID、顺序、分组标签；新增 `#sidebar-backdrop`；引入 `navigation.css`（cinema.css 之后）与 `navigation.js`（app.js 之后）。各 `data-panel` 内容、命名、关闭按钮位置未动。 |
| `javsp_web/web/assets/navigation.js`（新增，约 230 行） | 侧栏唯一行为所有者：desktop 折叠/展开、phone 抽屉、遮罩、Escape、焦点进入/恢复、Tab 焦点循环、`aria-current` 同步、旧存储键兼容。无第三方依赖，暴露 `window.JavspNavigation` 供测试与初始化。 |
| `javsp_web/web/assets/navigation.css`（新增） | 侧栏布局：desktop 240px / 折叠 72px；`<=800px` 常驻 56px 左图标栏，展开为 240px（`min(240px, 82vw)`）左抽屉 + 全屏遮罩；导航纵向滚动；主区为剩余列宽；图标栏/抽屉可见性、44px 触摸目标、`prefers-reduced-motion`。只用现有主题变量。 |
| `javsp_web/web/assets/app.js` | 只删除原 `setSidebarCollapsed()` 及其 `#sidebar-toggle` 监听（约 775 字符），避免双所有者；view 切换、权限删除、轮询、业务逻辑均未改。 |
| `tests/test_navigation_client.cjs`（新增） | 14 个行为/DOM 契约测试（先写、先失败）。未修改任何既有测试。 |
| `DELIVERY.md` | 本文件。 |

## 行为与需求对应

- **宽度/断点**：`>800px` 240px；折叠 72px；`<=800px` 固定 56px 图标栏；抽屉 240px（320px 屏为 82vw 内）。无顶部横向 nav：`nav` 只在 `aside` 内，桌面/手机均纵向排列（浏览器实测）。
- **滚动/主区**：侧栏 `100vh` sticky，`.nav` 纵向独立滚动（`overscroll-behavior: contain`）；主区 `grid-column: 2` 占剩余宽度，页面整体纵向滚动；抽屉为 `position: fixed`，打开时主区不重排。
- **手机交互**：选择任一项后关闭抽屉，焦点移到 `#section-title`（`tabindex="-1"`）；Escape、点击遮罩关闭并把焦点还给 `#sidebar-toggle`；打开时焦点进入当前项（若该项 `hidden/disabled` 则落在 toggle）；抽屉内 Tab 循环；`aria-expanded` 在手机上表示抽屉、桌面表示非折叠；`aria-current="page"` 由 MutationObserver 跟随 `.active`，也兼容 app.js `showView()`。
- **状态独立**：desktop 折叠写旧键 `javsp-web.sidebar-collapsed`（`'1'`/`'0'`，缺省展开，读取兼容旧值，初始化不回写）；手机抽屉不读写该键，不持久化；跨断点时抽屉关闭，折叠偏好保留（`sidebar-collapsed` 类在手机宽度下被 CSS 忽略而不清除）。
- **可访问性/图标**：每项「图标 + 文字」，图标 `aria-hidden="true"`、24 viewBox、`currentColor` 描边；折叠/图标栏时文字用 clip 视觉隐藏而非 `display:none`，可访问名称与 `title` 保留；toggle 有动态 `aria-label/title`；44px 触摸目标（手机）。
- **保留项**：所有 `data-view`、`#settings-nav`/`#auto-scrape-nav`/`#crawler-config-nav`/`#ai-scrape-nav`、`data-panel`、hidden/disabled 语义、角色权限删除逻辑、明暗主题与隐私模式、登录页均未改；登录页不加载 `navigation.*`，且无侧栏时 `init()` 直接返回。
- **可扩展性（热片/下片）**：未创建任何页面、数据或占位菜单。扩展一个视图 = 在 `#sidebar-nav` 增加同样结构的 `button.nav-item[data-view][data-*]`（图标 + `.nav-item-label`）并提供对应 `[data-panel]`；分组用现有 `.nav-label`，无需改 `navigation.js`。类名/结构不绑定具体功能语义，避免提前定义业务。未提供注册 API，以免发明尚未确认的语义。

## 验证

### 1. 先失败测试 → 再实现
`tests/test_navigation_client.cjs` 先于实现编写，首次运行 13/13 因 `navigation.js` 缺失（ENOENT）全部失败；实现后修正了两处测试夹具（焦点列表 selector、title 回退），最终 14/14 通过。测试通过 vm 中的最小 DOM 驱动真实 `navigation.js`，覆盖：旧键恢复、桌面折叠持久化、手机抽屉/遮罩/ARIA、选择后关闭与焦点、Escape（含原生 dialog 让行）、遮罩、Tab 循环、断点独立性、`aria-current` 同步、hidden/disabled 焦点回退、DOM 契约（无顶部 nav、ID/`data-view` 保留、登录页无侧栏、app.js 不再持有侧栏逻辑）。

```bash
node tests/test_navigation_client.cjs        # 14 pass
```

### 2. 全量 Node 回归
```bash
for f in tests/*.cjs; do node "$f"; done
```
结果：12 个文件通过，含新测试；仅 `test_demo.cjs`、`test_theme_client.cjs` 失败。二者在改动前即失败：本副本按约定不含 `docs/`，测试读取 `docs/demo.html`/`docs/assets/*`；与本次改动无关，待主代理重建 demo。

### 3. Python 回归
本机系统 Python 缺项目依赖，故在副本内临时 venv（已删除）安装 `fastapi/httpx/pytest` 及测试所需运行依赖后执行：

```bash
python -m pytest tests -q
# 334 passed, 1 skipped, 167 subtests passed
```
（初跑 2 个失败均因临时 venv 缺 `uvicorn`/`pretty_errors`/`colorama`，补齐后通过，非代码问题。）

### 4. 真实浏览器与交互验证
环境：Firefox 为 snap 包，因 `/run/user/1000/snap.firefox` 位于只读文件系统无法启动；改用本机已缓存的 Chromium `chrome-headless-shell 156`，用 Node 内置 WebSocket 直接走 CDP 驱动真实页面（真实 `index.html` + CSS/JS，仅 `/api/*` 用桩），临时脚本与截图在验证后删除。检查项全部通过：

| 视口 | 实测 |
| --- | --- |
| 1440×900 | 侧栏 240px，主区 1200px，`scrollWidth == innerWidth`；图标 20px、文字可见、目标高度 ≥36px；折叠后 72px 且主区左移 72px；`aria-expanded=false`、`aria-label=展开侧边栏`、旧键 `'1'`；刷新后仍 72px |
| 1024×768 | 展开 240px / 折叠 72px，无横向溢出 |
| 390×844 | 常驻图标栏 56px，主区 334px，无横向溢出；菜单按钮 44×44；导航项 44px；抽屉打开 240px、遮罩覆盖整个视口、`aria-expanded=true`、主区仍从 56px 开始；选择「下载管理」后抽屉关闭、`aria-current=downloads`、焦点到 `#section-title`；旧键保持 `'1'`；Escape 关闭并把焦点还给菜单按钮 |
| 320×568 | 图标栏 56px、抽屉 240px，标签可见，无横向溢出 |
| 390×300 + 长内容 | 图标栏内导航纵向可滚动；页面滚动时侧栏 `top=0` 保持 sticky，无横向溢出 |
| 1440 深色 + 隐私模式 | 侧栏 `#111113` 深色主题生效，`data-privacy-mode=1` 保留 |
| 登录页 | 无 `.sidebar`、无 `.nav-item`、无遮罩元素 |

另以截图像素抽样确认实际渲染宽度：桌面 0–239px 为侧栏、240px 起为主区；折叠 0–70px 侧栏、90px 起主区；手机 0–55px 侧栏、57px 起主区；抽屉 0–239px 侧栏、241px 起为被遮罩压暗的主区。

### 5. 其他
- 所有 `javsp_web/web/assets/*.js` 通过 `node --check`。
- 既有测试文件未修改；无「改测试掩盖回归」。（唯一涉及旧交互的关闭按钮位置属于第 7 项，本次未触碰。）

## 限制与后续

1. **demo 构建需主代理补两步**（本次按指令不生成 `docs/demo`，也未改 demo 脚本/测试）：`scripts/build_demo.py` 的 `assets` 列表加入 `navigation.css`、`navigation.js`，并同步 demo 资产一致性断言（现为 `tests/test_demo.cjs` 的资产列表），然后重建 demo；否则 demo 页会 404 这两个资源。
2. 图标为按现有视图语义临时手写的 inline SVG（`nav-item-icon`，24 viewBox / currentColor / 1.8 描边），待第 5 项全站 SVG 代理统一替换；届时只需改图标内容，结构/类名/`aria-hidden` 约定不变。
3. 热片/下片未建页面、未加菜单、未定义数据；本项只保证结构可扩展（见上）。
4. 浏览器 QC 为一次性脚本，未纳入仓库；CI 中由 Node 行为测试覆盖，CSS 几何仅本次实测（避免纯 CSS 字符串镜像测试）。若后续需持续回归，可把该 CDP 脚本作为可选任务另立。
5. 焦点陷阱为简单 Tab 循环；抽屉打开时背景内容未设 `inert`，屏幕阅读器仍可读到主区（视觉与指针已由遮罩隔断）。
6. Escape 监听在检测到 `dialog[open]` 时让行，避免与原生对话框关闭冲突。
7. 手机宽度下 `sidebar-collapsed` 类仍保留在 DOM（CSS 忽略），用于跨断点保留桌面偏好，属有意设计。
8. 未改动任何 `data-panel` 内容、视图命名、标题映射（`showView` 中「概览」等文字）、角色权限、主题/隐私逻辑与登录页。
9. 集成顺序：`navigation.css` 必须保持在 `app.css`/`overrides.css`/`cinema.css` 之后（当前在 `</head>` 前最后一份），它负责 `.app-shell` 在桌面与手机两个断点的列布局；第 3 项页面布局若调整 shell 网格或移动端，需要以本文件为准合并，避免重新引入顶部横向导航或单列堆叠。

## 回滚

删除 `navigation.js`、`navigation.css`、`tests/test_navigation_client.cjs`，移除 `index.html` 中两处资源引用并恢复原 `aside` 标记（图标退回文字按钮、删除遮罩），把删除的 `setSidebarCollapsed` 段恢复到 `app.js` 原位置。无数据迁移：旧键 `javsp-web.sidebar-collapsed` 沿用，回滚后旧逻辑可直接读取现有 `'1'/'0'`。
