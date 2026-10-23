# A/B 分 P 与 `(1)` 重复副本收尾报告

日期：2026-10-23
执行：ds小弟3
状态：实现与联合回归完成，等待 6.1sol 独立审核；未部署、未改动运行实例。

## 1. 范围与结论

本项在**保留工作区既有实现、不重写**的前提下收尾，只处理三个授权点：

1. `Scheduler.stop()` 对线程未启动、已经结束、重复停止的边界处理，并补回归。
2. 副本跳过日志归属：只进入关联任务或扫描级日志，不再向所有任务重复追加；保留副本关联与原因，日志不含链接内容。
3. 联合回归与交付材料。

既有分 P／副本识别实现经只读核对与回归，未发现需要重写的缺陷。现有实现的原始作者未知，本报告不凭时间戳推定归属。

## 2. 本次实际修改清单

| 文件 | 位置 | 修改 |
|---|---|---|
| `javsp_web/directory_watch.py` | 1074-1088 `Scheduler.stop()` | 未启动线程（`ident is None`）和当前线程不 `join`；仅当 `_thread` 仍是同一对象时才清空引用，避免并发 `start()` 被误清。 |
| `javsp_web/tasks.py` | 1130-1152 | 单文件入口：副本提示保存为 `copy_message`，只追加到新建任务自己的日志。 |
| `javsp_web/tasks.py` | 1202-1250 | 目录/多选入口：跳过信息按“原文件路径”建立映射，仅追加到 `input_files` 含该原文件的任务；同时保留 `progress()` 的扫描级提示。 |
| `tests/test_directory_watch.py` | 561-589 | 新增 3 个调度器回归：未启动即停止、`Thread.start` 被替换导致创建未启动、线程已结束后停止及重复停止。 |
| `tests/test_multipart.py` | 163-192、272 | 新增 2 个任务日志归属回归；`create_web_tasks(path=None)` 支持单文件入口。 |
| `docs/reports/multipart-copy-20261023/README.md` | 本文件 | 交付材料。 |

未修改：`vendor/JavSP/javsp/multipart.py`、`vendor/JavSP/javsp/file.py`、`javsp_web/task_scans.py`、`tests/test_task_scans.py`、`.venv-multipart/`、行尾；未部署，未清理其他工作区改动。

## 3. 既有实现（只读复核，未重写）

- `vendor/JavSP/javsp/multipart.py`：字母分 P、`media_identity` 前后一致性、`inspect_download_copy`（BOM/换行规范化、链接不同不判重）、`_filter_download_copies` 在分组前过滤副本。
- `javsp_web/tasks.py`：本次收尾前已存在副本识别接入（单文件入口与扫描入口）。
- `javsp_web/directory_watch.py`：监控侧 `_copy_checks()` / `_duplicate_record()` 用 `inspect_download_copy` 判定副本，只在台账记录 `status=duplicate` 和原因，不提交副本，不持久化链接。
- `tests/test_multipart.py`、`tests/test_directory_watch.py`：既有分 P、副本、监控回归。

## 4. 测试证据

环境：`.venv-multipart/bin/python`（Python 3.14.7，未修改该 venv）。

### 4.1 联合回归（6.1sol 指定顺序）

```bash
.venv-multipart/bin/python -m pytest \
 tests/test_multipart.py \
 tests/test_task_scans.py \
 tests/test_directory_watch.py -q
```

结果：**87 passed, 2 skipped, 32 subtests passed**（24.00s）。

### 4.2 后两个文件反序

```bash
.venv-multipart/bin/python -m pytest \
 tests/test_multipart.py \
 tests/test_directory_watch.py \
 tests/test_task_scans.py -q
```

结果：**87 passed, 2 skipped, 32 subtests passed**（24.49s）。顺序污染已消失。

### 4.3 单文件单独运行

| 命令 | 结果 |
|---|---|
| `pytest tests/test_multipart.py -q` | 28 passed, 32 subtests passed |
| `pytest tests/test_task_scans.py -q` | 23 passed, 1 skipped |
| `pytest tests/test_directory_watch.py -q` | 36 passed, 1 skipped |

