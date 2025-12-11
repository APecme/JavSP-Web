import io
import json
import logging
import os
import re
import shutil
import sys
import threading
import time
import subprocess
import pty
import select
import struct
import fcntl
import termios
import base64
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any

# 获取时区，默认使用Asia/Shanghai，可通过TZ环境变量修改
def get_local_timezone():
    """获取本地时区，默认Asia/Shanghai，可通过TZ环境变量修改"""
    tz_name = os.environ.get('TZ', 'Asia/Shanghai')
    try:
        import zoneinfo
        return zoneinfo.ZoneInfo(tz_name)
    except ImportError:
        # Python < 3.9 使用pytz
        try:
            import pytz
            return pytz.timezone(tz_name)
        except ImportError:
            # 如果都没有，使用UTC
            return timezone.utc

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field

from javsp.__main__ import RunNormalMode, import_crawlers
from javsp.config import Cfg
from javsp.datatype import Movie
from javsp.file import scan_movies
from javsp.lib import resource_path
from .auth import get_current_user, UserInfo


class TaskType(str, Enum):
    manual = "manual"


class TaskStatus(str, Enum):
    pending = "PENDING"
    running = "RUNNING"
    succeeded = "SUCCEEDED"
    failed = "FAILED"


class ManualTaskCreate(BaseModel):
    input_directory: str = Field(..., description="要刮削的目录（容器内路径，例如 /video）")
    profile: Optional[str] = Field("default", description="任务规则预设名称，占位字段，当前仅支持 default")


class TaskModel(BaseModel):
    id: str  # 改为字符串类型，基于刮削路径+时间戳
    type: TaskType
    status: TaskStatus
    input_directory: str
    profile: str
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    movie_count: Optional[int] = None
    message: Optional[str] = None


class TaskLogResponse(BaseModel):
    id: str  # 改为字符串类型
    status: TaskStatus
    lines: List[str]


class HistoryItem(BaseModel):
    id: int
    task_id: str  # 改为字符串类型
    type: TaskType
    created_at: datetime
    dvdid: Optional[str] = None
    cid: Optional[str] = None
    save_dir: Optional[str] = None
    display_name: Optional[str] = None
    # 源文件列表（原始视频文件路径）
    source_files: Optional[List[str]] = None
    # 整理后的 basename（不含扩展名）
    target_basename: Optional[str] = None
    # NFO / 封面 / fanart / 剧照目录等路径，供前端展示刮削结果
    nfo_file: Optional[str] = None
    poster_file: Optional[str] = None
    fanart_file: Optional[str] = None
    extrafanart_dir: Optional[str] = None
    # 封面和剧照下载信息
    cover_urls: Optional[List[str]] = None  # 封面下载链接列表
    cover_download_success: Optional[bool] = None  # 封面下载是否成功
    cover_download_count: Optional[int] = 0  # 封面下载成功数量
    fanart_urls: Optional[List[str]] = None  # 剧照下载链接列表
    fanart_download_success: Optional[bool] = None  # 剧照下载是否成功
    fanart_download_count: Optional[int] = 0  # 剧照下载成功数量
    fanart_download_failed_count: Optional[int] = 0  # 剧照下载失败数量
    fanart_download_results: Optional[List[bool]] = None  # 每个剧照的下载状态列表 [True, False, True, ...]
    used_crawlers: Optional[List[str]] = None  # 使用的爬虫列表


class FileEntry(BaseModel):
    """用于前端 /videode 资源管理器的简易文件条目。"""

    name: str
    path: str
    is_dir: bool
    size: Optional[int] = None


_tasks: Dict[str, TaskModel] = {}
_task_logs: Dict[str, List[str]] = {}
_task_streams: Dict[str, str] = {}
_task_lock = threading.Lock()
_task_procs: Dict[str, subprocess.Popen] = {}
_history: List[HistoryItem] = []
_history_lock = threading.Lock()
_history_id_seq = 0
# 历史记录文件落盘在 data/history.jsonl，下挂载到宿主机的 /app/data 目录，便于持久保存
_HISTORY_FILE = Path(resource_path("data/history.jsonl"))
# 任务日志文件目录，用于持久化任务日志
_TASK_LOGS_DIR = Path(resource_path("data/task_logs"))
_TASK_LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ANSI 转义序列（颜色、光标控制等），用于清理子进程输出中的控制码，便于后续基于文本做匹配
_ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def set_winsize(fd: int, row: int, col: int, xpix: int = 0, ypix: int = 0) -> None:
    """设置伪终端窗口大小，避免 pretty_errors 等库拿到 0 宽度导致异常。

    在 Docker / 无真实 TTY 的环境下，显式设置终端尺寸，可以让 tqdm、pretty_errors 等
    正确计算进度条长度和换行位置。
    """

    winsize = struct.pack("HHHH", row, col, xpix, ypix)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)


def _load_history() -> None:
    """从本地 JSONL 文件加载历史记录到内存。"""

    global _history, _history_id_seq
    try:
        text = _HISTORY_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    except OSError:
        return

    items: List[HistoryItem] = []
    max_id = 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            item = HistoryItem(**data)
        except Exception:
            # 单条历史记录解析失败时跳过，避免影响整体加载
            continue
        items.append(item)
        try:
            if item.id and item.id > max_id:
                max_id = item.id
        except Exception:
            continue

    with _history_lock:
        _history = items
        _history_id_seq = max_id


def _next_history_id() -> int:
    global _history_id_seq
    with _history_lock:
        _history_id_seq += 1
        return _history_id_seq


def _append_history_item(item: HistoryItem) -> None:
    """将单条历史记录追加到内存与 JSONL 文件。"""

    with _history_lock:
        _history.append(item)
        try:
            _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            try:
                data = item.model_dump(mode="json")  # type: ignore[attr-defined]
            except AttributeError:
                # 兼容 Pydantic v1
                data = json.loads(item.json(ensure_ascii=False))
            line = json.dumps(data, ensure_ascii=False)
            with _HISTORY_FILE.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            # 历史记录落盘失败时不影响任务本身
            pass


_load_history()


def _load_task_logs() -> None:
    """从本地文件加载历史任务日志到内存。"""
    global _task_logs, _task_streams
    try:
        if not _TASK_LOGS_DIR.exists():
            return
        for log_file in _TASK_LOGS_DIR.glob("task_*.log"):
            try:
                # 从文件名提取任务ID（现在是字符串格式）
                task_id = log_file.stem.replace("task_", "")
                # 读取日志文件
                stream = log_file.read_text(encoding="utf-8")
                # 按行分割并过滤空行
                lines = [line.rstrip() for line in stream.splitlines() if line.strip()]
                with _task_lock:
                    _task_logs[task_id] = lines
                    _task_streams[task_id] = stream
            except (ValueError, OSError):
                # 跳过无法解析的文件
                continue
    except Exception:
        # 加载失败不影响启动
        pass


_load_task_logs()


router = APIRouter(prefix="/tasks", tags=["tasks"])


def _next_task_id(directory: str) -> str:
    """生成基于刮削路径的任务ID：路径编码 + 时间戳，直接显示刮削路径，避免同一路径的多次刮削日志重合"""
    # 将路径进行base64编码（去掉填充字符，替换不安全的文件名字符）
    # 这样可以直接从任务ID中看到路径信息
    path_encoded = base64.urlsafe_b64encode(directory.encode('utf-8')).decode('ascii').rstrip('=')
    # 替换可能不适合文件名的字符
    path_encoded = path_encoded.replace('/', '_').replace('+', '-')
    local_tz = get_local_timezone()
    timestamp = datetime.now(local_tz).strftime("%Y%m%d_%H%M%S")
    # 任务ID格式：路径编码_时间戳，例如：L3ZpZGVv_20251207_143022
    # 前端可以通过base64解码来显示原始路径
    task_id = f"{path_encoded}_{timestamp}"
    return task_id


