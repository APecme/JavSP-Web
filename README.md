![JavSP WEB](./javsp_web/web/assets/javsp-logo.png)

# JavSP WEB

**JavSP 的 Web 控制台**

官网与使用文档：[apecme.github.io/JavSP-Web](https://apecme.github.io/JavSP-Web/)

JavSP WEB 基于 [JavSP](https://github.com/Yuukiy/JavSP)，用于从影片文件名识别番号、汇总多个站点的影片数据并生成媒体库可用的元数据。它提供浏览器界面，用于启动刮削、查看任务进度、管理配置预设，以及连接下载器和媒体服务器。

[![Latest release](https://img.shields.io/github/v/release/APecme/JavSP-Web)](https://github.com/APecme/JavSP-Web/releases/latest)
[![Docker Image](https://img.shields.io/docker/v/apecme/javsp-web?label=Docker&logo=docker)](https://hub.docker.com/r/apecme/javsp-web)
[![Docker Pulls](https://img.shields.io/docker/pulls/apecme/javsp-web)](https://hub.docker.com/r/apecme/javsp-web)
[![JavSP](https://img.shields.io/badge/core-JavSP-blue)](https://github.com/Yuukiy/JavSP)

## 功能特点

- [x] 自动识别影片番号，支持单个视频和整个文件夹。
- [x] 汇总多个站点的数据，生成 NFO、封面和剧照。
- [x] 在网页中查看任务状态、三阶段进度和完整日志。
- [x] 创建多个刮削预设，使用表单或完整 `config.yml` 配置。
- [x] 定时自动刮削指定文件夹。
- [x] 连接多个 qBittorrent 下载器，并在下载完成后自动刮削。
- [x] 连接 Emby 或 Jellyfin，在刮削完成后扫描媒体库。
- [x] Windows 托盘程序、Docker 和浏览器访问。

## 安装并运行

### Windows

1. 从 [Releases](https://github.com/APecme/JavSP-Web/releases) 下载 `JavSP-Web.exe`。
2. 双击运行。程序会出现在 Windows 通知区域，并自动打开登录页。
3. 未自动打开时，访问 `http://127.0.0.1:8090/login`。

### Docker

以下示例将本机影片目录映射到容器内的 `/video`：

```powershell
docker run -d --name javsp-web --restart unless-stopped -p 8090:8090 `
  -v "${PWD}\data:/app/data" `
  -v "D:\Videos:/video" `
  apecme/javsp-web:bata
```

将 `D:\Videos` 替换为实际影片目录，然后访问 `http://127.0.0.1:8090/login`。Docker 版中填写路径时使用实际挂载的容器路径，例如 `/video/Movies` 或 `/mnt/movies`。

### Docker Compose

新建 `docker-compose.yml`，填入以下内容：

```yaml
services:
  javsp-web:
    image: apecme/javsp-web:bata
    container_name: javsp-web
    restart: unless-stopped
    ports:
      - "8090:8090"
    volumes:
      - ./data:/app/data
      - ./video:/video
```

在该文件所在目录运行：

```powershell
docker compose up -d
```

影片放入 `./video`，或将 `./video` 改为本机的实际影片目录。网页中使用实际挂载的容器路径，例如 `/video/Movies` 或 `/mnt/movies`。默认时区为 `Asia/Shanghai`；可通过 `JAVSP_WEB_TIMEZONE` 和 `TZ` 覆盖。

## 使用

首次登录账号和密码均为 `admin`。登录后请立即在“系统设置”中修改密码。

软件开箱即用。基本流程如下：

1. 在“刮削预设”检查默认预设，按需要创建其他预设。
2. 在“手动刮削”选择视频或文件夹和预设，点击启动。
3. 在任务队列展开任务，查看进度、日志和失败原因；图片下载失败时可重新下载。
4. 需要定时处理时，在“自动刮削”添加 Cron 规则。例如 `0 2 * * *` 表示每天 02:00 执行。

### 下载器和媒体库

- 在“系统设置”添加 qBittorrent 下载器，测试连接后可在“下载管理”设置接管、下载/上传限速、做种和下载完成自动刮削规则。
- 在“系统设置”添加 Emby 或 Jellyfin，选择要同步的媒体库，并按需开启刮削完成后的自动扫描。
- 在“系统设置”配置 CookieCloud 服务地址、UUID 和密码；每次刮削任务启动时会同步 Cookie，用于需要登录凭据的网站。密码和 Cookie 不会在页面或接口响应中回显。
- Docker 环境使用路径映射，将下载器保存路径转换为容器内可访问的路径。
- 定时规则不会重叠执行。同一规则上一次刮削仍在排队、运行或重试图片时，下一次触发会跳过并写入运行记录。

JavSP 配置项说明和命名规则请参阅 [JavSP Wiki](https://github.com/Yuukiy/JavSP/wiki)。

## 问题反馈

任务日志按处理过程、数据源和图片下载分组，同一站点的重试及图片进度会原位更新。站点失败原因可展开查看，支持复制摘要；单个数据源失败不代表整部影片失败。

完整调试日志保存在 `data/task-logs/<任务ID>.log`，每个任务最多保留两份 2 MiB 日志，用于排查解析错误。对外分享前请脱敏。

JavDB、JavBus 的配置镜像若出现证书错误，会尝试对应官网一次并继续校验证书。

Docker 使用系统 CA 证书库并在启动时更新。若代理使用自签名根证书，可将可信的 PEM 格式 `.crt` 文件只读挂载到 `/usr/local/share/ca-certificates/` 后重启容器；自定义非 root 用户需在镜像构建时安装证书。证书错误也可能来自过期镜像域名或站点证书链，请检查域名及代理配置，不要关闭 HTTPS 证书校验。403 表示站点拒绝访问，请检查代理出口及该域名的 CookieCloud 登录状态；同步成功不代表所有站点均授权访问。

使用前请确认网络、代理和数据站点可用。遇到问题时，请附上任务日志、使用的部署方式和脱敏后的相关配置，并先搜索 [已有 Issue](https://github.com/APecme/JavSP-Web/issues)。

## 参与贡献

欢迎提交 Issue、改进文档、补充测试数据或发起 Pull Request。

## 许可与声明

本项目包含并依赖 JavSP 核心。JavSP 核心遵循 [GPL-3.0](./vendor/JavSP/LICENSE) 与 [Anti 996 License](https://github.com/996icu/996.ICU/blob/master/LICENSE_CN) 的相关条款。使用本项目时，请遵守当地法律法规、数据源服务条款及 JavSP 的使用说明。
