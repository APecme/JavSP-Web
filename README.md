![JavSP WEB](./javsp_web/web/assets/javsp-logo.png)

# JavSP WEB

**在浏览器中刮削影片资料、整理文件和管理媒体库。**

JavSP WEB 基于 [JavSP](https://github.com/Yuukiy/JavSP)，从文件名识别番号，汇总多个站点的资料，生成 NFO、封面和剧照。支持 Windows 本机运行，也可通过 Docker 部署到服务器或 NAS。

[使用教程](https://apecme.github.io/JavSP-Web/docs.html) · [交互示例](https://apecme.github.io/JavSP-Web/demo.html) · [下载正式版](https://github.com/APecme/JavSP-Web/releases/latest) · [反馈问题](https://github.com/APecme/JavSP-Web/issues)

[![Latest release](https://img.shields.io/github/v/release/APecme/JavSP-Web)](https://github.com/APecme/JavSP-Web/releases/latest)
[![Docker Image](https://img.shields.io/docker/v/apecme/javsp-web?label=Docker&logo=docker)](https://hub.docker.com/r/apecme/javsp-web)
[![Docker Pulls](https://img.shields.io/docker/pulls/apecme/javsp-web)](https://hub.docker.com/r/apecme/javsp-web)

## 可以做什么

- 处理单个视频、整个文件夹和分 P 影片，查看任务进度、日志与失败原因。
- 为不同媒体库保存刮削预设，配置数据源、命名、图片和翻译；支持可视化表单与 `config.yml`。
- 定时扫描文件夹，连接多个 qBittorrent 下载器，在下载完成后自动刮削。
- 连接 Emby / Jellyfin，在整理完成后刷新媒体库。
- 用 AI 分析任务、查找资料、辅助制作爬虫，并按预设翻译标题和简介。

## 快速开始

### Windows

1. 从 [Releases](https://github.com/APecme/JavSP-Web/releases/latest) 下载 `JavSP-Web.exe`，放到固定文件夹。
2. 双击运行。程序会进入通知区域并打开浏览器；未自动打开时，访问 `http://127.0.0.1:8090/login`。
3. 首次账号和密码均为 `admin`。登录后在“系统设置 → 用户管理”修改密码。

配置与任务记录默认保存在程序旁的 `data` 文件夹。关闭浏览器不会退出程序；需要退出时使用通知区域菜单。

### Docker Compose

安装 Docker 与 Compose 后，新建文件夹，将以下内容保存为 `docker-compose.yml`。示例使用官方正式版镜像，无需本地构建。

```yaml
services:
  javsp-web:
    image: apecme/javsp-web:latest
    container_name: javsp-web
    restart: unless-stopped
    ports:
      - "8090:8090"
    environment:
      JAVSP_WEB_HOST: 0.0.0.0
      JAVSP_WEB_PORT: 8090
      JAVSP_WEB_TIMEZONE: Asia/Shanghai
      TZ: Asia/Shanghai
    extra_hosts:
      - "host.docker.internal:host-gateway"
    volumes:
      - ./data:/app/data
      - ./video:/video
```

将 `./video` 改为实际影片目录，例如 `/mnt/media:/video`；Windows Docker 可用 `D:/Videos:/video`。在配置文件所在目录执行：

```sh
docker compose config --quiet
docker compose up -d
```

打开 `http://服务器地址:8090/login`，用 `admin` / `admin` 登录并修改密码。本机部署可将服务器地址换成 `127.0.0.1`。

**网页中使用容器路径。** 例如宿主机的 `/mnt/media/待整理` 映射后应填写 `/video/待整理`。输入与输出目录都需要挂载；`./data` 保存账号、配置和任务记录，更新或重建容器时请保留。更多说明见[安装教程](https://apecme.github.io/JavSP-Web/guide-install.html)。

## 配置与日常使用

1. 在“刮削预设”检查数据源、输出目录和整理方式，先保存一个适合自己的预设。
2. 在“手动刮削”选择文件或文件夹，选定预设后启动。Windows 支持 Ctrl / Shift 多选文件；Docker 使用容器路径浏览器。
3. 在队列中查看扫描和刮削进度。打开任务详情查看失败原因、编辑资料或重试图片。
4. 单次任务结果符合预期后，再配置定时规则或下载完成自动刮削。

CloudDrive2、WebDAV 等挂载目录也可使用。目录较慢时查看扫描进度，避免重复提交；“停止扫描”会停止后续任务创建，正在等待挂载盘响应时可能需要稍候。已经创建的影片任务需单独停止。

目录中混有广告视频时，可在“扫描器”开启“仅扫描匹配影片分类”，并确认分类规则能识别需要保留的影片。STRM 文件可开启“STRM 忽略最小文件大小”。修改预设后，新任务使用新设置，已创建任务保留原设置。

“删除任务记录”不会撤销文件整理；需要恢复文件时，查看任务详情中是否提供“还原文件”。输出目录已有同名文件时，应先核对现有内容。更多操作见[刮削与整理教程](https://apecme.github.io/JavSP-Web/guide-scraping.html)。

### 自动化与外部服务

| 需要做什么 | 在哪里设置 |
|---|---|
| 定时扫描目录 | “自动刮削”添加规则，选择路径、预设和 Cron 时间；例如 `0 2 * * *` 表示应用时区的每天 02:00。同一规则上批任务未结束时会跳过本次执行。 |
| 下载完成后刮削 | 先在“系统设置”连接 qBittorrent，再配置下载完成规则；下载器与应用路径不同时，添加路径映射。 |
| 管理做种与限速 | “下载管理”设置接管范围、限速和做种条件；自动删种保留影片文件。仍需做种时，先核对整理方式是否影响原路径。 |
| 刷新媒体库 | “系统设置”添加 Emby / Jellyfin，选择媒体库，并按需开启刮削完成后自动扫描。 |
| 使用站点登录状态 | “系统设置 → CookieCloud”填写服务信息，测试后启用；Cookie 过期时需在浏览器重新登录并同步。 |

操作步骤见[自动化与集成教程](https://apecme.github.io/JavSP-Web/guide-automation.html)。

## AI 接入、刮削与翻译

管理员在“系统设置 → AI 接入”填写模型服务商、模型 API 地址、模型名称和 API 密钥，勾选 **启用 AI 刮削**，测试连接后保存。这是 AI 功能的总开关；具体预设是否用 AI 查资料或翻译，在预设中分别选择。

支持 OpenAI 兼容服务（含 DeepSeek、Ollama）及 Anthropic。API 地址按服务商说明填写，通常以 `/v1` 结尾；不要填写聊天网页地址。AI 对话需要模型支持工具调用。Docker 中应填写容器可访问的模型地址，`127.0.0.1` 指向容器自身。

### 对话与 AI 刮削

进入“AI 刮削”描述需求，例如“按原因归类最近失败的任务”或“查看这个番号的资料”。回复中的工具记录可核对查询结果。整理文件、修改预设、保存爬虫等操作会先显示预览，确认后才执行。

需要在任务中使用 AI 时，进入“刮削预设 → 爬虫”：

- 勾选“启用 AI 刮削”，允许当前预设使用 AI。
- 勾选“仅在爬虫失败时使用 AI”，先查普通爬虫，查不到必需资料时再用 AI；取消此项则直接使用 AI。

AI 查找公开资料需要在系统 AI 设置中开启联网搜索，可选择 Bing RSS 或 SearXNG。没有可核实的资料时会报告失败，不会凭空补齐封面。关闭联网搜索仍可分析已有任务和翻译已抓取资料。

制作爬虫时，可以直接把搜索页或详情页链接发给 AI。开启联网搜索后，AI 可读取页面 HTML、正文、链接和图片地址，并使用系统代理及 CookieCloud 中对应站点的登录信息。工具不执行 JavaScript；遇到登录失效或浏览器验证时，需要先处理站点访问问题。Cookie 只用于请求站点，不作为工具结果发送给模型。

### AI 翻译

系统总开关开启后，进入 **刮削预设 → 翻译器**，选择要翻译的标题、剧情简介，再勾选 **启用 AI 翻译** 并保存。使用该预设的新任务会将选中字段翻译为简体中文，沿用现有命名、NFO 和整理规则。

**AI 翻译与翻译引擎二选一。** 勾选 AI 翻译后，其他引擎及其设置会停用；取消勾选后，才能使用所选引擎。原来的引擎配置会保留，不需要重新填写。

AI 翻译使用系统设置中的模型，不需要联网搜索，也不需要开启预设“爬虫”中的 AI 刮削。系统 AI 关闭、模型出错或译文不合格时，任务会报错，不会改用其他引擎，也不会继续整理文件。标题、简介都未选中时，不翻译。

### 提示词与 Skills

“预设提示词”调整对话的回答方式，保存后从下一次提问生效。“项目 Skills”提供刮削、AI 翻译、使用爬虫、制作爬虫、更改设置和开发功能六份说明，可查看、编辑或添加。“恢复已移除的内置 Skills”会重新启用被移除的技能，保留已保存的自定义修改。

AI 翻译会读取 `javsp-translate` Skill；删除它后需要恢复才能继续翻译。对话提示词不会改变翻译所需的输出格式。“开发功能”需要能访问源码的外部编码工具，内置助手不能直接修改项目代码。

问题、工具资料和待翻译原文会发送到配置的模型服务。连接信息、会话与自定义 Skills 保存在数据目录中，备份时注意保护密钥。完整设置与示例见 [AI 教程](https://apecme.github.io/JavSP-Web/guide-ai.html)。

## 更新与备份

Docker 用户可在“系统设置 → 软件更新”检查和安装新版本。网页更新会短暂重启服务；恢复后检查页面显示的版本。自动检查默认开启，自动安装默认关闭。

**勾选“加入体验计划”会立即尝试安装体验版**，不必另外打开“自动更新”；安装失败时页面会说明原因。加入后继续接收体验版更新，运行体验版时该选项保持勾选。

网页更新只更换应用程序。若提示需要更新镜像，或使用的旧镜像不支持网页安装，先等待当前任务结束并备份数据，再在 Compose 文件所在目录执行（服务名沿用本教程的 `javsp-web`）：

```sh
docker compose pull javsp-web
docker compose up -d --force-recreate javsp-web
```

**从体验版回到正式版：** 在“系统设置 → 软件更新”取消“加入体验计划”，程序会保存设置并尝试安装当前正式版，不必等待更高版本。若正在刮削或安装失败，退出状态仍会保留，处理问题后可点击“立即检查”和“立即更新”重试。若提示需要更新镜像，将 Compose 中的镜像改为 `apecme/javsp-web:latest`，再执行上述两条命令。保留原有 `data` 挂载和文件夹，无需删除数据。重新登录后核对版本和更新通道。

旧版可能在换镜像后继续加载先前的网页更新。自动处理镜像切换需要**包含启动修复的新镜像**，仅做网页更新不能修复旧镜像。如果拉取结果仍是原来同一镜像，程序也会保留已通过网页安装的版本；要恢复镜像自带的正式版，请按[恢复正式版步骤](https://apecme.github.io/JavSP-Web/guide-maintenance.html#restore-stable)操作。页面显示的是实际运行的应用版本，只修改镜像标签名称或手填版本号不会将体验版变成正式版。

自行发布镜像时，本仓库的 `main` 分支工作流会写入 `bata.时间戳` 版本；即使只把镜像推送标签改成 `latest`，内置版本仍是体验版。正式版由 `vX.Y.Z` Git 标签触发正式发布工作流，同时生成对应版本镜像和 `latest`。

Windows EXE 退出后下载并替换程序，保留原 `data` 文件夹；源码运行需更新代码及依赖。这两种方式仅支持网页检查版本。

迁移或更新前，建议停机备份整个数据目录，影片文件另行备份。详细说明见[维护与排错教程](https://apecme.github.io/JavSP-Web/guide-maintenance.html)。

## 常见问题与反馈

| 现象 | 先检查 |
|---|---|
| 没有找到影片 | 输入路径、扩展名、最小大小、分类过滤及已有 NFO 跳过规则。Docker 还需检查目录挂载。 |
| 没有取得资料或缺少封面 | 番号是否正确、所选数据源是否收录；展开数据源日志，先测试单个爬虫。 |
| 403、超时或证书错误 | 预设代理、站点域名、系统时间及登录 Cookie。证书错误不要通过关闭 HTTPS 校验解决。 |
| 只有图片失败 | 在任务详情重试图片，或搜索、上传封面。 |
| 下载完成但未刮削 | 下载规则是否命中、路径映射是否正确，以及自动刮削执行记录。 |
| AI 翻译未生效 | 系统“启用 AI 刮削”、预设“启用 AI 翻译”、翻译字段、模型连接及 `javsp-translate` Skill。 |

完整日志位于 `data/task-logs/<任务ID>.log`；容器启动失败可运行 `docker compose logs --tail 100 javsp-web`。代理使用自签名证书时，按[网络排错说明](https://apecme.github.io/JavSP-Web/guide-scraping.html#crawlers)配置受信任证书。

反馈前请搜索 [已有 Issue](https://github.com/APecme/JavSP-Web/issues)，并附上版本、部署方式、操作步骤和脱敏日志。不要上传密钥、Cookie 或完整数据目录。

## 文档与贡献

欢迎改进文档、补充测试和提交 Pull Request。官网源文件位于 `docs/`，内置 Skills 位于 `javsp_web/skills/`，核心配置说明可查阅 [JavSP Wiki](https://github.com/Yuukiy/JavSP/wiki)。感谢 @usePattern 在 [PR #14](https://github.com/APecme/JavSP-Web/pull/14) 中贡献挂载盘批量刮削与多选方案。

修改前端、AI 设置、内置 Skills 或示例接口后，安装 PyYAML 并更新交互示例：

```sh
python scripts/build_demo.py
node tests/test_demo.cjs
```

示例使用模拟数据，不执行真实刮削、联网或更新。页面操作变化时同步更新 `docs/assets/guide/` 中的教程截图；Pages 工作流会构建并校验示例后发布。

## 许可

本项目包含 JavSP 核心，遵循 [GPL-3.0](./vendor/JavSP/LICENSE) 与 [Anti 996 License](https://github.com/996icu/996.ICU/blob/master/LICENSE_CN) 的相关条款。使用时请遵守当地法律、数据源服务条款及 JavSP 使用说明。