class _TaskStream(io.TextIOBase):
    """将指定线程的 stdout/stderr 输出重定向到任务日志缓存。

    只拦截当前任务线程的输出，其它线程写回原始流，保证 uvicorn 等日志不受影响。
    """

    def __init__(self, task_id: str, thread_id: int, original):  # type: ignore[no-untyped-def]
        super().__init__()
        self.task_id = task_id
        self.thread_id = thread_id
        self._original = original
        self._buffer = ""

    def write(self, s: str) -> int:  # type: ignore[override]
        # 只拦截当前任务线程以及以 "javsp.web." 开头名称的爬虫线程输出；
        # 其它线程（如 uvicorn）直接写回原始流，避免将 Web 访问日志写入任务日志。
        current = threading.current_thread()
        if current.ident != self.thread_id and not current.name.startswith("javsp.web."):
            return self._original.write(s)

        text = str(s)
        if not text:
            return 0

        # 对于被拦截的线程，不再写回原始 stdout，而是缓冲并按行写入任务日志缓存，
        # 避免 tqdm 进度条等内容刷到 Docker 日志。
        self._buffer += text
        written = len(text)
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.rstrip()
            if line:
                with _task_lock:
                    buf = _task_logs.setdefault(self.task_id, [])
                    buf.append(line)
                    if len(buf) > 2000:
                        del buf[:-1000]
        return written

    def flush(self) -> None:  # type: ignore[override]
        # 手动任务线程：把缓冲中剩余内容刷入日志
        if threading.get_ident() == self.thread_id and self._buffer:
            line = self._buffer.rstrip()
            self._buffer = ""
            if line:
                with _task_lock:
                    buf = _task_logs.setdefault(self.task_id, [])
                    buf.append(line)
                    if len(buf) > 2000:
                        del buf[:-1000]
        # 其它线程或无剩余缓冲：仍然刷新原始流
        return self._original.flush()


class _TaskLogHandler(logging.Handler):
    """将 JavSP 相关 logger 的输出写入指定任务的内存日志缓存。"""

    def __init__(self, task_id: str) -> None:
        super().__init__()
        self.task_id = task_id

    def emit(self, record: logging.LogRecord) -> None:  # type: ignore[name-defined]
        msg = self.format(record)
        # 避免在 Web 日志里输出整段 Traceback，将多行日志压缩为首行摘要
        if "\n" in msg:
            msg = msg.splitlines()[0]
        with _task_lock:
            buf = _task_logs.setdefault(self.task_id, [])
            buf.append(msg)
            if len(buf) > 2000:
                del buf[:-1000]


