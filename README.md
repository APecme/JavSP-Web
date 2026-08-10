![JavSP WEB](./javsp_web/web/assets/javsp-logo.png)

# JavSP WEB

JavSP 的本地 Web 控制台。用浏览器管理影片刮削、任务进度、下载器和媒体库。

当前版本：`1.1.01`

- 下载 Windows 版：[Releases](https://github.com/APecme/JavSP-Web/releases)
- Docker 镜像：[apecme/javsp-web](https://hub.docker.com/r/apecme/javsp-web)
- JavSP 原项目：[Yuukiy/JavSP](https://github.com/Yuukiy/JavSP)

## 能做什么

- 手动刮削单个视频或整个文件夹，查看进度和完整日志。
- 使用多个刮削预设，按界面表单配置，也可直接使用 `config.yml`。
- 定时自动刮削指定文件夹。
- 连接多个 qBittorrent 下载器，按标签或分类在下载完成后自动刮削。
- 连接 Emby 或 Jellyfin，在刮削完成后扫描媒体库并从任务详情播放。

## Windows 版

1. 在 [Releases](https://github.com/APecme/JavSP-Web/releases) 下载 `JavSP-Web.exe`。
2. 双击运行，程序会出现在 Windows 通知区域并自动打开登录页。
3. 打开失败时，访问 `http://127.0.0.1:8090/login`。

首次登录账号和密码均为 `admin`。登录后请立即在“系统设置”中修改密码。

## Docker 版

将本机的影片目录映射到容器内的 `/video`：

```powershell
docker run -d --name javsp-web --restart unless-stopped -p 8090:8090 `
  -v "${PWD}\data:/app/data" `
  -v "D:\Videos:/video" `
  apecme/javsp-web:latest
```

将 `D:\Videos` 改为实际影片目录，然后打开 `http://127.0.0.1:8090/login`。在 Docker 中填写路径时，使用容器路径，例如 `/video/Movies`。

## 基本使用

1. 在“刮削预设”检查默认预设，按需要新建其他预设。
2. 打开“手动刮削”，选择视频或文件夹并点击启动。
3. 在任务队列展开任务查看进度和日志；图片下载失败时可重新下载图片。
4. 需要定时处理时，在“自动刮削”添加 Cron 规则。例如 `0 2 * * *` 表示每天 02:00 执行。

## 可选功能

- **下载管理**：先在“系统设置”添加 qBittorrent 下载器，再设置接管、做种和下载完成自动刮削规则。
- **媒体服务器**：在“系统设置”添加 Emby 或 Jellyfin，测试连接后选择要同步的媒体库。
- **路径映射**：Docker 环境下，使用路径映射把下载器保存路径转换为容器内路径。

## 注意事项

- 刮削依赖公开数据站点，网络、代理和站点反爬策略会影响结果。
- qBittorrent 使用 Web UI 的账号密码连接。
- Docker、下载器与媒体服务器之间必须能互相访问。
- 请遵守当地法律法规、数据源服务条款和 [JavSP 文档](https://github.com/Yuukiy/JavSP/wiki)。
