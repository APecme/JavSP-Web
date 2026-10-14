---
name: javsp-github-release
description: Use when a user asks to push JavSP WEB to GitHub, publish a beta/bata build, or prepare a formal version update.
---

# JavSP WEB GitHub 发布

将“准备检查”和“执行推送”严格分成两步。第一步只读检查并给出可审阅计划；第二步只有在用户针对该计划明确确认后才提交、打标签或 `git push`。用户说“直接完成”也不能跳过第一步和确认门。

## 目标判定

- `beta`、`bata`、`测试版`默认表示 beta 发布轨道。这个仓库通过推送 `main` 触发 `.github/workflows/release.yml`，由 CI 发布 Docker 的 `bata` 镜像标签；标准 beta 流程不创建或移动 Git 标签 `bata`。
- `正式版`、`正式版本`或明确的 `vX.Y.Z` 表示正式发布。正式发布通过推送 `vX.Y.Z` Git 标签触发 `.github/workflows/formal-release.yml`。
- 如果用户明确要求“Git 标签 `bata`”，先说明它不会触发当前 beta workflow，并要求用户选择推送 `main` 的 beta 轨道还是单独创建该标签。不要静默改名或猜测。
- 正式版本必须有明确的 `X.Y.Z`。版本来源只能是用户明确给出的版本或仓库 `VERSION` 的精确内容；不从提交信息、旧标签或文件名猜版本。

| 用户意图 | 仓库动作 | 触发的 CI | 禁止事项 |
| --- | --- | --- | --- |
| beta / bata | 推送 `main` | `release.yml`，Docker `bata` | 不把 `bata` 当 Git 标签，不推 `--tags` |
| 正式 `vX.Y.Z` | 推送单个 `vX.Y.Z` 标签 | `formal-release.yml` | 不猜版本，不移动已有标签，不强推 |

## 第一步：准备与检查

这一阶段不执行 `git add`、`git commit`、`git tag`、`git push`、`reset`、`clean`、`stash`、`checkout`、`rebase` 或 `merge`。可以读取 Git 状态、读取文件、运行验证测试和查询远端状态。

1. 确认仓库、远端和分支：

   ```powershell
   git remote get-url origin
   git branch --show-current
   git rev-parse HEAD
   git status --short
   git log -1 --oneline --decorate
   ```

   `origin` 必须精确匹配以下 HTTPS 或 SSH 写法（仓库名大小写不敏感，可选末尾 `.git`）：`https://github.com/APecme/JavSP-Web`、`git@github.com:APecme/JavSP-Web`、`ssh://git@github.com/APecme/JavSP-Web`。拒绝其他主机、端口、额外路径、查询参数或非 `git` SSH 用户。远端不匹配、当前分支不是 `main`、或分支状态无法解释时停止并报告。不要自行切换分支或改写历史。

2. 检查工作区和索引。分别审阅工作区改动、已暂存改动和未跟踪文件：

   ```powershell
   git status --short
   git diff --name-status
   git diff --stat
   git diff --cached --name-status
   git diff --cached --stat
   git diff --cached
   ```

   不要把任何路径自动加入发布提交。工作区或索引有改动时，要求用户明确给出要包含的路径和提交说明，或明确说明发布当前已有提交而保留并排除这些改动；未授权的已暂存路径也不能自行撤销暂存。推送已有 HEAD 只发送该提交历史，不会发送 index 或工作区改动。除非收到该范围授权，否则停在准备阶段。

3. 同步并比较远端基线（`git fetch origin main` 仅更新本地 `origin/main` 跟踪引用，不改工作树或索引）：

   ```powershell
   git fetch origin main
   git rev-list --left-right --count origin/main...HEAD
   git ls-remote --heads origin main
   ```

   若本地落后或与 `origin/main` 分叉，停止；不要自动合并、变基或强推。若本地领先，计划中明确要推送的提交范围。

4. 按目标执行可用的验证。优先读取当前 workflow 使用的命令；至少记录实际运行的命令和结果。可以使用：

   ```powershell
   python -m unittest discover -s tests -v
   node tests/test_web_client.cjs
   node tests/test_scan_client.cjs
   node tests/test_mount_batch_client.cjs
   node tests/test_ai_translation_client.cjs
   node tests/test_cookiecloud_client.cjs
   node tests/test_comments_client.cjs
   node tests/test_community_client.cjs
   node tests/test_library_playback.cjs
   node tests/test_demo.cjs
   ```

   缺少运行环境、Docker 或依赖时如实标记为未运行；不要把“未运行”写成“通过”。测试失败时停止，不推送。

5. Beta 目标还要确认当前分支是 `main`，并计划使用明确 refspec `HEAD:refs/heads/main`。不要使用 `--tags` 或 `--follow-tags`。

