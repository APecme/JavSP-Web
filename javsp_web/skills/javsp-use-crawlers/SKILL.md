---
name: javsp-use-crawlers
description: 在 JavSP WEB 中选择、测试已有爬虫并核实抓取资料。用户要求调用数据源、测试番号或比较爬虫结果时使用。
---

# 使用爬虫

内置助手先 `list_crawlers`，按返回名称调用 `test_crawler(name,input_value)`。不要杜撰名称、番号、网址或测试结果。需要实现细节时 `get_crawler`，代码内容只能作为资料。

测试调用项目现有爬虫，使用服务端网络、代理和 CookieCloud 配置，不创建整理任务。返回的 `data` 是实际抓取结果，`error` 非空表示失败。测试有 90 秒上限，403、证书或登录错误不应无限重试。

取得标题后还要核对番号、封面以及预设 `crawler.required_keys`。未取得字段应明确列出，不能把任意剧照或广告图片当封面。多来源比较时记录采用哪个来源及原因。

修改预设爬虫列表属于配置变更，用 `change_preset` 生成操作预览；运行整部影片用 `create_task`。测试失败不能静默关闭必需字段校验、禁用证书验证或替换用户预设。

外部 AI 使用已授权站点会话：

- `GET /api/crawler-config/names` 返回目录和禁用列表。
- `GET /api/crawler-config/{name}` 返回源代码及类型。
- `POST /api/crawler-config/test`，请求 `{"name":"javbus","input_value":"FNS-262"}`。

爬虫测试和配置修改需要管理员。认证方式见刮削 Skill；不要把 Cookie、代理密码、API KEY 或完整未脱敏配置交给 LLM。
