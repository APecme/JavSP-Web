# 第 2 项：自更新后容器/设备重启回旧版（update-persistence）

## 0. 边界与本轮实际动作

- 只在独立副本 `/data12t/AutoOrder/JavSP-Web/tmp/oct23-work/update-persistence` 内改代码。未修改原仓库、未修改其他功能副本。
- 未运行任何 `docker`/`docker compose` 命令，未接触线上容器、真实 `data/`、真实更新源、真实用户媒体或评论。
- 未执行 git 提交/推送/部署，未构建 docs/demo。
- 测试不联网：GitHub/registry 调用全部 mock，端到端用例只用本机回环端口 + 标准库 HTTP 桩。
- 环境：系统 `python3` = Python 3.14.4，已装 `yaml/requests/pytest`；**不存在** `/tmp/javsp-bata-validation-venv/bin/python`（该路径在会话开始时即缺失，已按备选 `python3` 执行）。该环境**没有** `fastapi/uvicorn/Crypto/pydantic`，所以 17 个测试模块在基线副本里同样收集失败（见 §5 对照），端到端用例因此用标准库 HTTP 桩替代真实 server，未用真实 server。

## 1. 结论摘要（4 个真实缺陷，均先失败测试后修复）

| # | 缺陷 | 用户可见后果 | 修复位置 |
|---|---|---|---|
| D1 | 更新下载阶段进程/容器中断后，`job.json` 停在 `scheduled/downloading/restarting`，没有任何活着的 worker；`updater.busy()` 永久为真 | UI 一直「正在更新」，手动更新被「已有更新正在执行」拒绝，自动更新也被 `busy()` 永久跳过 | `app_supervisor.py:190 reconcile_job()` + `:241` 每次启动/子进程退出后对账 |
| D2 | 子进程记录基础镜像身份时回落到 `JAVSP_WEB_RELEASE_LABEL`。当启动器是旧版（不传 `JAVSP_WEB_BASE_RELEASE_*`）且子进程正跑在 overlay 上时，overlay 版本被记成「基础镜像」 | 下次启动读到「镜像变了」，把已安装的新版本静默丢弃 → **重启回旧版** | `app_supervisor.py:48 image_identity()`（子进程侧不再无条件回落）、`:90 base_identity()`、`:113 reconcile_image_state()`（未知绑定分支） |
| D3 | `data/updates/apps/<label>` 损坏/半写时，`stage()` 早退直接 `root_for()` 抛错；`root_for` 还漏出 `FileNotFoundError` | 该版本永远装不上（「更新文件不完整」直接裸 OSError），损坏目录既不清理也不重下 → 只能人工删 data | `app_update.py:88 _remove_version_dir()`、`:95 staged_version_usable()`、`:103 stage()`、`app_supervisor.py:159 root_for()` |
| D4 | 当前版本目录损坏时，启动器清空 `current` 并直接跳回镜像自带版本，即使磁盘上还有完整的上一版本 | 一次磁盘损坏就让用户退回镜像版本，丢掉可用的上一版 | `app_supervisor.py:248`（先尝试 `previous`） |

附带加固（同一需求内、非行为倒退）：

- `save_state()` 改为唯一临时名 + `os.replace`：启动器与子更新线程会并发写 `app-current.json`，原来的固定 `.tmp` 名在并发下有互相覆盖/交错写窗口（`app_supervisor.py:34`）。
- `updater.status()` 增加 `base` / `selected` / `pending`，让「基础镜像 / 已选应用 / 检查目标」三者可区分（`updater.py:169-176`）。纯增量字段，不改 `server.py`、不改 UI。
- `stage()` 遇到 `apps/<label>` 是符号链接时不再跟随（防被种入的链接把校验/启动引到 `apps/` 之外）。

## 2. 复现与证据（修复前实测）

修复前用探针（现已删除的 `.probe/`）在同一进程内复现，均无网络副作用：

