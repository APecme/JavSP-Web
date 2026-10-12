# bata.20261010195006 前端、更新与发布专项体检

> 路径约定：源码位置均相对于目标提交根目录；下文脚本、日志和 JSON 的交付副本统一位于 [evidence/](evidence/README.md)。原独立源码及运行环境保留在项目 `tmp/audit-bata-20261010195006/`。

## 审查边界与证据

- 唯一源码：`source/`，目标提交 `1e2d73bc180bf1b61ec83ed10df2fd6687acf275`。下列源码位置均相对于该隔离源码目录，不能用当前工作分支行号替代。
- 目标镜像内版本标签 `bata.20261010195006` 是发布流水线采用北京时间生成的标签字符串。对应 GitHub run `38049788026` 成功，生成标签步骤 `2026-10-10T11:50:06Z`（北京时间 2026-10-10 19:50:06），发布证据由主报告 `github-jobs.json` 承载。
- 没有读取用户现有 data，没有执行真实应用更新、发布、Docker 重建或文件整理。自建实验均为临时目录、mock 进程、mock 网络，无真实网络副作用。
- 原有 Node 检查三套全部通过：`test_web_client.cjs`、`test_scan_client.cjs`、`test_mount_batch_client.cjs`。本机 Node 24.13.0，原流水线 Node 22，版本差异需保留在报告中。日志：`node-tests.log`。
- 生产 JS 三文件通过 `node --check`。另执行了独立故障探针：`probe_frontend_release.py`（Python 3.12.14 隔离 venv）、`probe_frontend.cjs`；日志分别为 `frontend-release-probes.log`、`frontend-probes.log`。
- Node 原有检查使用 VM 截取函数，未启动浏览器，不构成点击链路、浏览器兼容性、视觉布局、无障碍或移动端验收。本专项未实际启动生产容器。

## 功能适配复核与分类

2026-10-11 复核后，本专项为 **4 项功能缺陷（FR-01/02/06/07）、1 项条件性恢复风险（FR-03）、2 项构建边界/元数据观察（FR-04/05）**。FR-01/02 对应官方 Docker 更新流程，FR-06/07 对应现有界面操作；FR-03 要求更新期间异常中断。目标 README 引导直接使用已构建官方镜像，未承诺不带 release 参数的源码构建流程；官方 beta 标签也不受包版本漂移影响。完整依据见[功能适配复核说明](功能适配复核说明.md)。下文保留原探针与源码证据，分类调整不代表已修复。

## 逐项发现

### FR-01 / 功能缺陷 / P1：更新期间未禁止新任务，更新线程可直接终止刚开始的工作

**位置**：`javsp_web/updater.py:183`，`javsp_web/updater.py:85`，`javsp_web/app_update.py:131–136`。所有源码中对 `ensure_not_updating` 的检索只有函数定义，无调用。

**触发**：发起更新时无活动任务，随后在版本查询、下载和校验期间，另一个页面、账号、定时规则或 AI 确认操作创建了任务。`apply()` 只在最初检查一次 `active_tasks()`；`schedule()` 在安装后等待两秒，直接 `os._exit(75)`。

**证据**：探针对 `apply()` 记录到仅一次活动任务检查；mock `active_tasks=True` 后执行生产 `schedule()` 的 worker，活动任务检查调用数仍为 0，且调用 `_exit(75)`。前端 overlay 仅限制启动更新的那个页面，无法替代服务端互斥。

**影响**：新刮削/扫描/图片任务可能在处理文件或写状态时被进程立即中止。任务恢复机制可以标记中断，但不能据此保证正在执行的文件操作具有原子性；这里已证明“并行工作会被终止”，没有声称已观察到用户文件损坏。

**建议**：把“进入维护模式”与“接受任务”放入同一互斥机制；任务创建、扫描、重试图片、定时触发和 AI 确认入口统一检查；更新下载完成后再次检查/排空工作，使用可控关闭流程。追加并发更新/创建任务集成测试。

### FR-02 / 功能缺陷 / P1：手动升级镜像后仍可能运行持久化的旧应用代码

**位置**：`javsp_web/app_supervisor.py:85–100`、`javsp_web/app_supervisor.py:41`，文档承诺 `README.md:85–87`。

