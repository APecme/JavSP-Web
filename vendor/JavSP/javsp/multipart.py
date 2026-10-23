"""Shared, configuration-aware multipart recognition for Web and CLI scans."""
import logging
import re
from pathlib import Path
from urllib.parse import urlsplit

from javsp.avid import configured_media_type, get_cid, get_id


logger = logging.getLogger(__name__)
_PART_NUMBER_RE = re.compile(
    r'(?:[-_ .]+(?:cd|part|pt|p)?\s*|(?:cd|part|pt|p)\s*)'
    r'(\d{1,3})(?:(?:[-_ .]+)(?:\d{3,4}p|\d{1,2}k))?$',
    re.I,
)
_PART_LETTER_RE = re.compile(r'[-_ .]+([a-z])(?:(?:[-_ .]+)(?:\d{3,4}p|\d{1,2}k))?$', re.I)
_COPY_SUFFIX_RE = re.compile(r'\s*\(([1-9]\d*)\)$')


def media_identity(path, scanner=None):
    configured = configured_media_type(str(path), scanner)
    if configured:
        return configured[1], configured[2].casefold()
    cid = get_cid(str(path), scanner)
    return ('cid', cid.casefold()) if cid else ('dvdid', get_id(str(path), scanner).casefold())


def copy_original(path):
    """Return the same-directory filename without a terminal (n) copy tag."""
    path = Path(path)
    match = _COPY_SUFFIX_RE.search(path.stem)
    if not match:
        return None
    return path.with_name(path.stem[:match.start()] + path.suffix)


def _normalized_strm(path):
    try:
        text = Path(path).read_text(encoding='utf-8-sig')
    except (OSError, UnicodeError):
        return None
    text = text.replace('\r\n', '\n').replace('\r', '\n').strip()
    if not text or '\x00' in text or '\n' in text:
        return None
    try:
        parsed = urlsplit(text)
        if parsed.scheme.lower() not in {'http', 'https', 'rtsp', 'rtmp', 'ftp', 'smb', 'nfs'} or not parsed.hostname:
            return None
        parsed.port
    except ValueError:
        return None
    if any(character.isspace() for character in text):
        return None
    return text


def inspect_download_copy(path):
    """Inspect a numbered .strm copy candidate; never modifies either file."""
    path = Path(path)
    original = copy_original(path)
    if original is None or path.suffix.lower() != '.strm' or not original.is_file():
        return None
    duplicate_text = _normalized_strm(path)
    original_text = _normalized_strm(original)
    if duplicate_text is None or original_text is None:
        reason = '副本或原文件内容无法读取或不是有效 STRM 链接'
        duplicate = False
    elif duplicate_text == original_text:
        reason = '链接内容一致'
        duplicate = True
    else:
        reason = '链接内容不同'
        duplicate = False
    return {
        'path': str(path), 'original': str(original), 'duplicate': duplicate,
        'reason': reason,
    }


def _part_match(path):
    path = Path(path)
    numeric = _PART_NUMBER_RE.search(path.stem)
    if numeric:
        return numeric, int(numeric.group(1))
    letter = _PART_LETTER_RE.search(path.stem)
    if letter:
        return letter, ord(letter.group(1).upper()) - ord('A') + 1
    return None, None


def part_number(path, scanner=None):
    path = Path(path)
    # Check the unmodified name first, then strip only a terminal download-copy
    # marker so a lone ABC-123-A(1).strm remains part A.
    match, number = _part_match(path.with_name(path.stem.rstrip(' .') + path.suffix))
    if match is None:
        original = copy_original(path)
        if original is not None:
            match, number = _part_match(original)
    if match is None:
        return None
    base = path.with_name(path.stem[:match.start()] + path.suffix)
    identity = media_identity(path, scanner)
    # ABC-123 and date-based identifiers must not lose their actual number.
    if identity[1] and media_identity(base.name, scanner) == identity:
        return number
    # Legacy CLI folder-named movies (ABC-123/CD1.mp4) have no filename ID.
    if (identity[1] and match.start() == 0
            and re.match(r'^(?:cd|part|pt|p)\s*\d', path.stem, re.I)
            and media_identity(base, scanner) == identity):
        return number
    return None