- **D1**：稳定态（`base-image.json` 已记录）把 `job.json` 写成 `downloading` 后重启一次：
  `job after restart: downloading`，`busy(): True`，`updater.apply()` → `已有更新正在执行`。
- **D2**：模拟旧启动器（子进程无 `JAVSP_WEB_BASE_RELEASE_*`，`JAVSP_WEB_RELEASE_LABEL=<overlay>`）执行 `install()`：
  记录为 `base_image.label = bata.20260924044117`（即 overlay 版本）；下一次启动 `cwd = <base>`，`state.current = null` → 新版本被丢弃。
- **D3**：`apps/<label>/javsp_web/server.py` 半写后 `install()` 抛 `FileNotFoundError: .../Dockerfile`，再次 `install()` 仍同样失败（该版本永久不可再安装）。
- **D4**：`current` 目录缺文件 → 直接回镜像版本，且 `previous` 一起被清空。

对应失败测试（先写、先看到失败，再实现）：

- `tests/test_update_persistence.py`（14 个）
- `tests/test_update_restart_e2e.py`（4 个，真实进程）
- 追加验证：把 `reconcile_job(state)` 调用临时注掉后，`test_restart_after_a_crashed_download_leaves_updates_usable` 失败（`'downloading' != 'interrupted'`），恢复后通过；证明该端到端用例确实能测出 D1。

## 3. 精确修改文件

生产代码（3 个文件，均无整文件重排，保留原行尾：`updater.py` 仍是 CRLF）：

- `javsp_web/app_supervisor.py`
  - `:34 save_state()` 原子唯一临时名
  - `:48 image_identity()` 子进程侧仅用 `JAVSP_WEB_BASE_RELEASE_*`；仅在「自身 label ≠ 数据卷已选 current」时才允许把自身 label 当作镜像身份（旧启动器兼容），父进程侧保留 `__version__` 兜底
  - `:81 recorded_image()` 新增：读 `base-image.json`，回退 `app-current.json.base_image`
  - `:90 base_identity()` 新增：子进程可用的「基础镜像身份」（含数据卷记录兜底）
  - `:113 reconcile_image_state()` 新增「已知记录但 label 为空」分支：构建文件哈希未变则保留用户所选版本并重绑；仍是「镜像替换优先」
  - `:159 root_for()` 缺失文件统一报 `ValueError('更新文件不完整')`（不再漏 OSError）
  - `:178 job_status()` / `:190 reconcile_job()` 新增：无活 worker 的 ACTIVE job 标记 `interrupted`（`pending` 未决时交给健康检查）
  - `:241` 循环顶部调用 `reconcile_job(state)`
  - `:248` 当前版本文件损坏时优先回退 `previous`，失败才回镜像版本，并写清原因
- `javsp_web/app_update.py`
  - `:88 _remove_version_dir()`、`:95 staged_version_usable()` 新增
  - `:103 stage()`：符号链接清理；已存在但不可用的目录不再早退，而是在**验证通过的新副本就绪后**才替换（下载失败不会删掉旧副本）
  - `:146 install()` 记录 `base_image` 改用 `base_identity()`
- `javsp_web/updater.py`
  - `:17` 引入 `app_supervisor`
  - `:169-176 status()` 增加 `base` / `selected` / `pending`

测试（2 个新文件）：

- `tests/test_update_persistence.py`：崩溃恢复、父/子环境不一致、未知绑定、损坏目录重下、脏文件占位、`root_for` 错误类型、回滚目标持久、`status` 版本分层
- `tests/test_update_restart_e2e.py`：真实 supervisor 进程 + 真实子进程 + 真实 HTTP 健康检查，覆盖「两个独立启动周期」「拉取新镜像覆盖 overlay」「坏更新回滚并保持回滚」

未改动：`server.py`、UI/前端、`storage.py`（共享文件留给主代理三方整合）、`Dockerfile`、`docker-entrypoint.sh`（理由见 §6）。