**触发**：曾经网页更新，data 中存在 `updates/app-current.json` 和旧应用目录；之后按文档拉取新镜像并复用原 data。新旧镜像 `Dockerfile` 和 `requirements.txt` 内容不变。

**原因**：启动总是优先读取持久化 `current`，只校验目录、Dockerfile 和依赖文件，不比较镜像内 `JAVSP_WEB_RELEASE_LABEL` / commit 与已保存应用的版本。还把子进程环境重新覆盖为旧 label、旧 commit。

**证据**：输入新镜像标签 `bata.20261010195006` 与保存的旧标签 `bata.20260924044117`，生产 `run()` 实际传给 Popen 的 cwd 与 release label 均为旧包，探针断言通过。

**影响**：镜像拉取成功不代表应用升级生效，修复或安全更新可能仍未启用；旧 beta overlay 也可能在手动换正式镜像后继续接管（满足相同文件校验条件时）。

**建议**：持久化记录绑定基础镜像 identity；检测基础镜像改变后按明确策略选用新镜像/迁移 overlay，并在状态页同时显示基础镜像版本和实际运行应用版本。测试“旧 overlay + 更新镜像 + 同一 data 卷”。

### FR-03 / 条件风险 / P2：下载阶段容器中断后，更新状态可永久卡在执行中

**分类依据**：文档提供安装失败回退机制，但没有承诺任意下载阶段断电后自动续传；本项需先发生进程/容器异常中断。状态阻止再次更新的证据成立，列为异常恢复风险，不能用它否定正常安装失败回退路径。

**位置**：`javsp_web/updater.py:81–82`、`177–180`、`203–206`；`javsp_web/app_supervisor.py:116–119`；`javsp_web/app_update.py:131`。

**触发**：写入 `scheduled`/`downloading` 后、保存 pending 安装状态前，容器被重启、断电或进程异常终止。

**证据**：临时 job 写为 `downloading`，生产 supervisor 完整走过健康启动分支后 job 仍是 `downloading`，`updater.busy()` 为 true，再次 `apply()` 抛出“已有更新正在执行”。启动仅在 `state.pending` 存在时结束成功 job，没有重建已丢失的下载线程或标记 interrupted。

**影响**：自动检查和自动更新因 busy 永久跳过，手动更新也被拒；前端十五分钟后可关闭提示，但后端状态仍不会恢复。没有正常 UI 恢复入口，需要人工处理状态文件。

**建议**：启动时将没有可恢复 worker 的 ACTIVE job 转为 `interrupted`，记录失败阶段，允许用户重试；pending 状态由 supervisor 对账。添加崩溃点覆盖测试。

### FR-04 / 构建边界观察：不传 release build args 的 Docker 自建镜像会被健康监护误杀

**分类依据**：目标 README Docker/Compose 使用 `apecme/javsp-web:latest`，并说明无需本地构建；官方流水线会注入版本参数。本项不属于目标 beta 官方镜像启动缺陷，不再列 P2 发布阻断项。若将无参数源码构建纳入支持范围，则应修正默认值并增加相应构建验收。

**位置**：`Dockerfile:3–6`，`javsp_web/app_supervisor.py:100–115`，`javsp_web/server.py:99–101`、`463–465`。

**触发**：直接 `docker build` 使用 Dockerfile 默认的空 `JAVSP_WEB_RELEASE_LABEL`，且没有已安装 overlay。该问题不适用于已正常注入目标 beta label 的官方镜像。

**证据**：`run()` 给健康检查的 expected 为 `''`，服务 `/api/public-info` 按生产逻辑回退到 `__version__='1.1.38'`；探针模拟连续 45 次 HTTP 200 且正确返回 1.1.38，`health_ready()` 仍返回 false。实际 run 会终止子进程并返回 1。

**影响**：自建容器短暂正常响应后退出，配合 restart 策略可反复重启。现有 CI 只测试注入 label 的镜像，因此覆盖不到此场景。

**建议**：supervisor 与 server 共用版本解析逻辑，空 label 回退包版本；加无 build args 的持久在线 smoke 测试。

