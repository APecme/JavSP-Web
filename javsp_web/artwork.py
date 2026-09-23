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


def image_response(path: Path, request, thumbnail=False):
    stat = path.stat()
    revision = hashlib.sha256(f'{path.resolve()}:{stat.st_mtime_ns}:{stat.st_size}:{thumbnail}'.encode()).hexdigest()
    etag = '"' + revision + '"'
    headers = {'Cache-Control': 'private, no-cache', 'ETag': etag}
    if etag in request.headers.get('if-none-match', '').split(', ') or request.headers.get('if-none-match') == '*':
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
