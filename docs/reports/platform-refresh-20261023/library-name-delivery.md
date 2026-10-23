# 第 6 项交付：概览可见名称改为「片库」

本副本仅处理计划 `docs/superpowers/plans/2026-10-23-platform-refresh.md` 第 6 项。内部 `overview` 标识、data keys、API、DOM hooks、持久化 key 全部保持不变；未改动业务逻辑、CSS、其他功能。

## 文件清单

| 文件 | 位置 | 改动 |
| --- | --- | --- |
| `javsp_web/web/index.html` | `index.html:24` | 侧栏导航按钮文案 `概览` → `片库`（`data-view="overview"` 保留） |
| `javsp_web/web/index.html` | `index.html:37` | header 标题 `<h1 id="section-title">概览</h1>` → `片库` |
| `javsp_web/web/assets/app.js` | `app.js:2860` | `showView()` 标题映射 `overview: '概览'` → `'片库'`，未知视图兜底 `\|\| '概览'` → `\|\| '片库'` |
| `javsp_web/skills/javsp-scrape/SKILL.md` | `SKILL.md:15` | AI 技能对用户说明「在手动刮削和概览中查看」→「在手动刮削和片库中查看」 |
| `scripts/build_demo.py` | `build_demo.py:60` | demo 顶部提示文案「体验概览分类…」→「体验片库分类…」（只改字符串，未运行生成） |
| `tests/test_library_naming.cjs` | 新增 | 命名行为的回归测试（先失败后实现） |
| `DELIVERY.md` | 新增 | 本文件 |

改动全部为可见文案/标题映射，共 6 处文本替换（4 个文件），未新增/删除函数，未改变量名，未触碰样式。原文件为 CRLF 换行，已按字节级替换保留原换行方式，未引入整文件格式化差异。

## 刻意保留（兼容性）

- DOM hooks：`data-view="overview"`、`data-panel="overview"`、`#overview-tasks`、`#overview-group-tabs`、`#library-search`、`.lc-overview` 等原样保留。
- 持久化：`localStorage['javsp-web.active-view']` 的键和值仍为 `overview`；旧客户端存过的 `overview` 仍能恢复片库视图（已用真实浏览器验证，见下）。
- 首屏预绘制：`index.html` 内联脚本仍写 `data-initial-view="overview"`，配套内联 CSS 的 `html[data-initial-view="overview"] [data-panel="overview"]` 未改动，因此刷新时不会先闪出别的面板。
- 内部命名：`renderOverview`、`overviewCoverCard`、`state.overviewGroupBy`、`overviewGroupType`、`/api/tasks` 等概览相关标识与接口未重命名；Python 侧的概览聚合函数未动（本项未修改任何 Python 业务代码）。
- 主题/隐私/角色权限：未改 CSS 与权限判断；浏览器验证中 `data-theme`、`data-privacy-mode` 与原行为一致。

## 测试

### 先失败后实现

新增 `tests/test_library_naming.cjs`，先运行得到预期失败：

```
not ok 1 - the sidebar and header present the overview view as 片库        expected '片库', actual '概览'
not ok 2 - showView labels overview as 片库 and keeps the overview persistence key   同上
ok     3 - showView keeps the other view titles untouched
ok     4 - saved overview view still restores the library panel on load
not ok 5 - user-facing copy no longer calls this view 概览
```

实现后：

```
ok 1 - the sidebar and header present the overview view as 片库
ok 2 - showView labels overview as 片库 and keeps the overview persistence key
ok 3 - showView keeps the other view titles untouched
ok 4 - saved overview view still restores the library panel on load
ok 5 - user-facing copy no longer calls this view 概览
```

测试内容（行为而非 CSS 字符串镜像）：

1. 解析 `index.html`：`data-view="overview"` 按钮文案为「片库」，`#section-title` 初始为「片库」，`data-panel="overview"` 仍在。
2. 用 `vm` 执行真实的 `showView()`：`showView('overview')` 后 `#section-title`=`片库`、eyebrow=`工作区`、`overview` 导航与面板得到 `active`、写入 `javsp-web.active-view=overview`、仍触发一次 `loadTasks()`。
3. 其余视图标题（手动刮削/自动刮削/下载管理/系统设置）与持久值未被误改。
4. 旧 `active-view=overview` 恢复链路：内联脚本读取键、内联 CSS 首屏映射、`showView(savedView)` / `else showView('overview')` 兜底均存在。
5. 面向用户的 5 个文件不再出现「概览」。

### 旧测试语义

`grep -rn 概览 tests/` 无命中：已有测试没有任何断言依赖「概览」这个可见文案，因此本项没有出现"旧需求被改变需更新语义预期"的用例，也没有修改任何既有测试。

### 全量回归（本副本）