### 4.4 两个 skipped 的原因（不计为通过）

| 位置 | 原因 | 性质 |
|---|---|---|
| `tests/test_task_scans.py:235` | `@unittest.skipUnless(os.name == 'nt', 'Case-insensitive Windows paths')` | 平台前提：Linux 无法验证 Windows 大小写不敏感路径。 |
| `tests/test_directory_watch.py:366` | `@unittest.skipIf(geteuid() == 0, 'root ignores directory permissions')` | 运行用户为 root，无法用 `chmod 000` 制造权限失败。 |

### 4.5 更大范围回归

`.venv-multipart` 缺少 `uvicorn`、`lxml_html_clean`，因此：

- `tests/test_ai_translation.py`、`tests/test_scrape_logging.py` 无法收集（`lxml.html.clean` ImportError）；
- `tests/test_login_security.py::test_server_entrypoint_preserves_socket_peer` 因缺少 `uvicorn` 失败。

排除上述环境阻塞项后：

```bash
.venv-multipart/bin/python -m pytest tests -q \
 --ignore=tests/test_ai_translation.py \
 --ignore=tests/test_scrape_logging.py \
 --deselect tests/test_login_security.py::LoginSecurityTests::test_server_entrypoint_preserves_socket_peer
```

结果：**372 passed, 2 skipped, 1 deselected, 188 subtests passed**（108.16s）。以上失败／未收集均为 venv 依赖缺失，与本次改动无关。

### 4.6 原有调度器污染复现

修复前同进程运行：

```bash
pytest tests/test_multipart.py tests/test_task_scans.py tests/test_directory_watch.py -q
# 32 failed, 50 passed, 2 skipped
# RuntimeError: cannot join thread before it is started
# directory_watch.py: stop() -> thread.join()
```

根因：`tests/test_task_scans.py:43` 在 `patch('threading.Thread.start')` 上下文中导入 `javsp_web.server`，留下“已创建未启动”的全局调度线程；`stop()` 直接 `join` 抛错。修复点放在 `Scheduler.stop()`，未改测试导入方式。

## 5. 两组原例的实际任务输入与提示

使用真实临时目录、真实配置和 `tasks._prepare_tasks()`，输入：

- `SAVR-619-A.strm`、`SAVR-619-B.strm`（同链接）
- `hhd800.com@AVSA-223.strm`、`hhd800.com@AVSA-223(1).strm`（副本带 BOM + CRLF，链接一致）

实际输出（路径已按临时目录原样，未改内容）：

```json
[
  {
    "input_files": [".../hhd800.com@AVSA-223.strm"],
    "skip_messages": ["跳过重复副本：hhd800.com@AVSA-223(1).strm → hhd800.com@AVSA-223.strm"]
  },
  {
    "input_files": [".../SAVR-619-A.strm", ".../SAVR-619-B.strm"],
    "skip_messages": []
  }
]
```

即：A/B 合并为一个任务并按 A→B 排序；`(1)` 不进入任务清单、文件保留原处；跳过提示只出现在关联任务（该例还同时进入扫描级 `progress`）。

## 6. CLI／Web／监控调用链核对

| 入口 | 调用链 | 核对结果 |
|---|---|---|
| Web 手动扫描 | `POST /api/tasks` → `task_scans.submit_scan` → `run_scan` → `tasks._prepare_tasks(on_progress=progress)` | 副本提示进入扫描任务日志（`task["log_tail"]`，0.5s 节流）；任务日志只挂关联任务。 |
| Web 显式多选 | `create_tasks(..., input_files=[...])` → `_prepare_tasks` 显式清单 | 清单保持精确；`group_files` 仍做副本与分 P 校验。 |
| CLI | `javsp.file.scan_movies` → `group_files` + `part_number` | 与 Web 共用 `javsp.multipart`；副本在分组前过滤，日志只记文件名与原因，不含链接。 |
| 目录监控 | `_walk` → `_copy_checks` / `_duplicate_record` → `_submit` → `tasks.create_tasks(input_files=originals)` | 监控先判定副本并写台账 `status=duplicate`、`reason`；副本不进入提交清单。台账保存内容哈希用于判断副本是否变化，不保存链接。 |

