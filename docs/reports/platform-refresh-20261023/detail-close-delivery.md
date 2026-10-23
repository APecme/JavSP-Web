# 交付说明：影片详情关闭按钮移入标题动作组（平台刷新第 7 项）

范围：仅本独立副本 `/data12t/AutoOrder/JavSP-Web/tmp/oct23-work/detail-close`。未改原仓库、未改其他副本、未委托其他代理、未提交/推送/部署，未生成 `docs/`、`docs/demo*`。

需求来源：`docs/superpowers/plans/2026-10-23-platform-refresh.md` §7「影片详情关闭」——标题栏动作组按「编辑资料、关闭」顺序，仅一个关闭按钮；窄屏标题可换行、动作按钮不被挤走；标题栏 sticky，分区导航独立，关闭位于编辑右侧；扫描任务隐藏编辑但保留关闭；剧照 dialog 自己的关闭不影响父层，Esc/焦点/滚动/后台刷新保持。

## 文件清单（改动 5 个）

| 文件 | 改动 |
| --- | --- |
| `javsp_web/web/index.html:114` | 详情 dialog 结构：新增 `.film-detail-top`（标题栏 + 分区导航），标题动作组 `.film-detail-actions` 内按「编辑资料 → SVG 关闭」排列；`nav.film-navigation` 删除 `film-nav-close`（"关闭 ×"）；`.film-detail-shell` 只保留 `#task-detail-content` 与 `#task-comments`；标题文本容器加 `.film-detail-titles`。所有原有 ID/data hook（`task-detail-dialog`、`task-detail-title`、`task-detail-subtitle`、`task-detail-content`、`task-comments`、`data-edit-task-metadata`、`data-detail-section`、`data-dialog-close`、`stills-*`）保持不变。 |
| `javsp_web/web/assets/cinema.css:203-210` | `.film-detail-top` 为唯一 sticky 区域（`position: sticky; top: 0; z-index: 6`）；标题栏 `position: static`、`flex-wrap: nowrap`、标题容器 `min-width: 0`；动作组 `flex: none; nowrap`；圆形 SVG 关闭按钮 36px（焦点轮廓复用 cinema.css 既有 `.icon-button:focus-visible` 规则）；导航改成同一 sticky 区域内的普通条（`position: static`），不再叠第二层 sticky。 |
| `javsp_web/web/assets/cinema.css:283,285,311,333-340,548` | 详情 shell 网格只剩内容列 + 评论列（评论区 `grid-row: 1`，与内容顶部对齐）；移动端（≤720px）标题栏 12/16px 内距、图标 34px、动作组紧凑、关闭 40px、长标题 2 行截断、副标题 1 行截断；`[hidden]` 时整条导航 `display: none`。删除失效的 `.film-nav-close` 规则（原 223、538-543 行）。 |
| `javsp_web/web/assets/overrides.css`（原 769 行） | 删除已无对应元素的 `.film-navigation .film-nav-close{...}` 死规则。 |
| `javsp_web/web/assets/app.js:1593` | 分区导航点击：滚动前用 `.film-detail-top` 实测高度写入 `scrollMarginTop`（+12px），避免 sticky 加高后跳转目标被标题条盖住；`scrollIntoView` 行为（smooth / instant）与 `block: start` 不变。 |
| `javsp_web/web/assets/app.js:2018-2020` | 扫描任务：分区按钮隐藏、导航条整条隐藏（否则只剩空白条）、编辑按钮隐藏；关闭按钮不属于任何隐藏分支。编辑按钮查询选择器改为 `#task-detail-dialog > .film-detail-top [data-edit-task-metadata]`（结构变更后仍能命中）。 |
| `tests/test_film_detail_ux.cjs:197-303` | 见下节「测试变更」。 |

未触碰：全站图标（无 `icons.js`，关闭图标为本 dialog 内联 SVG，与现有 `.lc-dialog-icon` 内联 SVG 同风格）、侧边栏、主题/隐私/角色权限、剧照 viewer 模块、Python 后端、demo 生成脚本。

## 关键设计决定