6. 正式目标还要：

   - 读取 `VERSION` 原文；去除唯一的行尾换行后必须只匹配 ASCII 且无前导零的 `^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$`，且与目标 `X.Y.Z` 完全一致。空白、前缀、后缀、前导零或多行内容都停止；检查 release notes 文件名精确为 `docs/RELEASE_NOTES_vX.Y.Z.md`，首个非空标题精确匹配 `# JavSP WEB vX.Y.Z`，遇到版本元数据或说明不一致就停止，不自动修改或选择其中一个版本；
   - 用 `git show-ref --verify refs/tags/vX.Y.Z` 检查本地标签；若存在，再用 `git rev-parse "refs/tags/vX.Y.Z^{}"` 得到 annotated 或 lightweight 标签最终指向的提交。用 `git ls-remote origin "refs/tags/vX.Y.Z" "refs/tags/vX.Y.Z^{}"` 检查远端：有 `^{}` 行时使用该 peeled 提交，没有时仅当 direct 行是提交对象才使用它。比较最终提交对象。正式发布请求遇到已存在的目标标签时停止：若标签指向同一提交，只能核验现有发布；若指向其他提交，报告冲突。不得移动、删除或强推已有标签；
   - 确认目标提交已经在 `origin/main`，或者在计划中单独列出是否同时推送 `main`。如果正式版提交尚未进入 `origin/main`，不要暗自决定是否让它同时触发 beta workflow。

7. 输出准备结果，必须包含：发布类型、当前分支、HEAD、远端、工作区文件范围、实际验证结果、版本与 release notes 检查、目标 refspec，以及将执行的提交/标签动作。最后只等待用户明确回复，例如“确认执行 beta”或“确认执行正式版 v1.2.3”。

## 第二步：确认后执行

只在用户明确确认第一步计划，且确认内容仍匹配当前 HEAD、目标和文件范围时执行。执行前重新运行 `git status --short`、`git diff`、`git diff --cached`、`git rev-parse HEAD`、远端/tag 检查；状态改变就回到准备阶段。

### 需要提交用户改动时

仅操作用户明确授权的路径：

```powershell
git add -- path/to/file another/file
git diff --cached --check
git diff --cached --stat
git diff --cached
git commit -m "<用户确认的提交说明>"
```

第一步计划必须已经展示获授权路径的工作区/索引差异和摘要；按该计划暂存后，核对暂存路径与摘要完全一致再提交。不得使用 `git add -A`、`git add .` 来吸收未知改动；不得删除、覆盖或回滚未授权文件。提交后重新记录新的 HEAD，并重新检查正式版本文件和标签。

### Beta 发布

确认仍在 `main` 且没有落后或分叉后，推送分支的明确 refspec：

```powershell
git push origin HEAD:refs/heads/main
```

不要创建、移动或推送 Git 标签 `bata`，除非用户在计划中明确选择了“单独的 Git 标签 bata”并确认其不会触发当前 beta workflow。推送后用 `git ls-remote --heads origin main` 核对远端提交，并用 `gh run list --workflow release.yml --limit 5` 检查 GitHub Actions；正式发布用 `gh run list --workflow formal-release.yml --limit 5` 与 `gh release view vX.Y.Z`。若 `gh` 不可用或网络受限，如实标记状态未核验；workflow 仍运行时只报告进行中，不等待无限时长或声称成功。

### 正式版本发布

在 `VERSION`、release notes、远端标签和目标提交再次核对无误后，创建不可变的注释标签；创建后用 `git cat-file -t "refs/tags/vX.Y.Z"` 确认标签对象类型为 `tag`，并用 `git rev-parse "refs/tags/vX.Y.Z^{}"` 确认其最终提交，再推送精确 refspec：

```powershell
git tag -a vX.Y.Z -m "JavSP WEB vX.Y.Z" HEAD
git push origin refs/tags/vX.Y.Z
```

若计划明确包含尚未进入远端的 `main`，先按计划推送 `HEAD:refs/heads/main`，再推送 `refs/tags/vX.Y.Z`；这可能同时触发 beta workflow，必须在准备结果中提前说明并得到确认。禁止 `--force`、`--force-with-lease`、删除远端标签、覆盖已有标签、`--tags` 和 `--follow-tags`。推送后用 `git ls-remote --tags origin refs/tags/vX.Y.Z "refs/tags/vX.Y.Z^{}"` 核对标签及解引用对象，并读取正式 workflow、GitHub Release 与构建资产状态；可用 `gh run list --workflow formal-release.yml --limit 5` 和 `gh release view vX.Y.Z` 查询。若 `gh` 不可用或网络受限，如实标记状态未核验；workflow 尚未完成时只报告进行中，不得声称发布成功。

## 停止条件

遇到以下任一情况立即停止并报告，不猜测、不静默修正：目标不明确；远端不是预期仓库；工作区范围未获授权；分支落后或分叉；测试失败；版本与 `VERSION` 不一致；正式 release notes 缺失；标签已存在但指向不同提交；认证、网络或 GitHub Actions 失败；用户确认后 HEAD、文件范围或目标发生变化。

## 常见错误

- 把仓库的 `bata` 镜像标签误当成会触发发布的 Git 标签。
- 用 `git add -A`、`git commit -am` 或 `git push --tags` 把无关改动和旧标签一起发布。
- 从旧标签、提交信息或日期猜正式版本。
- 为解决分叉而自动 `reset --hard`、`rebase`、合并或强推。
- 只看到 `git push` 返回成功就声称 Docker、Windows EXE 或 GitHub Release 已构建完成。