三条路径均使用同一套 `inspect_download_copy`／`group_files`／`part_number` 规则；不同目录不合并的逻辑保持不变。

## 7. 未覆盖项与风险

1. **既有实现作者未知**：本项只在其上收尾，仍需 6.1sol 检查完整差异并复跑关键测试。
2. **未部署**：未修改运行实例、未重建镜像、未验证容器/设备重启持久性。
3. **扫描级日志节流**：`run_scan.progress` 每 0.5s 最多记一条；大批量副本时扫描日志可能少记个别提示，但关联任务日志逐条保留。
4. **调度器其余并发边界未扩展**：`stop()` 设置 `_stop` 后若并发 `start()` 清事件，仍存在既有竞态；本次只修 join 边界与引用清理。从调度线程内部调用 `stop()` 会跳过 join 并立即返回，线程在下一轮循环退出。
5. **单文件入口**：仅当副本能确认原文件存在且链接一致时改指向原文件；原文件低于最小大小时不建任务并报错，提示只留在扫描进度。
6. **路径映射**：任务日志归属使用 `realpath` 规范化，虚拟挂载不支持时回退 `abspath`；与既有去重逻辑一致。
7. **平台与权限测试**：Windows 大小写、非 root 权限两项 skipped，未在对应平台验证。
8. **未跑前端 JS 测试**：本项未改前端，但联合回归只覆盖 Python 侧。
9. **范围外文档**：热片／下片留空与侧边栏重做不在本报告范围。

## 8. 第二轮收尾（GPT组长退回的两个阻塞项，2026-10-23 13:10）

上节 3、4 条已被本节取代：扫描级提示不再依赖 0.5s 节流，调度器超时停止后也不再丢引用。

### 8.1 本轮实际修改清单

| 文件 | 位置 | 修改 |
|---|---|---|
| `javsp_web/directory_watch.py` | 1094-1191 `Scheduler` | 新增 `_restart_requested`。`stop(timeout)` 在旧线程仍存活时保留 `_thread`；`start()` 遇到“停止中但还活着的线程”只置重启意向，由原线程在退出点自清 `_stop` 继续轮询，不再创建第二个线程。`running` 同时要求线程已启动、存活且未收到停止请求。`stop()` 仍安全处理未启动、已结束、重复停止与线程内部停止。 |
| `javsp_web/directory_watch.py` | 611-635、774-792、954-978、1065-1080 | 新增 `_copy_skip_messages()` / `_duplicate_summary()`：本轮新确认的副本在规则 `status.message` 中提示一次；后续轮询不重复，副本内容变化后重新评估。台账继续保留 `status=duplicate`、`original`、`reason`、内容哈希；提示只含文件名。 |
| `javsp_web/tasks.py` | 1093-1120、1222-1249 | `_prepare_tasks()` 新增可选 `on_message`（默认 None，兼容既有调用）。显式清单不再可能把未选择的原文件拉进任务；仅选已确认副本时抛 `NoScrapeTasksError("已跳过重复副本，无可处理文件：副本 → 原文件")`；混合清单继续处理有效影片，副本提示只进扫描级通道，不挂到无关任务。 |
| `javsp_web/task_scans.py` | 82-99 | `run_scan()` 新增 `scan_message()`：扫描级副本提示绕过 0.5s 节流写入扫描任务日志，重复内容不重复追加。 |
| `tests/test_directory_watch.py` | 275-303、615-683 | 副本提示可见一次且不含链接、基线阶段也提示；调度器超时停止后复用同一线程、正常退出后重启、线程内部停止 3 项回归。 |
| `tests/test_multipart.py` | 272-298 | `create_web_tasks(selected=...)` 支持显式清单；仅选副本时不误报大小、不自动加入原文件、提示不含链接。 |
| `tests/test_task_scans.py` | 61-67、215-241 | 新增 `streams()` 夹具；Web 扫描入口“仅副本清单”与“副本＋无关影片混合清单”的端到端回归。 |

