![JavSP WEB](./javsp_web/web/assets/javsp-logo.png)

# JavSP WEB

在浏览器中刮削影片资料、整理媒体文件并管理媒体库。JavSP WEB 基于 [JavSP](https://github.com/Yuukiy/JavSP)，支持 Windows、Docker 和 NAS 部署。

完整的安装、配置、刮削、AI、自动化、故障排查和接口说明，请查看官网文档：

## [打开 JavSP WEB 官网文档](https://apecme.github.io/JavSP-Web/)

## 主要功能

- 识别番号，调用多个资料源获取标题、演员、剧情、封面和剧照。
- 处理单个视频、文件夹和批量任务，查看进度、日志与失败原因。
- 在封面墙浏览影片、查看资料和剧照，开启隐私模式模糊图片。
- 在个人中心选择头像，用用户名和 6 位 PIN 创建匿名评论身份；可跨设备查看自己的评论，支持点赞和安全验证。
- 使用刮削预设管理扫描、命名、NFO、图片和翻译设置。
- 定时扫描目录，连接 qBittorrent，并在下载完成后自动刮削。
- 连接 Emby / Jellyfin，整理完成后刷新媒体库。
- 支持 AI 刮削、AI 翻译、上下文自动压缩和模型列表获取。
- 支持 CookieCloud、代理、路径映射、封面重试与任务文件还原。

## 快速开始

### Windows

1. 从 [Releases](https://github.com/APecme/JavSP-Web/releases/latest) 下载 `JavSP-Web.exe`。
2. 双击运行，浏览器打开 `http://127.0.0.1:8090/login`。
3. 首次使用账号和密码均为 `admin`，登录后立即在“系统设置 → 用户管理”修改密码。

配置和任务记录默认保存在程序旁的 `data` 文件夹。升级时保留该文件夹即可。

### Docker Compose

安装 Docker 和 Compose，在空目录创建 `docker-compose.yml`：

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

把 `./video` 改成影片目录后执行：

```sh
docker compose up -d
```

访问 `http://服务器地址:8090/login`，使用 `admin` / `admin` 登录并修改密码。容器内路径应填写映射后的路径，例如宿主机 `/mnt/media` 对应 `/video`。

通过反向代理提供 HTTPS 时，在环境变量 `JAVSP_WEB_TRUSTED_PROXIES` 中配置代理连接到应用时的实际源 IP（多个 IP 用逗号分隔；默认不信任代理）。代理必须覆盖客户端传入的 `X-Real-IP` 和 `X-Forwarded-Proto`，分别填写真实客户端 IP 和外部协议。应用仅信任这些指定来源，并为 HTTPS 登录设置 Secure Cookie；直接 HTTP 登录仍可用。使用自定义 Uvicorn 启动命令时，须加 `--no-proxy-headers`，以保留应用校验所需的真实连接来源。

登录失败限制为每 5 分钟每 IP 30 次、每用户名 10 次，超限返回 429 和 `Retry-After`。成功登录不消耗失败额度，计数保存在当前进程内，重启会清零；当前单进程部署适用，多进程或多副本部署须先改用共享限流存储。

## 贡献

欢迎提交 Issue、改进文档、补充测试或提交 Pull Request。请先搜索已有 Issue，并在反馈中附上版本、部署方式、复现步骤和脱敏日志；不要上传密钥、Cookie 或完整数据目录。

```sh
python -m unittest discover -s tests -v
python scripts/build_demo.py
node tests/test_demo.cjs
```

官网文档源文件位于 `docs/`，内置 Skills 位于 `javsp_web/skills/`。提交前请同步更新受影响的文档和示例。

项目包含 JavSP 核心，遵循 [GPL-3.0](./vendor/JavSP/LICENSE) 与 [Anti 996 License](https://github.com/996icu/996.ICU/blob/master/LICENSE_CN) 的相关条款。
