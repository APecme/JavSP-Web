# 本机 javsp-web 重启记录（2026-10-23 16:03–16:07）

目标：让运行中的 `apps/1.1.42` 子进程真正加载新代码，使 GLM 的分 P 容错改动
（`vendor/JavSP/javsp/multipart.py:181` `group_files_skipping_conflicts`、
`javsp_web/tasks.py:1215-1245`）生效。此前这些文件只是落盘（mtime 15:09:40），
14:22 启动的子进程仍是旧模块。

## 前置事实（重启前核对）

- `apps/1.1.42/javsp_web`、`apps/1.1.42/scripts` 与工作区 `diff -rq` 返回 0；
  `vendor/JavSP/javsp` 仅差 `__pycache__`。
- 关键文件 sha256 三方一致（overlay / 工作区）：
  - `tasks.py` `0548f1b5d92955330337d1621ed2b0f6281d37c24bcb8611a4504bdca8e3501b`
  - `multipart.py` `8ea35e53c9a953fca1c8cb6de11f460f02b12755a47769de8c0606f61544ac85`
- `apps/bata.20261023090847` 与 `apps/1.1.42` 整树 `diff -rq` 返回 0（仅 `__pycache__` 无关），
  因此切通道过程中的中间态也跑同一份代码。

## 可用手段与两条死路

唯一能让子进程重启的通道是 `app_supervisor`：子进程退出码 75 → supervisor 重新拉起。
产生 75 的唯一代码路径是 `app_update.schedule()`（`javsp_web/app_update.py:160`），
它只在 `updater.apply()` 成功后被调用。

1. **改 `app-current.json` 无效**：`updater.current_version()` 读的是环境变量
   `JAVSP_WEB_RELEASE_LABEL`（进程启动时冻结），不读状态文件。16:00 前后的第一版
   脚本（伪造 `current=bata.…`）因此完全没触发检查，已作废并回滚状态文件。
2. **人工触发也受拦**：`updater.apply()` 在 `active_tasks()`（DB 中 `queued`/`running`
   任务）非空时直接拒绝；当时队列有 1 跑 + 8 排队，且本沙箱无 API 凭据、无 docker、
   无宿主 PID 命名空间，无法取消任务或发信号。只能等队列排空（15:57:48 清空）。

结论：沿用 14:21/14:22 的老办法——真实切换更新通道触发 75。

## 执行时序（CST）

| 时间 | 事件 |
|---|---|
| 15:52:47 | 备份状态文件；清掉 15:13:46 被置为 true 的 `experience_program`/`auto_update`（否则任务一清空就会自动切到 bata 标签） |
| 15:57:48 | 活跃刮削任务清空（8 个任务逐个跑完） |
| 16:03:46 | 阶段 A 开始：`experience_program=true, auto_update=true` |
| 16:04:50 | 阶段 A 更新作业启动 → 子进程 `os._exit(75)` → supervisor 拉起新子进程，`/api/public-info` 版本变为 `bata.20261023090847`（新进程实测） |
| 16:06:04 | 阶段 B 更新作业启动 → 再次重启，版本回到 `1.1.42` |
| 16:07:07 | 新子进程首个调度器 tick 重写 `updates/check.json`（`current=1.1.42, available=false`） |
| 16:07:1x | 设置复原：`experience_program=false, auto_update=false` |

脚本：`docs/reports/multipart-copy-20261023/restart-20261023.py`；
日志与结果：`data/updates/backup-20261023-160346-restart/{restart.log,result.json}`。

## 重启后状态（线上实测）

- `GET /api/public-info` → `{"name":"JavSP WEB","version":"1.1.42"}`；`/` 200、`/assets/theme.js` 200。
- `app-current.json`：`current=1.1.42`、`commit=f031065…`、`previous=bata.20261023090847`、
  `previous_commit=42d8961…`、`pending=false`、`base_image.label=1.1.41`（与重启前逐字段一致）。
- `update-settings.json`：`check_enabled=true, auto_update=false, experience_program=false,
  check_interval_hours=24`。
- `check.json` 时间戳 16:07:07 由新进程写入，证明是重新拉起的解释器在服务，而非旧进程。
- 代码生效证据链：文件 mtime 15:09:40 → 进程 16:06:04 启动 → overlay 与工作区逐字节一致
  ⇒ 运行进程加载的就是分 P 容错版本。

## 风险与遗留

1. 两次重启清空了内存会话，浏览器需重新登录；16:06 前后正在进行的请求会失败
   （当时队列已空，无刮削任务受影响）。
2. `15:13:46` 有人把 `experience_program` 与 `auto_update` 同时置 true，那会让实例在队列
   清空后自动切到 bata 标签；本次已清除并按 14:22 记录复原成 false/false。若这是有意的
   配置变更，需要再改回去。
3. 代码本身仍待 GPT组长独立验收（本记录只证明“已上线并生效”，不代表审批通过）。
4. 镜像仍是 `v1.1.41`，未重建；容器/设备重启后的版本保持仍未做真实验证。
5. 未做登录态业务回归：分 P 歧义目录是否真的“跳过并继续其余影片”，需有凭据的人实测一次。

## 回滚

```bash
# 1) 代码回滚：把 backup-20261023-141751-deploy/apps-1.1.42-pre 覆盖回 apps/1.1.42
# 2) 状态回滚：把 backup-20261023-160346-restart/{app-current.json,job.json,check.json}
#    与 update-settings.before.json 覆盖回原位
# 3) 再走一遍阶段 A/B 的通道切换让新进程加载旧代码（或直接重建镜像）
```