### FR-05 / 元数据观察：版本来源发生漂移，源码/EXE 与版本文件不一致

**分类依据**：目标官方 beta 以 release label 显示正确的 `bata.20261010195006`；产品语义版本、渠道标签本就可以不同。本项证据仅证明 `VERSION` 与包内 semver 不一致，应统一来源，但不能据此声称 beta 代码未升级或某个发布 EXE 错版，不再单列目标 beta 功能缺陷优先级。

**位置**：`VERSION:1` 为 1.1.39，`javsp_web/__init__.py:3` 为 1.1.38；`javsp_web/server.py:87` 与 `459–460` 使用后者。`formal-release.yml:50–55` 直接打包，没有按 tag 生成版本或检查一致性。

**影响/范围**：目标 beta 的用户可见 release label 仍能正确显示 bata.20261010195006，但 `/health`、OpenAPI version 以及运行时 app_version 来源是 1.1.38；由当前源码构建的 EXE/普通 Python 部署也会报 1.1.38。不能据此声称某个已发布正式 EXE 一定如此，本次没有下载该 EXE。

**建议**：单一版本源；构建时生成 metadata，CI 验证 tag、VERSION、包版本和产物版本。区分产品 semver、渠道标签、commit 和基础镜像 digest。

### FR-06 / 功能缺陷 / P3：已确认是最新 beta 的顶栏仍显示“无法比较”

**位置**：`javsp_web/web/assets/app.js:973–1008`。

**证据**：给 `checkForAppUpdate()` 输入 runtime.version=bata.20261010195006，更新结果 target 同版本、available=false、checked_at 已设置，函数仍用仅支持三段 semver 的比较器比较 1.1.38 与 bata 字符串，最终写入 `data-update-status=unknown`，title 为“当前部署版本无法与 GitHub Release 标签比较”。实际更新源是 Docker registry，不是该提示中的 GitHub Releases。

**影响**：目标版管理员顶部得到错误/过时的检查说明；系统设置详情页仍能显示正确结果，更新安装本身不由此受阻。

**建议**：以服务端 available、error、checked_at 和 current/target 为准，支持渠道标签，移除不准确的更新源说明。

### FR-07 / 功能缺陷 / P3：下载筛选重置按钮重复绑定且只响应一次

**位置**：`javsp_web/web/assets/app.js:2161–2167`、`2213`。

**证据**：每次成功加载下载列表调用 `ensureDownloadFilters()`，普通控件有 dataset.bound 防护，但 reset 按钮每次注册一个新 `{once:true}` 回调。探针调用 12 次后收到 12 个不同重置回调。

**影响**：长时间不点击会累积回调；一次点击重复渲染多次；两次点击之间若没有新的成功轮询，第二次不再重置。规模较小的性能与体验问题。

**建议**：为 reset 按钮仅绑定一次常驻监听，增加连续两次重置的 UI/DOM 测试。

## 发布工程与供应链：已观察事实和待验证风险

