"""Refresh the avatar directory from gfriends without downloading portraits.

Usage: python scripts/sync_gfriends.py [path/to/Filetree.json]
Existing avatar IDs remain valid. Deploy the generated comments Worker allowlist
alongside the web application when the independent Worker checkout is present.
"""
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import quote
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
INDEX_URL = 'https://raw.githubusercontent.com/gfriends/gfriends/master/Filetree.json'
IMAGE_ROOT = 'https://raw.githubusercontent.com/gfriends/gfriends/master/Content/'


def catalog_from_tree(tree):
    # Filetree orders providers by ascending quality; later providers win.
    entries = {}
    for provider, portraits in tree.get('Content', {}).items():
        for alias, filename in portraits.items():
            name = Path(alias).stem
            if not name or '/' in alias or '\\' in alias:
                continue
            key = hashlib.sha256(name.encode('utf-8')).hexdigest()[:16]
            path, _, query = filename.partition('?')
            if '/' in path or '\\' in path or not path.lower().endswith('.jpg'):
                continue
            entries[key] = {'id': key, 'name': name, 'source': 'gfriends',
                            'url': IMAGE_ROOT + quote(provider, safe='') + '/' + quote(path, safe='') + ('?' + query if query else '')}
    return sorted(entries.values(), key=lambda item: item['name'].casefold())


def build(tree):
    assets = ROOT / 'javsp_web/web/assets'
    old = json.loads((assets / 'avatar-catalog.json').read_text(encoding='utf-8'))
    friends = catalog_from_tree(tree)
    ids = {item['id'] for item in friends}
    # Keep legacy portraits first for saved identities and offline fallback.
    catalog = [item for item in old if item.get('source') != 'gfriends' and item['id'] not in ids] + friends
    (assets / 'avatar-catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    worker = ROOT / 'comments-service/worker/src/avatars.js'
    allowlist = 'export const avatarIds = new Set(' + json.dumps([item['id'] for item in catalog]) + ');\n'
    if worker.parent.is_dir():
        worker.write_text(allowlist, encoding='utf-8')
    print('Indexed {} gfriends avatars; {} total IDs'.format(len(friends), len(catalog)))


if __name__ == '__main__':
    if len(sys.argv) > 1:
        tree = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    else:
        with urlopen(INDEX_URL, timeout=30) as response:
            tree = json.load(response)
    build(tree)