def _run_manual_task(task_id: str, directory: str) -> None:
    global _tasks
    thread_id = threading.get_ident()
    history_written = False  # 标记是否已收到子进程发出的 summary 事件

    # 针对 JavSP 相关 logger（main / javsp / javsp.web）做局部劫持：
    # 关闭向上冒泡，并仅挂载任务专用 handler，确保业务日志不再流向 docker logs
    # 只记录ERROR和CRITICAL级别的日志到docker，其他日志只写入任务日志
    task_log_handler = _TaskLogHandler(task_id)
    task_log_handler.setLevel(logging.DEBUG)  # 设置为DEBUG级别以捕获所有日志，包括INFO级别的下载日志
    task_log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    
    # 设置根logger只输出ERROR和CRITICAL到docker日志
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.ERROR)

    logger_names = ["main", "javsp", "javsp.web"]
    logger_states = []
    for name in logger_names:
        lg = logging.getLogger(name)
        logger_states.append(
            (lg, lg.level, lg.propagate, list(lg.handlers)),
        )
        lg.setLevel(logging.DEBUG)
        lg.handlers = [task_log_handler]
        lg.propagate = False

    # 当前线程的 stdout/stderr 仍然通过 _TaskStream 写入任务日志，避免任务线程自身的日志流向 docker
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = _TaskStream(task_id, thread_id, old_stdout)
    sys.stderr = _TaskStream(task_id, thread_id, old_stderr)
    try:
        with _task_lock:
            task = _tasks.get(task_id)
            if not task:
                return
            task.status = TaskStatus.running
            task.started_at = datetime.now(timezone.utc)
            _tasks[task_id] = task

            # 确保任务日志缓存存在，并写入一条起始日志，便于前端确认
            buf = _task_logs.setdefault(task_id, [])
            line0 = f"任务 #{task_id} 已启动，目录：{directory}"
            buf.append(line0)
            # 同步写入原始流缓冲区，供 xterm.js 按 offset 增量读取
            stream0 = _task_streams.get(task_id, "")
            _task_streams[task_id] = stream0 + line0 + "\n"

        # 为当前任务构造配置文件路径（JSON），供子进程使用
        # 手动刮削任务统一使用固定的配置文件名，便于作为“当前手动规则预设”复用
        task_cfg_path = Path(resource_path("data/tasks/manual.json"))

        log = logging.getLogger(__name__)
        log.info("启动 JavSP 子进程执行手动刮削任务 #%s，配置文件：%s", task_id, task_cfg_path)

        # 启动子进程：使用 `python -m javsp -c <task_config>`，并通过 pty 提供伪终端，
        # 让 tqdm 等库认为 stdout 是 TTY，从而输出带 \r 的进度条。
        cmd = [sys.executable, "-m", "javsp", "-c", str(task_cfg_path)]

        master_fd: Optional[int] = None
        slave_fd: Optional[int] = None
        try:
            master_fd, slave_fd = pty.openpty()

            # 显式设置伪终端窗口大小，避免 pretty_errors 等库拿到 0 宽度
            # 这里设置为 30 行、120 列，足够容纳 tqdm 进度条
            set_winsize(slave_fd, 30, 120)

            # 基于当前环境构造一份新的 env，补充终端相关变量
            env = os.environ.copy()
            env["COLUMNS"] = "120"
            env["LINES"] = "30"
            env["TERM"] = "xterm-256color"
            # 限制 tqdm 进度条宽度，预留边距，减少边缘换行
            env["TQDM_NCOLS"] = "110"

            proc = subprocess.Popen(
                cmd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                env=env,
                text=False,
                bufsize=0,
            )

            # 父进程不再需要 slave 端
            os.close(slave_fd)
            slave_fd = None
        except Exception as e:  # noqa: BLE001
            log.exception("无法启动 JavSP 子进程：%s", e)
            with _task_lock:
                task = _tasks.get(task_id)
                if not task:
                    return
                task.status = TaskStatus.failed
                task.finished_at = datetime.now(timezone.utc)
                task.message = f"Failed to start subprocess: {e}"
                _tasks[task_id] = task
            # 出错时清理 pty fd
            if master_fd is not None:
                try:
                    os.close(master_fd)
                except OSError:
                    pass
            if slave_fd is not None:
                try:
                    os.close(slave_fd)
                except OSError:
                    pass
            return

        # 记录子进程句柄，便于后续取消任务时终止
        with _task_lock:
            _task_procs[task_id] = proc

        # 使用 pty master 端按字节块读取子进程输出：
        # 1）每个 chunk 立即追加到 _task_streams，保持完整终端流（含 \r / \n / ANSI 控制）；
        # 2）使用 buffer 按 \n 切分为行，仅用于 _task_logs（表格用）。
        in_traceback = False
        buffer = b""
        seen_noise_lines = set()
        try:
            assert master_fd is not None
            while True:
                # 使用 select 进行非阻塞读取，避免永久阻塞在 os.read 上
                r, _, _ = select.select([master_fd], [], [], 0.1)
                if master_fd in r:
                    try:
                        chunk = os.read(master_fd, 10240)
                    except OSError:
                        break

                    if not chunk:
                        break

                    # ① 先按 \n 切分为行进行处理和过滤
                    buffer += chunk
                    filtered_chunks = []  # 存储过滤后的内容，用于写入流
                    while True:
                        nl = buffer.find(b"\n")
                        if nl == -1:
                            break
                        line_bytes = buffer[: nl + 1]
                        buffer = buffer[nl + 1 :]

                        # 原始行（包含换行符）用于从 _task_streams 中按需删除 Traceback 堆栈行
                        raw_line = line_bytes.decode(errors="replace")
                        # 去掉行尾换行并移除 ANSI 控制码后用于 _task_logs
                        text = raw_line.rstrip("\r\n")
                        if not text:
                            continue
                        # 清理 ANSI 转义序列，避免以 ESC 开头导致 JAVSP_EVENT / 关键日志匹配失败
                        cleaned = _ANSI_RE.sub("", text)
                        text = cleaned.strip()
                        if not text:
                            continue

                        # 完全折叠 JavLib 反爬提示：不写入 _task_logs，并从 _task_streams 中移除
                        if "无法绕开JavLib的反爬机制" in text:
                            with _task_lock:
                                cur_stream = _task_streams.get(task_id, "")
                                if raw_line in cur_stream:
                                    _task_streams[task_id] = cur_stream.rsplit(raw_line, 1)[0]
                            continue

                        # 折叠噪声型爬虫日志：如 javsp.web.* 的重复错误行
                        # 仅保留第一次出现，后续相同文本从 _task_streams 中移除并不再写入 _task_logs
                        if text.startswith("javsp.web."):
                            if text in seen_noise_lines:
                                with _task_lock:
                                    cur_stream = _task_streams.get(task_id, "")
                                    if raw_line in cur_stream:
                                        _task_streams[task_id] = cur_stream.rsplit(raw_line, 1)[0]
                                continue
                            seen_noise_lines.add(text)

                        # 进度条行（tqdm）：保留在 _task_streams 以驱动 xterm 动态刷新，但不写入 _task_logs，
                        # 避免"最新日志"停留在 "正在整理: XXX.mp4: 0%|" 这类信息。
                        if "%|" in text or ("%" in text and "it/s" in text):
                            continue
                        
                        # 过滤只包含ANSI转义序列的行（清理后为空）
                        if not text or text.strip() == "":
                            continue

                        # 过滤 JAVSP_MOVIE 事件：从流中移除，不写入日志
                        if "JAVSP_MOVIE " in text:
                            with _task_lock:
                                cur_stream = _task_streams.get(task_id, "")
                                if raw_line in cur_stream:
                                    _task_streams[task_id] = cur_stream.rsplit(raw_line, 1)[0]
                                else:
                                    # 尝试移除包含 JAVSP_MOVIE 的部分
                                    movie_start = raw_line.find("JAVSP_MOVIE ")
                                    if movie_start >= 0:
                                        movie_end = raw_line.find("\n", movie_start)
                                        if movie_end < 0:
                                            movie_end = len(raw_line)
                                        movie_part = raw_line[movie_start:movie_end+1]
                                        if movie_part in cur_stream:
                                            _task_streams[task_id] = cur_stream.replace(movie_part, "", 1)
                            continue

                        # 解析 JavSP 子进程发出的结构化事件，用于构建刮削历史 + 生成精简日志
                        # 检查是否包含 JAVSP_EVENT（可能与其他内容混在一起）
                        javsp_event_pos = text.find("JAVSP_EVENT ")
                        if javsp_event_pos >= 0:
                            # 不将 JAVSP_EVENT 行写入流，但需要解析其内容

                            # 提取 JAVSP_EVENT 后的 JSON 部分
                            raw = text[javsp_event_pos + len("JAVSP_EVENT ") :]
                            # 尝试找到 JSON 的结束位置（可能在同一行，也可能被截断）
                            evt = None
                            try:
                                evt = json.loads(raw)
                            except (ValueError, json.JSONDecodeError):
                                # JSON 可能被截断或与其他内容混在一起，尝试提取完整的 JSON
                                # 查找第一个 { 和最后一个 }
                                json_start = raw.find("{")
                                json_end = raw.rfind("}")
                                if json_start >= 0 and json_end > json_start:
                                    try:
                                        evt = json.loads(raw[json_start:json_end+1])
                                    except (ValueError, json.JSONDecodeError):
                                        # JSON 解析失败时跳过
                                        evt = None
                            
                            if evt is None:
                                continue
                            
                            evt_type = evt.get("type")
                            evt_kind = evt.get("kind")

                            # 1) 影片整理摘要：写入刮削历史，不写入任务日志
                            if evt_type == "summary" and evt_kind == "movie":
                                try:
                                    history_written = True
                                    hid = _next_history_id()
                                    src_files = evt.get("source_files") or []
                                    # 尝试从源文件或番号推导一个可读名称
                                    display_name = None
                                    if src_files:
                                        display_name = os.path.basename(src_files[0])
                                    if not display_name:
                                        display_name = (
                                            evt.get("basename")
                                            or evt.get("dvdid")
                                            or evt.get("cid")
                                            or f"任务#{task_id}"
                                        )

                                    # 从任务配置中读取output_folder_pattern，用于判断存储位置
                                    output_folder_pattern = None
                                    nfo_basename_pattern = None
                                    cover_basename_pattern = None
                                    fanart_basename_pattern = None
                                    try:
                                        task_cfg_path = Path(resource_path("data/tasks/manual.json"))
                                        if task_cfg_path.is_file():
                                            task_cfg_data = json.loads(task_cfg_path.read_text(encoding="utf-8"))
                                            summarizer_cfg = task_cfg_data.get("summarizer", {})
                                            path_cfg = summarizer_cfg.get("path", {})
                                            output_folder_pattern = path_cfg.get("output_folder_pattern")
                                            nfo_cfg = summarizer_cfg.get("nfo", {})
                                            nfo_basename_pattern = nfo_cfg.get("basename_pattern", "movie")
                                            cover_cfg = summarizer_cfg.get("cover", {})
                                            cover_basename_pattern = cover_cfg.get("basename_pattern", "poster")
                                            fanart_cfg = summarizer_cfg.get("fanart", {})
                                            fanart_basename_pattern = fanart_cfg.get("basename_pattern", "fanart")
                                    except Exception:
                                        # 读取配置失败时使用默认值
                                        pass

                                    # 如果路径缺失，尝试根据output_folder_pattern和任务配置计算
                                    save_dir = evt.get("save_dir")
                                    nfo_file = evt.get("nfo_file")
                                    poster_file = evt.get("poster_file")
                                    fanart_file = evt.get("fanart_file")
                                    extrafanart_dir = evt.get("extrafanart_dir")
                                    
                                    # 如果save_dir存在但其他文件路径缺失，根据output_folder_pattern计算
                                    if save_dir and output_folder_pattern:
                                        if not nfo_file and nfo_basename_pattern:
                                            nfo_file = os.path.join(save_dir, f"{nfo_basename_pattern}.nfo")
                                        if not poster_file and cover_basename_pattern:
                                            poster_file = os.path.join(save_dir, f"{cover_basename_pattern}.jpg")
                                        if not fanart_file and fanart_basename_pattern:
                                            fanart_file = os.path.join(save_dir, f"{fanart_basename_pattern}.jpg")
                                        if not extrafanart_dir:
                                            extrafanart_dir = os.path.join(save_dir, "extrafanart")

                                    item = HistoryItem(
                                        id=hid,
                                        task_id=task_id,
                                        type=TaskType.manual,
                                        created_at=datetime.now(timezone.utc),
                                        dvdid=evt.get("dvdid"),
                                        cid=evt.get("cid"),
                                        save_dir=save_dir,
                                        display_name=display_name,
                                        source_files=src_files,
                                        target_basename=evt.get("basename"),
                                        nfo_file=nfo_file,
                                        poster_file=poster_file,
                                        fanart_file=fanart_file,
                                        extrafanart_dir=extrafanart_dir,
                                        cover_urls=evt.get("cover_urls"),
                                        cover_download_success=evt.get("cover_download_success"),
                                        cover_download_count=evt.get("cover_download_count", 0),
                                        fanart_urls=evt.get("fanart_urls"),
                                        fanart_download_success=evt.get("fanart_download_success"),
                                        fanart_download_count=evt.get("fanart_download_count", 0),
                                        fanart_download_failed_count=evt.get("fanart_download_failed_count", 0),
                                        fanart_download_results=evt.get("fanart_download_results"),
                                        used_crawlers=evt.get("used_crawlers"),
                                    )
                                    _append_history_item(item)
                                    # 在任务日志中追加一条提示，便于确认"刮削历史"已记录
                                    with _task_lock:
                                        buf = _task_logs.setdefault(task_id, [])
                                        hint = f"[历史] 已记录刮削结果：{display_name}"
                                        buf.append(hint)
                                        if len(buf) > 2000:
                                            del buf[:-1000]
                                except Exception:
                                    log = logging.getLogger(__name__)
                                    log.debug("追加刮削历史失败", exc_info=True)
                                # 影片摘要事件不再写入 _task_logs，避免干扰"最新日志"展示
                                continue

                            # 2) 进度事件：转换为简明中文日志，不保留原始 JSON
                            if evt_type == "progress":
                                msg = None
                                if evt_kind == "task":
                                    status = evt.get("status") or ""
                                    desc = evt.get("desc") or ""
                                    # 例如："[任务] 开始整理影片 (状态: RUNNING)"
                                    msg = f"[任务] {desc}"
                                    if status:
                                        msg += f" (状态: {status})"
                                elif evt_kind == "step":
                                    idx = evt.get("index")
                                    total = evt.get("total")
                                    desc = evt.get("desc") or ""
                                    if idx is not None and total is not None:
                                        # 例如："[步骤 {idx}/{total}] {desc}" - 只保留最新步骤
                                        # 移除之前的步骤消息，只保留最新的
                                        msg = f"[步骤 {idx}/{total}] {desc}"
                                    else:
                                        msg = f"[步骤] {desc}"

                                if msg:
                                    with _task_lock:
                                        buf = _task_logs.setdefault(task_id, [])
                                        # 如果是步骤消息，先移除之前的步骤消息
                                        if evt_kind == "step":
                                            buf[:] = [line for line in buf if not line.startswith("[步骤")]
                                        buf.append(msg)
                                        if len(buf) > 2000:
                                            del buf[:-1000]
                                        # 同时将关键进度信息追加到过滤后的流缓冲
                                        filtered_chunks.append(msg + "\n")
                                # 进度事件的原始 JSON 不再写入流和日志
                                continue

                            # 其它类型的 JAVSP_EVENT 目前不需要出现在任务日志中，直接忽略
                            continue

                        # 过滤 Python Traceback 堆栈：
                        # 遇到 "Traceback" 相关行时全部移除，包括错误信息行
                        if ("Traceback" in text or 
                            text.startswith("<frozen ") or 
                            text.startswith('"<frozen ') or
                            ("File " in text and ("line " in text or "line:" in text)) or
                            (text.startswith("  ") and ("File " in text or "in " in text))):
                            # 从流中移除所有 Traceback 相关行
                            with _task_lock:
                                cur_stream = _task_streams.get(task_id, "")
                                if raw_line in cur_stream:
                                    _task_streams[task_id] = cur_stream.rsplit(raw_line, 1)[0]
                                else:
                                    # 尝试移除包含该文本的部分
                                    trace_start = raw_line.find(text[:50] if len(text) > 50 else text)
                                    if trace_start >= 0:
                                        trace_end = raw_line.find("\n", trace_start)
                                        if trace_end < 0:
                                            trace_end = len(raw_line)
                                        trace_part = raw_line[trace_start:trace_end+1]
                                        if trace_part in cur_stream:
                                            _task_streams[task_id] = cur_stream.replace(trace_part, "", 1)
                            # Traceback 行不写入日志
                            continue

                        # 将过滤后的行添加到流中（除了已经被过滤掉的内容）
                        # 注意：JAVSP_EVENT、JAVSP_MOVIE、Traceback 等已经被 continue 跳过，不会到这里
                        filtered_chunks.append(raw_line)
                        
                        with _task_lock:
                            buf = _task_logs.setdefault(task_id, [])
                            buf.append(text)
                            if len(buf) > 2000:
                                del buf[:-1000]
                    
                    # ② 将过滤后的内容写入流，并实时持久化到文件
                    if filtered_chunks:
                        filtered_text = ''.join(filtered_chunks)
                        with _task_lock:
                            cur_stream = _task_streams.get(task_id, "")
                            _task_streams[task_id] = cur_stream + filtered_text
                            # 实时持久化任务日志到文件
                            try:
                                log_file = _TASK_LOGS_DIR / f"task_{task_id}.log"
                                log_file.write_text(cur_stream + filtered_text, encoding="utf-8")
                            except OSError:
                                pass  # 日志持久化失败不影响任务本身

                # 子进程已结束且没有更多输出时退出循环
                if proc.poll() is not None:
                    # 再尝试读一次，确保缓冲区读空
                    try:
                        if master_fd in select.select([master_fd], [], [], 0)[0]:
                            chunk = os.read(master_fd, 10240)
                            if chunk:
                                chunk_str = chunk.decode(errors="replace")
                                with _task_lock:
                                    cur_stream = _task_streams.get(task_id, "")
                                    _task_streams[task_id] = cur_stream + chunk_str
                        # 不再继续拆分为行，剩余内容通常极少
                    except OSError:
                        pass
                    break
        finally:
            if master_fd is not None:
                try:
                    os.close(master_fd)
                except OSError:
                    pass

        proc.wait()
        returncode = proc.returncode

        with _task_lock:
            task = _tasks.get(task_id)
            if not task:
                return
            if returncode == 0:
                task.status = TaskStatus.succeeded
                task.message = "ok"
            else:
                task.status = TaskStatus.failed
                task.message = f"javsp exited with code {returncode}"
            task.finished_at = datetime.now(timezone.utc)
            _tasks[task_id] = task
            
            # 持久化任务日志到文件
            try:
                log_file = _TASK_LOGS_DIR / f"task_{task_id}.log"
                stream = _task_streams.get(task_id, "")
                if stream:
                    log_file.write_text(stream, encoding="utf-8")
            except OSError:
                pass  # 日志持久化失败不影响任务本身

        # 若任务成功结束但未收到 summary 事件，补写一条兜底刮削历史，避免前端缺失记录
        if returncode == 0 and not history_written:
            try:
                hid = _next_history_id()
                # 从目录名推导一个可读名称
                display_name = os.path.basename(directory) or f"任务#{task_id}"
                save_dir = None
                nfo_file = None
                poster_file = None
                fanart_file = None
                extrafanart_dir = None
                # 尝试从已收集的任务日志中提取保存路径等信息
                cover_download_success = None
                fanart_download_success = None
                fanart_download_count = 0
                cover_urls = None
                fanart_urls = None
                
                with _task_lock:
                    buf_copy = list(_task_logs.get(task_id, []))
                for line in reversed(buf_copy):
                    if save_dir is None:
                        m = re.search(r"已保存到[：:]\s*(.+)", line)
                        if m:
                            save_dir = m.group(1).strip()
                    if nfo_file is None and "nfo" in line.lower():
                        m = re.search(r"([\w\-/\\.]+\.nfo)", line, re.IGNORECASE)
                        if m:
                            nfo_file = m.group(1)
                    if poster_file is None and re.search(r"(poster\.jpg|cover\.jpg|folder\.jpg)", line, re.IGNORECASE):
                        m = re.search(r"([\w\-/\\.]+(poster|cover|folder)\.jpg)", line, re.IGNORECASE)
                        if m:
                            poster_file = m.group(1)
                    if fanart_file is None and re.search(r"(fanart\.jpg|fanart\.png)", line, re.IGNORECASE):
                        m = re.search(r"([\w\-/\\.]+fanart\.(jpg|png))", line, re.IGNORECASE)
                        if m:
                            fanart_file = m.group(1)
                    if extrafanart_dir is None and "extrafanart" in line:
                        m = re.search(r"([\w\-/\\.]*extrafanart[\w\-/\\]*)", line, re.IGNORECASE)
                        if m:
                            extrafanart_dir = m.group(1)
                    
                    # 提取下载状态信息
                    if cover_download_success is None:
                        if "封面下载成功" in line:
                            cover_download_success = True
                        elif "下载封面图片失败" in line or "封面下载失败" in line:
                            cover_download_success = False
                    
                    if fanart_download_success is None:
                        if "剧照下载成功" in line:
                            fanart_download_success = True
                            # 提取剧照数量
                            m = re.search(r"剧照下载成功[，,]\s*共\s*(\d+)\s*张", line)
                            if m:
                                fanart_download_count = int(m.group(1))
                        elif "下载剧照失败" in line or "剧照下载失败" in line:
                            fanart_download_success = False
                    
                    if save_dir and nfo_file and poster_file and fanart_file and extrafanart_dir:
                        break

                # 如果路径缺失，尝试从任务配置中读取output_folder_pattern来计算
                if save_dir and (not nfo_file or not poster_file or not fanart_file):
                    try:
                        task_cfg_path = Path(resource_path("data/tasks/manual.json"))
                        if task_cfg_path.is_file():
                            task_cfg_data = json.loads(task_cfg_path.read_text(encoding="utf-8"))
                            summarizer_cfg = task_cfg_data.get("summarizer", {})
                            nfo_cfg = summarizer_cfg.get("nfo", {})
                            nfo_basename_pattern = nfo_cfg.get("basename_pattern", "movie")
                            cover_cfg = summarizer_cfg.get("cover", {})
                            cover_basename_pattern = cover_cfg.get("basename_pattern", "poster")
                            fanart_cfg = summarizer_cfg.get("fanart", {})
                            fanart_basename_pattern = fanart_cfg.get("basename_pattern", "fanart")
                            
                            if not nfo_file:
                                nfo_file = os.path.join(save_dir, f"{nfo_basename_pattern}.nfo")
                            if not poster_file:
                                poster_file = os.path.join(save_dir, f"{cover_basename_pattern}.jpg")
                            if not fanart_file:
                                fanart_file = os.path.join(save_dir, f"{fanart_basename_pattern}.jpg")
                            if not extrafanart_dir:
                                extrafanart_dir = os.path.join(save_dir, "extrafanart")
                    except Exception:
                        # 读取配置失败时使用已提取的路径
                        pass

                item = HistoryItem(
                    id=hid,
                    task_id=task_id,
                    type=TaskType.manual,
                    created_at=datetime.now(timezone.utc),
                    dvdid=None,
                    cid=None,
                    save_dir=save_dir,
                    display_name=display_name,
                    source_files=[],
                    target_basename=None,
                    nfo_file=nfo_file,
                    poster_file=poster_file,
                    fanart_file=fanart_file,
                    extrafanart_dir=extrafanart_dir,
                    cover_urls=cover_urls,
                    cover_download_success=cover_download_success,
                    cover_download_count=1 if cover_download_success else 0,
                    fanart_urls=fanart_urls,
                    fanart_download_success=fanart_download_success,
                    fanart_download_count=fanart_download_count,
                    fanart_download_failed_count=0,
                    fanart_download_results=None,  # 补写时无法获取详细结果
                    used_crawlers=None,
                )
                _append_history_item(item)
                with _task_lock:
                    buf = _task_logs.setdefault(task_id, [])
                    buf.append(f"[历史] 未收到 summary 事件，已补写刮削历史：{display_name}")
                    if len(buf) > 2000:
                        del buf[:-1000]
            except Exception:
                log = logging.getLogger(__name__)
                log.debug("兜底补写刮削历史失败", exc_info=True)
    except Exception as e:  # noqa: BLE001
        # 记录异常到任务日志
        log = logging.getLogger(__name__)
        log.exception("手动刮削任务 #%s 失败：%s", task_id, e)

        with _task_lock:
            task = _tasks.get(task_id)
            if not task:
                return
            task.status = TaskStatus.failed
            task.finished_at = datetime.now(timezone.utc)
            task.message = f"{type(e).__name__}: {e}"
            _tasks[task_id] = task
    finally:
        # 刷新并恢复 stdout / stderr
        try:
            sys.stdout.flush()
        except Exception:
            pass
        try:
            sys.stderr.flush()
        except Exception:
            pass
        sys.stdout = old_stdout
        sys.stderr = old_stderr

        # 任务结束时清理子进程记录
        with _task_lock:
            _task_procs.pop(task_id, None)

        # 恢复 main / javsp logger 的原有 handler / 配置
        for lg, level, propagate, handlers in logger_states:
            lg.setLevel(level)
            lg.propagate = propagate
            lg.handlers = handlers