1. **sticky 必须脱离详情网格。** 原 `.film-detail-shell` 是 `display: grid`（内容 + 右侧评论）。CSS 规范下 sticky 元素的约束框是其**网格区域**，而标题行高度等于标题自身高度 → 无法滚动吸附，这既解释了旧导航 `position: sticky` 实际不生效，也说明"把关闭放进 sticky 导航"并不真的常驻。因此把标题栏与导航一起放进 `#task-detail-dialog > .film-detail-top`（dialog 直接子级、块级流），由 dialog 自身作为滚动容器吸附；导航在其内部为普通条，避免两层 sticky 互相遮挡。
2. **关闭是唯一入口，且可键盘可见。** `aria-label`/`title` = 「关闭影片详情」，按钮内只有 `<svg aria-hidden="true">`（`M6 6l12 12M18 6l-12 12`，24 viewBox、`currentColor`、`stroke-width:2`、圆头），无 `×`/文字；走既有全局 `[data-dialog-close]` 事件（`closest('dialog').close()`），因此点击、剧照层叠、`close` 事件里对评论/剧照的清理逻辑完全复用。
3. **窄屏不挤走动作。** 标题容器 `flex: 1 1 auto; min-width: 0`，动作组 `flex: none`；≤720px 标题最多 2 行（`-webkit-line-clamp`）、副标题 1 行，图标与按钮同步缩小，320px 宽度下固定占用 ≈16+34+10+10+68+6+40+16 ≈ 200px，剩余宽度留给标题，无横向溢出。桌面不截断标题（宁可标题区变高也不丢信息）。
4. **扫描任务。** 编辑隐藏后动作组只剩关闭；分区导航三条按钮全隐藏时导航条本身也隐藏，避免留下一条空的工具栏（关闭已不在其中）。
5. **剧照弹窗与 Esc。** 未改动 `stills-dialog`、`JavspStills` 模块与 `#task-detail-dialog` 的 `close` 事件；Esc 在剧照层被 `preventDefault + stopPropagation` 拦下，只关剧照；详情 `close` 仍清理评论/剧照。

## 测试变更（旧需求被用户改变，非掩盖回归）

原第 9 个用例 `the film detail keeps exactly one close control, inside the sticky navigation` 断言的正是被用户改掉的旧位置（关闭在导航内、标题栏不得有关闭），按新需求替换为 5 个用例；剧照/隐私/评论帮助等 13 个旧用例全部保留并按原样通过。

| 用例（`tests/test_film_detail_ux.cjs`） | 覆盖 |
| --- | --- |
| `the film detail closes from the title action group, right of 编辑资料` (197) | 详情内 `data-dialog-close` 恰好 1 个；位于 `.film-detail-actions` 且顺序在 `data-edit-task-metadata` 之后；按钮内只有 SVG、无 `×`/文字；`aria-label="关闭影片详情"`；导航内 0 个关闭且保留 3 个分区按钮。 |
| `the sticky title region carries the close and stays out of the detail grid` (222) | 标题栏与导航同处 `#task-detail-dialog > .film-detail-top`，该块包含唯一关闭；块位于 `.film-detail-shell` 之前（不进网格）；`cinema.css` 中 `.film-detail-top` 为 `position: sticky; top: 0`，导航不再自带 sticky。 |
| `section links scroll clear of the now sticky title region` (238) | 执行真实点击处理器：`scrollIntoView({behavior:'smooth',block:'start'})` 仍触发，且 `scrollMarginTop` 按实测 sticky 高度（121+12）计算，不再用旧的 55px。 |
| `the title close rides the shared dialog close handler` (264) | 执行真实 `[data-dialog-close]` 分支：点击标题关闭会 `close()` 最近的 dialog（回归保护，实现前即可通过）。 |
| `scan tasks hide the empty navigation and the edit action but keep the close` (274) | 执行真实隐藏逻辑（`scan` 与影片两种 `task_type`）：扫描时 3 个分区按钮、导航条、编辑均隐藏，块内无任何关闭隐藏分支；影片任务全部恢复显示。 |

## 验证（在本副本内实际执行）

