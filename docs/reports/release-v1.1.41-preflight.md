# v1.1.41 发布前检查（2026-10-19）

## 正式推送准备

用户已明确要求“正式推送”，随后要求不再使用 Claude 审核。已停止审核委托，由 Codex 完成最终核对。

- 本轮重新运行完整 Python 测试：326 项通过；12 个 Node 前端回归脚本通过，主题检查通过。
- 联网恢复后已 fetch main，远端 main 为 `e7b7a97f9ee239d6acfedb7f5739d742edb78b55`，当前本地 HEAD 为 `312e49c262e836fa0d87ef2262c641bab05a4806`，没有分叉。
- `v1.1.41` 本地和远端均不存在。版本元数据均为 1.1.41，Release 五条及依赖升级提醒已核对。
- 本次包含当前版本元数据、发布说明、Gfriends 目录及评论分页修复、相应测试与生成 demo；不包含嵌套评论仓库原有头像改动。
- 仅推送单个注释标签 `refs/tags/v1.1.41`，不推送 main；正式 workflow 构建 Docker 与 Windows，并使用对应发布说明生成 Release。

以下记录保留此前准备过程，较早的审批故障现已恢复。

## 当前准备结果

用户已指定最终五条 Release 文案，并追加明显的依赖升级提醒。发布说明已采用该文案，开头注明：本次已更新依赖，Docker 用户必须拉取新镜像并重建容器，仅安装网页更新不足以完成升级。

- `VERSION` 和 `javsp_web/__init__.py` 已统一为 `1.1.41`，尚未提交、打标签或推送。
- 已修复 Gfriends 全目录的分页、当前页统计不完整及点击目标丢失：范围选择交由服务端在完整集合上统计、搜索、分页；前端只展示当前页，并显示目录头像。
- 已实现评论每页 20 条的上一页/下一页，翻页替换列表、缓存已读页，保留评论草稿及回复目标。
- 已修正问号弹层的固定阴影颜色；主题测试 9 项全部通过。
- 最新完整 Python 回归 326 项通过；12 个前端回归脚本均通过（含新增 overview actress、theme）。demo 已重新生成并验证同步。
- 独立 Claude Code 最终审核未能启动：自动审批返回 HTTP 503，审批模型 `gpt-5.6-luna` 无可用通道。未得到审核结果，不宣称审核通过。
- `git ls-remote` 同样在执行前被自动审批服务 503 拒绝。没有联网核实远端 main 或目标版本标签，没有新增远端写入。用户的发布授权已明确；故障是审批服务不可用，不是缺少发布同意，也不是动作被判为不安全。
- 正式发布计划：仅推送 `refs/tags/v1.1.41`，触发正式 workflow，生成版本镜像、latest、Windows EXE 及 GitHub Release；不推送 main，不触发新的 bata 发布。
- 恢复人工审批后需完成远端只读核对、最终审核、明确路径暂存提交、创建单个注释标签并推送该标签，等待两个构建产物验收。不能把推送成功等同发布成功。

下文保留首次检查时的发现，以上结果为最新状态。

本文件是本地准备记录，不是已发布声明。用户要求先提供 Release 文案；当前未新增提交、Git 标签、远程推送或 GitHub Release。

- 当前分支：`main`；HEAD：`312e49c262e836fa0d87ef2262c641bab05a4806`。
- 远端地址：`https://github.com/APecme/JavSP-Web.git`。本地缓存的 origin/main 比 HEAD 少 1 个提交，尚未联网复核最新远端；本次没有 fetch 或 push。
- 用户指定正式版：`1.1.41`。`VERSION` 当前为 `1.1.39`，`javsp_web/__init__.py` 为 `1.1.40`；发布提交前必须统一为 `1.1.41`。
- Release 草稿：`docs/RELEASE_NOTES_v1.1.41.md`，覆盖本地 `v1.1.40` 至 HEAD 的用户可见变化。
- 正式轨道：推送单个 `v1.1.41` 标签触发 `.github/workflows/formal-release.yml`，发布 Docker 版本标签和 latest、构建 Windows EXE 并生成 GitHub Release。main 推送会触发 bata；用户要求显式 bata 指令后才推送，须避免把正式发布准备混同为新的 bata 发布授权。

## 本次实际验证

- Python 3.12：`python -m unittest discover -s tests`，324 项通过。
- 发布使用的 10 个 Node 回归脚本全部通过：web、scan、mount batch、AI translation、CookieCloud、comments、comment Markdown、community、library playback、demo。
- 额外主题检查：`node tests/test_theme_client.cjs`，8 项通过，1 项失败。原因是 overrides.css 中 comment-help-content 的 `rgba(0,0,0,.15)` 固定阴影，未使用主题 token。
- 嵌套 comments-service 仍有用户已有的 worker/src/avatars.js 修改；未纳入本次发布文案修改。

## 发布前需完成

1. 统一版本元数据，联网核对远端 main 及目标 v1.1.41 标签是否存在。
2. 修正问号弹层的主题测试失败并重新生成 demo，验证通过后再提交。
3. 完成 Gfriends 全部女优目录的分页、影片数量与点击定位：当前只用服务端当前页的已有女优匹配全部目录，渲染未切页，openOverviewGroup 仍只在服务端当前页查找。不能把当前功能宣传为已经完善。
4. 若 Release 要声明“评论分页”，需实现真正上一页/下一页；目前每次请求 limit=20 后仍累积到当前列表，只能描述为每次加载 20 条。
5. 剧照替换/删除尚无充分复现与修复证据，不列为已修复。

以上问题确认解决并完成最终测试、审阅发布说明后，再按用户批准的具体发布范围执行。不得因已有测试通过而推断未覆盖交互已正确。
