"""Offline audit reproductions for commit 1e2d73b. No live data or network."""
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import ast
import copy
import json
import os
import shutil
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parent / 'source'
SANDBOX = Path(tempfile.mkdtemp(prefix='task-audit-', dir=Path(__file__).parent))
os.environ['JAVSP_WEB_DATA_DIR'] = str(SANDBOX / 'data')
sys.path[:0] = [str(ROOT), str(ROOT / 'vendor/JavSP')]
from javsp_web import tasks, storage, qbittorrent
from javsp.datatype import Movie

RESULTS = {}

def item(task_id, status='succeeded', **extra):
    return dict(id=task_id, status=status, created_at='2026-10-11T00:00:00Z',
                input_directory=str(SANDBOX / f'{task_id}.mp4'), file_name=task_id,
                size_bytes=1, log_tail=[], config_path=str(SANDBOX / f'{task_id}.yml'), **extra)

def server_functions(names, namespace):
    tree = ast.parse((ROOT / 'javsp_web/server.py').read_text(encoding='utf-8'))
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    for node in nodes:
        node.decorator_list = []
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'server-audit-extract', 'exec'), namespace)
    return namespace

# 1: The rounded display percentage controls destructive workflow decisions.
with patch.object(qbittorrent, '_open', return_value=('https://example.invalid', None, {})), \
     patch.object(qbittorrent, '_request', return_value=json.dumps([dict(hash='incomplete', progress=0.9996,
     state='downloading', completion_on=-1)]).encode()):
    download = qbittorrent.list_downloads({})[0]
deleted = []
ns = server_functions({'_auto_scrape_match', '_auto_scrape_download_matches', '_auto_remove_downloads'},
                      {'delete_torrent': lambda settings, torrent_hash: deleted.append(torrent_hash)})
matches = ns['_auto_scrape_match'](download, dict(enabled=True))
ns['_auto_remove_downloads']({}, [download], dict(auto_remove=True, ratio_limit=0))
assert download['progress'] == 100 and matches and deleted == ['incomplete']
RESULTS['incomplete_download'] = dict(raw_progress=0.9996, displayed=download['progress'],
                                    state=download['state'], scrape_match=matches, removed=deleted)

# 2: Cancel between running persistence and child process creation.
worker_task = item('cancel-before-popen', 'queued')
tasks._persist(worker_task)
observed_cancel = {}
def cancel_during_setup(**kwargs):
    observed_cancel['ok'] = tasks.cancel_task(worker_task['id'])
    observed_cancel['during'] = storage.get_task_record(worker_task['id'])['status']
    return {'enabled': False}
with patch.object(tasks, 'get_cookiecloud_settings', side_effect=cancel_during_setup), \
     patch.object(tasks.subprocess, 'Popen', side_effect=AssertionError('No subprocess permitted')):
    tasks._run_task(worker_task)
observed_cancel['after'] = storage.get_task_record(worker_task['id'])['status']
assert observed_cancel == {'ok': True, 'during': 'cancelled', 'after': 'running'}
RESULTS['cancel_lost'] = observed_cancel

# 3: Delete during image retry; the final stale upsert resurrects the record.
image_task = item('delete-during-retry', image_retry_running=True)
progress = dict(image_sources=dict(cover_urls=['https://example.invalid/image'], preview_pics=[]),
                output=dict(fanart_file=str(SANDBOX / 'fanart.jpg'), poster_file=str(SANDBOX / 'poster.jpg')))
tasks._persist(image_task)
observed_delete = {}
def delete_during_download(*args):
    observed_delete['accepted'] = tasks.delete_task(image_task['id'])
    observed_delete['absent_after_delete'] = storage.get_task_record(image_task['id']) is None
with patch.object(tasks, '_download_retry_image', side_effect=delete_during_download), \
     patch.object(tasks, '_rebuild_retry_poster'):
    tasks._retry_task_images(image_task, progress)
observed_delete['exists_after_retry'] = storage.get_task_record(image_task['id']) is not None
assert all(observed_delete.values())
RESULTS['deleted_task_resurrected'] = observed_delete

# 4: A concurrent accepted metadata update is overwritten by the retry snapshot.
edit_task = item('edit-during-retry', image_retry_running=True)
tasks._persist(edit_task)
observed_edit = {}
def edit_during_download(*args):
    observed_edit['accepted'] = tasks.update_task_metadata(edit_task['id'], {'title': 'User edit'}) is not None
    observed_edit['during'] = storage.get_task_record(edit_task['id'])['metadata_override']['title']
with patch.object(tasks, '_download_retry_image', side_effect=edit_during_download), \
     patch.object(tasks, '_rebuild_retry_poster'):
    tasks._retry_task_images(edit_task, progress)
observed_edit['after'] = storage.get_task_record(edit_task['id']).get('metadata_override')
assert observed_edit == {'accepted': True, 'during': 'User edit', 'after': None}
RESULTS['metadata_lost'] = observed_edit

# 5: Failure moving the second part leaves part one moved without a manifest.
media_dir = SANDBOX / 'multipart'
output_dir = SANDBOX / 'organized'
media_dir.mkdir()
output_dir.mkdir()
originals = [media_dir / 'TEST-001-1.mp4', media_dir / 'TEST-001-2.mp4']
for p in originals:
    p.write_bytes(b'Audit fixture only')