@router.post("/{task_id}/cancel", status_code=status.HTTP_200_OK)
def cancel_task(task_id: str, user: UserInfo = Depends(get_current_user)) -> Dict[str, str]:  # noqa: ARG001
    """请求停止正在运行的手动刮削任务。

    实现方式：查找对应的子进程并调用 terminate()，实际退出码由 _run_manual_task 负责
    处理并更新任务状态。此接口只负责发出终止信号和记录一条日志提示。
    """

    with _task_lock:
        task = _tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

        proc = _task_procs.get(task_id)
        # 记录一条停止请求日志
        line = f"收到停止请求，正在尝试终止任务 #{task_id} ..."
        buf = _task_logs.setdefault(task_id, [])
        buf.append(line)
        stream = _task_streams.get(task_id, "")
        _task_streams[task_id] = stream + line + "\n"

    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
        except Exception:
            # best-effort 终止即可，失败时由后续日志和状态兜底
            pass

    return {"status": "ok"}


@router.post("/manual", response_model=TaskModel, status_code=status.HTTP_201_CREATED)
def create_manual_task(
    payload: ManualTaskCreate,
    user: UserInfo = Depends(get_current_user),  # noqa: ARG001
) -> TaskModel:
    directory = payload.input_directory
    if not os.path.isabs(directory):
        # 对于 Web / Docker 部署，强制要求绝对路径，避免误操作
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="必须提供绝对路径。")
    # 这里放宽校验：既支持目录也支持单个文件路径，只要路径存在即可。
    if not os.path.exists(directory):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="路径不存在或不可访问。")

    task_id = _next_task_id(directory)

    # 为本次任务生成专属配置文件：以最新的全局配置为模板，覆盖 scanner.input_directory
    # 1) 优先从磁盘上的 data/config.yml 读取（由 Web 全局规则保存），确保使用的是最新规则
    cfg_path = Path(resource_path("data/config.yml"))
    cfg_data = None
    if cfg_path.is_file():
        try:
            text = cfg_path.read_text(encoding="utf-8")
            cfg_data = json.loads(text)
        except Exception:
            # 解析失败时退回到进程内的 Cfg() 单例配置
            cfg_data = None

    # 2) 磁盘配置不可用时，退回到当前进程内的 Cfg() 导出
    if cfg_data is None:
        cfg = Cfg()
        try:
            cfg_data = cfg.model_dump(mode="json")  # type: ignore[attr-defined]
        except AttributeError:
            cfg_data = json.loads(cfg.json())  # type: ignore[no-untyped-call]

    # 深拷贝并覆盖扫描目录
    merged = dict(cfg_data)
    
    # 如果指定了自定义规则，应用该规则的配置
    if payload.profile and payload.profile != "default":
        manual_rules_path = Path(resource_path("data/tasks/manual_rules.json"))
        if manual_rules_path.is_file():
            try:
                manual_rules_text = manual_rules_path.read_text(encoding="utf-8")
                all_manual_rules = json.loads(manual_rules_text)
                # 查找指定名称的规则
                if payload.profile in all_manual_rules:
                    manual_rules = all_manual_rules[payload.profile]
                    # 深度合并手动规则到配置中
                    def _deep_merge(base: dict, override: dict) -> dict:
                        result = base.copy()
                        for key, value in override.items():
                            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                                result[key] = _deep_merge(result[key], value)
                            else:
                                result[key] = value
                        return result
                    merged = _deep_merge(merged, manual_rules)
            except Exception:
                # 手动规则解析失败时忽略，使用全局规则
                pass
    
    scanner_cfg = dict(merged.get("scanner", {}))
    scanner_cfg["input_directory"] = directory
    # Web 环境下运行手动刮削任务，不支持 CLI 交互确认番号，强制关闭 manual 模式
    scanner_cfg["manual"] = False
    merged["scanner"] = scanner_cfg

    # 手动刮削统一使用固定文件名 manual.json，便于作为当前手动规则预设复用
    task_cfg_path = Path(resource_path("data/tasks/manual.json"))
    try:
        task_cfg_path.parent.mkdir(parents=True, exist_ok=True)
        task_cfg_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as e:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"无法写入任务配置文件: {e}")

    task = TaskModel(
        id=task_id,
        type=TaskType.manual,
        status=TaskStatus.pending,
        input_directory=directory,
        profile=payload.profile or "default",
        created_at=datetime.now(timezone.utc),
    )
    with _task_lock:
        _tasks[task_id] = task

    t = threading.Thread(target=_run_manual_task, args=(task_id, directory), daemon=True)
    t.start()

    return task


