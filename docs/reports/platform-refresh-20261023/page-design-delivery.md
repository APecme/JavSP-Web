# DELIVERY — 第 3 项：功能页布局重排

本轮只处理“页面布局与视觉”第 3 项。改动全部位于独立副本
`tmp/oct23-work/page-design`，未修改原仓库、其他副本、`.git` 或生产 `data`，
未提交、未推送、未部署；未委托其他代理。

## 1. 文件清单

### 生产文件

| 文件 | 变更 |
| --- | --- |
| `javsp_web/web/index.html` | 主要改动集中在各 `data-panel` 内部：手动刮削、自动刮削、下载、爬虫、预设、设置、AI、个人中心结构；新增 `page-layouts.css` 引用。sidebar 与 header nav 未改。 |
| `javsp_web/web/login.html` | 登录页改为与控制台一致的左右分栏卡片；新增 `page-layouts.css` 引用；主题引导、登录 ID 与登录脚本保持不变。 |
| `javsp_web/web/assets/page-layouts.css` | 新增，581 行。所有规则按 `[data-panel="..."]` 限定，另含 `#profile-dialog` 与登录页规则；覆盖 1440/1024/390/320、明暗主题、空态、长文本、折叠与 reduced-motion。 |
| `javsp_web/web/assets/app.js` | 7 处必要布局/状态改动：任务筛选改为原生 `<details>`；爬虫配置改为来源列表 + 编辑/测试主从面板；预设空态；自动刮削两个模块的状态计数；设置动态模块挂到分组容器并保留根节点回退。 |
| `javsp_web/web/assets/ai.js` | 1 行：AI 设置优先插入 `#settings-ai-mount`，缺失时回退到原 `[data-panel="settings"]` 锚点。 |

### 测试与验证产物

| 文件 | 说明 |
| --- | --- |
| `tests/test_page_layouts.cjs` | 新增，294 行。先写失败测试再实现；覆盖页面区域、设置分组、动态挂载、任务筛选折叠、爬虫主从、状态计数、预设空态、CSS 作用域、登录/个人中心和旧 ID 保留。 |
| `tmp/page-verification/` | 临时验收产物，不属于生产构建：64 张截图、`layout-report.json`（118 项浏览器检查）、BiDi 探针、预览生成器与合成 API 数据。未放入 `docs/`。 |
| `DELIVERY.md` | 本文件。 |

### 未修改

`javsp_web/web/assets/cinema.css`、`theme.css`、`app.css`、`overrides.css`、
`community.js`、`scripts/build_demo.py`、`docs/`、sidebar/header nav、
影片详情关闭位置与全站图标相关文件均未改。`index.html` 的 sidebar/header
与 `cinema.css` 与基线逐字对比一致；概览 `data-panel="overview"` 内部也未改。

## 2. 各功能页的实际结构变更

### 手动刮削

- 两区布局：左侧紧凑输入/预设主操作卡，右侧独立任务队列。
- 路径与路径工具保持原 ID；预设与开始按钮收进 `.scrape-primary-row`。
- 任务筛选/分页由 `app.js` 插入为原生 `<details id="task-filter-panel" open>`，
  可收起；筛选控件、摘要、分页 ID 全部保留。
- 长任务标题使用 `overflow-wrap:anywhere`；窄屏单列。

### 自动刮削

- 三个明确模块：`目录监控`、`定时自动刮削`、`下载完成自动刮削`。
- 目录监控预留稳定挂载点：`[data-auto-scrape-module="watch"] #directory-watch-mount`
  （同时带 `data-directory-watch-mount`），内含空态；未删除任何监控实现。
- 定时与下载完成模块分别显示状态计数（`N 条规则 · M 条启用` / `N 条自动记录`）。
- 1440 为“监控全宽 + 定时/下载两列”，1024 及以下单列。

### 下载管理

- 顺序改为：下载器标签与摘要 → 可折叠筛选 → 列表 → 策略。
- 筛选包在原生 `<details id="download-filter-panel" open>` 中，仍保留
  `#download-filter-bar`、`#download-filter-summary` 等 ID。
- 策略面板移到列表下方，默认折叠；原 `#download-policy-toggle` /
  `#download-policy-content` 与 localStorage 记忆逻辑不变。
