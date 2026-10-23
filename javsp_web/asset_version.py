"""Content-hashed asset versions with cheap stat-signature invalidation.

``current_asset_version`` returns a version string for a directory of static
files. It re-reads file bytes only when a file signature (size, mtime_ns,
ctime_ns) or the file set changes, so unchanged requests cost one ``stat`` per
file. The version is derived from real content hashes (one SHA-256 per file)
combined in sorted name order, so an in-place edit with identical length still
changes the version via ctime_ns, and restoring identical content (e.g. after
delete/re-add) restores the previous version.
"""
import hashlib
import threading
from pathlib import Path

_LOCK = threading.Lock()
# resolved directory -> (signatures, version)
_VERSIONS: dict[str, tuple[dict[str, tuple[int, int, int]], str]] = {}
# (resolved directory, file name) -> (signature, content digest)
_DIGESTS: dict[tuple[str, str], tuple[tuple[int, int, int], str]] = {}
_MAX_STABLE_ATTEMPTS = 16


def _read_bytes(path: Path) -> bytes:
    """Read file content; separated so tests can observe byte reads."""
    return path.read_bytes()


def _signature(stat_result) -> tuple[int, int, int]:
    # ctime_ns cannot be restored by users, which catches same-length in-place edits.
    return (stat_result.st_size, stat_result.st_mtime_ns, stat_result.st_ctime_ns)


def _scan(assets_dir: Path) -> dict[str, tuple[int, int, int]]:
    signatures = {}
    try:
        entries = sorted(assets_dir.iterdir())
    except (FileNotFoundError, NotADirectoryError):
        return {}
    for path in entries:
        try:
            if path.is_file():
                signatures[path.name] = _signature(path.stat())
        except FileNotFoundError:
            continue  # vanished between listing and stat; callers rescan anyway
    return signatures


def _digest(key: str, name: str, path: Path, signature) -> str | None:
    cached = _DIGESTS.get((key, name))
    if cached and cached[0] == signature:
        return cached[1]
    for _ in range(_MAX_STABLE_ATTEMPTS):
        try:
            content = _read_bytes(path)
            if _signature(path.stat()) != signature:
                continue  # changed while reading; retry for a stable digest
        except FileNotFoundError:
            return None  # treat as absent; the caller's rescan notices the removal
        digest = hashlib.sha256(content).hexdigest()
        _DIGESTS[(key, name)] = (signature, digest)
        return digest
    return None


def _compute(assets_dir: Path, key: str, signatures) -> str | None:
    parts = []
    for name in sorted(signatures):
        digest = _digest(key, name, assets_dir / name, signatures[name])
        if digest is None:
            return None  # unstable view; caller rescans and retries
        parts.append(f'{name}:{digest}')
    return hashlib.sha256('\n'.join(parts).encode()).hexdigest()[:16]


def current_asset_version(assets_dir) -> str:
    """Return the current version of ``assets_dir``, recomputing on any change.

    The directory is read at call time so callers may repoint it (tests swap
    WEB_DIR). Reads are serialized by one lock; the cached version is only
    stored after a rescan confirms the signature set observed while hashing,
    which prevents stamping a half-old half-new version under concurrent edits.
    """
    assets_dir = Path(assets_dir)
    key = str(assets_dir.resolve())
    for _ in range(_MAX_STABLE_ATTEMPTS):
        with _LOCK:
            signatures = _scan(assets_dir)
            cached = _VERSIONS.get(key)
            if cached and cached[0] == signatures:
                return cached[1]
            version = _compute(assets_dir, key, signatures)
            if version is None:
                continue  # files churned while hashing; rescan and retry
            if _scan(assets_dir) == signatures:
                _VERSIONS[key] = (signatures, version)
                return version
    # Pathological constant churn: fall back to the latest hash so callers still
    # get a usable version; the next call rescans and corrects it.
    with _LOCK:
        signatures = _scan(assets_dir)
        version = _compute(assets_dir, key, signatures) or ''
        _VERSIONS[key] = (signatures, version)
        return version