@router.put("/manual/rules", status_code=status.HTTP_200_OK)
def update_manual_rules(
    payload: Dict[str, Any],
    user: UserInfo = Depends(get_current_user),  # noqa: ARG001
) -> Dict[str, str]:
    """保存手动刮削任务的自定义规则，支持多个规则（每个规则有名称和配置）"""
    try:
        manual_rules_path = Path(resource_path("data/tasks/manual_rules.json"))
        manual_rules_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 读取现有规则
        existing_rules = {}
        if manual_rules_path.is_file():
            try:
                text = manual_rules_path.read_text(encoding="utf-8")
                existing_rules = json.loads(text)
            except Exception:
                existing_rules = {}
        
        # 如果payload包含name字段，说明是保存单个规则
        if "name" in payload and "config" in payload:
            rule_name = payload["name"]
            rule_config = payload["config"]
            if not rule_name or not rule_name.strip():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="规则名称不能为空")
            existing_rules[rule_name.strip()] = rule_config
        elif "name" in payload and "delete" in payload:
            # 删除规则
            rule_name = payload["name"]
            if rule_name in existing_rules:
                del existing_rules[rule_name]
        else:
            # 兼容旧格式：直接保存为单个规则
            existing_rules = payload
        
        manual_rules_path.write_text(json.dumps(existing_rules, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"status": "ok"}
    except OSError as e:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"无法保存手动规则: {e}")


