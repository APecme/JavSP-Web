![JavSP WEB](./javsp_web/web/assets/javsp-logo.png)

# JavSP WEB

JavSP WEB 是 [JavSP](https://github.com/Yuukiy/JavSP) 的本地 Web 控制端。它将刮削、预设配置、下载任务接管、媒体库联动和用户管理分别放在独立工作区中，便于在浏览器、Docker 或 Windows 托盘程序中管理本机的 JavSP 任务。

当前版本：`1.1.01`

## 功能特点

### 刮削工作区

- 手动输入目录或单个视频文件创建刮削任务。
- Windows EXE 可调用系统文件/目录选择窗口；Docker 环境可从 `/video` 映射目录中选择路径。
- 目录中的多个视频会拆分为独立任务，并按照预设中的并发数依次调度。
- 任务队列提供状态、路径、预设、时间、结构化刮削进度、可折叠日志、日志复制、停止、删除和失败图片重新下载。
- 概览使用已完成任务的封面墙；详情中可查看封面、剧照与已汇总的影片数据。

### 预设与配置

- 支持多个刮削预设，内置默认预设不可删除，用户创建的预设可从预设列表删除。
- 默认使用按 `config.yml` 分类的表单：扫描、网络、爬虫、文件夹整理、替代文本、图片、自定义、翻译器和其他。
- 每个字段显示中文名称、原始配置路径、说明和备注；布尔值使用“是/否”选择。
- 可在表单与完整 `config.yml` 之间切换，保存时验证 YAML 和 JavSP 配置合法性。
- 命名规则字段提供可复制的变量提示。

### 自动化与下载管理

- 定时自动刮削：为指定目录和预设创建 Cron 规则，支持立即运行、启停、编辑和全部运行记录。
- 每次定时运行保留关联任务；任务日志和手动刮削一样可按任务折叠查看及复制。
- 支持添加多个 qBittorrent 下载器，通过账号密码验证 Web API。
- 下载管理按下载器分标签页显示接管任务，可配置全局分享率、做种时长、非活跃时长和自动删种。
- 下载完成自动刮削支持多个规则，可按标签和分类匹配预设。
- 路径映射可将 qBittorrent 的下载路径转换为 JavSP WEB 容器中的路径。

### 系统与媒体库

- 管理员可新增、编辑和删除用户；新密码必须输入两次确认。
- 支持多个 Emby 或 Jellyfin 媒体服务器，保存前验证连接并选择管理的媒体库。
- 刮削完成后可按设置延迟扫描指定媒体库；任务详情封面可直接打开可播放的媒体库条目。
- 登录页与主界面显示当前版本号。

## 项目结构

| 路径 | 说明 |
| --- | --- |
| `javsp_web/` | FastAPI 服务、任务调度和 Web 界面 |
| `vendor/JavSP/` | 随项目分发的 JavSP 核心代码 |
| `data/` | 运行时用户、会话、预设、任务、下载器与媒体服务器数据 |
| `build-windows.ps1` | Windows 单文件 EXE 构建脚本 |
| `docker-compose.yml` | Docker Compose 部署配置 |

`data/` 为持久化目录，请保留并备份。任务会使用独立配置快照，因此后续修改预设不会改变已排队任务。

## 本地运行

### Python

需要 Python 3.11 或更新版本。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m javsp_web.server
```

打开 `http://127.0.0.1:8090/login`。首次登录账号为 `admin`，密码为 `admin`；登录后请立刻在“系统设置”中修改。

### Windows 托盘 EXE

```powershell
.\build-windows.ps1
```

构建产物为 `dist\JavSP-Web.exe`。启动后程序只保留一个实例，显示在 Windows 通知区域，并打开本机登录页。退出托盘菜单只会停止服务，不会删除 `data/` 中的配置和任务记录。

## Docker Compose 部署

```powershell
docker compose up -d --build
```

默认访问地址为 `http://127.0.0.1:8090/login`。当前 `docker-compose.yml` 会持久化数据，并将宿主机的 `./video` 映射到容器内 `/video`：

```yaml
services:
  javsp-web:
    ports:
      - "8090:8090"
    volumes:
      - ./data:/app/data
      - ./video:/video
```

将待处理视频放入 `./video`，或把该卷替换为实际媒体目录。Docker 内的手动刮削、定时规则和路径映射都必须使用容器可访问的路径，例如 `/video/Movies`。

停止服务但保留数据：

```powershell
docker compose down
```

## 使用说明

1. 登录后在“刮削预设”中检查默认配置，或创建适合不同片源的预设。
2. 在“手动刮削”中选择目录/文件和预设，然后启动任务。
3. 在任务队列展开任务查看三个阶段的进度和完整日志；失败的封面或剧照可使用“重新下载图片”。
4. 需要自动执行时，在“自动刮削”创建 Cron 规则。示例：`0 2 * * *` 表示每天 02:00。
5. 需要接管下载时，先在“系统设置”添加并测试 qBittorrent 下载器，再在“下载管理”设置接管、做种和自动刮削规则。
6. 需要媒体库联动时，在“系统设置”添加 Emby 或 Jellyfin，测试连接、选择媒体库并按需开启完成后自动扫描。

## 注意事项

- 本项目需要网络访问多个公开数据源；站点可用性、反爬策略和返回内容会影响刮削结果。
- qBittorrent 使用原生 Web API 的账号密码认证。请填写可从 JavSP WEB 运行环境访问的服务地址。
- Docker、qBittorrent 和媒体服务器不在同一网络时，应配置可互相访问的地址、端口和路径映射。
- 请遵守当地法律法规、数据源的服务条款以及 [JavSP 项目文档](https://github.com/Yuukiy/JavSP/wiki)。

## 致谢

- [Yuukiy/JavSP](https://github.com/Yuukiy/JavSP) 提供核心刮削能力与配置规则。
- [APecme/JavSP-Web](https://github.com/APecme/JavSP-Web) 为本项目参考的公开仓库与发布入口。