未修改：`vendor/JavSP/javsp/multipart.py`、`vendor/JavSP/javsp/file.py`、`.venv-multipart/`、行尾；未部署，未清理或覆盖其他人的改动。

### 8.2 测试结果

GPT组长指定顺序：

```bash
.venv-multipart/bin/python -m pytest \
  tests/test_multipart.py tests/test_task_scans.py tests/test_directory_watch.py -q
# 95 passed, 2 skipped, 32 subtests passed (25.35s)
```

后两个反序（`multipart → directory_watch → task_scans`）：**95 passed, 2 skipped, 32 subtests passed（25.07s）**。

单文件：multipart **29 passed + 32 subtests**；task_scans **25 passed, 1 skipped**；directory_watch **41 passed, 1 skipped**。

两个 skipped 与上节相同，均不计为通过：Windows 大小写路径（Linux 无法运行）、非 root 权限失败（当前为 root）。

更大范围（排除 venv 缺依赖导致的 2 个模块不可收集和 1 个 uvicorn 入口测试）：

```bash
.venv-multipart/bin/python -m pytest tests -q \
 --ignore=tests/test_ai_translation.py --ignore=tests/test_scrape_logging.py \
 --deselect tests/test_login_security.py::LoginSecurityTests::test_server_entrypoint_preserves_socket_peer
# 380 passed, 2 skipped, 1 deselected, 188 subtests passed (112.05s)
```

### 8.3 两组原例（本轮实测）

| 输入 | 任务 `input_files` | 提示 |
|---|---|---|
| `SAVR-619-A.strm` + `SAVR-619-B.strm` | `["SAVR-619-A.strm", "SAVR-619-B.strm"]`（A→B 排序） | 无副本提示 |
| `hhd800.com@AVSA-223.strm` + `hhd800.com@AVSA-223(1).strm`（BOM+CRLF，链接一致） | `["hhd800.com@AVSA-223.strm"]` | `跳过重复副本：hhd800.com@AVSA-223(1).strm → hhd800.com@AVSA-223.strm` |
| 只选 `hhd800.com@AVSA-223(1).strm` | 不建任务 | `NoScrapeTasksError: 已跳过重复副本，无可处理文件：hhd800.com@AVSA-223(1).strm → hhd800.com@AVSA-223.strm` |

### 8.4 调用链核对（本轮变更后）

| 入口 | 结果 |
|---|---|
| Web 手动扫描 / 多选 | `run_scan` → `_prepare_tasks(on_message=scan_message)`：副本提示必达扫描任务 `log_tail`；关联任务的提示仍只追加到对应任务。 |
| Web 单文件 | 未改：副本改指向原文件并把提示写进新任务自己的日志。 |
| CLI | 未改：`javsp.file.scan_movies` → `group_files` / `part_number`，与 Web 共用规则，日志只含文件名。 |
| 目录监控 | 副本不进候选清单，台账保留关联/原因；本轮新增规则卡片 `status.message` 的一次性提示，重复轮询不刷屏。 |

### 8.5 未覆盖项与风险

1. 未部署、未重启运行实例，未验证容器/设备重启持久性。
2. 目录监控提示只在“本轮新确认副本”时出现；下一次扫描的通用摘要会覆盖 `last_message`，台账与界面规则行不长期保留该句（副本关联仍持久化在 `committed`）。
3. `Scheduler.start()` 在“旧线程仍未退出”时只置重启意向；若旧线程卡死在扫描 I/O，重启意向要等该轮扫描结束后才生效（不会创建第二个线程，但也不会立刻恢复轮询）。
4. `stop()` 的返回值仍为 `None`（兼容既有调用与测试）；需要判断是否真正停止时使用 `running` / `_thread`。
5. Windows 大小写、非 root 权限两项 skipped；未跑前端 JS 测试；前端 `directory-watch.js` 直接渲染 `status.message`，无需改动。
6. 现有实现作者仍记为未知；本轮只在其上做授权范围内的最小修改。