- 桌面策略面板已放宽为整行，避免窄条错位。

### 爬虫配置

- `loadCrawlerConfig` 生成的标记改为 `crawler-workbench` 主从结构：
  左侧 `crawler-source-panel` 来源列表，右侧 `crawler-editor-panel`
  编辑与测试区。
- `#crawler-code-list`、`#crawler-code-detail`、`#add-custom-crawler`、
  `data-crawler-code-name` 等 hooks 全部保留。
- 桌面来源列表 sticky；980px 以下堆叠，来源列表变为横向卡片网格。

### 刮削预设

- 左侧选择列表、右侧分组编辑器；桌面列表 sticky。
- 1100px 以下切换为“列表横向条 → 编辑器”的顺序（`order:1/2`），
  1024 与移动端都可先选预设再编辑；这是 1024 下避免编辑器内容横向溢出的
  实际结构变更。
- 空预设时显示 `page-empty-state`，不再空白。

### 系统设置

- 新增设置分组导航：`软件更新`、`连接与下载`、`AI 接入`、`账号与权限`。
- 桌面为 200px sticky 侧栏 + 分组内容；1024 保持侧栏；980px 以下变为
  横向可滚动导航，所有分组仍在文档中，不隐藏表单。
- 动态模块挂载点：
  - `#settings-connection-mount`：媒体服务器（`app.js` 原动态插入）与路径映射。
  - `#settings-ai-mount`：AI 设置（`ai.js` 原 `prepend`）。
  - 两处都保留“找不到锚点就回退到设置根节点”的兼容路径。
- 更新、CookieCloud、下载器、用户管理、媒体服务器、路径映射、AI 表单均保留原 ID。

### AI 刮削

- 左侧会话栏增加标题与搜索区，右侧工作区为独立卡片。
- 对话区滚动、输入区固定在会话底部（`position:sticky` + flex 收缩）。
- 1440 左栏 260px；960–1100px 保留 220px 左栏，避免 1024 出现空白列；
  1100px 以下恢复抽屉，820px 以下单列，390/320 可打开会话抽屉。
- `#ai-new-chat`、`#ai-history-list`、`#ai-workspace`、`#ai-conversation`、
  `#ai-chat-form`、`#ai-message`、`#ai-send` 等 hooks 未改。

### 个人中心与登录

- 个人中心：`profile-body` 包裹原有身份表单与评论列表，使用与功能页一致的
  卡片、圆角、边框和留白；`#profile-form`、`#my-comments-*` 等 ID 未改。
- 登录：左右分栏品牌区 + 表单区；保留主题引导、`#login-form`、`#username`、
  `#password`、`#login-error`、`#login-version` 与登录 fetch 逻辑。

## 3. 验证

### 测试驱动

先写 `tests/test_page_layouts.cjs`，在实现前运行并确认 9 项失败（缺少
`page-layouts.css`、设置分组、折叠筛选、爬虫主从、状态计数、空态、动态锚点、
登录/个人中心结构）。实现后：

```bash
node --test tests/test_page_layouts.cjs
```

结果：**10 passed / 0 failed**。

### Node 全回归 / 语法

```bash
node --test tests/*.cjs
for f in javsp_web/web/assets/*.js; do node --check "$f"; done
```

- 全量：**52 passed / 9 failed**。
- 9 项失败全部是基线副本缺少 `docs/` 的 demo/文档测试（`docs/demo.html`、
  `docs/demo-seed.js`、`docs/assets/...`），本轮未生成 `docs/demo`，不是本次
  改动引入；改动前同样为这 9 项失败。
- 所有前端 JS `node --check` 通过。

### 真实浏览器验证（Firefox headless + WebDriver BiDi）

环境：Firefox 158 headless，直接调用
`/snap/firefox/current/usr/lib/firefox/firefox`，指定可写
`XDG_RUNTIME_DIR`/`HOME`；使用合成 API 数据与合成 SVG 封面，不加载真实媒体。

`tmp/page-verification/verify_layouts.py` 结果：

- **118 项检查，0 失败**。
- 1440/1024/390/320 下的面板可见性、文档无横向溢出、双栏/单栏切换；
  1024 全页面无横向溢出，爬虫保持主从、设置保持侧栏。
