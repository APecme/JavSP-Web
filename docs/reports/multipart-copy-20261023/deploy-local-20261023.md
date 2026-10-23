# 本机 javsp-web 部署记录（2026-10-23 14:19–14:23）

目标：把工作区已验收的改动部署到本机运行实例 `javsp-web`，并让运行进程真正加载新代码（不只是文件落盘）。

部署内容（相对 11:10 装配的 overlay）：

| 文件 | 改动来源 |
|---|---|
| `javsp_web/web/index.html` | 侧栏新增「热片」「下片」菜单 + 两个空面板（KIMI3 交付） |
| `javsp_web/web/assets/app.js` | `showView` 标题映射新增 `hot` / `download-script` |
| `javsp_web/directory_watch.py` | 调度器停止/重启边界修复；副本提示写入 `status.message` |
| `javsp_web/tasks.py` | 显式清单副本语义：不自动加入原文件，仅副本时明确提示 |
| `javsp_web/task_scans.py` | 扫描级副本提示绕过节流写入扫描日志 |
| `vendor/JavSP/javsp/{file,multipart,download_copy}.py` | 分 P／重复副本识别实现 |

`scripts/`、`navigation.css`、`navigation.js`、`icons.js` 等其余文件与上一版 overlay 逐字节一致。

## 环境与限制

- 运行实例：容器 `javsp-web`（镜像 `apecme/javsp-web:latest` → `v1.1.41`），宿主端口 `8590`，数据卷 `/data/docker/DPanel-data/javsp-web/data:/app/data`。
- 沙箱内**无 docker daemon / 无 systemd / 无宿主 PID 命名空间**：不能 `docker build`、`compose up`、重启容器，也不能给子进程发信号。
- 因此沿用该实例自带机制：数据卷 overlay（`data/updates/apps/<label>`）+ `app_supervisor` 重启子进程。**镜像仍是 1.1.41，本次是代码级 overlay 更新。**

## 为什么需要两次重启

正在运行的子进程只在两种情况下重启：退出码 75（应用更新完成）或容器重启。更新入口 `updater.apply()` 要求 `check()` 报告有可用更新，而 stable 通道当前版本就是 1.1.42，不满足条件。因此按通道切换完成同版本重装：

1. **阶段 A**：把新代码装配成 `apps/bata.20261023090847`，把 `experience_program=true`、`auto_update=true` 写入 `data/update-settings.json`。调度器下一轮 tick 发现「稳定版 → 体验版」需要切换，`stage()` 命中已装配目录，`install()` 后 `os._exit(75)`，supervisor 用新代码拉起子进程（PID 1282，14:21:06 CST）。
2. **阶段 B**：把 `apps/1.1.42` 整体替换为新代码（`Dockerfile`／`requirements.txt` 取自旧 overlay，与镜像 `/app` 逐字节一致），改回 `experience_program=false` 并保持 `auto_update=true`。调度器下一轮 tick 发现「体验版 → 稳定版」需要切换，装配命中，重启（PID 1302，14:22:21 CST）。

最终状态：`current=1.1.42`、`previous=bata.20261023090847`、`pending=false`、`base_image.label=1.1.41`、`auto_update=false`、`experience_program=false`。

## 预检与证据

- 新 overlay 在沙箱内用独立 venv（Python 3.14.7，`requirements.txt` 去掉无法在 3.14 编译的 `slimeface`）实际启动：`/api/public-info` → `1.1.42`，`/` 返回 10 个 `data-view`，`/assets/app.js` 含 `download-script`，启动/关闭无异常。预检产物已删除。
- 前端回归：`node tests/test_navigation_client.cjs`、`node tests/test_page_layouts.cjs` 均 `fail 0`。
- 线上校验（`http://192.168.0.101:8590`）：
  - `/api/public-info` → `{"name":"JavSP WEB","version":"1.1.42"}`
  - `/` 含 10 个 `data-view`（`overview/scrape/ai-scrape/auto-scrape/downloads/hot/download-script/crawler-config/presets/settings`）与两个空面板
  - `/assets/{app.js,navigation.css,directory-watch.js,icons.js}` 的 sha256 与工作区逐字节一致
  - `/`、`/login`、`/api/public-info` 200；`/api/directory-watch/rules`、`/api/comments/` 401（未登录，符合预期）
- 容器日志：两次重启后无 `Traceback`／ERROR，`Application startup complete` 后正常处理请求。

## 备份与回滚

- 备份目录：`data/updates/backup-20261023-141751-deploy/`
  - `app-current.json`、`base-image.json`、`job.json`、`check.json`、`update-settings.data-vol.json`
  - `apps-1.1.42-pre/`：部署前的 1.1.42 overlay（23MB）
- 回滚：把 `apps-1.1.42-pre` 覆盖回 `apps/1.1.42`、`app-current.json` 覆盖回原文件，再触发一次子进程重启（重复阶段 B 的 `auto_update` 流程，或直接重启容器）。

## 边界与风险

1. 镜像仍是 `v1.1.41`，正式镜像未重建；数据卷丢失会回到镜像自带代码。
2. `apps/bata.20261023090847` 目录内容为本轮工作区代码（标签对应的是 GitHub commit 42d8961），`previous` 指向它；若之后切到体验版通道，会装配/复用该目录，内容即当前代码，不影响功能，但标签与实际内容不一致。
3. 两次重启清空了内存会话，浏览器需要重新登录一次；重启瞬间正在进行的请求会失败。
4. 未验证容器／设备重启：沙箱无 docker 权限。数据卷 overlay 与 `base_image` 绑定已确认一致，重启后应继续选中 1.1.42。
5. 未做登录态下的业务回归（无凭据），仅做匿名路由探针与静态资源哈希比对；Python 侧正确性依据部署前的 96 passed 联合回归。
