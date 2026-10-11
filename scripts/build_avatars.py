"""Build centered square avatars from locally saved portrait pages.

Usage: python scripts/build_avatars.py comments-service/data
The source pages stay local; only labeled 128px portraits enter the app bundle.
"""
from pathlib import Path
from html.parser import HTMLParser
import hashlib
import json
import sys
from PIL import Image, ImageOps


def center_portrait(image):
    image = ImageOps.exif_transpose(image).convert('RGB')
    # Remove only near-solid black edge rows, never interior areas of the photo.
    gray = image.convert('L')
    def black_row(y):
        histogram = gray.crop((0, y, image.width, y + 1)).histogram()
        return sum(histogram[:24]) >= image.width * .96
    top, bottom = 0, image.height
    while top < image.height // 3 and black_row(top):
        top += 1
    while bottom > image.height * 2 // 3 and black_row(bottom - 1):
        bottom -= 1
    return ImageOps.fit(image.crop((0, top, image.width, bottom)), (128, 128),
                        method=Image.Resampling.LANCZOS, centering=(.5, .5))


def build(source):
    root = Path(source).resolve()
    destination = Path(__file__).resolve().parents[1] / 'javsp_web/web/assets'
    images = []
    class Parser(HTMLParser):
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'img' and attrs.get('alt') and attrs.get('src', '').startswith('./'):
                path = (root / attrs['src']).resolve()
                if path.is_relative_to(root) and path.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp') and path.is_file():
                    images.append((attrs['alt'].strip(), path))
    for page in sorted(root.glob('*.html')):
        Parser().feed(page.read_text(encoding='utf-8'))
    entries = {}
    for name, path in images:
        key = hashlib.sha256(name.encode()).hexdigest()[:16]
        if key in entries:
            continue
        with Image.open(path) as image:
            center_portrait(image).save(destination / 'avatars' / f'{key}.webp', 'WEBP', quality=85)
        entries[key] = {'id': key, 'name': name}
    if not entries:
        raise ValueError('No portrait images found in the supplied pages')
    (destination / 'avatar-catalog.json').write_text(json.dumps(sorted(entries.values(), key=lambda x:x['name']), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'Built {len(entries)} centered portraits')


if __name__ == '__main__':
    build(sys.argv[1])
