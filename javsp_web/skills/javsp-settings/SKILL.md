---
name: javsp-settings
description: 为 JavSP WEB 更改刮削预设、创建预设和定时刮削规则。用户要求调整扫描、爬虫、图片、翻译或自动刮削设置时使用。
---

# 更改设置与创建规则

先读后改，只修改用户要求的字段，不用脱敏配置覆盖完整配置。修改密钥、密码、CookieCloud、用户权限和 模型接入参数应在系统设置页面完成，不能要求用户把凭据发送给模型。

内置助手支持：

- `list_presets`、`get_preset`：取得实际 ID、完整配置的脱敏视图。
- `change_preset`：参数 `preset_id`、`changes`；后端按分组递归合并，保留未提及项。
- `create_preset`：额外提供 `name`；`preset_id` 指复制来源。
- `list_schedules`、`create_schedule`：先查重，再提议新建；后者字段 `name`、`enabled`、`cron`、`input_directory`、`preset_id`，cron 使用服务端时区。

所有修改仅生成待确认操作。创建启用规则会按时间自动整理文件，要让用户看到路径、预设、时间和启用状态。依赖前一操作的新 ID 时，等待确认返回真实 ID 后再提议下一操作。

例如启用剧照下载：

```json
{"preset_id":"实际预设ID","changes":{"summarizer":{"extra_fanarts":{"enabled":true}}}}
```

扫描配置在 `scanner`，数据源与必需字段在 `crawler`，输出与图片在 `summarizer`，翻译在 `translator`。修改前读取实际结构，不猜字段。原有翻译引擎使用预设配置；AI 翻译复用系统 AI 接入的模型，具体规则先读取 `javsp-translate`。

AI 总开关：管理员在“系统设置 → AI 接入”打开“启用 AI 刮削”，开放对话、预设 AI 刮削和翻译能力。内置助手没有修改模型连接或总开关的工具，不能通过改预设代替开启系统能力。

AI 翻译：在当前预设的“翻译器”中设置 `translator.ai_enabled=true`，翻译范围沿用 `translator.fields.title` 和 `translator.fields.plot`。无需开启该预设的 AI 刮削或联网搜索。仅合并用户要求的翻译字段，保留原 `translator.engine`。AI 与该引擎二选一：选择 AI 后，系统 AI 关闭或翻译失败都应报错，不得切换引擎；用户取消预设 AI 翻译后才使用所选引擎，引擎为“不翻译”时跳过翻译。

预设 AI 刮削：`crawler.ai_enabled=true` 允许该预设用 AI 查找资料；`crawler.ai_fallback_only=true` 表示先运行普通爬虫，全部失败或缺少必需字段时再尝试 AI，设为 false 则直接使用 AI。它需要系统 AI 总开关和联网搜索均开启。按用户指定范围修改，不同时改动其他预设。

Skills 在系统设置的 AI 接入卡片中管理。`GET /api/ai/skills` 列目录，`GET /api/ai/skills/{name}` 读源文件，`PUT /api/ai/skills` 用 `{"source":"完整 SKILL.md"}` 添加或保存，`DELETE /api/ai/skills/{name}` 删除。内置 Skill 删除后不会随应用更新重新启用；“恢复已移除的内置 Skills”会重新启用被移除的技能，保留已保存的自定义修改。Skill 只提供指令，不能扩展内置助手的工具权限。

外部 AI 可在已有用户授权内使用：

- `GET /api/presets`，`POST /api/presets`，`PUT /api/presets/{id}`。写请求包含 `name`、`mode`、`content` 或 `form`、`task_concurrency`。与内置 `change_preset` 不同，此 API 需要保留未修改配置。
- `GET /api/auto-scrape-schedules`，`POST /api/auto-scrape-schedules`，`PUT /api/auto-scrape-schedules/{id}`。
- 下载器、媒体服务器、路径映射等 API 的具体结构从站点 `/openapi.json` 查看，在现有权限内操作；内置助手未暴露这些写工具，不能宣称已创建。

结果以服务器响应为准，记录返回的 ID；不能仅凭 LLM 文本宣称保存成功。
