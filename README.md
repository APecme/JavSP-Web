![JavSP](./image/JavSP.svg)

# JavSP-Web

**JavSP 的 Web 界面版本 - 汇总多站点数据的AV元数据刮削器**

JavSP-Web 是基于 [JavSP](https://github.com/Yuukiy/JavSP) 开发的 Web 界面版本，提供了完整的图形化操作界面，让您可以通过浏览器轻松管理刮削任务。

提取影片文件名中的番号信息，自动抓取并汇总多个站点数据的 AV 元数据，按照指定的规则分类整理影片文件，并创建供 Emby、Jellyfin、Kodi 等软件使用的元数据文件。

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
    build: .
    image: javsp-web:latest
    container_name: javsp-web
    restart: unless-stopped
    ports:
      - "8090:8090"  # 端口映射：宿主机端口:容器端口
    volumes:
      - ./data:/app/data      # 数据目录：配置、缓存、日志
      - ./video:/video        # 视频目录：容器内使用 /video
    entrypoint: ["/app/.venv/bin/server"]
```

#### 配置项说明

- **ports**: 端口映射
  - `8090:8090`：将容器的 8090 端口映射到宿主机的 8090 端口
  - 如需修改端口，将左侧端口号改为其他值，如 `8080:8090` 表示通过宿主机的 8080 端口访问

- **volumes**: 数据卷映射
  - `./data:/app/data`：将本地的 `data` 目录映射到容器内的 `/app/data`
    - 包含配置文件 `config.yml`
    - 包含任务日志和历史记录
    - 包含缓存数据
  - `./video:/video`：将本地的 `video` 目录映射到容器内的 `/video`
    - 这是 Web 界面中手动刮削的默认路径
    - 可根据实际情况修改为其他视频目录路径

- **restart**: 重启策略
  - `unless-stopped`：容器会在停止后自动重启，除非手动停止

- **environment**: 环境变量（可选）
  - 如需设置时区，可添加：
    ```yaml
    environment:
      - TZ=Asia/Shanghai
    ```

#### 自定义配置示例

如果需要修改视频目录路径或添加环境变量，可以这样配置：

```yaml
version: "3.9"

services:
  javsp-web:
    build: .
    image: javsp-web:latest
    container_name: javsp-web
    restart: unless-stopped
    ports:
      - "8090:8090"
    volumes:
      - ./data:/app/data
      - /path/to/your/videos:/video  # 修改为你的视频目录路径
    environment:
      - TZ=Asia/Shanghai              # 设置时区
    entrypoint: ["/app/.venv/bin/server"]
```

## 配置说明

### 基本配置

1. **首次运行**：首次启动时会自动创建默认配置文件 `data/config.yml`
2. **修改配置**：可以通过 Web 界面的"全局规则"页面修改配置，或直接编辑 `data/config.yml` 文件

## 使用方法

### 1. 手动刮削

1. 登录 Web 界面
2. 进入"手动刮削"页面
3. 浏览文件系统，选择要刮削的影片文件
4. （可选）选择自定义规则预设
5. 点击"开始刮削"按钮
6. 在任务日志中查看执行进度

### 2. 配置规则

1. 进入"全局规则"页面
2. 根据需要修改各个配置项：
   - **扫描设置**：文件扫描相关配置
   - **网络设置**：代理、重试、超时等
   - **爬虫设置**：选择使用的爬虫站点
   - **整理与元数据**：输出格式、NFO、封面、剧照等
   - **翻译设置**：标题和简介翻译配置
3. 点击"保存"按钮

### 3. 创建自定义规则

1. 在"手动刮削"页面点击"添加自定义规则"
2. 输入规则名称（必填）
3. 配置各项规则（默认继承全局规则）
4. 保存后可在"任务规则预设"下拉框中选择使用

### 4. 查看刮削历史

1. 进入"刮削历史"页面
2. 可以切换"列表"和"封面墙"两种视图
3. 点击封面可查看详细信息
4. 支持多选删除历史记录
5. 支持重新下载封面/剧照

### 5. 查看任务日志

1. 在"手动刮削"页面查看任务列表
2. 点击任务可展开/折叠日志
3. 支持复制日志和删除任务
4. 实时查看任务执行进度

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

## CI/CD 自动化流程

项目已配置 GitHub Actions，当您推送代码到 GitHub 时，会自动构建 Docker 镜像并推送到 Docker Hub。

### 配置 Docker Hub 认证

在 GitHub 仓库中配置以下 Secrets（Settings → Secrets and variables → Actions）：

1. **DOCKER_HUB_USERNAME**：您的 Docker Hub 用户名
2. **DOCKER_HUB_TOKEN**：您的 Docker Hub Access Token
   - 创建方法：登录 Docker Hub → Account Settings → Security → New Access Token
   - 权限选择：Read & Write
   - 复制生成的 Token 并添加到 GitHub Secrets

### 工作流触发条件

- **自动触发**：
  - 推送到 `main` 或 `master` 分支
  - 创建版本标签（如 `v1.0.0`）
- **手动触发**：
  - 在 GitHub Actions 页面点击 "Run workflow"

### 构建的镜像标签

- `latest`：最新版本（main/master 分支）
- `v1.0.0`：版本标签（如 `git tag v1.0.0 && git push --tags`）
- `v1.0`：主版本号
- `v1`：大版本号
- `main-abc1234`：分支名 + commit SHA

### 使用预构建的镜像

配置好 CI/CD 后，您可以直接使用 Docker Hub 上的预构建镜像：

```yaml
# docker-compose.yml
services:
  javsp-web:
    image: your-dockerhub-username/javsp-web:latest  # 替换为您的 Docker Hub 用户名
    # build: .  # 注释掉本地构建
```

然后运行：
```bash
docker-compose pull
docker-compose up -d
```

### 提交代码和创建版本

```bash
# 提交代码（会自动触发构建）
git add .
git commit -m "描述你的更改"
git push origin main

# 创建版本标签（会触发构建并推送带版本号的镜像）
git tag v1.0.0
git push --tags
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
