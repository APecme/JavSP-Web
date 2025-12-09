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

### 主要配置项

#### 扫描设置

```yaml
scanner:
  # 扫描目录（留空时在 Web 界面中手动选择）
  input_directory: null
  # 视频文件扩展名
  filename_extensions: [.mp4, .mkv, .avi, ...]
  # 最小文件大小（小于此大小的文件将被忽略）
  minimum_size: 232MiB
```

#### 网络设置

```yaml
network:
  # 代理服务器（如需要）
  proxy_server: null
  # 重试次数
  retry: 3
  # 超时时间
  timeout: PT10S
```

#### 爬虫设置

```yaml
crawler:
  # 使用的爬虫列表
  selection:
    normal: [airav, avsox, javbus, javdb, javlib, ...]
```

#### 整理设置

```yaml
summarizer:
  # 输出文件夹模式
  path:
    output_folder_pattern: "{number} {title}"
  # NFO 文件名模式
  nfo:
    basename_pattern: "movie"
  # 封面文件名
  cover:
    basename_pattern: "poster"
  # 剧照设置
  extra_fanarts:
    enabled: yes
```

### 环境变量

可以通过环境变量设置以下选项：

- `TZ`：时区设置（默认：`Asia/Shanghai`）
- `JAVSP_DATA_DIR`：数据目录路径（默认：`./data`）

### Web 界面配置

1. **登录账号**：
   - 默认用户名和密码在首次启动时设置
   - 可通过"账号与安全"页面修改

2. **端口配置**：
   - 默认端口：`8090`
   - 修改 `javsp/server.py` 中的端口号可更改

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

## 常见问题

### Q: 如何修改默认端口？

A: 编辑 `javsp/server.py` 文件，修改 `uvicorn.run(app, host="0.0.0.0", port=8090)` 中的端口号。

### Q: 如何修改视频目录？

A: 在 Docker Compose 中修改 `volumes` 配置，或在 Web 界面中手动选择路径。

### Q: 忘记登录密码怎么办？

A: 删除 `data/web_settings.json` 文件，重新启动服务后使用默认账号登录。

### Q: 如何查看详细的执行日志？

A: 在任务日志中展开对应的步骤，可以查看详细的执行信息。

### Q: 支持哪些视频格式？

A: 默认支持 `.mp4`, `.mkv`, `.avi`, `.mov`, `.wmv` 等常见格式，可在配置文件中自定义。

## 开发与贡献

### 本地开发

```bash
# 克隆项目
git clone git@github.com:APecme/JavSP-Web.git
cd JavSP-Web

# 安装开发依赖
poetry install

# 启动开发服务器
poetry run python -m javsp.server
```

### 提交代码

```bash
# 添加更改
git add .

# 提交更改
git commit -m "描述你的更改"

# 推送到 GitHub
git push origin main
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
