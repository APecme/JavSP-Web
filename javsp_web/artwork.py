"""Private conditional image responses and bounded-size cover thumbnails."""
import hashlib
import os
from pathlib import Path
import threading
import uuid

from fastapi.responses import FileResponse, Response
from PIL import Image, ImageOps

from .storage import DATA_DIR

_lock = threading.Lock()


def _etag_matches(if_none_match: str, etag: str) -> bool:
    """RFC 9110 If-None-Match matching: weak comparison, comma lists and '*'."""
    header = (if_none_match or '').strip()
    if not header:
        return False
    if header == '*':
        return True
    for candidate in header.split(','):
        candidate = candidate.strip()
        if candidate.startswith('W/'):
            candidate = candidate[2:]
        if candidate == etag:
            return True
    return False


def image_response(path: Path, request, thumbnail=False):
    stat = path.stat()
    # ctime_ns is included so same-length in-place edits that restore mtime still rotate the ETag.
    revision = hashlib.sha256(f'{path.resolve()}:{stat.st_mtime_ns}:{stat.st_ctime_ns}:{stat.st_size}:{thumbnail}'.encode()).hexdigest()
    etag = '"' + revision + '"'
    # The frontend versions image URLs with ?v=<task updated_at>; after an edit or replacement a
    # new version yields a new URL, so such responses may reuse a short private cache. The ETag
    # alone cannot expire an unexpired cached entry. Unversioned URLs keep revalidating every time.
    versioned = bool(request.query_params.get('v'))
    cache_control = 'private, max-age=300' if versioned else 'private, no-cache'
    headers = {'Cache-Control': cache_control, 'ETag': etag}
    if _etag_matches(request.headers.get('if-none-match', ''), etag):
        return Response(status_code=304, headers=headers)
    if thumbnail:
        folder = DATA_DIR / 'thumbnails'
        # One cache entry per source path, replaced when the source changes.
        key = hashlib.sha256(str(path.resolve()).encode()).hexdigest()
        target = folder / (key + '.jpg')
        marker = folder / (key + '.revision')
        with _lock:
            folder.mkdir(parents=True, exist_ok=True)
            if not target.exists() or not marker.exists() or marker.read_text(encoding='ascii') != revision:
                temp = folder / (key + '.' + uuid.uuid4().hex + '.tmp')
                try:
                    with Image.open(path) as original:
                        image = ImageOps.exif_transpose(original)
                        image.thumbnail((360, 540))
                        image.convert('RGB').save(temp, 'JPEG', quality=82, optimize=True)
                    os.replace(temp, target)
                    marker.write_text(revision, encoding='ascii')
                finally:
                    temp.unlink(missing_ok=True)
            # Reading the small thumbnail avoids a concurrent replacement during response streaming.
            return Response(target.read_bytes(), media_type='image/jpeg', headers=headers)
    return FileResponse(path, headers=headers)
