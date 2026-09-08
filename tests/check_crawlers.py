"""Read-only live smoke test: metadata only, no media files or task records."""
from concurrent.futures import ThreadPoolExecutor
import importlib
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vendor/JavSP'))
from javsp.datatype import MovieInfo


def check(name):
    module = importlib.import_module('javsp.web.' + name)
    movie = MovieInfo('BBAN-601')
    try:
        module.parse_data(movie)
        return f'{name}: title={bool(movie.title)}, cover={bool(movie.cover)}, source={urlsplit(movie.url or "").hostname}'
    except Exception as error:
        return f'{name}: {type(error).__name__}'


if __name__ == '__main__':
    with ThreadPoolExecutor(max_workers=2) as pool:
        for result in pool.map(check, ['javbus', 'javdb']):
            print(result)
