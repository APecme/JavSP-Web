# bata 界面更新发布准备

2026-10-22。状态：用户已确认逐项核对、重叠变更只保留最新版；在隔离工作区整理最终发布提交。

## 当前 Git 状态

- 仓库：`https://github.com/APecme/JavSP-Web.git`。
- 当前分支：`main`。
- 本地 HEAD：`f031065acef229ae951aceb902173124346fe6b8`。
- 远端 main：`f15c395eb16a55f434bf4d3be13ac7d7e2ed6ecc`。
- 共同祖先：`e7b7a97f9ee239d6acfedb7f5739d742edb78b55`。
- 本地独有三个提交：`312e49c`（评论帮助与女优范围）、`03b3566`（v1.1.41）、`f031065`（v1.1.42 概览去重）。远端独有一个 README 更新提交 `f15c395`。
- 索引为空。工作区存在大量先前改动，其中多数为行尾差异，不得整体加入提交。
- 只读合并预览显示远端只需带入 README，未发现冲突。

## 推荐操作方案（待确认）

保留远端 README 更新、本地三个既有提交和本次界面改版，在隔离工作区完成合入与验证后，使用明确 refspec 将最终提交快进推送到 `HEAD:refs/heads/main`，触发 `.github/workflows/release.yml` 发布 `apecme/javsp-web:bata`。不创建或移动 Git 标签 `bata`，不发布正式版本标签，不变更 `VERSION`（仍为 `1.1.42`），不强推。

拟提交说明：`feat: unify console theme and improve film detail UX`。

本次提交范围：

- `javsp_web/web/index.html`、`javsp_web/web/login.html`。
- `javsp_web/web/assets/app.js`、`cinema.css`、`overrides.css`。
- 对应生成文件 `docs/assets/demo-app.js`、`cinema.css`、`overrides.css`，以及 `docs/demo.html`、`docs/demo-seed.js`。
- `tests/test_film_detail_ux.cjs`。
- `docs/superpowers/plans/2026-10-22-console-theme-refresh.md` 与 `docs/reports/console-theme-20261022/` 验收证据。
- 本准备记录。
- 若按推荐方案执行，同步纳入当前 `scripts/build_demo.py` 的版本参与缓存计算及演示页版本展示调整，以便重建结果与已验收 demo 一致；提交前另行核对差异。
- 执行阶段补充 `docs/RELEASE_NOTES_bata.md` 中这四项界面更新，并将新增回归加入 `.github/workflows/release.yml`；两者目前尚未修改。

保留并排除其他本地未提交修改。README 更新来自远端既有提交，通过合入保留。

## 实际验证

- `node --test tests/*.cjs`：51 项全部通过。
- 对 `javsp_web/web/assets/*.js` 逐文件执行 `node --check`：通过。
- `git -c core.whitespace=cr-at-eol diff --check` 检查五个前端源文件：通过。
- 本机 Python 缺少项目依赖，直接运行未通过，不能作为发布结果。
- 使用已有 `apecme/javsp-web:latest` 启动临时容器，源码只读挂载后复制到容器临时目录，安装 `tests/requirements.txt`，执行 `python -m unittest discover -s tests -v`：335 项，`OK (skipped=1)`，约 44 秒。未修改运行中服务或真实媒体数据。
- 合入后的提交仍需重新运行必要验证并检查暂存范围，再推送。
- `gh` 不可用；推送后需通过 GitHub API 或网页核验 CI 状态，不能将 Git 推送成功等同镜像发布成功。

Git 标签 `bata` 已存在，最终解引用到 `080b3a5c84099c409d8493e59f064efd356451aa`；它不会触发现有 beta workflow。本次推荐方案不操作此标签。

## 最新实现核对结论

用户在 2026-10-22 确认：“你核对三个版本提交变化和本次更改，均只保留最新版”。因此在 `origin/main` 上汇总最终代码为一个提交；不重放三个旧版本提交，不改写远端历史。

| 范围 | 旧实现 | 本次保留的最终实现 |
| --- | --- | --- |
| 女优目录 | 312e49c 在浏览器加载全部目录并合成分组 | 03b3566 的服务端搜索/分页、头像接口和空收藏目录支持 |
| 评论帮助 | 小问号及绝对定位帮助浮层 | 本次紫色图标文字按钮与正常文档流分组说明 |
| 评论列表 | 累积加载更多 | 03b3566 的上一页/下一页及草稿保留 |
| 概览聚合 | 旧完整路径合并逻辑 | f031065 的重复刮削合并、路径映射去重、保守挂载前缀匹配和媒体引用保留 |
| 视觉/剧照/关闭按钮 | 概览外旧样式、剧照不可放大、两个关闭按钮 | 本次已审批实现及新增行为回归 |
| 版本 | 旧 1.1.40/1.1.41 | VERSION 与 Python 元数据均为 1.1.42 |
| README | 本地旧文本 | 远端 f15c395 的最新文案 |

生成资源从最终源码重新构建，每份资源只保留最终状态。保留历史正式版本发布说明作为发布记录；它们不是并行生效的旧代码。其他不在发布范围的未提交修改留在原工作区。

## 最终发布组合验证

隔离目录 `/tmp/javsp-bata-release-20261022` 基于远端最新 `f15c395`，以 squash 整理三个本地提交的最终状态，再覆盖本次最新的已审批界面源码；未改写远端历史或原工作区。

- 前端：`node --test tests/*.cjs`，51 项全部通过；7 个源 JavaScript 文件语法检查通过。
- 后端：临时容器复制最终源码后安装测试依赖，`python -m unittest discover -s tests -v`，335 项，`OK (skipped=1)`，44.636 秒，容器命令退出 0。
- 最终后端、版本字段、旧修复对应测试与 `f031065` 逐字节一致；最终五个界面源文件与已审批工作副本按文本一致（Git 提交按仓库 LF 存储）；远端 README 逐字节一致。
- demo 重新构建为 `demo.fd79430f7d93`，生成资产与最终源码逐字节一致。
- `git diff --check HEAD` 通过；本次提交路径采用明确清单核验。
- beta workflow 加入新增详情交互测试，release notes 改为最新说明。VERSION 保持 1.1.42。

发布状态以随后读取的远端提交与 GitHub Actions 结果为准。
