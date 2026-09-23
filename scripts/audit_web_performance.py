"""Reproducible local audit using synthetic history in a temporary data directory.

Run with Python 3.12 and project dependencies plus httpx. Never imports the server
against the real data directory, starts workers, or contacts a crawler/downloader.
"""
import argparse
import copy
import gzip
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def timing(call, repeats=3):
    values = []
    for _ in range(repeats):
        start = time.perf_counter()
        call()
        values.append((time.perf_counter() - start) * 1000)
    return {'median_ms': round(statistics.median(values), 2), 'max_ms': round(max(values), 2)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--sizes', nargs='+', type=int, default=[100, 1000, 5000])
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='javsp-web-audit-') as temp:
        os.environ['JAVSP_WEB_DATA_DIR'] = temp
        os.environ['JAVSP_VENDOR_DIR'] = str(ROOT / 'vendor/JavSP')
        from PIL import Image
        from fastapi.testclient import TestClient
        # Import-time scheduler threads are unrelated to this isolated benchmark.
        with patch('threading.Thread.start'):
            from javsp_web import server, storage, tasks
        server.app.dependency_overrides[server.current_user] = lambda: {'username': 'audit', 'role': 'admin'}
        client = TestClient(server.app)
        output = Path(temp) / 'artwork'
        output.mkdir()
        poster = output / 'poster.jpg'
        Image.new('RGB', (900, 1300), '#507090').save(poster)
        report = {
            'environment': {'python': platform.python_version(), 'platform': platform.platform(), 'repeats': 3},
            'method': 'Synthetic completed tasks, 40 progress events/task; warm summaries. In-process HTTP via TestClient; authentication dependency stubbed. No WAN, NAS or browser layout measurements.',
            'assets': [], 'history': [], 'empty_api': {},
        }
        for path in sorted((ROOT / 'javsp_web/web/assets').iterdir()):
            if path.is_file():
                content = path.read_bytes()
                response = client.get('/assets/' + path.name)
                report['assets'].append({'name': path.name, 'bytes': len(content), 'gzip_bytes_estimate': len(gzip.compress(content)), 'cache_control': response.headers.get('cache-control')})
        for route in ('/api/tasks', '/api/runtime', '/api/presets', '/api/crawler-config/names', '/api/downloads'):
            response = client.get(route)
            response.raise_for_status()
            report['empty_api'][route] = {**timing(lambda: client.get(route)), 'decoded_bytes': len(response.content)}
        for count in args.sizes:
            history = []
            for index in range(count):
                item = {
                    'id': f'audit{index:07}', 'input_directory': str(Path(temp) / f'TEST-{index:05}.mp4'),
                    'file_name': f'TEST-{index:05}', 'name': f'TEST-{index:05}', 'title': 'Synthetic audit record',
                    'size_bytes': 1024**3, 'status': 'succeeded', 'source': 'manual',
                    'created_at': f'2026-09-23T10:{index % 60:02}:00+08:00', 'preset_id': 'default', 'preset_name': 'Audit',
                    'image_output': {'save_dir': str(output / str(index)), 'poster_file': str(poster), 'fanart_file': str(poster)},
                    'log_tail': ['JAVSP_PROGRESS ' + json.dumps({'stage': 'images', 'kind': 'fanart', 'done': n, 'total': 40, 'status': 'completed'}) for n in range(40)],
                }
                item['list_summary'] = tasks._stored_task_summary(item)
                history.append(item)
            storage.save_tasks(history)
            tasks.list_task_summaries()
            row = {'tasks': count, 'sqlite_bytes': storage.TASKS_DB_FILE.stat().st_size}
            row['load_tasks'] = timing(storage.load_tasks)
            row['summary_warm'] = timing(tasks.list_task_summaries)
            row['detail'] = timing(lambda: tasks.get_task(history[0]['id']))
            response = client.get('/api/tasks', headers={'Accept-Encoding': 'identity'})
            response.raise_for_status()
            row['api_decoded_bytes'] = len(response.content)
            row['api_gzip_bytes_estimate'] = len(gzip.compress(response.content))
            row['api_identity'] = timing(lambda: client.get('/api/tasks', headers={'Accept-Encoding': 'identity'}))
            row['api_gzip'] = timing(lambda: client.get('/api/tasks', headers={'Accept-Encoding': 'gzip'}))
            row['cover_lookup_24_serial'] = timing(lambda: [tasks.get_cover_path(item['id'], 0) for item in history[:24]], repeats=1)
            row['page_50'] = timing(lambda: client.get('/api/tasks?view=manual&limit=50'))
            row['overview_24'] = timing(lambda: client.get('/api/tasks?view=overview&limit=24'))
            page = client.get('/api/tasks?view=manual&limit=50')
            row['page_decoded_bytes'] = len(page.content)
            row['page_unchanged'] = timing(lambda: client.get('/api/tasks?view=manual&limit=50', headers={'If-None-Match': page.headers['etag']}))
            row['persist_one_task'] = timing(lambda: tasks._persist(copy.deepcopy(history[0])))
            report['history'].append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
        report['log_processing'] = []
        for count in (100, 500, 1000):
            lines = ['JAVSP_PROGRESS ' + json.dumps({'stage': 'images', 'kind': 'fanart', 'done': n, 'total': count}) for n in range(count)]
            def ingest():
                for end in range(1, count + 1):
                    tasks._task_progress({}, tasks._clean_log_lines(lines[:end]))
            report['log_processing'].append({'events': count, **timing(ingest)})
        client.close()
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
