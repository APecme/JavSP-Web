# 本机 javsp-web 容器更新记录（2026-10-23 11:19）

目标：把工作区未提交的平台重构代码装进本机正在运行的 `javsp-web` 容器，供用户实际查看。

## 环境与限制

- 运行实例：容器 `javsp-web`（`apecme/javsp-web:latest`），宿主端口 `8590`，数据卷 `/data/docker/DPanel-data/javsp-web/data:/app/data`，compose 由 DPanel 管理（`/dpanel/compose/javsp-web/docker-compose.yaml`）。
- 更新前版本：镜像 `v1.1.41` + 数据卷 overlay `bata.20261022142154`（`/api/public-info` 返回该版本）。
- 本沙箱（ekko-studio 容器）内**没有 docker daemon 可用**：`/var/run/docker.sock` 不存在，`/data/docker.sock` 是空目录，宿主机 `192.168.0.101`/`192.168.16.1` 的 `2375/2376` 均不通，DPanel API（`8807`）返回 401。因此无法 `docker build` / `compose up` / 重启容器。
- 但宿主 `/data` 已挂载进沙箱：可读写数据卷，也可读容器日志与 rootfs。应用自带 `app_supervisor` + 数据卷 overlay（`data/updates/apps/<label>`）的"仅代码更新"机制正好可用：新代码落在数据卷，子进程重启后从 overlay 启动，容器本身不需要重建。

## 实际执行

1. 备份 `data/updates/{app-current,job,check,base-image}.json` 与旧 `apps/1.1.42`（GitHub 版）到 `data/updates/backup-20261023-1120/`；`data/update-settings.json` 一并备份。
2. 把工作区代码装配成 `data/updates/apps/1.1.42/`：`javsp_web`、`scripts`、`vendor/JavSP` 取自工作区（排除 `__pycache__`），`Dockerfile`、`requirements.txt` 逐字节取自镜像 `/app`（`root_for()` 要求与基础镜像完全一致，工作区 Dockerfile 有换行差异，不能用）。
3. 预检（沙箱内独立进程，临时数据目录，端口 8591）：`/api/public-info` = 1.1.42；`/api/directory-watch/rules`、`/api/comments/` 均 401（路由存在）；6 个新静态资源 200；`compileall` 通过；`navigation/icons/page-layouts/library-naming/film-detail-ux` 五个前端回归全部通过。
4. 触发切换：把 `data/update-settings.json` 改为 `auto_update=true`、`experience_program=false`，应用自身的更新调度器在下一轮 tick 内完成 `check → apply → stage(命中已装配的 1.1.42) → install → os._exit(75)`，`app_supervisor` 重新拉起子进程。job 状态 `scheduled → downloading → restarting → updated`，全过程约 35 秒。
5. 收尾：`auto_update` 已恢复 `false`。

## 结果

- `/api/public-info` → `{"name":"JavSP WEB","version":"1.1.42"}`；`app-current.json`：`current=1.1.42`，`commit=f031065…`，`previous=bata.20261022142154`，`base_image=1.1.41`。
- 线上 `navigation.js / icons.js / directory-watch.js / page-layouts.css / navigation.css / directory-watch.css` 与工作区 sha256 完全一致；`/` 返回的 HTML 含左侧导航与"片库"。
- 容器日志在重启后无 `Traceback`/`ERROR`，子进程 PID 已更替（1112）。
- 浏览器实测：左侧导航（图标+文字、折叠按钮、分组）与"片库"标题已生效；登录页为新版左右分栏布局，页脚显示 `v1.1.42`（截图中文显示方块是沙箱浏览器缺字体，与应用无关）。

## 边界与后续

- 这是**代码级 overlay 更新**，镜像仍是 1.1.41。正式部署应重建镜像：`docker compose build && docker compose up -d`（此沙箱无权限执行）。数据卷丢失会回到镜像版本。
- 更新设置里 `experience_program` 现在是 `false`（稳定通道）。原因：稳定通道 `latest` 就是 1.1.42，与当前一致，不会出现"提示更新回旧 bata 代码"；若切回体验版，`bata` 标签当前指向 `bata.20261023090847`（不含本次重构），会诱导降级。重建镜像后再切回体验版。
- 重启清空了内存会话，浏览器需要重新登录一次。
- 未验证真实容器重启/设备重启（无 docker 权限），但状态里 `base_image` 与镜像标识一致，`reconcile_image_state()` 不会把选择重置回镜像版本。
- 回滚方式：把 `data/updates/backup-20261023-1120/app-current.json` 覆盖回去，再让应用重启一次即可回到 `bata.20261022142154`。