| 项目 | 证据与判断 | 建议 |
|---|---|---|
| beta 发布门禁 | `release.yml:24–28,53–67` 含 Node、Python、容器启动与 HTTPS 检查；目标 run 成功。属于积极控制。 | 保留，并加入更新状态机、恢复与长期启动检查。 |
| 正式版门禁不对等 | `formal-release.yml:19–40,46–62` 没有上述测试，直接构建并发布 Docker/EXE。是当前仓库正式发布流程的缺口，不是声称本次 beta 未测试。 | 复用同一验证 workflow，通过后发布两种产物。 |
| 无可复现依赖清单 | `requirements.txt:1–24` 全为范围约束，`slimeface`、`tzdata` 无上界；Dockerfile:1 的基础镜像无 digest，apt 包无锁定；顶层未使用 vendor 的 poetry.lock。无法从源码精确还原已发布镜像的完整依赖。 | 发布 lock + hashes、基础镜像 digest、SBOM；在 CI 对实际 resolved 依赖做漏洞与许可证核查。这里没有运行 CVE/SBOM 扫描，不报告未经核实的具体 CVE。 |
| 第三方 CI action 未固定 commit | checkout@v4、build-push-action@v6 等使用可变 major tag。属于供应链完整性风险，不是已发现被篡改。 | 固定完整 SHA 并用依赖机器人更新。 |
| beta 历史版本可寻址性不足 | `release.yml:42–43` 仅推送 `:bata`，时间字符串作为环境标签嵌入，没有推送 `:bata.20261010195006`。 | 同时发布 immutable 时间标签与 digest，保留发布元数据；报告定位不能把嵌入版本误写成 Docker Hub 已有同名 tag。 |
| 并行发布时序 | beta workflow 没有 concurrency；多个 main push 可以并行，较旧 run 若更晚完成可覆盖 mutable bata。仅证明缺少协调，没有观察到此次发生倒退。 | 发布前检查 head，序列化发布或使用受控 promotion。 |
| 架构 | workflow 无 platforms 列表，在 ubuntu-latest 原生构建；配置未提供 ARM64 验收证据。 | 明确支持架构，有 ARM NAS 需求则构建并验证多架构。不要把没有证据的 ARM 支持写入产品报告。 |
| 测试候选与最终镜像 | beta 先 build load，再另一个 build push。存在同次构建缓存但未用经过测试的 digest 作不可变 promotion。 | 先生成单一 digest、测试该 digest 后加正式标签。 |
| 代码更新校验 | `app_update.py` 验 commit、Git blob、路径穿越、symlink、包/解包大小，并拒绝 Dockerfile/requirements 变化。积极控制；无 Docker socket。 | 保留，同时补状态恢复和维护互斥。 |
| 更新包留存 | stage 以版本目录永久保存，源码未看到清理策略。大量自动更新后持久化空间可增长；未实测长时间空间耗尽。 | 明确保留当前/前一版及有限历史，安全清理未引用旧包。 |

## 前端质量与文档一致性

已见的良好设计：共享并发 GET、防超时、任务 ETag 缓存上限、任务分页、任务列表差量 DOM patch、后台页面暂停主任务轮询、错误重试退避、批量选择文件同批次提交、防重复提交、扫描卡片、可关闭失败 overlay 和重连提示。AI markdown 使用 DOM textContent，链接只允许 HTTP(S)，减少直接 HTML 注入风险；本专项没有完整安全审计证明。

遗留维护问题：`app.js` 共 3407 行，`taskCard` 定义 3 次（737/783/1867）、`progressMarkup` 3 次（772/793/806）、`renderTasks` 2 次（859/1906）、`renderOverview` 4 次（865/880/888/2041）、`renderPresetList` 2 次（1337/1351）。JS 实际只采用最后声明，容易维护/测试错对象；属于可维护性债务，未因此宣称现有功能全部失效。建议拆分模块并清理被覆盖实现，再用 lint 阻止重复声明。

官网版本显示也滞后：`docs/index.html:37` 为 v1.1.34，`docs/demo.html:31` 为 v1.1.31。官网 demo 有独立 app 副本，需明确仅演示用途并设同步策略。README 自更新说明与主要设计一致，但“拉取新镜像即可更新”和“失败自动恢复”的陈述尚未覆盖 FR-02/03 的具体边界。

无障碍正向迹象包括页面 viewport、部分 live status、overlay alertdialog 与 aria-modal；尚未人工验证键盘焦点圈定、Tab 不逃逸、读屏、对比度、不同缩放和小屏横向溢出。不能以静态 aria 属性视为无障碍达标。

## 建议处理顺序与验收

1. 首先修复 FR-01 的维护互斥、FR-02 的基础镜像/overlay 优先级；在隔离 Docker 环境验证“更新中创建任务”“更新镜像复用 data”。FR-03 单独纳入异常中断后的恢复演练。
2. 统一 FR-05 版本元数据；若确认支持无 release 参数自建镜像，再按 FR-04 补默认构建路径。相关持续运行验收需覆盖监护健康检查窗口，避免仅一次 /health=200 即判定正常。
3. 将正式版与 beta 门禁合并，提供可复现依赖与不可变产物索引，再进行平台支持和漏洞扫描。
4. 修复 FR-06/07，清理重复前端实现，补真实浏览器端到端、移动端和无障碍验收。现有三套 Node 用例通过证明其覆盖范围内的回归检查正常，不否定本报告的边界故障。