movie = Movie('TEST-001')
movie.files = list(map(str, originals))
movie.part_numbers = [1, 2]
movie.save_dir, movie.basename = str(output_dir), 'TEST-001'
real_move = shutil.move
calls = []
def fail_second_move(src, dst):
    calls.append(src)
    if len(calls) == 2:
        raise OSError('Injected mount failure for second part')
    return real_move(src, dst)
with patch('javsp.datatype.shutil.move', side_effect=fail_second_move):
    try:
        movie.rename_files()
    except OSError:
        pass
partial = dict(original_part1_exists=originals[0].exists(), original_part2_exists=originals[1].exists(),
               output_part1_exists=(output_dir / 'TEST-001-CD1.mp4').exists(),
               organizer_manifest_exists=hasattr(movie, 'new_paths'))
assert partial == dict(original_part1_exists=False, original_part2_exists=True,
                      output_part1_exists=True, organizer_manifest_exists=False)
RESULTS['multipart_partial_commit'] = partial

# 6: History truncation discards the only deduplication key.
history_downloads = [dict(hash=str(i), name=str(i), content_path='fixture') for i in range(1001)]
created_ids = []
def fake_create_tasks(*args, **kwargs):
    created_ids.append(str(len(created_ids)))
    return [{'id': created_ids[-1]}]
ns = server_functions({'_auto_scrape_downloads'}, dict(
    _auto_scrape_rules=lambda management: [dict(enabled=True, preset_id='default')],
    list_path_mappings=lambda: [], load_auto_scrape_history=storage.load_auto_scrape_history,
    save_auto_scrape_history=storage.save_auto_scrape_history,
    _auto_scrape_match=lambda item, rule: True, get_preset=lambda preset: True,
    _map_download_path=lambda path, mappings: path,
    os=SimpleNamespace(path=SimpleNamespace(exists=lambda path: True)),
    create_tasks=fake_create_tasks, now_iso=lambda: '2026-10-11T00:00:00Z'))
ns['_auto_scrape_downloads']({'id': 'test'}, history_downloads, {})
initial_count = len(created_ids)
retained_count = len(storage.load_auto_scrape_history())
ns['_auto_scrape_downloads']({'id': 'test'}, history_downloads, {})
duplicate_count = len(created_ids) - initial_count
assert initial_count == 1001 and retained_count == 1000 and duplicate_count == 1
RESULTS['download_dedup_evicted'] = dict(initial_tasks=initial_count, retained_keys=retained_count,
                                       duplicate_tasks_next_tick=duplicate_count)

# 7: Ordinary task summary persistence stats the remote output under the global task lock.
blocked, release, second_done = threading.Event(), threading.Event(), threading.Event()
locking_task = item('blocked-artwork', image_output=dict(poster_file=str(SANDBOX / 'remote/poster.jpg'),
                                                       fanart_file=str(SANDBOX / 'remote/fanart.jpg')))
def blocked_stat(path):
    if str(path).endswith('poster.jpg'):
        blocked.set()
        assert release.wait(3)
    return False
def save_second():
    tasks._persist(item('unrelated-scan', task_type='scan'))
    second_done.set()
with patch.object(tasks, '_existing_artwork', side_effect=blocked_stat):
    one = threading.Thread(target=tasks._persist, args=(locking_task,))
    one.start()
    assert blocked.wait(3)
    two = threading.Thread(target=save_second)
    two.start()
    unrelated_blocked = not second_done.wait(0.2)
    release.set()
    one.join(3)
    two.join(3)
assert unrelated_blocked and second_done.is_set()
RESULTS['global_lock_mount_io'] = dict(unrelated_scan_blocked=unrelated_blocked,
                                      completed_after_mount_release=second_done.is_set())

# 8: Default relative organizer output is persisted relative to the child CWD.
relative_root = SANDBOX / 'relative-organizer'
relative_root.mkdir()
relative_original = relative_root / 'TEST-002.mp4'
relative_original.write_bytes(b'Audit relative path fixture')
relative_movie = Movie('TEST-002')
relative_movie.files = [str(relative_original)]
relative_movie.save_dir, relative_movie.basename = '#organized/TEST-002', 'TEST-002'
previous_cwd = Path.cwd()
try:
    os.chdir(relative_root)
    Path(relative_movie.save_dir).mkdir(parents=True)
    relative_movie.rename_files()
finally:
    os.chdir(previous_cwd)
relative_task = item('relative-restore', file_organizer=dict(original_files=relative_movie.files,
    organized_files=relative_movie.new_paths, generated_files=[]),
    image_output=dict(save_dir=str(relative_root / '#organized/TEST-002')))
tasks._persist(relative_task)
advertised = tasks.get_task(relative_task['id'])['restore_available']
restored = tasks.restore_task_files(relative_task['id'])
assert advertised and not restored and (relative_root / relative_movie.new_paths[0]).exists()
RESULTS['relative_output_restore'] = dict(organized_path=relative_movie.new_paths[0],
    advertised_restore_available=advertised, restore_result=restored,
    actual_output_exists=(relative_root / relative_movie.new_paths[0]).exists())

print(json.dumps({'sandbox': str(SANDBOX), 'results': RESULTS}, ensure_ascii=False, indent=2))