@router.get("/manual/rules")
def get_manual_rules(
    user: UserInfo = Depends(get_current_user),  # noqa: ARG001
) -> Dict[str, Any]:
    """获取所有手动刮削任务的自定义规则"""
    manual_rules_path = Path(resource_path("data/tasks/manual_rules.json"))
    if manual_rules_path.is_file():
        try:
            text = manual_rules_path.read_text(encoding="utf-8")
            return json.loads(text)
        except Exception:
            return {}
    return {}


@router.get("/manual/rules/{rule_name}")
def get_manual_rule(
    rule_name: str,
    user: UserInfo = Depends(get_current_user),  # noqa: ARG001
) -> Dict[str, Any]:
    """获取指定名称的自定义规则"""
    manual_rules_path = Path(resource_path("data/tasks/manual_rules.json"))
    if manual_rules_path.is_file():
        try:
            text = manual_rules_path.read_text(encoding="utf-8")
            all_rules = json.loads(text)
            if rule_name in all_rules:
                return all_rules[rule_name]
        except Exception:
            pass
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="规则不存在")


@router.get("/history", response_model=List[HistoryItem])
def list_history(
    limit: int = 100,
    user: UserInfo = Depends(get_current_user),  # noqa: ARG001
) -> List[HistoryItem]:
    try:
        if limit <= 0:
            limit = 50
        with _history_lock:
            items = list(_history)
        items.sort(key=lambda x: x.created_at, reverse=True)
        if len(items) > limit:
            items = items[:limit]
        return items
    except Exception as e:  # noqa: BLE001
        log = logging.getLogger(__name__)
        log.exception("加载刮削历史失败：%s", e)
        # 出错时返回空列表，避免前端展示报错提示
        return []


class HistoryDeleteRequest(BaseModel):
    ids: List[int] = Field(..., description="要删除的历史记录ID列表")
    mode: str = Field(..., description="删除模式：record=仅删除记录, files=删除文件, both=删除记录和文件")


