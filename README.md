![JavSP](./image/JavSP.svg)

# JavSP-Web

**JavSP 的 Web 界面版本 - 汇总多站点数据的AV元数据刮削器**

JavSP-Web 是基于 [JavSP](https://github.com/Yuukiy/JavSP) 开发的 Web 界面版本，提供了完整的图形化操作界面，让您可以通过浏览器轻松管理刮削任务。

提取影片文件名中的番号信息，自动抓取并汇总多个站点数据的 AV 元数据，按照指定的规则分类整理影片文件，并创建供 Emby、Jellyfin、Kodi 等软件使用的元数据文件。

[![Version](https://img.shields.io/badge/version-1.0.1-blue)](https://github.com/APecme/javsp-web/releases/tag/v1.0.1)
[![Docker Image](https://img.shields.io/docker/v/apecme/javsp-web?label=Docker&logo=docker)](https://hub.docker.com/r/apecme/javsp-web)
[![Docker Pulls](https://img.shields.io/docker/pulls/apecme/javsp-web)](https://hub.docker.com/r/apecme/javsp-web)
![License](https://img.shields.io/github/license/APecme/JavSP-Web)
![Python 3.10](https://img.shields.io/badge/python-3.10+-green.svg)
[![原项目](https://img.shields.io/badge/原项目-JavSP-blue)](https://github.com/Yuukiy/JavSP)
[![本项目](https://img.shields.io/badge/本项目-JavSP--Web-green)](https://github.com/APecme/JavSP-Web)

## 功能特点

### Web 界面功能

- ✅ **手动刮削**：通过文件浏览器选择影片文件，按顺序执行刮削任务
- ✅ **监控刮削**：监控指定目录，自动处理新添加的影片文件
- ✅ **定时刮削**：按计划定期触发刮削任务
- ✅ **全局规则配置**：通过 Web 界面配置扫描、网络、爬虫、整理、翻译等规则
- ✅ **自定义规则**：创建多个规则预设，针对不同需求使用不同配置
- ✅ **刮削历史**：查看所有刮削任务的记录，支持列表和封面墙两种视图
- ✅ **任务日志**：实时查看任务执行日志，支持展开/折叠、复制、删除
- ✅ **剧照预览**：查看剧照图片，支持全屏预览和左右翻页
- ✅ **下载状态**：显示封面和剧照的下载成功/失败状态
- ✅ **账号安全**：支持修改登录用户名和密码


## 项目链接

- **原项目（JavSP）**：https://github.com/Yuukiy/JavSP
- **本项目（JavSP-Web）**：https://github.com/APecme/JavSP-Web

## 安装与运行

### 使用 Docker Compose 部署

#### 1. 克隆项目

```bash
git clone https://github.com/APecme/JavSP-Web.git
cd JavSP-Web
```

#### 2. 创建必要的目录

```bash
mkdir -p data video
```

#### 3. 启动服务

```bash
# 启动服务（后台运行）
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

#### 4. 访问 Web 界面

服务启动后，访问 **http://localhost:8090** 即可使用 Web 界面。

**默认登录信息**：
- 首次启动时会提示设置用户名和密码
- 可在"账号与安全"页面修改登录信息

#### 5. 更新服务

```bash
# 拉取最新代码
git pull

# 重新构建并启动
docker-compose up -d --build
```

#### 6. 使用 Docker Hub 镜像（推荐）

项目已配置 GitHub Actions 自动构建并推送镜像到 Docker Hub，您可以直接使用预构建的镜像：

```bash
# 修改 docker-compose.yml，使用 Docker Hub 镜像
# 将 build: . 改为 image: your-dockerhub-username/javsp-web:latest

# 然后直接启动
docker-compose pull
docker-compose up -d
```

**Docker Hub 镜像地址**：`your-dockerhub-username/javsp-web:latest`

> **注意**：需要将 `your-dockerhub-username` 替换为您的 Docker Hub 用户名

### Docker Compose 配置说明

`docker-compose.yml` 文件配置如下：

```yaml
version: "3.9"

services:
  javsp-web:
    image: apecme/javsp-web:latest
    container_name: javsp-web
    restart: unless-stopped
    ports:
      - "8090:8090"
    volumes:
      - ./data:/app/data
      - ./video:/video
    entrypoint: ["/app/.venv/bin/server"]

```

#### 配置项说明

  - 如需设置时区，可添加：
    ```yaml
    environment:
      - TZ=Asia/Shanghai
    ```

## 目录结构

```
JavSP-Web/
├── data/                  # 数据目录（配置、缓存、日志）
│   ├── config.yml        # 主配置文件
│   ├── tasks/            # 任务相关数据
│   │   ├── manual.json   # 手动任务配置
│   │   └── manual_rules.json  # 自定义规则
│   └── history.jsonl     # 刮削历史记录
├── video/                # 视频文件目录（示例）
├── javsp/                # 核心代码
│   ├── webapp/           # Web 应用
│   │   ├── index.html    # 前端界面
│   │   ├── tasks.py      # 任务管理
│   │   └── ...
│   ├── server.py         # Web 服务器入口
│   └── ...
├── docker-compose.yml    # Docker Compose 配置
├── Dockerfile            # Docker 镜像构建文件
└── README.md            # 本文件
```

## 许可

此项目的所有权利与许可受 GPL-3.0 License 与 [Anti 996 License](https://github.com/996icu/996.ICU/blob/master/LICENSE_CN) 共同限制。此外，如果你使用此项目，表明你还额外接受以下条款：

- 本软件仅供学习 Python 和技术交流使用
- 请勿在微博、微信等墙内的公共社交平台上宣传此项目
- 用户在使用本软件时，请遵守当地法律法规
- 禁止将本软件用于商业用途

## 致谢

- 感谢 [Yuukiy](https://github.com/Yuukiy) 开发了优秀的 [JavSP](https://github.com/Yuukiy/JavSP) 项目
- 本项目基于 JavSP 开发，保留了所有核心功能，并添加了 Web 界面支持

---

**注意**：本项目是 JavSP 的 Web 界面版本，核心刮削功能完全继承自原项目。如有问题，请先查看 [原项目文档](https://github.com/Yuukiy/JavSP/wiki)。
