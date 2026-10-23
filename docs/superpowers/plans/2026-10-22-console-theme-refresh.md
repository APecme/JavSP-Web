# 控制台视觉统一与影片详情体验实施计划

**目标：** 将概览页的紫色强调、柔和表面、16–18px 卡片圆角、10–12px 控件圆角和清晰排版扩展至其他控制台页面与登录页，优化评论帮助与剧照查看，消除重复关闭按钮。

**授权与分工：** 用户授权主代理制定完整方案、委托 DeepSeek Harness 实现并由主代理最终审批。不额外等待设计确认；不提交、推送或部署。

**技术：** 保持原生 HTML/CSS/JavaScript 与现有 dialog、事件委托、主题变量、离线测试和 demo 构建机制。无新增生产依赖。

## 约束与文件

- 当前有大量既有未提交修改，不得重置或覆盖既有工作。真实工作副本基线的行尾为 CRLF：主代理确认改动前行数为 `app.js` 3961、`cinema.css` 335、`overrides.css` 771，`index.html` 与 `login.html` 全文 CRLF。实现方会话内 `/tmp` 不可读，故按字节逆向重建改动前副本作对照。
- 主要修改 `javsp_web/web/assets/{cinema.css,app.js,overrides.css}`、`javsp_web/web/index.html` 与 `javsp_web/web/login.html`；测试位于 `tests/`。
- 概览页作为视觉基准；统一 sidebar/topbar、手动刮削、AI 刮削、自动刮削、下载管理、爬虫配置、刮削预设、系统设置、个人中心、登录页及常用弹窗。
- 保留表单字段、ID、数据属性、业务权限与 API 行为。语义状态色继续表达成功、警告和危险，避免所有状态均变紫。
- 明暗主题均使用语义变量，保留键盘焦点、disabled、hidden、reduced-motion，移动端无页面横向溢出。
- 行尾沿用既有工作副本：`app.js`、`cinema.css`、`overrides.css`、`index.html`、`login.html` 全为 CRLF，不制造整文件行尾差异；`docs/` 产物按 `build_demo.py` 既有行为生成（资产按字节复制、`docs/demo.html` 为 LF）。

## 设计

1. 视觉采用既有 `--lc-*` 语义变量。统一标题、说明、面板、输入框、按钮、分段导航、任务卡片与空态；各功能页保留适合其任务的布局，AI 保留对话布局，配置保留可扫描的表单分组。登录页加载既有 `cinema.css`，只追加 `.auth-shell` / `.auth-card` 的表面样式，复用同一套 18px 卡片圆角、10px 控件圆角与紫色柔光，不改登录 API、提示文案、密码字段与主题 bootstrap。
2. 将孤立问号替换为信息/排版线性图标 + “格式说明”轻量按钮；保留原生 details 的键盘可操作性。展开内容按字数、Markdown、时间标签分组，示例用 code 呈现；卡片参与正常文档流，避免弹层被裁切或超出屏幕。帮助按钮的 hover/open/focus、分组线与 code 使用 `--lc-*` 紫色主题，触发按钮高度约 28px 以保证可点击面积。保留原说明的全部限制和播放条件。
3. 剧照缩略图使用真实 button 与明确可访问名称。点击在独立原生 dialog 内以 contain 显示，提供张数、前后切换及关闭；支持 Escape 与左右方向键，图片加载失败提示，窄屏安全布局，关闭恢复焦点。查看层关闭只关闭自身，不关闭影片详情。任务切换、详情关闭时清理查看层及旧图片；不绕过隐私模式。
4. 删除详情标题栏关闭控件，仅保留 sticky 详情导航末尾的一个关闭按钮，确保键盘可访问及窄屏布局。

## 实施与验收