- JS 语法：`node --check` 通过（`app.js`，改动文件；其余 assets 亦通过）。
- Node 全回归：14 个 `tests/*.cjs`，12 通过。失败 2 个均为基线即失败、与本项无关：
  - `tests/test_demo.cjs`、`tests/test_theme_client.cjs` 读取 `docs/`（本副本不含 docs，报 `ENOENT: docs/assets/theme.css`）。
- Python：17 个测试文件收集失败（环境缺 `Crypto`、`confz` 等依赖），可收集子集 61 passed、9 failed，9 个失败全部是同一依赖缺失（`javsp_web/cookiecloud.py` 的 `Crypto`、`vendor/JavSP/javsp/config.py` 的 `confz`）。均为基线状态，本项未改 Python 业务代码。
- `python3 -m py_compile scripts/build_demo.py` 通过。

## 浏览器/交互验证（真实 Firefox）

环境只有 snap Firefox，需要可写 `XDG_RUNTIME_DIR` 与 `HOME` 才能启动（workspace-write 下 `/run/user/1000` 只读），因此验证在放开文件权限的临时进程中完成；用 Python 静态服务器托管本副本的真实 `javsp_web/web`，仅把 `/api/*` 桩成最小 JSON（`auth/me`、`runtime`、`tasks` 等），未改仓库文件。验证脚本、截图、临时 profile 已全部清理。

无头 Firefox（1280×900）驱动 `index.html`，结果：

1. **旧 `active-view=overview` 恢复**：预置 `localStorage['javsp-web.active-view']='overview'`、`theme=dark`、`privacy-mode=1` 后加载页面：
   - `#section-title` = `片库`，eyebrow = `工作区`
   - 活动面板 = `overview`，活动导航 = `overview`
   - 导航文案 = `["片库","手动刮削","AI 刮削","自动刮削","下载管理","爬虫配置","刮削预设","系统设置"]`
   - 片库面板可见、`.lc-overview .lc-stats` 与 `#library-search` 存在、`#overview-tasks` 显示空态文案
   - `data-theme=dark`、`data-privacy-mode=1` 保持
2. **导航切换往返**：点击「下载管理」→ 标题 `下载管理`、面板 `downloads`、持久值 `downloads`、片库面板隐藏；再点「片库」→ 标题 `片库`、面板 `overview`、持久值回到 `overview`。
3. **非默认视图恢复**：预置 `active-view=downloads` 刷新 → 标题 `下载管理`、活动面板 `downloads`，说明视图恢复链路未被本项破坏。
4. **渲染测量**（非字符串断言）：导航按钮 `片库` 文字可见（`visibility:visible`、207×41 px、中心点命中该按钮）、header `片库` 可见（26px、51×39 px）、片库面板 `display:block`。

截图已生成但因会话内图片读取工具报错（`cannot get property "fs" without inject`）无法在本次还原查看，故视觉结论以上述 DOM 计算样式与命中测试为准；未做像素级视觉比较。

## 文档

本副本不含 `docs/`（计划要求 demo/文档由主代理统一构建），按指示未凭空创建旧文档，也未生成 demo。需要在用户指南/使用教程中同步的措辞仅一处概念替换，供主代理并入：

- 侧栏「概览」→「片库」；页面标题「概览」→「片库」。
- 涉及片库的说明、空态、教程锚点文字统一称「片库」；「片库」页面行为、入口位置、搜索与分类方式不变，仅名称变化。
- demo 顶部提示已改「体验片库分类、明暗主题、隐私模式、预设与 AI 助手。」（`scripts/build_demo.py:60`），重建 demo 时生效。

## 限制与未做

- 未重新构建 demo、未重新生成 `docs/`，未运行 `scripts/build_demo.py`；`tests/test_demo.cjs` 在本副本因缺 `docs/` 仍失败（基线亦然），主代理重建 demo 后才可判定。
- 未拍照留档（图片工具不可用）；视觉验收仅有计算样式与点击交互证据。
- 未做移动端窄屏截图；导航文案长度由「概览」(2 字) 变为「片库」(2 字)，宽度不变，布局风险低，但仍建议主代理在 390/320 宽度截图复核。
- Python 测试环境依赖不齐（`Crypto`、`confz`），无法在本副本跑全量 Python 回归；本项未改 Python 业务逻辑，仅改 `build_demo.py` 一处字符串。
- 会话期间原仓库 `javsp_web/web/index.html` / `app.js` 的影片详情对话框结构发生了变化（原仓库现为 `film-detail-top`，本副本基线为 `film-detail-shell`），因此"与原仓库逐行 diff"不能当作基线证据；本副本自身基线（含第 7 项详情改造）保留完好，`tests/test_film_detail_ux.cjs` 通过。本项的改动边界就是上表 6 处文字。
- 未提交、未推送、未部署；未改动原仓库与其他副本（仅以只读方式对照原仓库字符串与换行符）。
