"""Keep the Docker app process running across verified code-only updates."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import urllib.request

from . import storage


BASE_ROOT = Path('/app')
APP_DIR = storage.DATA_DIR / 'updates' / 'apps'
STATE_FILE = storage.DATA_DIR / 'updates' / 'app-current.json'
JOB_FILE = storage.DATA_DIR / 'updates' / 'job.json'
RESTART_CODE = 75
_child = None


def read_state():
    return storage._read_json(STATE_FILE, {})


def save_state(state):
    storage._write_json(STATE_FILE, state)


def root_for(label):
    if not label:
        return BASE_ROOT
    if not re.fullmatch(r'(?:bata\.\d{14}|v?\d+\.\d+\.\d+)', label):
        raise ValueError('更新版本标识无效')
    root = APP_DIR / label
    if not (root / 'javsp_web' / 'server.py').is_file():
        raise ValueError('更新目录不完整')
    if any((root / filename).read_bytes() != (BASE_ROOT / filename).read_bytes() for filename in ('Dockerfile', 'requirements.txt')):
        raise ValueError('应用包需要更新 Docker 镜像或依赖，无法原地运行')
    return root


def set_job(status, message):
    job = storage._read_json(JOB_FILE, {})
    if job.get('mode') == 'app':
        job.update(status=status, message=message)
        storage._write_json(JOB_FILE, job)


def health_ready(child, expected, port):
    url = f'http://127.0.0.1:{port}/api/public-info'
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(45):
        if child.poll() is not None:
            return False
        try:
            with opener.open(url, timeout=2) as response:
                if response.status == 200 and json.load(response).get('version') == expected:
                    time.sleep(3)
                    return child.poll() is None
        except (OSError, ValueError):
            pass
        time.sleep(1)
    return False


def terminate(signum, frame):
    if _child is not None and _child.poll() is None:
        _child.terminate()
        try:
            _child.wait(timeout=20)
        except subprocess.TimeoutExpired:
            _child.kill()
    raise SystemExit(0)


def run():
    global _child
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    while True:
        state = read_state()
        label = state.get('current')
        try:
            root = root_for(label)
        except (ValueError, OSError) as exc:
            state.update(current=None, previous=None, pending=False)
            save_state(state)
            set_job('rolled_back', f'应用包不可用，已恢复镜像内版本：{exc}')
            label = None
            root = BASE_ROOT
        environment = os.environ.copy()
        environment.update(JAVSP_WEB_DATA_DIR=str(storage.DATA_DIR), JAVSP_VENDOR_DIR=str(root / 'vendor' / 'JavSP'), JAVSP_WEB_APP_SUPERVISOR='1')
        if label:
            environment['JAVSP_WEB_RELEASE_LABEL'] = label
            environment['JAVSP_WEB_RELEASE_COMMIT'] = state.get('commit', '')
        expected = (label or os.environ.get('JAVSP_WEB_RELEASE_LABEL', '')).lstrip('vV')
        _child = subprocess.Popen([sys.executable, '-m', 'javsp_web.server'], cwd=root, env=environment)
        if not health_ready(_child, expected, environment.get('JAVSP_WEB_PORT', '8090')):
            if _child.poll() is None:
                _child.terminate()
                try:
                    _child.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    _child.kill()
                    _child.wait()
            if label:
                state.update(current=state.get('previous'), commit=state.get('previous_commit', ''), previous=None, pending=False)
                save_state(state)
                set_job('rolled_back', '新版本未能启动，已恢复旧版本')
                continue
            return 1
        if state.get('pending'):
            state['pending'] = False
            save_state(state)
            set_job('updated', '应用更新完成')
        exit_code = _child.wait()
        if exit_code != RESTART_CODE:
            return exit_code


if __name__ == '__main__':
    sys.exit(run())
