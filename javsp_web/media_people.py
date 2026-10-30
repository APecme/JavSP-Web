"""Gfriends 演员头像刮削：给媒体服务器上没有头像的女优补头像。

范围控制：只处理「绑定媒体库的影片 Cast 中实际出现的演员」——先拉库内
影片（Recursive、IncludeItemTypes=Movie、Fields=People），客户端汇总
Cast 名字集合，再与 /Persons 交叉；男演员/配音/导演/编剧天然不在范围内。

匹配：精确名 → 别名表（vendor/JavSP/data/actress_alias.json）→ 归一化名
（NFKC、去空格/中点、全角转半角、平假名↔片假名折叠、繁→简）。

只对「服务器上没有 Primary 头像」的演员上传（POST /Items/{id}/Images/Primary），
不覆盖已有头像、不碰其他元数据。日志持久化在
data/media-people-scrape/<server_id>.log，重启不丢。

计数口径：
- skipped：已有头像；
- unmatched：在范围内但 Gfriends 无匹配（不算失败，前 20 个名字单独展示）；
- failed：真正的上传/网络错误。
"""
from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import requests
from PIL import Image

from . import avatars
from .storage import DATA_DIR

MAX_LOG_LINES = 50
UPLOAD_RETRY_TIMES = 3
UPLOAD_RETRY_DELAY = 0.5
UNMATCHED_PREVIEW = 20
_TIME_FORMAT = '%Y-%m-%d %H:%M:%S'

# 内置头像（webp）的物理根目录，便于测试重定向。
_ASSET_ROOT = Path(avatars.__file__).parent / 'web'
_ALIAS_FILE = Path(__file__).resolve().parents[1] / 'vendor/JavSP/data/actress_alias.json'

# server_id -> {"running": bool, "stats": {...}, "started_at": str, "finished_at": str}
_scrapes: dict[str, dict] = {}
_scrape_lock = threading.RLock()


def _now() -> str:
    return datetime.now().strftime(_TIME_FORMAT)


def _server_scrape_dir(server_id: str) -> Path:
    return DATA_DIR / 'media-people-scrape'


def _log_file(server_id: str) -> Path:
    return _server_scrape_dir(server_id) / f'{server_id}.log'


def _state_file(server_id: str) -> Path:
    return _server_scrape_dir(server_id) / f'{server_id}.json'


