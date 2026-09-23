"""Shared, configuration-aware multipart recognition for Web and CLI scans."""
import re
from pathlib import Path

from javsp.avid import configured_media_type, get_cid, get_id


def media_identity(path, scanner=None):
    configured = configured_media_type(str(path), scanner)
    if configured:
        return configured[1], configured[2].casefold()
    cid = get_cid(str(path), scanner)
    return ('cid', cid.casefold()) if cid else ('dvdid', get_id(str(path), scanner).casefold())


def part_number(path, scanner=None):
    path = Path(path)
    match = re.search(r'(?:[-_ .]+(?:cd|part|pt)?\s*|(?:cd|part|pt)\s*)(\d{1,3})$', path.stem, re.I)
    if not match:
        return None
    base = path.with_name(path.stem[:match.start()] + path.suffix)
    identity = media_identity(path, scanner)
    # ABC-123 and date-based identifiers must not lose their actual number.
    if identity[1] and media_identity(base.name, scanner) == identity:
        return int(match.group(1))
    return None


def group_files(files, scanner=None):
    """Group only one directory's copies of an ID; reject ambiguous duplicates."""
    groups = {}
    for path in files:
        path = Path(path)
        kind, avid = media_identity(path, scanner)
        key = (str(path.parent), kind, avid) if avid else (str(path),)
        groups.setdefault(key, []).append(path)
    result = []
    for paths in groups.values():
        numbers = [part_number(path, scanner) for path in paths]
        if len(paths) > 1:
            if None in numbers or len(set(numbers)) != len(numbers):
                names = '、'.join(path.name for path in paths)
                raise ValueError(f'同番号文件的分 P 编号不明确或重复，请检查后重试: {names}')
            paths = [path for _, path in sorted(zip(numbers, paths))]
        result.append(paths)
    return result