## 4. 修复后的语义（逐条对齐验收）

- **两个独立启动周期使用更新后版本**：`test_two_independent_restart_cycles_run_the_installed_update`（真实进程 ×2，断言启动目录、`JAVSP_WEB_RELEASE_LABEL`、`base_image.label`、job=`updated`）。
- **基本镜像未变不回退**：同上 + `test_install_reuses_the_recorded_image_binding_without_base_metadata`。
- **失败才回滚**：`test_pending_install_is_left_for_the_health_check_to_settle`、`test_rolled_back_pending_install_reports_the_failure_reason`、`test_update_that_cannot_start_rolls_back_and_stays_back`（回滚后第二个周期仍是旧版，job 保留 `rolled_back` 与原因）。
- **损坏处理**：`test_corrupted_staged_version_is_downloaded_again`、`test_stray_file_occupying_a_version_name_is_replaced`、`test_incomplete_update_copy_is_reported_as_value_error`、`test_corrupted_current_version_rolls_back_to_the_previous_version`、`test_corrupted_current_version_rolls_back_to_base_and_stays`。
- **手动镜像替换优先**：`test_pulled_image_replaces_the_persisted_overlay`（真实进程）＋原有 `test_new_image_wins_even_when_saved_update_has_a_newer_version` 等。
- **依赖哈希/构建声明**：`image_identity().files_sha256` 覆盖 `Dockerfile` + `requirements.txt`；`root_for()` 每次启动仍逐字节复检，`stage()` 在安装时复检，未知绑定分支只在哈希一致时保留（`test_unknown_binding_is_discarded_when_the_image_build_files_change`）。
- **崩溃可恢复**：D1 修复后，中断的 job 变 `interrupted` 并带阶段说明，`apply()` 可再发起（`test_crashed_download_does_not_block_future_updates_forever`、e2e 版）。
- **状态原子**：`save_state()` 唯一临时名 + `os.replace`；`reconcile_image_state()` 的写入顺序保持「settings → job → state → base-image」，任一步崩溃下次启动可重入。
- **当前/基础/目标区分**：`status()` 返回 `current`（正在跑的应用版本）、`base.label`（镜像身份）、`selected`（启动器选定版本）、`result.target`（检查到的目标）、`pending`（已安装待验证）。

## 5. 测试命令与结果

```bash
cd /data12t/AutoOrder/JavSP-Web/tmp/oct23-work/update-persistence

# 单元（本功能 + 既有更新相关回归）
python3 -m pytest tests/test_update_persistence.py tests/test_app_update.py tests/test_updater.py -q
#   42 passed, 10 subtests passed in 1.24s

# 端到端（真实进程，约 48s）
python3 -m pytest tests/test_update_restart_e2e.py -q
#   4 passed in 47.76s

# 全量 Python（与基线副本逐条对比）
python3 -m pytest tests/ -q --continue-on-collection-errors
#   本副本：9 failed, 79 passed, 17 errors, 43 subtests passed
#   基线副本 ../baseline：9 failed, 61 passed, 17 errors, 43 subtests passed
#   FAILED 集合 diff 完全一致（IDENTICAL FAILURE SETS）
```

- 全量里 9 failed（`test_config_validation_messages.py` ×7、`test_organization_log.py` ×2）与 17 errors（缺 `Crypto/fastapi/pydantic` 等依赖）在**未改动的基线副本上完全相同**，属环境缺依赖，非本次改动引入。
- Node 回归：`for f in tests/*.cjs; do node "$f"; done` → 仅 `test_demo.cjs`、`test_theme_client.cjs` 失败，二者在基线副本同样失败（缺 README/docs 与构建资产），本次改动不涉及 JS。

## 6. Docker / 启动逻辑：为什么没改，以及一次性迁移限制