- 手动刮削：两区、队列持有任务表、筛选可折叠、长标题换行。
- 自动刮削：三模块、监控挂载点、状态计数、行数。
- 下载：摘要 → 筛选 → 列表 → 策略顺序、策略默认折叠、筛选 details、长名称截断。
- 爬虫：来源列在编辑列左侧、代码/测试区可见、3 个来源项。
- 预设：1440 左右双栏；1024 与移动端列表在编辑器上方，10 个分组 tab。
- 设置：四组、侧栏/移动横向导航、动态媒体/路径/AI 挂载、主表单可见、
  锚点点击滚动到目标组。
- AI：1440 左栏 + 对话区 + 底部输入，1024 保留 220px 左栏，390/320 抽屉。
- 登录：1440 两栏、390/320 堆叠、无横向溢出；个人中心弹窗结构可见。
- 明暗主题：1440/390/320 的深色页面检查通过；隐私模式开关实测为 `1/0`。
- 键盘：设置锚点获得焦点后 Enter 改变 hash 到 `#settings-account`；
  `<summary>` 可获得焦点。headless BiDi 发送 Enter 未触发 Firefox 对
  `<details>` 的默认展开（自动化限制），因此收起动作以点击验证，见限制。

`tmp/page-verification/shots.py` / `shots_extra.py` 生成 **64 张截图**：
7 个功能页 × 1440/1024/390/320 × 明暗，另加登录与个人中心各 4 张。
截图与报告在 `tmp/page-verification/`，不属于生产构建。

控制台检查：逐页导航时收集 `log.entryAdded`，7 个功能页均无 error/warn。

### 静态检查

- HTML 解析：`index.html` 257 个 ID、`login.html` 7 个 ID，无重复、无未闭合标签。
- CSS：花括号 215/215；使用的 CSS 变量全部有定义。
- 行尾：修改的既有 Web 文件与新增 CSS 保持 CRLF；新增 Node 测试为 LF。

### Python

```bash
python3 -m pytest -q tests
```

当前环境缺少 `Crypto`（pycryptodome），17 个测试在 collection 阶段报
`ModuleNotFoundError: No module named 'Crypto'`，未能执行。本轮未修改 Python
文件；主代理在完整依赖环境运行全回归。

## 4. 限制与整合注意事项

1. **未生成 `docs/demo`**。主代理构建 demo 时必须把 `page-layouts.css` 加入
   `scripts/build_demo.py` 的 assets 列表与复制逻辑，并让 `test_demo.cjs`
   的资产清单/顺序包含它；否则 demo 会 404 或缺失布局。本轮按分工未改这些文件。
2. **目录监控仍是挂载点**。另一个代理应把监控内容插入
   `#directory-watch-mount`，保留
   `[data-auto-scrape-module="watch"]` 区域；不要把该区域替换成仅监控面板而丢掉
   定时/下载完成两区。
3. **sidebar/header nav 未改**。移动端截图顶部的深色横向导航来自基线 sidebar，
   由 sidebar 代理负责；本轮页面内容自身在 390/320 下无文档级横向溢出。
4. **键盘限制**：设置锚点 Enter 已实测；`<summary>` 在 headless BiDi 下可获得
   焦点，但 BiDi 的 Enter 没有触发 Firefox 对 `<details>` 的默认激活，故未把
   “键盘 Enter 收起筛选”作为通过项。原生 `<summary>` 仍是标准可键盘操作元素，
   没有自定义键盘拦截。
5. **无真实媒体/真实服务**。浏览器验证全部使用合成 API 响应和合成 SVG 封面，
   不读取生产数据、不连接真实爬虫/下载器。
6. **个人中心评论与头像**只验证了弹窗结构与样式；真实评论/身份接口仍由
   `community.js` 原逻辑负责，未改业务。
7. **Python 全回归未执行**，原因见上；前端 JS/Node 与浏览器验证已完成。
8. **未做 Safari/Chrome 实测**。只在 Firefox 158 headless 验证；CSS 使用仓库
   既有的语义变量、CSS 变量和 `minmax`/grid，未引入实验性布局特性。

## 5. 复跑入口

见 `tmp/page-verification/README.md`。`make_preview.py` 会临时生成
`javsp_web/web/.preview.html`，验收后应删除；该文件不进入交付。