- [x] DeepSeek 阅读现有实现与适用规范，明确剧照渲染、事件委托与自动刷新行为。
- [x] 为剧照打开/切换/关闭/清理、独立 Escape 行为与详情单一关闭入口添加有意义的离线回归，先确认失败。
- [x] 实现统一视觉、评论说明、剧照查看与单关闭入口。不得做无关业务重构。
- [x] 运行相关测试、所有 Node 前端回归及逐文件 `node --check` 语法检查（`node --check` 的 glob 只检查首个文件，故以 for 循环逐文件执行）。
- [x] 运行 `python3 scripts/build_demo.py` 同步 demo，检查生成文件与源码逐字节一致。
- [x] 主代理独立比对基线增量并做浏览器验收：Node 51 项通过；Playwright 8 页 × 1440/390 宽 × 明暗主题共 32 组无页面横向溢出、无 JS 异常；真实浏览器配合合成 SVG 模拟图验证剧照左右键、Esc 只关查看层、错误提示、焦点、轮询保持、详情关闭清理与隐私 blur。
- [x] 审批返修三项：评论帮助改用 `--lc-*` 紫色并提高可点击高度；`login.html` 加载 `cinema.css` 并补统一表面样式；三个被误改为 LF 的资产恢复 CRLF。
- [x] 返修后复核：逐文件 `node --check`、`build_demo.py`、`node --test tests/*.cjs`，并用无头 Chromium 检查登录页与评论帮助的明暗主题、圆角、强调色、横向溢出与帮助卡片流式布局。
- [x] 主代理已复核返修增量，审批通过，交付当前工作区；未提交、推送或部署。详见 `docs/reports/console-theme-20261022/README.md`。

## 实施记录（DeepSeek Harness，2026-10-22）

### 修改文件

| 文件 | 内容 |
| --- | --- |
| `javsp_web/web/index.html` | 删除详情标题栏的关闭控件，只保留 sticky 导航末尾的 `.film-nav-close`；新增顶层 `#stills-dialog` 剧照查看层。行尾保持 CRLF。 |
| `javsp_web/web/login.html` | 在 `overrides.css` 之后加载既有 `cinema.css`（复用 `ASSET_VERSION` 缓存参数），其余结构、登录请求、提示文案、密码字段与主题 bootstrap 未改；新增 1 行，全文 CRLF。 |
| `javsp_web/web/assets/app.js` | 新增 `fanartGridMarkup()`（剧照改用带可访问名称的原生 `button`）；新增 `window.JavspStills` 查看层模块与 `[data-fanart-open]` 事件委托；任务切换／详情关闭时清理查看层；scan 任务改为只隐藏导航分区按钮；评论帮助改为图标＋“格式说明”＋四组规则。 |
| `javsp_web/web/assets/cinema.css` | 追加“Console-wide refresh”整段：侧边栏／顶栏、面板与标题、按钮、输入框、分段导航、任务卡片、空态、下载、爬虫配置、预设、设置、AI、个人中心与常用弹窗统一到概览页语义变量；新增 `.detail-fanart`、`.stills-dialog` 与隐私模式规则；末段新增 `.auth-shell` / `.auth-card` 登录页表面样式（18px 卡片圆角、10px 输入与按钮圆角、紫色柔光阴影、明暗焦点环、≤560px 收窄为 14px）。 |
| `javsp_web/web/assets/overrides.css` | 评论帮助从绝对定位浮层改为随表单流展开的分组卡片；触发按钮 hover/open/focus、分组左边线与 code 由旧 `--accent*` 蓝色改为 `--lc-*` 紫色，`min-height` 由约 22px 提升到 28px（`padding: 5px 13px 5px 11px`）。 |
| `tests/test_film_detail_ux.cjs` | 新增 10 项离线回归（先失败后通过）。 |
| `docs/demo.html`、`docs/demo-seed.js`、`docs/assets/{cinema.css,overrides.css,demo-app.js}` | `build_demo.py` 生成结果。 |

### 审批返修（第二轮）

1. 评论帮助配色与可点击面积：`overrides.css` 中 `.comment-help` 段全部换成 `--lc-line` / `--lc-raised` / `--lc-accent` / `--lc-accent-soft` / `--lc-accent-text` / `--lc-accent-border`，不再引用旧 `--accent*`。实测亮色触发按钮 open 态为 `color #7e3aa8`、`background rgba(155,77,202,.1)`、`border #9b4dca`，暗色为 `#d8b4fe` / `rgba(179,102,214,.18)` / `#9f50c2`；分组左边线亮色 `rgba(155,77,202,.5)`、暗色 `rgba(179,102,214,.5)`；`code` 亮 `#7e3aa8`、暗 `#d8b4fe`。按钮高度 28px，分组卡片仍为正常文档流（宽 1070@1200、328@390，无浮层）。
2. 登录页统一：`login.html` 新增 `cinema.css` 链接；`cinema.css` 末尾新增登录页专用段。实测 1440 宽卡片圆角 18px、390 宽 14px，输入框与按钮 10px，主按钮亮 `rgb(155,77,202)`、暗 `rgb(159,80,194)`，卡片阴影含紫色柔光（亮 `rgba(155,77,202,.5)`、暗 `rgba(179,102,214,.5)`），1440 与 390 宽 `documentElement.scrollWidth == clientWidth`，无横向溢出。
3. 行尾恢复：`app.js`、`cinema.css`、`overrides.css` 用「读字节 → 归一 CRLF → 写回」方式处理，未产生重复 `\r`；`index.html`、`login.html` 保持原 CRLF。返修后行数：`app.js` 4077、`cinema.css` 620、`overrides.css` 783、`index.html` 146、`login.html` 52，全部为纯 CRLF（无裸 LF、无裸 CR）。`build_demo.py` 以字节复制资产，`docs/assets/*` 随之与源文件逐字节一致；`docs/demo.html` 仍按既有行为为 LF。