def _filter_download_copies(paths):
    """Drop only verified same-link .strm copies and log privacy-safe diagnostics."""
    paths = [Path(path) for path in paths]
    verified = set()
    for path in paths:
        info = inspect_download_copy(path)
        if info is None:
            continue
        if info['duplicate']:
            verified.add(path)
            logger.info('跳过重复副本：%s → %s', path.name, Path(info['original']).name)
        else:
            raise ValueError('重复下载候选冲突，保留文件：%s → %s（%s）' % (
                path.name, Path(info['original']).name, info['reason']))
    return [path for path in paths if path not in verified]


def _filter_download_copies_tolerant(paths):
    """Drop verified same-link copies; keep conflicting pairs with a report.

    Unlike :func:`_filter_download_copies`, a pair whose links differ (or
    cannot be read) does not abort the batch: both files are kept out of the
    result and one conflict message is returned for the user.
    """
    paths = [Path(path) for path in paths]
    verified = set()
    conflicts = []
    for path in paths:
        info = inspect_download_copy(path)
        if info is None:
            continue
        if info['duplicate']:
            verified.add(path)
            logger.info('跳过重复副本：%s → %s', path.name, Path(info['original']).name)
        else:
            conflicts.append('重复下载候选冲突，保留文件：%s → %s（%s）' % (
                path.name, Path(info['original']).name, info['reason']))
            # Both the copy and its original stay out of this batch.
            verified.add(path)
            verified.add(Path(info['original']))
    return [path for path in paths if path not in verified], conflicts


def group_files(files, scanner=None):
    """Group only one directory's copies of an ID; reject ambiguous duplicates."""
    filtered = _filter_download_copies(files)
    groups = {}
    for path in filtered:
        kind, avid = media_identity(path, scanner)
        key = (str(path.parent), kind, avid) if avid else (str(path),)
        groups.setdefault(key, []).append(path)
    result = []
    for paths in groups.values():
        if len(paths) == 1:
            result.append(paths)
            continue
        numbers = [part_number(path, scanner) for path in paths]
        if len(paths) > 1:
            if None in numbers or len(set(numbers)) != len(numbers):
                names = '、'.join(path.name for path in paths)
                raise ValueError(f'同番号文件的分 P 编号不明确或重复，请检查后重试: {names}')
            paths = [path for _, path in sorted(zip(numbers, paths))]
        result.append(paths)
    return result


def group_files_skipping_conflicts(files, scanner=None):
    """Tolerant variant of :func:`group_files` for whole-batch scans.

    Returns ``(groups, conflicts)``. A same-ID group whose part numbers are
    ambiguous or duplicated is skipped (files stay in place) instead of
    aborting the whole batch; the conflict text names the files so the user
    can fix them later. A download-copy conflict inside the batch is likewise
    contained: both files are kept and reported.
    """
    try:
        filtered, copy_conflicts = _filter_download_copies_tolerant(files)
    except ValueError as exc:
        # Unexpected copy inspection failure: keep every file and report it.
        return [], [str(exc)]
    groups = {}
    for path in filtered:
        kind, avid = media_identity(path, scanner)
        key = (str(path.parent), kind, avid) if avid else (str(path),)
        groups.setdefault(key, []).append(path)
    result = []
    conflicts = []
    for paths in groups.values():
        if len(paths) == 1:
            result.append(paths)
            continue
        numbers = [part_number(path, scanner) for path in paths]
        if len(paths) > 1:
            if None in numbers or len(set(numbers)) != len(numbers):
                names = '、'.join(path.name for path in paths)
                conflicts.append(f'同番号文件的分 P 编号不明确或重复，已跳过该组文件: {names}')
                continue
            paths = [path for _, path in sorted(zip(numbers, paths))]
        result.append(paths)
    return result, conflicts + copy_conflicts
