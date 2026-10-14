"""Bundled gfriends directory, shared by profile validation and image routing."""
from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=1)
def avatar_directory():
    path = Path(__file__).parent / 'web/assets/avatar-catalog.json'
    return {item['id']: item for item in json.loads(path.read_text(encoding='utf-8'))}


def avatar_url(avatar_id):
    item = avatar_directory().get(avatar_id)
    if not item:
        return None
    return item.get('url') or f'/assets/avatars/{avatar_id}.webp'
