# 目录监控与定时全量扫描合并：本地交付记录

日期：2026-10-23。此次是本地实现及代码级验证，未部署、未重启、未构建 Docker 镜像。8590 运行实例不能用于验收本版。

## 已落实

- 统一规则模型及管理员 API 接收 `trigger=watch|schedule`、`cron`；定时规则必须填写有效五段 Cron；切回 watch 后清除 Cron。
- 同一个规则表单用单选切换触发方式，隐藏并禁用非当前模式配置；列表按模式展示信息。旧定时模块隐藏，保留旧 DOM 钩子及历史查看能力。
- watch 保持目录轮询、稳定等待、分 P 聚组，仅提交该文件或组；组中任一成员未稳定时等待。重复副本不会被误算为未稳定的分片。
- schedule 保持全量目录扫描和预设语义，不使用 watch 成功台账；每分钟原子声明，上批任务仍排队/运行时跳过。旧 cron worker 已停止启动。
- 同目录和父子目录重叠规则提交互斥；按规范化路径及分 P 身份检查原始任务库中的排队/运行任务。来源规则暂停、修改或删除后，活动任务仍参与去重。提交期间使用预留，异常会释放；失败/取消不视作成功，同签名可重试。
- 旧规则迁移保留停用规则、离线目录、预设、Cron、时区、历史快照及任务关联。ID 冲突用稳定映射保留双方；版本、映射、规则和历史快照以一个原子替换写入。删除后的映射保留，重启不会复活旧规则。
- 旧 API 读写统一存储，运行历史合并旧快照与新运行结果，恢复历史删除接口；编辑保留历史及分钟声明。迁移和运行中断恢复都有行为测试。

## 最终验证

环境：Python 3.14.7（项目 `.venv-multipart`）、Node v24.22.1。

```sh
.venv-multipart/bin/python -m compileall -q javsp_web/directory_watch.py javsp_web/directory_watch_router.py javsp_web/server.py javsp_web/storage.py javsp_web/tasks.py javsp_web/task_scans.py
.venv-multipart/bin/python -m pytest -q tests/test_directory_watch.py tests/test_task_scans.py tests/test_multipart.py tests/test_task_store.py
node --check javsp_web/web/assets/app.js
node --check javsp_web/web/assets/directory-watch.js
node --test tests/test_unified_automation_client.cjs tests/test_navigation_client.cjs tests/test_page_layouts.cjs
git -c core.whitespace=cr-at-eol diff --check -- javsp_web/server.py javsp_web/storage.py javsp_web/web/assets/app.js javsp_web/web/index.html
```

- Python 编译：通过。
- Python 回归：157 passed、36 subtests passed、2 skipped、1 warning，53.67 秒。
- JavaScript 语法：通过；前端回归：31 passed、0 failed。
- 差异空白检查：通过（按工作区已有 CRLF 配置检查，没有清理其他文件）。
- 2 skipped：Linux 上无法运行 Windows 大小写路径用例；root 无法按普通用户方式模拟目录权限失败。均不计为通过。
- warning：Starlette 测试客户端使用的 AnyIO BlockingPortal 别名弃用提示。
- 本轮新增后端 17 项边界用例，前端 4 项行为/结构用例。扩展回归曾发现稳定分组包含已跳过副本导致 4 项失败；已修复并在最终整组回归通过。

证据：`backend-final.log`、`frontend-final.log`、`diff-check.log`、`sha256.json`。

## 尚未验证

- 原生浏览器弹窗、焦点、窄屏与视觉效果没有运行期验收；前端 VM 行为测试不能替代这些实测。
- 没有修改运行实例或正式数据，也没有验证容器/设备重启后的部署持久性。
- 图片缓存头、剧照加载优化、静态资源版本自动刷新均不在本次范围。
- 本记录是执行者的本地交付证据，不替代独立审批或上线验收。
