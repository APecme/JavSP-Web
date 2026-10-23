# bata 界面更新发布准备

2026-10-22。状态：验证通过，尚未提交或推送，等待分叉处理范围确认。

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

## 最新执行状态（2026-10-22）

用户已确认核对三个版本提交与本次改版，重叠内容只保留最新版。已在隔离目录基于远端最新提交整理为一个更新提交：`270e4de382c2bd9a893a4d47cb90aa9549317df4`。

- 最终提交保存在 `/data12t/AutoOrder/JavSP-Web-bata-release-20261022`，分支 `release/bata-theme-ready-20261022`，工作区干净。
- 最终 Node 51 项全部通过；最终源码的容器 Python 回归 335 项完成、跳过 1 项、退出 0；生成资源同步、版本与实现比对通过；提交的空白检查通过。
- 原工作区 HEAD 仍为 `f031065`，索引未变，无关未提交改动保留。
- 已尝试 `git push origin HEAD:refs/heads/main`，HTTPS 因无可用 GitHub 账号凭据失败；SSH 也因无可用公钥认证失败。无凭据被输出。
- 远端仍为 `f15c395eb16a55f434bf4d3be13ac7d7e2ed6ecc`，该最终提交暂无 beta workflow，尚未发布 bata 镜像。
- 配置本环境 GitHub 写入认证后，在上述隔离目录再次核对远端并执行 `git push origin HEAD:refs/heads/main`，无需重新整理代码。

## 推送结果（2026-10-22，Codeg 凭据配置后）

已使用 Codeg 的 Git 凭据助手完成命令级认证，未更改全局 Git 配置，未显示凭据内容。

- `git -c credential.helper=/home/apecme/.local/share/codeg/git-credential-codeg.sh push origin HEAD:refs/heads/main` 成功，远端从 `f15c395` 快进到 `270e4de382c2bd9a893a4d47cb90aa9549317df4`。
- `git ls-remote --heads origin main` 已确认远端为该提交。
- GitHub beta workflow 已启动：`https://github.com/APecme/JavSP-Web/actions/runs/39733447349`，首次查询状态 `in_progress`，对应提交正确。
- bata 镜像构建尚在运行，未宣称镜像发布完成；Git 标签 bata 未移动。
- 原工作区及无关未提交改动保持，发布提交保留在隔离目录。