@router.post("/history/delete")
def delete_history(
    payload: HistoryDeleteRequest,
    user: UserInfo = Depends(get_current_user),  # noqa: ARG001
) -> Dict[str, bool]:
    """删除刮削历史记录。
    
    mode 参数说明：
    - record: 仅从历史记录中删除，不删除实际文件
    - files: 删除媒体库文件，但保留历史记录
    - both: 同时删除历史记录和媒体库文件
    """
    log = logging.getLogger(__name__)
    
    try:
        with _history_lock:
            # 找到要删除的记录
            items_to_delete = [item for item in _history if item.id in payload.ids]
            if not items_to_delete:
                return {"success": True, "message": "未找到要删除的记录"}
            
            # 根据模式执行删除
            if payload.mode in ("record", "both"):
                # 从内存中删除
                _history[:] = [item for item in _history if item.id not in payload.ids]
                
                # 重新写入文件（覆盖整个文件）
                try:
                    _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
                    with _HISTORY_FILE.open("w", encoding="utf-8") as f:
                        for item in _history:
                            try:
                                data = item.model_dump(mode="json")  # type: ignore[attr-defined]
                            except AttributeError:
                                # 兼容 Pydantic v1
                                data = json.loads(item.json(ensure_ascii=False))
                            line = json.dumps(data, ensure_ascii=False)
                            f.write(line + "\n")
                except OSError as e:
                    log.error("保存历史记录文件失败：%s", e)
                    return {"success": False, "error": "保存历史记录文件失败"}
            
            if payload.mode in ("files", "both"):
                # 删除实际文件
                deleted_dirs = []
                for item in items_to_delete:
                    try:
                        # 删除保存目录（如果存在）
                        if item.save_dir and os.path.exists(item.save_dir):
                            shutil.rmtree(item.save_dir)
                            deleted_dirs.append(item.save_dir)
                            log.info("已删除目录：%s", item.save_dir)
                    except Exception as e:
                        log.warning("删除目录失败 %s: %s", item.save_dir, e)
                
                if deleted_dirs:
                    log.info("已删除 %d 个目录", len(deleted_dirs))
        
        return {"success": True}
    except Exception as e:  # noqa: BLE001
        log.exception("删除历史记录失败：%s", e)
        return {"success": False, "error": str(e)}


class HistoryRedownloadRequest(BaseModel):
    ids: List[int]


@router.post("/history/redownload")
def redownload_history(
    payload: HistoryRedownloadRequest,
    user: UserInfo = Depends(get_current_user),  # noqa: ARG001
) -> Dict[str, Any]:
    """重新下载选中历史记录的封面和剧照。"""
    log = logging.getLogger(__name__)
    
    try:
            with _history_lock:
                # 找到要重新下载的记录
                items_to_redownload = [item for item in _history if item.id in payload.ids]
                if not items_to_redownload:
                    return {"success": False, "error": "未找到要重新下载的记录"}
                
                # 收集所有需要下载的封面和剧照URL
                cover_urls = []
                fanart_urls = []
                for item in items_to_redownload:
                    # 优先使用历史记录中保存的URL
                    if item.cover_urls:
                        cover_urls.extend(item.cover_urls)
                    if item.fanart_urls:
                        fanart_urls.extend(item.fanart_urls)
                    
                    # 如果历史记录中没有URL，尝试从NFO文件中读取
                    if not item.cover_urls and item.nfo_file and os.path.exists(item.nfo_file):
                        try:
                            import xml.etree.ElementTree as ET
                            tree = ET.parse(item.nfo_file)
                            root = tree.getroot()
                            # 查找封面URL
                            thumb = root.find("thumb")
                            if thumb is not None and thumb.text:
                                cover_urls.append(thumb.text)
                            # 查找剧照URL
                            for fanart in root.findall("fanart/thumb"):
                                if fanart.text:
                                    fanart_urls.append(fanart.text)
                        except Exception:
                            pass
                
                if not cover_urls and not fanart_urls:
                    return {"success": False, "error": "选中的记录没有可下载的封面或剧照（历史记录中未保存URL，且无法从NFO文件读取）"}
            
            # 创建一个新的手动任务来下载这些资源
            # 使用第一个记录的保存目录作为任务目录
            task_directory = items_to_redownload[0].save_dir or "/video"
            task_id = _next_task_id(f"redownload_{task_directory}")
            
            # 创建任务
            task = TaskModel(
                id=task_id,
                status=TaskStatus.RUNNING,
                created_at=datetime.now(timezone.utc),
                directory=task_directory,
            )
            with _task_lock:
                _tasks[task_id] = task
                _task_logs[task_id] = []
                _task_streams[task_id] = ""
            
            # 在后台线程中执行下载任务
            def _run_redownload_task():
                try:
                    import requests
                    from pathlib import Path
                    
                    log.info(f"开始重新下载任务 {task_id}，封面 {len(cover_urls)} 张，剧照 {len(fanart_urls)} 张")
                    
                    # 下载封面
                    if cover_urls:
                        for idx, url in enumerate(cover_urls):
                            try:
                                # 这里需要根据实际保存路径下载封面
                                # 简化处理：只记录日志
                                log.info(f"下载封面 {idx + 1}/{len(cover_urls)}: {url}")
                            except Exception as e:
                                log.error(f"下载封面失败 {url}: {e}")
                    
                    # 下载剧照
                    if fanart_urls:
                        for idx, url in enumerate(fanart_urls):
                            try:
                                log.info(f"下载剧照 {idx + 1}/{len(fanart_urls)}: {url}")
                            except Exception as e:
                                log.error(f"下载剧照失败 {url}: {e}")
                    
                    # 标记任务完成
                    with _task_lock:
                        if task_id in _tasks:
                            _tasks[task_id].status = TaskStatus.SUCCEEDED
                            _tasks[task_id].finished_at = datetime.now(timezone.utc)
                    
                    log.info(f"重新下载任务 {task_id} 完成")
                except Exception as e:
                    log.exception(f"重新下载任务 {task_id} 失败: {e}")
                    with _task_lock:
                        if task_id in _tasks:
                            _tasks[task_id].status = TaskStatus.FAILED
                            _tasks[task_id].finished_at = datetime.now(timezone.utc)
            
            # 启动后台线程
            import threading
            thread = threading.Thread(target=_run_redownload_task, daemon=True)
            thread.start()
            
            return {"success": True, "task_id": task_id}
    except Exception as e:  # noqa: BLE001
        log.exception("重新下载失败：%s", e)
        return {"success": False, "error": str(e)}


@router.get("/{task_id}", response_model=TaskModel)
def get_task(task_id: str, user: UserInfo = Depends(get_current_user)) -> TaskModel:  # noqa: ARG001
    with _task_lock:
        task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return task


@router.get("/{task_id}/logs", response_model=TaskLogResponse)
def get_task_logs(
    task_id: str,
    limit: int = 500,
    user: UserInfo = Depends(get_current_user),  # noqa: ARG001
) -> TaskLogResponse:
    if limit <= 0:
        limit = 100
    if limit > 2000:
        limit = 2000
    with _task_lock:
        task = _tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        lines = _task_logs.get(task_id, [])
        
        # 如果内存中没有日志，尝试从文件加载
        if not lines:
            try:
                log_file = _TASK_LOGS_DIR / f"task_{task_id}.log"
                if log_file.exists():
                    stream = log_file.read_text(encoding="utf-8")
                    # 按行分割并过滤空行
                    lines = [line.rstrip() for line in stream.splitlines() if line.strip()]
                    # 加载到内存以便后续访问
                    _task_logs[task_id] = lines
                    # 同时加载到stream缓存
                    _task_streams[task_id] = stream
            except OSError:
                pass
        
        if len(lines) > limit:
            lines = lines[-limit:]

        # 兜底：如果状态仍为 RUNNING，但日志中已经出现失败标记，则强制标记为 FAILED
        status_value = task.status
        if status_value == TaskStatus.running:
            fail_marker = f"手动刮削任务 #{task_id} 失败"
            success_marker = f"手动刮削任务 #{task_id} 完成"
            if any(fail_marker in line for line in lines):
                status_value = TaskStatus.failed
                task.status = status_value
                if not task.finished_at:
                    task.finished_at = datetime.now(timezone.utc)
                _tasks[task_id] = task
            elif any(success_marker in line for line in lines):
                status_value = TaskStatus.succeeded
                task.status = status_value
                if not task.finished_at:
                    task.finished_at = datetime.now(timezone.utc)
                _tasks[task_id] = task

    return TaskLogResponse(id=task_id, status=status_value, lines=lines)