### 验证命令与结果

```
for f in javsp_web/web/assets/*.js; do node --check "$f" || exit 1; done
node --test tests/*.cjs                        # 51 tests, 51 pass, 0 fail
node --test tests/test_film_detail_ux.cjs      # 实现前 0/10 通过，实现后 10/10 通过
python3 scripts/build_demo.py                  # Generated demo: demo.fd79430f7d93
cmp docs/assets/cinema.css javsp_web/web/assets/cinema.css        # 一致
cmp docs/assets/overrides.css javsp_web/web/assets/overrides.css   # 一致
cmp docs/assets/demo-app.js javsp_web/web/assets/app.js            # 一致
```

浏览器侧（无头 Chromium，经本地静态服务加载真实资产）：登录页 1440/390 宽 × 明暗两组读取计算样式与像素统计，确认圆角、强调色、紫色柔光与无横向溢出；评论帮助用等价标记加载 `theme.css`/`app.css`/`overrides.css`/`cinema.css`，在 390/800/900 宽与明暗两主题下读取 `summary`、分组线、`code` 与卡片计算样式。主代理此前的 Playwright 32 组页面检查与真实浏览器剧照交互结论未受本轮改动影响（本轮只动配色、按钮高度与登录页样式）。

### 基线说明

`/tmp/javsp-theme-20261022-baseline` 在实现会话中不存在（该会话的 `/tmp` 为每次命令重置的临时挂载）。第一轮按改动逆向重建了改动前完整副本并逐字节比对：

- `javsp_web/web/assets/{app.js,cinema.css,overrides.css}`：内容与 `HEAD` 完全一致（当时副本为 LF，与真实工作副本的 CRLF 仅行尾不同，已在第二轮统一恢复为 CRLF）。
- `javsp_web/web/index.html`：内容与 `HEAD` 仅差行尾（工作副本为 CRLF），已原样保留 CRLF。

重建基线、SHA-256 与增量补丁位于工作区的 `tmp/theme-refresh-baseline/`（`/tmp/` 已在 `.gitignore` 中）：`web/` 为改动前副本，`sha256.json` 为哈希，`increment.patch` 为第一轮增量（9 个 hunk）。全程未使用 `git reset`、`checkout`、`stash`，未提交、推送或部署。

### 遗留说明

- 演示站 `docs/demo-mock.js` 中任务的 `fanart_count` 均为 0，演示页无剧照缩略图；剧照查看层已在真实任务与合成 SVG 模拟图中验证，演示页需临时调大 mock 的 `fanart_count` 才能点到。

## 主代理最终审批（2026-10-22）

已独立比对本次真实工作副本基线，确认仅修改五个前端源文件及对应 demo 生成文件，并新增行为回归与方案/验收文档。五个源文件均保留 CRLF，原有元素 ID 无删除或重复，登录脚本逐字保持一致。返修后的 51 项 Node 测试、7 个 JavaScript 文件语法检查、demo 构建及三对生成资产字节一致检查通过。

浏览器独立复核共 42 组：8 页 × 2 种宽度 × 2 个主题（32 组），详情/评论/剧照 × 2 种宽度 × 2 个主题（4 组），登录页 × 3 种宽度 × 2 个主题（6 组）。页面无横向溢出或 JS 异常；剧照功能以合成 SVG 与模拟 404 验证，未读取真实媒体，未连接真实评论/媒体服务。上述范围审批通过，无待修阻塞项；未部署，不对现有运行实例宣称已更新。
