---
name: javsp-develop
description: 在 JavSP WEB 源码中创建功能、增加 API 与标签页、修复缺陷并验证兼容性。适用于具有项目工作区访问权限的编码 AI；不用于把普通设置请求升级为代码修改。
---

# 开发项目功能

内置 AI 刮削助手没有源码写入、shell、Git 发布权限。此模式下只能给出明确方案或爬虫草稿，告知需要编码环境，不伪称已实现或发布。

外部编码 AI 在用户指定仓库中工作：先读适用的 `AGENTS.md`、`git status`、相关实现和测试，保留用户未提交修改。

## 代码位置

- `javsp_web/server.py`：FastAPI 路由、请求模型、鉴权及已有业务接口。
- `javsp_web/tasks.py`、`task_scans.py`、`task_store.py`：任务执行、异步扫描和任务存储。
- `javsp_web/storage.py`：配置持久化和数据目录。
- `javsp_web/web/index.html`、`web/assets/app.js`、`web/assets/overrides.css`：标签页、交互和样式。
- `javsp_web/ai.py`、`ai_router.py`、`ai_tools.py`：LLM 协议、对话与操作审批、工具白名单。
- `javsp_web/skills/`：内置 Skills，可在系统设置中管理。
- `vendor/JavSP/javsp/`：底层扫描、爬虫和整理引擎。
- `tests/`：离线 Python 回归和 Node 前端测试。

## 实现约定

复用现有业务函数与鉴权。系统配置和爬虫代码写入必须验证管理员权限。LLM 工具是独立白名单，不允许根据模型输出任意 URL 调用 API 或执行代码。新增写工具沿用操作预览、服务端记录及一次性确认流程。

LLM API KEY 仅保存在服务端数据目录，响应、工具结果和日志不能泄漏。供应商错误返回状态和可操作信息，不原样回显可能包含密钥的上游响应。

保持 Docker、源码、EXE 路径兼容；新增运行时资源要包含在 PyInstaller 数据文件中。避免无关依赖变更导致应用包自更新要求更换镜像。

为实际行为增加离线回归，用 Mock 测试 LLM 和外部网站，覆盖拒绝访问、输入校验、工具失败、重复提交和密钥脱敏。运行受影响测试及语法检查。不要使用真实媒体、真实云额度验证非必要场景。

向用户说明完成行为、验证结果及部署状态。提交、推送、打标签和发布只在当前授权范围内执行，不因开发功能自动发布。