1. TDD 顺序：先改测试 → `node --test tests/test_film_detail_ux.cjs` 红（3 个新用例失败：8/9/11；后续新增滚动与扫描用例同样先红）→ 实现 → 全绿。另做反证：临时删掉 `sectionNav.hidden` 两行后扫描用例立即变红，恢复后变绿。
2. `node --test tests/test_film_detail_ux.cjs` → `pass 14, fail 0`。
3. Node 全回归（逐文件 `node --test`）：`test_ai_translation_client 1`、`test_comment_markdown 3`、`test_comments_client 10`、`test_community_client 3`、`test_cookiecloud_client 1`、`test_film_detail_ux 14`、`test_library_playback 1`、`test_mount_batch_client 1`、`test_overview_actress 2`、`test_scan_client 1`、`test_web_client 1` 全通过；`test_demo` 8 失败、`test_theme_client` 1 失败与**改动前基线完全一致**，原因均为本副本没有 `docs/`（`ENOENT docs/demo-seed.js`、`docs/demo.html`），demo 由主代理统一构建，不是本次改动引入。
4. `node --check` 通过全部 `javsp_web/web/assets/*.js`。
5. HTML 标签配平检查（`html.parser`）通过 `index.html`、`login.html`；CSS 花括号配平检查通过 `theme.css / app.css / overrides.css / cinema.css`。
6. 静态层叠审计脚本（按 文件顺序 + 特异性 + !important 取胜者，仅检查精确选择器、忽略媒体查询语境）：`.film-detail-top` → `position: sticky; top: 0`（cinema.css）；`.film-navigation` → `position: static`（cinema.css 的 `(1,1,0)` 胜过 overrides 的 `(0,1,0) sticky`）；标题栏 `position: static`、`flex-wrap: nowrap`；动作组 `flex: none`；关闭按钮 `border-radius: 50%`、`flex: none`；`nav[hidden]` 胜出 `display: none`。
7. Python 回归**未执行**：本环境无 `fastapi/pytest` 依赖（`ModuleNotFoundError: fastapi`），与改动前一致；本次只改静态前端，后端接口、任务模型与持久字段未动。

## 限制与已知事项

1. **没有浏览器可用**：本环境无 `playwright / puppeteer / jsdom / chromium`，无法做真实渲染的视觉/交互回归。sticky 吸附、移动端断行、深浅主题与隐私模式下的观感均按 CSS 层叠推理与静态审计给出，**需要主代理在真实浏览器按 1440/800/390px 各点一次「编辑资料/关闭」、滚动到底、长文件名扫描任务与暗色主题复核**。这也是没有写"纯 CSS 字符串镜像测试"的原因：可逆视觉只做了结构/机制级断言。
2. **间距的可见微调**：标题栏与导航原先作为网格行各带 18px 行间距，现在合并为一个连续的 sticky 区域（标题栏 `border-bottom` + 导航条 `border-bottom`），内容紧接其后；`backdrop-filter` 从标题栏/导航移到不透明的 `.film-detail-top` 背景（视觉等价，因为底色本就不透明）。若主代理希望恢复 18px 间隔，只影响 `.film-detail-top` 一条规则。
3. **桌面长标题不截断**：只在 ≤720px 做 2 行截断，桌面保持完整换行（sticky 区会变高但信息不丢）；如需桌面也截断，复用到 `--film-detail-sticky` 的滚动偏移仍然正确，因为偏移在点击时实测。
4. **移动端触控尺寸**：关闭按钮 40×40px（桌面 36×36px），低于 44px 推荐值，但与本 dialog 既有图标按钮量级一致（剧照关闭约 33px 高）；如需 44px 可只改一条规则。
5. **`overrides.css` 残留失效选择器**：`.task-detail-dialog > .film-detail-shell > .panel-heading...` 与 `.film-detail-shell > .panel-heading`（约 378、449、760、764 行，含打包压缩块）现在匹配不到新结构，属无害死规则；压缩块与其它组件规则混在同一行，为控制风险未做清理，交给主代理在集成时统一清理。
6. **图标体系**：全站 `icons.js` 属第 5 项，本副本没有；标题关闭按钮用内联 SVG。该图标落地后建议把这段内联 SVG 换成 `window.JavspIcons.render('close')`，DOM/类名与测试断言（`<svg aria-hidden="true">`、只含 SVG）可保持兼容。
7. **demo 与 `docs/`**：按要求未生成；`test_demo` / `test_theme_client` 的失败需在 demo 构建后复核。
8. **未做**：热片/下片、目录监控、评论转发、自更新等其它条目；未改 nav/header/侧栏命名与图标。

## 回滚

仅 5 个文件、均为局部替换：
- `index.html`：把 `#task-detail-dialog` 恢复为「`.film-detail-shell` > `.panel-heading` + `.film-navigation`（末位 `film-nav-close`）」结构。
- `cinema.css`：恢复 `.film-detail-shell > .panel-heading` / sticky 导航规则，删除第 203-210、333-340、548 行的新规则与移动端片段。
- `overrides.css`：恢复 `.film-navigation .film-nav-close{...}` 一行。
- `app.js`：删除 1593 行的 `stickyBar` 计算与 2018-2019 行的 `sectionNav`；编辑按钮选择器改回 `#task-detail-dialog > .film-detail-shell > .panel-heading [data-edit-task-metadata]`。
- 测试：恢复旧用例 `the film detail keeps exactly one close control, inside the sticky navigation`。
