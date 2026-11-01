<div align="center">

<img src="./javsp_web/web/assets/javsp-logo.png" alt="JavSP WEB Logo" width="120" height="120">

# JavSP WEB

**影片信息刮削与媒体库管理**

[![Release](https://img.shields.io/github/v/release/APecme/JavSP-Web?label=Release&color=ff5c35&style=flat-square)](https://github.com/APecme/JavSP-Web/releases/latest)
[![Docker](https://img.shields.io/badge/Docker-apecme%2Fjavsp--web-2496ED?logo=docker&logoColor=white&style=flat-square)](https://hub.docker.com/r/apecme/javsp-web)
[![Windows](https://img.shields.io/badge/Windows-EXE-0078D4?style=flat-square)](https://github.com/APecme/JavSP-Web/releases/latest/download/JavSP-Web.exe)
[![License](https://img.shields.io/badge/License-GPL--3.0-263146?style=flat-square)](./vendor/JavSP/LICENSE)

**[在线体验](https://apecme.github.io/JavSP-Web/demo.html) · [使用文档](https://apecme.github.io/JavSP-Web/docs.html) · [下载正式版](https://github.com/APecme/JavSP-Web/releases/latest) · [反馈问题](https://github.com/APecme/JavSP-Web/issues)**

</div>

<div align="center">

> **把影片文件，变成漂亮的媒体库。**
>
> 识别番号、刮削资料、生成 NFO 与图片，再按你的规则整理文件。<br>
> 在封面墙浏览收藏，用评论交流观影感受，用 AI 辅助刮削与翻译。
>
> **Windows EXE · Docker / NAS · 明亮／黑暗主题 · 浏览器访问**

</div>

---

JavSP WEB 基于 [JavSP](https://github.com/Yuukiy/JavSP) 构建，将影片刮削、文件整理和媒体库浏览集中到一个 Web 界面。无论是整理单部影片，还是管理 NAS 上的收藏，都可以在浏览器中完成。

**[在线体验 →](https://apecme.github.io/JavSP-Web/demo.html)** 无需安装，先看看界面和主要功能。示例使用模拟数据，刷新后恢复初始状态。

## 功能介绍

### 🎬 影片刮削与文件整理

- 自动识别番号，从多个资料源补全片名、女优、发行日期和简介，下载封面、剧照并生成 NFO。
- 支持单部与批量整理、多 P 影片归档，可自定义目录和命名规则，让媒体库保持统一。

### 🖼️ 片库与影片详情

- 以封面墙展示收藏，按女优、片商、媒体库或年份浏览，支持搜索、排序与批量管理。
- 整合 Gfriends 女优资料，方便查看已有收藏、浏览更多女优。
- 在详情页查看和编辑影片资料、封面与剧照。支持明亮／黑暗主题，隐私模式可模糊封面与剧照。

### 💬 评论与互动

- 在影片下分享观影感受，点赞、回复其他人的评论，在个人中心管理自己的发言和头像。
- 支持 Markdown 排版，可通过时间标签标记想讨论的影片片段。

### ✨ AI 助手与翻译

- 接入自己的模型服务，辅助查找影片资料、刮削信息，翻译标题与简介。
- 通过对话查询任务、分析失败原因，处理媒体库整理中的问题。

### ⚙️ 自动化与任务管理

- 联动 qBittorrent，下载完成后自动刮削；也可定时扫描目录，持续整理新影片。
- 为不同整理需求保存预设，常用规则无需重复设置。
- 随时查看任务进度和日志，重试失败图片，追踪每次整理的结果。

## 快速开始

### Docker

将 `/your/videos` 替换为你的影片目录，执行：

```sh
docker run -d --name javsp-web --restart unless-stopped -p 8090:8090 -v "./data:/app/data" -v "/your/videos:/video" apecme/javsp-web:latest
```

打开 `http://服务器地址:8090`。配置与任务保存在 `./data`，程序内的影片路径使用 `/video`。

### Windows

从 **[Releases 下载 JavSP-Web.exe](https://github.com/APecme/JavSP-Web/releases/latest/download/JavSP-Web.exe)**，放入独立文件夹后双击运行，浏览器访问 `http://127.0.0.1:8090`。升级时替换 EXE，并保留旁边的 `data` 文件夹。

首次登录账号与密码均为 `admin`，登录后请在“系统设置 → 用户管理”中修改密码。更多配置请查看 **[完整使用文档](https://apecme.github.io/JavSP-Web/docs.html)**。

## 反馈与贡献

欢迎通过 [Issues](https://github.com/APecme/JavSP-Web/issues) 反馈问题或建议，也欢迎提交 Pull Request。反馈时请附上版本、部署方式、复现步骤和脱敏日志。

## 致谢与许可

感谢 [Yuukiy / JavSP](https://github.com/Yuukiy/JavSP) 提供刮削核心，以及 [Gfriends](https://github.com/gfriends/gfriends) 项目提供的女优资料与头像资源。

项目包含 JavSP 核心，遵循 [GPL-3.0](./vendor/JavSP/LICENSE) 与 [Anti 996 License](https://github.com/996icu/996.ICU/blob/master/LICENSE_CN) 的相关条款。

## 开发调研

- [热片页面说明](./docs/hot-page.md)：全部／有码／无码、最新／最热、30 站批量连接检测及接入范围。
- [热片来源调研（30 站概览与页面建设建议）](./docs/hot-sources/README.md)：第一阶段调研档案；当前实现以热片页面说明为准。