def _load_state(server_id: str) -> dict:
    try:
        raw = json.loads(_state_file(server_id).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _save_state(server_id: str, entry: dict) -> None:
    folder = _server_scrape_dir(server_id)
    folder.mkdir(parents=True, exist_ok=True)
    payload = {
        'started_at': entry.get('started_at') or '',
        'finished_at': entry.get('finished_at') or '',
        'stats': entry.get('stats') or {},
        'unmatched': list(entry.get('unmatched') or [])[:UNMATCHED_PREVIEW],
    }
    tmp = _state_file(server_id).with_suffix('.json.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    tmp.replace(_state_file(server_id))


def _append_log(server_id: str, line: str) -> None:
    folder = _server_scrape_dir(server_id)
    folder.mkdir(parents=True, exist_ok=True)
    with _log_file(server_id).open('a', encoding='utf-8') as handle:
        handle.write(f'[{_now()}] {line}\n')


_ISO_PREFIX = re.compile(
    r'^\[(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(?:\.\d+)?(?:[+-]\d{2}:?\d{2}|Z)?\]')


def _format_log_time(line: str) -> str:
    """Rewrites legacy ISO timestamps to the local readable form."""
    return _ISO_PREFIX.sub(lambda m: f'[{m.group(1)} {m.group(2)}]', line, count=1)


def read_log(server_id: str) -> list[str]:
    """最近 MAX_LOG_LINES 行日志；文件不存在时返回空列表。"""
    try:
        lines = _log_file(server_id).read_text(encoding='utf-8').splitlines()
    except OSError:
        return []
    return [_format_log_time(line) for line in lines[-MAX_LOG_LINES:]]


# --------------------------------------------------------------------------- #
# 名字归一化与匹配
# --------------------------------------------------------------------------- #

_KANA = {chr(0x3041 + i): chr(0x30A1 + i) for i in range(86)}  # 平假名 → 片假名


def normalize_name(name: str) -> str:
    """NFKC → 去空格/中点 → 全角转半角 → 平假名折成片假名 → 繁转简。"""
    text = unicodedata.normalize('NFKC', str(name))
    text = re.sub(r'[\s　·・．.・]+', '', text)
    text = text.translate(_KANA)
    try:
        from zhconv import convert as zh_convert
        text = zh_convert(text, 'zh-cn')
    except Exception:  # noqa: BLE001 - zhconv 缺失时退化为不做繁简折叠
        pass
    return text.casefold()


def _alias_table() -> dict[str, set[str]]:
    """别名表：规范名 → {所有别名（含自身）}；返回双向查找用的原始结构。"""
    try:
        data = json.loads(_ALIAS_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return {str(canonical): {str(alias) for alias in aliases}
            for canonical, aliases in data.items()} if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def _build_lookup() -> dict[str, str]:
    """归一化名 → 头像 id 的三级匹配索引（含别名表的全部别名）。"""
    lookup: dict[str, str] = {}
    for avatar_id, item in avatars.avatar_directory().items():
        name = str(item.get('name') or '').strip()
        if not name:
            continue
        # "天然美月（天然かのん）" 括号内是别名，两者都可命中。
        for candidate in [name, name.split('（')[0], name.split('（')[-1].rstrip('）')]:
            candidate = candidate.strip()
            if candidate:
                lookup.setdefault(candidate.casefold(), avatar_id)
                lookup.setdefault(normalize_name(candidate), avatar_id)
    aliases = _alias_table()
    for canonical, aliases_for_name in aliases.items():
        # 组内若有名字能对上目录，优先取规范名/组内已命中的头像，
        # 把该头像共享给组内其余别名（一个艺名组的多个名字指向同一人）。
        avatar_ids = {lookup.get(alias.casefold()) or lookup.get(normalize_name(alias))
                      for alias in aliases_for_name | {canonical}}
        avatar_ids.discard(None)
        avatar_id = (lookup.get(canonical.casefold())
                     or lookup.get(normalize_name(canonical)))
        if avatar_id is None and avatar_ids:
            avatar_id = next(iter(avatar_ids))
        if avatar_id:
            for alias in aliases_for_name | {canonical}:
                lookup.setdefault(alias.casefold(), avatar_id)
                lookup.setdefault(normalize_name(alias), avatar_id)
    return lookup


def match_avatar(name: str) -> str | None:
    """精确名 → 归一化名匹配（别名已折进归一化索引）。"""
    stripped = str(name).strip()
    if not stripped:
        return None
    lookup = _build_lookup()
    return (lookup.get(stripped.casefold())
            or lookup.get(normalize_name(stripped)))


# --------------------------------------------------------------------------- #
# 媒体服务器交互
# --------------------------------------------------------------------------- #

def _list_cast_names(server: dict) -> set[str]:
    """绑定库内影片 Cast 中实际出现的演员名字集合（Role 过滤在服务端做不了，客户端只取 People 条目）。"""
    from .media import _headers, _service_url
    names: set[str] = set()
    library_ids = server.get('libraries') or []
    for library_id in library_ids:
        offset = 0
        while True:
            response = requests.get(
                f'{_service_url(server)}/Items',
                headers=_headers(server), timeout=30,
                params={'ParentId': library_id, 'Recursive': 'true',
                        'IncludeItemTypes': 'Movie', 'Fields': 'People',
                        'StartIndex': offset, 'Limit': 500})
            response.raise_for_status()
            data = response.json() or {}
            items = data.get('Items') or []
            for item in items:
                for person in item.get('People') or []:
                    role = str(person.get('Role') or '')
                    if role in {'Director', '导演', 'Writer', '编剧', 'Producer', '制片'}:
                        continue
                    if person.get('Type') and person.get('Type') not in ('Actor', 'Person'):
                        continue
                    name = str(person.get('Name') or '').strip()
                    if name:
                        # 库内影片与 /Persons 的写法可能差在空格/繁简等，归一化后再比对。
                        names.add(name)
                        names.add(normalize_name(name))
            offset += len(items)
            total = data.get('TotalRecordCount')
            if not items or (total is not None and offset >= int(total)) or (total is None and len(items) < 500):
                break
    return names


def _list_persons(server: dict) -> list[dict]:
    """拉取演员列表（分页，只取 Actor 类型），返回带 Id 的最小条目。"""
    from .media import _headers, _service_url
    persons, offset = [], 0
    while True:
        response = requests.get(
            f'{_service_url(server)}/Persons',
            headers=_headers(server), timeout=30,
            params={'PersonTypes': 'Actor', 'StartIndex': offset, 'Limit': 500,
                    'Fields': 'PrimaryImageAspectRatio', 'EnableTotalRecordCount': 'true'})
        response.raise_for_status()
        data = response.json() or {}
        batch = [item for item in data.get('Items') or [] if item.get('Id') and item.get('Name')]
        persons.extend(batch)
        offset += len(batch)
        total = data.get('TotalRecordCount')
        if not batch or (total is not None and offset >= int(total)) or (total is None and len(batch) < 500):
            break
    return persons


def _person_has_image(server: dict, person_id: str) -> bool:
    """演员是否已有头像：GET /Items/{id}/Images/Primary，200=有，404=没有。"""
    from .media import _headers, _service_url
    try:
        response = requests.get(f'{_service_url(server)}/Items/{person_id}/Images/Primary',
                                headers=_headers(server), timeout=20)
        return response.status_code == 200
    except requests.RequestException:
        return True  # 检查失败时保守跳过，避免覆盖已有头像


def _upload_image(server: dict, person_id: str, content: bytes) -> None:
    """上传头像，失败限流重试（3 次、间隔 0.5s），全部失败抛最后一个异常。"""
    from .media import _headers, _service_url
    headers = _headers(server)
    headers['Content-Type'] = 'image/jpeg'
    last: Exception | None = None
    for attempt in range(1, UPLOAD_RETRY_TIMES + 1):
        try:
            response = requests.post(f'{_service_url(server)}/Items/{person_id}/Images/Primary',
                                     headers=headers, data=content, timeout=30)
            response.raise_for_status()
            return
        except requests.RequestException as exc:
            last = exc
            if attempt < UPLOAD_RETRY_TIMES:
                time.sleep(UPLOAD_RETRY_DELAY)
    raise last  # type: ignore[misc]


def _avatar_content(avatar_id: str) -> bytes | None:
    """读取内置头像并转成 JPEG（媒体服务器对 webp 的兼容性参差不齐）。"""
    import io
    path = avatars.avatar_url(avatar_id)
    if not path or not path.startswith('/assets/avatars/'):
        return None
    file = _ASSET_ROOT / path.lstrip('/')
    if not file.is_file():
        return None
    try:
        with Image.open(file) as image:
            image = image.convert('RGB')
            buffer = io.BytesIO()
            image.save(buffer, 'JPEG', quality=90)
        return buffer.getvalue()
    except OSError:
        return None


# --------------------------------------------------------------------------- #
# 刮削主流程
# --------------------------------------------------------------------------- #

def _run_scrape(server: dict) -> None:
    server_id = str(server['id'])
    stats = {'created': 0, 'updated': 0, 'skipped': 0, 'unmatched': 0, 'failed': 0}
    unmatched_names: list[str] = []
    started = time.monotonic()
    _append_log(server_id, f'开始刮削：{server.get("name") or server_id}（{server.get("type")}）')
    try:
        cast_keys = _list_cast_names(server)
        persons = _list_persons(server)
        in_scope = [p for p in persons
                    if str(p['Name']).strip() in cast_keys
                    or normalize_name(str(p['Name'])) in cast_keys]
        _append_log(server_id, f'范围内演员：{len(in_scope)}/{len(persons)}'
                               f'（绑定库内 {len(cast_keys)} 个 Cast 名字交叉校验）')
        matched = 0
        for person in in_scope:
            person_id, name = str(person['Id']), str(person['Name']).strip()
            avatar_id = match_avatar(name)
            if not avatar_id:
                stats['unmatched'] += 1
                if len(unmatched_names) < UNMATCHED_PREVIEW:
                    unmatched_names.append(name)
                continue
            matched += 1
            if _person_has_image(server, person_id):
                stats['skipped'] += 1
                _append_log(server_id, f'跳过：{name}（服务器已有头像）')
                continue
            content = _avatar_content(avatar_id)
            if content is None:
                stats['failed'] += 1
                _append_log(server_id, f'失败：{name}（头像文件读取失败）')
                continue
            try:
                _upload_image(server, person_id, content)
                stats['created'] += 1
                _append_log(server_id, f'上传：{name} ← Gfriends（{len(content)} 字节）')
            except requests.RequestException as exc:
                stats['failed'] += 1
                _append_log(server_id, f'失败：{name}（上传重试 {UPLOAD_RETRY_TIMES} 次后放弃：{type(exc).__name__}）')
        elapsed = time.monotonic() - started
        _append_log(server_id, f'完成：范围 {len(in_scope)}，匹配 {matched}/{len(in_scope)}，'
                               f'新建 {stats["created"]}，跳过 {stats["skipped"]}，'
                               f'未匹配 {stats["unmatched"]}，失败 {stats["failed"]}，耗时 {elapsed:.1f}s')
        if unmatched_names:
            _append_log(server_id, '未匹配示例：' + '、'.join(unmatched_names))
    except (OSError, ValueError, requests.RequestException) as exc:
        _append_log(server_id, f'中止：{type(exc).__name__}：{exc}')
        stats['failed'] += 1
    finally:
        with _scrape_lock:
            entry = _scrapes.get(server_id) or {}
            entry.update(running=False, finished_at=_now())
            entry['stats'] = stats
            entry['unmatched'] = unmatched_names
            _scrapes[server_id] = entry
            try:
                _save_state(server_id, entry)
            except OSError:
                pass


def is_running(server_id: str) -> bool:
    with _scrape_lock:
        return bool(_scrapes.get(server_id, {}).get('running'))


def start_scrape(server: dict) -> dict:
    """启动一次异步刮削。正在跑时返回 started=False（不抛 409，调用方决定语义）。"""
    server_id = str(server['id'])
    with _scrape_lock:
        entry = _scrapes.get(server_id)
        if entry and entry.get('running'):
            return {'started': False, 'running': True}
        _scrapes[server_id] = {'running': True, 'started_at': _now(),
                               'stats': entry.get('stats') if entry else None}
    worker = threading.Thread(target=_run_scrape, args=(server,), daemon=True, name=f'people-scrape-{server_id}')
    worker.start()
    return {'started': True}


def scrape_state(server: dict) -> dict:
    server_id = str(server['id'])
    with _scrape_lock:
        entry = _scrapes.get(server_id) or {}
        if not entry:
            entry = _load_state(server_id)
        running = bool(entry.get('running'))
        stats = entry.get('stats') or {'created': 0, 'updated': 0, 'skipped': 0,
                                       'unmatched': 0, 'failed': 0}
        last_run_at = entry.get('finished_at') or entry.get('started_at') or ''
        unmatched = list(entry.get('unmatched') or [])[:UNMATCHED_PREVIEW]
    return {
        'enabled': bool((server.get('people_scrape') or {}).get('enabled')),
        'running': running,
        'last_run_at': last_run_at,
        'stats': stats,
        'unmatched': unmatched,
        'log': read_log(server_id),
    }
