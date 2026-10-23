#!/usr/bin/env python3
"""Restart the running javsp-web app child so the 1.1.42 overlay code is loaded.

Why a channel switch: the child only re-execs when it exits 75, and the only
producer is the bundled updater after `check()` reports an available update.
`current_version()` reads JAVSP_WEB_RELEASE_LABEL from the process environment,
not app-current.json, so editing that file cannot trigger anything. The updater
also refuses to apply while scrape tasks are active.

So: wait for the queue to drain, flip experience_program on (stable -> bata
switch), let the supervisor relaunch, then flip it back (bata -> stable) so the
instance ends on the 1.1.42 label. Both overlays hold byte-identical code, so
the first relaunch already loads the new code and the second only restores the
label.

Run: python3 restart-20261023.py [max_wait_seconds_per_phase]
"""
import json
import os
import shutil
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timezone

DATA = '/data/docker/DPanel-data/javsp-web/data'
UPDATES = os.path.join(DATA, 'updates')
STATE = os.path.join(UPDATES, 'app-current.json')
SETTINGS = os.path.join(DATA, 'update-settings.json')
JOB = os.path.join(UPDATES, 'job.json')
CHECK = os.path.join(UPDATES, 'check.json')
DB = os.path.join(DATA, 'tasks.db')
PROBE = 'http://192.168.0.101:8590/api/public-info'

STAMP = time.strftime('%Y%m%d-%H%M%S')
BACKUP = os.path.join(UPDATES, f'backup-{STAMP}-restart')
os.makedirs(BACKUP, exist_ok=True)
LOG = os.path.join(BACKUP, 'restart.log')


def log(message):
    line = f"[{time.strftime('%F %T')}] {message}"
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf-8') as handle:
        handle.write(line + '\n')


def read(path, default=None):
    try:
        with open(path, encoding='utf-8') as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return default


def write_json(path, value, mode):
    temporary = path + '.restart-tmp'
    with open(temporary, 'w', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def active_tasks():
    connection = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    try:
        return int(connection.execute(
            "SELECT count(*) FROM tasks WHERE status IN ('queued','running')"
            " OR json_extract(payload,'$.image_retry_running')=1"
            " OR json_extract(payload,'$.google_cover_search_running')=1").fetchone()[0])
    finally:
        connection.close()


def probe():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(PROBE, timeout=4) as response:
            return json.load(response).get('version')
    except (OSError, ValueError):
        return None


def settings(**changes):
    current = read(SETTINGS, {}) or {}
    current.update(changes)
    write_json(SETTINGS, current, 0o600)
    return current


def wait_until(description, predicate, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(5)
    log(f'超时：{description}')
    return None


def wait_idle(timeout):
    def idle():
        return active_tasks() == 0
    return wait_until('等待活跃任务清空', idle, timeout)


def phase(name, expect_label, timeout, **flag_changes):
    log(f'--- {name}：settings={flag_changes}，期望 label={expect_label}')
    if not wait_idle(60):
        log(f'{name} 放弃：仍有活跃任务，updater 会拒绝应用更新')
        return None
    armed = now_utc()
    settings(**flag_changes)

    def done():
        state = read(STATE, {}) or {}
        job = read(JOB, {}) or {}
        current = str(state.get('current') or '')
        if job.get('status') in ('failed', 'rolled_back', 'interrupted'):
            return {'aborted': job}
        if (current == expect_label and state.get('pending') is False
                and job.get('status') == 'updated' and str(job.get('started_at') or '') > armed):
            return {'state': state, 'job': job, 'version': probe()}
        return None

    result = wait_until(f'{name} 完成', done, timeout)
    if not result:
        log(f'{name} 未完成；当前 state={json.dumps(read(STATE, {}), ensure_ascii=False)} '
            f'job={json.dumps(read(JOB, {}), ensure_ascii=False)}')
        return None
    if 'aborted' in result:
        log(f'{name} 失败：{json.dumps(result["aborted"], ensure_ascii=False)}')
        return None
    log(f'{name} 完成：current={result["state"]["current"]} '
        f'previous={result["state"]["previous"]} job_started_at={result["job"]["started_at"]} '
        f'/api/public-info version={result["version"]}')
    return result


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    log('=== 目标：让 1.1.42 overlay 的分 P 容错代码真正被运行进程加载 ===')
    log(f'起始 state={json.dumps(read(STATE, {}), ensure_ascii=False)}')
    log(f'起始 settings={json.dumps(read(SETTINGS, {}), ensure_ascii=False)} 活跃任务={active_tasks()} '
        f'/api/public-info version={probe()}')
    for name, source in (('app-current.json', STATE), ('base-image.json', os.path.join(UPDATES, 'base-image.json')),
                         ('job.json', JOB), ('check.json', CHECK), ('update-settings.before.json', SETTINGS)):
        try:
            shutil.copy2(source, os.path.join(BACKUP, name))
        except OSError as exc:
            log(f'备份失败 {source}: {exc}')
    log(f'状态文件已备份到 {BACKUP}')

    # Phase A: stable -> bata, forces the child to exit 75 and be relaunched.
    first = phase('A 切到 bata 触发重启', 'bata.20261023090847', limit,
                  experience_program=True, auto_update=True)
    if not first:
        # Leave the instance on the code it already runs; never strand a half switch.
        settings(experience_program=False, auto_update=False)
        log('A 阶段失败，settings 已复原 experience_program=False auto_update=False')
        return 3

    # Phase B: back to the stable 1.1.42 label (same code, correct label).
    second = phase('B 切回 stable 1.1.42', '1.1.42', limit,
                   experience_program=False, auto_update=True)
    if not second:
        log('B 阶段失败：实例当前运行在 bata 标签但代码与 1.1.42 相同；'
            f'备份在 {BACKUP}')
        settings(auto_update=False)
        return 4

    final_settings = settings(experience_program=False, auto_update=False)
    check = read(CHECK, {}) or {}
    summary = {
        'phase_a': first,
        'phase_b': second,
        'final_state': read(STATE, {}),
        'final_job': read(JOB, {}),
        'final_settings': final_settings,
        'check': check,
        'backup': BACKUP,
    }
    write_json(os.path.join(BACKUP, 'result.json'), summary, 0o664)
    log(f'最终 state={json.dumps(summary["final_state"], ensure_ascii=False)}')
    log(f'最终 settings={json.dumps(final_settings, ensure_ascii=False)} '
        f'/api/public-info version={probe()}')
    log('=== 完成 ===')
    return 0


if __name__ == '__main__':
    sys.exit(main())