- 现状已正确：`docker-entrypoint.sh` 用 `exec python -m javsp_web.app_supervisor`，启动器就是 **PID 1**；`/app/data` 是卷，`data/updates/apps`、`app-current.json`、`base-image.json`、`job.json` 都在卷内；`Dockerfile` 把 `Dockerfile` 与 `requirements.txt` 一并放在 `/app`（`root_for`/哈希校验依赖它们）。因此本轮不需要改 `Dockerfile`/`docker-entrypoint.sh`，也不该改（改了会造成无谓的三方冲突）。
- **必须书面明确的限制（旧基础镜像 PID1 无法热更新）**：启动器来自镜像本身，网页自更新只能替换它启动的**子进程代码**。如果用户当前镜像里的 `app_supervisor.py` 是本轮修复之前的版本，那么无论安装多少次应用更新，重启后仍是旧启动器的判定逻辑，D2/D1 不会生效。这一类镜像需要**一次性手动更新镜像**（`docker compose pull` 或重建）后才进入新语义；此后应用热更新才真正可跨重启持久。UI 现有文案「当前镜像尚不支持网页安装更新；请先手动更新一次 Docker 镜像。」已经表达这层意思，本轮不改文案（避免与 UI 任务冲突），文档层面由主代理统一说明。
- 同理，**旧版更新器写下的记录**若跨渠道且没有 `base_image` 绑定（历史 legacy 记录），重启时仍按既有保守规则以镜像为准（会被丢弃一次）；用户重试一次更新后即写入绑定，此后跨重启保留。这是刻意保留的镜像优先级，不是本轮回退；已在 §7 列为已知迁移项。

## 7. 未解决项 / 需要主代理或用户知悉

1. **UI 尚未展示 `base`/`selected`/`pending`**：数据已就绪（`updater.status()`），但设置页展示归第 3/4 项（页面/导航）统一处理；本轮按要求没碰 UI。演示与文档构建也留给主代理。
2. **跨渠道 legacy 记录的一次性丢失**（§6 末）：无 `base_image` 且跨渠道的历史选择在重启时以镜像为准。修法需要产品决策（例如允许「先跑一次再验证」），本轮按既有测试约定保持不变。
3. **`data/updates/apps` 无保留策略**：每个版本目录永久留存（历史审计已指出）。本轮未加清理，避免误删「用户已选但暂未使用」的版本；建议后续单列「保留当前/上一版」策略并配套测试。
4. **`image_identity` 的文件哈希只覆盖 `Dockerfile` + `requirements.txt`**：同标签、同构建文件、仅代码不同的镜像无法与旧 overlay 区分（注释已写明「不是 Docker 镜像摘要」）。要彻底解决需要发布流水线注入不可变镜像 digest（属发布工程范畴）。
5. **端到端用标准库 HTTP 桩替代真实 `server.py`**：本机无 `fastapi/uvicorn`，真实 server 无法启动；桩只实现 `/api/public-info` 与「起不来」两种行为，健康检查、PID、状态文件、启动目录/环境变量均为真实路径。真实镜像内的启动冒烟建议在主代理集成后的容器验收里补一次。
6. **`reconcile_job` 的判定前提**：它只在「启动器启动时」和「子进程已退出后」执行，因此不会误杀仍在下载的线程；如果未来引入子进程以外的更新执行者，需要同步扩展这里的前提。
7. **`save_state` 的临时文件残留**：极端情况下（写入中途断电）`data/updates/app-current.json.<rand>.tmp` 会残留，无功能影响，未加清理。

## 8. 复现/自检入口

```bash
cd /data12t/AutoOrder/JavSP-Web/tmp/oct23-work/update-persistence
python3 -m pytest tests/test_update_persistence.py -q          # 缺陷级单测（14）
python3 -m pytest tests/test_update_restart_e2e.py -q          # 真实进程重启（4，约 48s）
python3 -m pytest tests/test_app_update.py tests/test_updater.py -q   # 既有回归（28）
```
