# JavSP-Web 四阶段工作流

工作区 `/code/JavSP-Web`。分析与评审使用 `claude-opus-5-5` profile；实现与测试使用 `kuaipao-gpt-6.1-sol` profile。密钥由现有 OpenHands profile 加载。

## 从 OpenHands 聊天提交需求

在该项目的 OpenHands 聊天中发送：

```text
使用已安装的 JavSP 四阶段工作流处理以下需求。
先把需求原文保存到 /code/JavSP-Web/.openhands-workflow/REQUEST.md，
不要自行修改业务代码。然后执行：
python /home/openhands/.openhands/javsp-workflow/submit.py --request-file /code/JavSP-Web/.openhands-workflow/REQUEST.md --wait
命令长时间运行时持续读取它的输出，直到完成。根据最终结果汇报，不把 PENDING 当成完成。

需求：在这里填写需求。
```

这会提交后台流程并等待结果；外层聊天只负责提交和汇报，不负责实现。

也可以先填写上述 REQUEST.md，再在 Canvas 的 Automations 页面打开 `JavSP-Web · Claude方案 → GPT实现 → Claude评审 → GPT测试`，点击 Run。手动 Run 使用文件当前内容；缺少或空需求时停止，不调用模型。

## 结果

- 各阶段会话在 Canvas 会话列表中，标题以 `JavSP` 开头。
- 状态和结果：`/home/openhands/.openhands/javsp-workflow/runs/<run_id>/`。
- `status.json` 记录模型、开始/结束时间、耗时和会话 ID。
- 各阶段 JSON 报告、真实命令日志及 `result.json` 保存在同目录。
- 每轮修改完成后 Claude 评审；拒绝评审不会进入测试。
- GPT 测试阶段选择适用命令和必要的浏览器检查；控制器执行返回的命令，记录真实退出码。
- 测试失败会回到实现，并再次评审；最多 3 轮。API 自动化运行最长 30 分钟。
- 同一项目仅允许一个流程执行。默认不提交 Git、不推送、不部署。
- 计划、评审和测试选择阶段不应修改项目；代码摘要变化时停止。测试生成的数据、缓存不纳入代码摘要。
- 所列测试命令通过不意味着覆盖所有业务；测试报告会列出覆盖范围和未验证项。

在自动化运行详情中可取消运行。不要只停止外层提交聊天；它已经把流程提交到后台。

本次安装验收不调用模型，不实施业务需求。