@router.get("/{task_id}/logstream")
def get_task_logstream(
    task_id: str,
    offset: int = 0,
    user: UserInfo = Depends(get_current_user),  # noqa: ARG001
) -> Dict[str, object]:
    """按 offset 返回原始日志流的增量片段。

    - offset: 上次读取结束时的偏移量（字符数）；
    - 返回 chunk: 从 offset 到当前末尾的新内容；offset: 当前总长度。
    """

    with _task_lock:
        stream = _task_streams.get(task_id, "")
        
        # 如果内存中没有日志，尝试从文件加载
        if not stream:
            try:
                log_file = _TASK_LOGS_DIR / f"task_{task_id}.log"
                if log_file.exists():
                    stream = log_file.read_text(encoding="utf-8")
                    # 加载到内存以便后续访问
                    _task_streams[task_id] = stream
            except OSError:
                pass

    total = len(stream)
    if offset < 0 or offset > total:
        offset = 0

    chunk = stream[offset:]
    return {"id": task_id, "chunk": chunk, "offset": total}


@router.get("", response_model=List[TaskModel])
def list_tasks(user: UserInfo = Depends(get_current_user)) -> List[TaskModel]:  # noqa: ARG001
    """列出所有任务，包括从日志文件恢复的历史任务。"""
    with _task_lock:
        tasks = list(_tasks.values())
        # 从日志文件目录中查找历史任务（可能不在内存中）
        if _TASK_LOGS_DIR.exists():
            for log_file in _TASK_LOGS_DIR.glob("task_*.log"):
                try:
                    # 从文件名提取任务ID（现在是字符串格式：pathhash_YYYYMMDD_HHMMSS）
                    task_id = log_file.stem.replace("task_", "")
                    # 如果任务不在内存中，创建一个基本任务记录
                    if task_id not in _tasks:
                        # 从任务ID中提取时间戳（格式：pathhash_YYYYMMDD_HHMMSS）
                        local_tz = get_local_timezone()
                        created_at = datetime.fromtimestamp(log_file.stat().st_mtime, tz=local_tz)
                        if "_" in task_id:
                            parts = task_id.split("_")
                            if len(parts) >= 3:
                                try:
                                    # 提取日期和时间部分：YYYYMMDD_HHMMSS
                                    date_str = parts[1]  # YYYYMMDD
                                    time_str = parts[2]  # HHMMSS
                                    datetime_str = f"{date_str}_{time_str}"
                                    created_at = datetime.strptime(datetime_str, "%Y%m%d_%H%M%S").replace(tzinfo=local_tz)
                                except (ValueError, IndexError):
                                    # 解析失败时使用文件修改时间
                                    pass
                        
                        # 尝试从日志中推断状态和输入目录
                        status = TaskStatus.succeeded
                        input_directory = ""
                        try:
                            log_content = log_file.read_text(encoding="utf-8")
                            if "失败" in log_content or "error" in log_content.lower():
                                status = TaskStatus.failed
                            # 尝试从日志中提取输入目录
                            m = re.search(r"任务 #.*? 已启动，目录[：:]\s*(.+)", log_content)
                            if m:
                                input_directory = m.group(1).strip()
                        except OSError:
                            pass
                        
                        task = TaskModel(
                            id=task_id,
                            type=TaskType.manual,
                            status=status,
                            input_directory=input_directory,
                            profile="default",
                            created_at=created_at,
                        )
                        tasks.append(task)
                        _tasks[task_id] = task
                except (ValueError, OSError):
                    continue
    # 简单按创建时间倒序
    tasks.sort(key=lambda x: x.created_at, reverse=True)
    return tasks


@router.delete("/{task_id}/logs", status_code=status.HTTP_200_OK)
def delete_task_logs(
    task_id: str,
    user: UserInfo = Depends(get_current_user),  # noqa: ARG001
) -> Dict[str, bool]:
    """删除指定任务的日志（内存和文件）。"""
    log = logging.getLogger(__name__)
    try:
        with _task_lock:
            # 从内存中删除
            _task_logs.pop(task_id, None)
            _task_streams.pop(task_id, None)
            _tasks.pop(task_id, None)
        # 同步删除历史记录中的该任务
        try:
            updated_history = []
            changed = False
            with _history_lock:
                for item in _history:
                    if getattr(item, "task_id", None) == task_id:
                        changed = True
                        continue
                    updated_history.append(item)
                if changed:
                    _history = updated_history
                    # 重写历史文件
                    try:
                        _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
                        with _HISTORY_FILE.open("w", encoding="utf-8") as f:
                            for it in _history:
                                try:
                                    data = it.model_dump(mode="json")  # type: ignore[attr-defined]
                                except AttributeError:
                                    data = json.loads(it.json(ensure_ascii=False))
                                f.write(json.dumps(data, ensure_ascii=False) + "\n")
                    except OSError as e:
                        log.warning("重写历史文件失败: %s", e)
        except Exception as e:  # noqa: BLE001
            log.warning("清理历史记录时出错: %s", e)
        
        # 删除日志文件
        try:
            log_file = _TASK_LOGS_DIR / f"task_{task_id}.log"
            if log_file.exists():
                log_file.unlink()
        except OSError as e:
            log.warning("删除任务日志文件失败: %s", e)
            return {"success": False, "error": f"删除日志文件失败: {e}"}
        
        return {"success": True}
    except Exception as e:  # noqa: BLE001
        log.exception("删除任务日志失败")
        return {"success": False, "error": str(e)}


@router.get("/fs/browse", response_model=List[FileEntry])
def browse_files(
    path: str = Query("/video", description="要浏览的目录（容器内绝对路径）"),
    user: UserInfo = Depends(get_current_user),  # noqa: ARG001
) -> List[FileEntry]:
    """浏览 /video 下的文件系统结构，供 /videode 前端使用。

    - 仅允许访问以 /video 为前缀的路径，防止越权浏览宿主机其它目录；
    - 返回当前目录下的一层子项（不递归）。
    """

    if not os.path.isabs(path):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="必须提供绝对路径。")

    try:
        real = os.path.realpath(path)
    except OSError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="路径无效。")

    # 仅允许访问 /video 映射卷内的内容
    root_allowed = os.path.realpath("/video")
    if not real.startswith(root_allowed):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只能浏览 /video 目录下的内容。")

    if not os.path.isdir(real):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="目标不是有效目录。")

    entries: List[FileEntry] = []
    try:
        with os.scandir(real) as it:
            for entry in it:
                # 隐藏 . 开头目录/文件，避免把一些挂载点或系统目录暴露给前端
                if entry.name.startswith("."):
                    continue
                try:
                    is_dir = entry.is_dir()
                    size: Optional[int]
                    if is_dir:
                        size = None
                    else:
                        try:
                            size = entry.stat().st_size
                        except OSError:
                            size = None
                    entries.append(
                        FileEntry(
                            name=entry.name,
                            path=os.path.join(real, entry.name),
                            is_dir=is_dir,
                            size=size,
                        )
                    )
                except OSError:
                    # 单个条目出错时跳过
                    continue
    except OSError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无法列出目录内容。")

    # 简单按类型 + 名称排序：目录在前，其次按名称字典序
    entries.sort(key=lambda x: (not x.is_dir, x.name.lower()))
    return entries
