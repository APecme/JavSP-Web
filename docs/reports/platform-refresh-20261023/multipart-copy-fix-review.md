# 字母分 P 与 STRM 下载副本修复：待独立审核

本轮只修改工作区代码与测试，未部署、未重启容器、未修改运行实例配置。保留工作区其他已有改动。

## 修改清单

- `vendor/JavSP/javsp/multipart.py`：字母后缀解析、同身份验证、下载副本候选检查、严格 STRM 内容比较、安全诊断、共享过滤/分组。
- `vendor/JavSP/javsp/download_copy.py`（新增）：共享 helper 的兼容导出，供监控使用。
- `vendor/JavSP/javsp/file.py`：CLI scanner 使用共享副本/分片验证；保留 CLI 原有跨目录同番号拒绝边界；稳定结果排序。
- `javsp_web/tasks.py`：单文件副本转向原文件；批次过滤副本；将跳过提示保存到任务日志。
- `javsp_web/directory_watch.py`：持久化 duplicate/original/reason/content_hash；已确认副本不再进入任务；原件移走仍抑制未变化副本；同大小同 mtime 的内容变化可重评。
- `tests/test_multipart.py`：新增用户原例、四类分隔符、单独 B、副本孤本、BOM/换行、空/无效/不可读/异链、混合 A/B 副本、数字冲突、配置化识别、Web manifest 与提示回归。
- `tests/test_directory_watch.py`：新增持久跳过、移动原件、重启、同 stat 内容变化、稳定等待窗口、冲突及不可读原件回归。
- `vendor/JavSP/unittest/test_file.py`：将“缺号或不从 1 开始必须失败”两条旧断言更新为新需求的保留编号断言。

## 核心规则

- 末尾分隔符 `- _ . 空格` + 单字母，不区分大小写，A=1…Z=26；保留数字/CD/Part/PT/P 规则和清晰度后缀。
- 字母去除前后必须具有相同非空 scanner 媒体类型/番号；不识别无分隔符和多字母后缀。
- 末尾正整数 `(n)` 仅为副本候选，不充当分 P。孤立 `-B(1)` 可保留 part=2。
- 只自动跳过同目录、存在对应原件、可成功严格 UTF-8-sig 解码的有效单链接 STRM。只去 BOM、统一换行、忽略首尾空白；不改变 URL 大小写、转义和查询参数，不访问网络。
- 有效链接保守支持 http/https/rtsp/rtmp/ftp/smb/nfs；其他协议或多行播放列表不自动判重。
- 异链或不可读取时返回针对性冲突，不删源、不移动副本、不覆盖；日志不包含链接正文。
- 无括号关系的 A/B 即使链接相同也不判重；映射后编号冲突拒绝整组。
- Web 不跨目录合并；CLI 保留其原先跨目录同番号整组跳过边界。

## 用户原例任务清单（自动测试）

输入顺序 B、A -> 一个任务，manifest `[SAVR-619-A.strm, SAVR-619-B.strm]`，part_numbers `[1,2]`。

输入 `hhd800.com@AVSA-223.strm` 和 `hhd800.com@AVSA-223(1).strm`、相同链接 -> 一个任务，manifest 仅无括号原文件；副本留在原位，提示 `跳过重复副本：hhd800.com@AVSA-223(1).strm → hhd800.com@AVSA-223.strm`。

链接不同时 -> `重复下载候选冲突，保留文件：副本名 → 原文件名（链接内容不同）`。

## 实际验证命令与结果

在工作区隔离虚拟环境 `.venv-multipart` 安装测试依赖，没有修改全局 Python。使用 Python 3.14。

```sh
TMPDIR="$PWD" PYTHONDONTWRITEBYTECODE=1 .venv-multipart/bin/python -m unittest discover -s tests -p test_multipart.py
# 26 tests, OK
TMPDIR="$PWD" PYTHONDONTWRITEBYTECODE=1 .venv-multipart/bin/python -m unittest discover -s tests -p test_task_scans.py
# 24 tests, OK (skipped=1)
TMPDIR="$PWD" PYTHONDONTWRITEBYTECODE=1 .venv-multipart/bin/python -m unittest discover -s tests -p test_directory_watch.py
# 34 tests, OK (skipped=1)
TMPDIR="$PWD" PYTHONDONTWRITEBYTECODE=1 .venv-multipart/bin/python -m pytest vendor/JavSP/unittest/test_file.py -q
# 19 passed
```

四组共 103 项，101 通过、2 跳过、0 失败。另 Python 编译检查通过。

普通 `git diff --check` 受工作区已存在 CRLF 行尾噪声影响失败；本次跟踪文件采用 `git -c core.whitespace=cr-at-eol diff --check -- <修改路径>` 通过。没有清理其他已有行尾变化。

初次测试尝试缺 yaml/pip，之后建立工作区隔离 venv；Web HTTP 测试初次受 starlette 1.x/httpx2 缺失影响，安装兼容 starlette<1 和 httpx 后完整通过。CLI 初次揭示空白后缀/目录命名回归，已修正并复跑；两条与新规则直接相反的旧断言已显式更新。

## 风险与未验证

- 未运行真实挂载盘、Windows 或生产实例验收，未跑整个仓库全部测试。
- URL 协议采取保守白名单；不认识的链接不自动跳过，需人工处理。
- 内容比较与整理之间的外部改写竞态没有文件系统事务保证。
- 监控为副本候选读取内容计算 SHA256，远程目录大量副本可能增加读取开销；本轮未进行规模性能测试。
- CLI scanner 移除独立 common-prefix 分片 fallback，收敛到共享显式规则；除已覆盖 vendor scanner 回归外，非标准遗留命名仍需独立审核关注。
- CLI 跨目录规则依旧比 Web 更保守（跳过而不合并）；不新增跨目录去重。
- `.venv-multipart` 是本轮测试环境，不应纳入发布产物。

结论：提交独立审核，不宣称已获审批，不部署。