## 9. 第三轮收尾（最后停止撤销重启意向，2026-10-23）

### 9.1 缺陷与修复

GPT组长 独立复核复现：阻塞 `run_due()` 时执行 `stop(timeout=0) → start() → stop(timeout=0)`，第二次 `stop()` 未清除 `start()` 置位的 `_restart_requested`，释放阻塞后旧线程带着重启意向继续轮询，最后发生的停止未生效。

修复（`javsp_web/directory_watch.py` `stop()`，约 1125-1131）：在生命周期锁内、`self._stop.set()` 之前置 `self._restart_requested = False`。语义为"最后发生的停止覆盖此前重启意向"；worker 到达 `_run()` 出口时看到 `_restart_requested=False` 即真正退出。对 worker 内部自停路径同样生效；`_restart_requested` 机制其余部分、join 超时路径、行尾均未改动。

### 9.2 回归测试

`tests/test_directory_watch.py` 新增 `test_scheduler_final_stop_cancels_pending_restart`：阻塞 `run_due()`（Event 卡住首轮扫描）→ `stop(timeout=0) → start() → stop(timeout=0)` → 释放阻塞，断言：

- 旧线程 `join(2)` 后 `is_alive() == False`（真正退出，不只是引用清除）
- `running == False`
- 释放阻塞后 0.5s 内 `run_due` 调用次数不再增长（复现并锁死 GPT组长 观察到的继续轮询场景）
- 无第二 `directory-watch` 存活线程；完全退出后再次 `start()` 创建新线程并可正常 `stop`

### 9.3 测试结果

单文件：`.venv-multipart/bin/python -m pytest tests/test_directory_watch.py -q` → **42 passed, 1 skipped**。

联合正序：

```bash
.venv-multipart/bin/python -m pytest \
  tests/test_multipart.py tests/test_task_scans.py tests/test_directory_watch.py -q
# 96 passed, 2 skipped, 32 subtests passed (27.65s)
```

联合反序（`multipart → directory_watch → task_scans`）：**96 passed, 2 skipped, 32 subtests passed（28.13s）**。

两个 skipped 与上节相同（Windows 大小写、非 root 权限），不计为通过；各有一条 Starlette 弃用警告，与既有基线一致，非本轮引入。

### 9.4 `running` 语义说明

### 9.5 KIMI3新兵 方案下的 GLM新兵 实施与独立复核记录（2026-10-23）

实施由 GLM新兵 按 KIMI3新兵 方案完成（方案与代码现状一致：`stop()` 在生命周期锁内先清 `_restart_requested` 再 `_stop.set()`；9.2 回归已并入）。GLM新兵 独立复跑（未改共享 venv、未部署、无并发编辑）：

- 单文件 `tests/test_directory_watch.py -q` → **42 passed, 1 skipped, 27.43s**
- 联合正序（multipart → task_scans → directory_watch）→ **96 passed, 2 skipped, 32 subtests passed, 29.24s**
- 联合反序（directory_watch → task_scans → multipart）→ **96 passed, 2 skipped, 32 subtests passed, 34.88s**

skipped 仍为 Windows 大小写与非 root 权限两项，不计为通过；各一条 Starlette 弃用警告，与基线一致。

`running == False` 表示调度器已收到停止请求或线程已退出，**不代表 worker 线程已实际结束**：`stop(timeout=0)` 后线程可能仍阻塞在扫描 I/O 中，此时 `running` 已为 `False` 但 `worker_alive` 仍为真。需要判断线程是否真正退出时，应检查线程 `is_alive()`（或 `join`）。此为本项遗留的非阻塞语义风险，已在 8.5 第 3 条基础上明确。

