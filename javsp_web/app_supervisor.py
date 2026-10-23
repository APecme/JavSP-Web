"""Keep the Docker app process running across verified code-only updates."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request

from . import __version__, storage


BASE_ROOT = Path('/app')
APP_DIR = storage.DATA_DIR / 'updates' / 'apps'
STATE_FILE = storage.DATA_DIR / 'updates' / 'app-current.json'
IMAGE_FILE = storage.DATA_DIR / 'updates' / 'base-image.json'
JOB_FILE = storage.DATA_DIR / 'updates' / 'job.json'
RESTART_CODE = 75
ACTIVE_JOB_STATUSES = ('scheduled', 'downloading', 'restarting')
JOB_PHASES = {'scheduled': '排队', 'downloading': '下载校验', 'restarting': '重启'}
_child = None


def read_state():
    return storage._read_json(STATE_FILE, {})


def save_state(state):
    """Replace the state file atomically; the child updater writes it as well."""
    path = STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=str(path.parent))
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as output:
            json.dump(state, output, ensure_ascii=False, indent=2)
        os.replace(name, path)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise


def image_identity(*, parent=False):
    """Identify the base image independently of the code selected for its child.

    Release metadata identifies official builds; the file digest also notices
    changes to image/dependency declarations. This is not a Docker image digest.
    """
    if parent:
        label = os.environ.get('JAVSP_WEB_RELEASE_LABEL', '')
        commit = os.environ.get('JAVSP_WEB_RELEASE_COMMIT', '')
        label = label or __version__
    else:
        label = os.environ.get('JAVSP_WEB_BASE_RELEASE_LABEL', '')
        commit = os.environ.get('JAVSP_WEB_BASE_RELEASE_COMMIT', '')
        if not label:
            # A child launched by an older supervisor gets no base metadata. Its
            # own release label describes the overlay only when it is running the
            # overlay this data volume selected; recording that as the image would
            # make the next launch read an image change and drop the selection.
            own = str(os.environ.get('JAVSP_WEB_RELEASE_LABEL', '')).lstrip('vV')
            selected = str(read_state().get('current') or '').lstrip('vV')
            if own and own != selected:
                label, commit = own, os.environ.get('JAVSP_WEB_RELEASE_COMMIT', '')
    digest = hashlib.sha256()
    for name in ('Dockerfile', 'requirements.txt'):
        digest.update(name.encode() + b'\0')
        try:
            digest.update((BASE_ROOT / name).read_bytes())
        except OSError:
            digest.update(b'<missing>')
        digest.update(b'\0')
    return {'label': str(label).lstrip('vV'), 'commit': commit or '', 'files_sha256': digest.hexdigest()}


def recorded_image():
    """The base image identity the supervisor last bound the selection to."""
    recorded = storage._read_json(IMAGE_FILE, None)
    if isinstance(recorded, dict):
        return recorded
    binding = read_state().get('base_image')
    return binding if isinstance(binding, dict) else None


def base_identity():
    """Base image identity as seen by a running child.

    Falls back to the identity the supervisor persisted for this data volume when
    the launch provided no base metadata.
    """
    live = image_identity()
    if live['label']:
        return live
    recorded = recorded_image()
    if recorded and recorded.get('label') and recorded.get('files_sha256') == live['files_sha256']:
        return dict(live, label=str(recorded['label']).lstrip('vV'), commit=str(recorded.get('commit') or ''))
    return live


def _newer_same_channel(current, base):
    if re.fullmatch(r'bata\.\d{14}', current) and re.fullmatch(r'bata\.\d{14}', base):
        return current > base
    if re.fullmatch(r'\d+\.\d+\.\d+', current) and re.fullmatch(r'\d+\.\d+\.\d+', base):
        return tuple(map(int, current.split('.'))) > tuple(map(int, base.split('.')))
    return False


def reconcile_image_state(state, image):
    """Make an explicit image replacement take precedence over saved updates."""
    # Only the supervisor writes this separate record. Older downloaded versions
    # replace app-current.json wholesale and do not preserve its base_image field.
    recorded = storage._read_json(IMAGE_FILE, None)
    bound_image = recorded if isinstance(recorded, dict) else state.get('base_image')
    if bound_image == image:
        if state.get('base_image') != image:
            state = dict(state, base_image=image)
            save_state(state)
        if recorded != image:
            storage._write_json(IMAGE_FILE, image)
        return state
    if isinstance(bound_image, dict) and not str(bound_image.get('label') or ''):
        # Installed by a child that could not read the image metadata (an older
        # supervisor). Nothing about the image build changed, so the selection is
        # still compatible: keep it and bind it to the image running now.
        if bound_image.get('files_sha256') and bound_image.get('files_sha256') == image['files_sha256']:
            state = dict(state, base_image=image)
            save_state(state)
            storage._write_json(IMAGE_FILE, image)
            return state
    current = str(state.get('current') or '').lstrip('vV')
    # Legacy state did not record its base image. Preserve a newer update only
    # within the same channel; across channels the selected image is authoritative.
    if bound_image is None and 'base_image' not in state and _newer_same_channel(current, image['label']):
        state = dict(state, base_image=image)
        save_state(state)
        storage._write_json(IMAGE_FILE, image)
        return state

    state = dict(state, current=None, commit='', previous=None, previous_commit='', pending=False, base_image=image)
    # Do this before saving the identity, so a failed write can be retried on the
    # next launch and an old beta preference cannot immediately reinstall beta.
    settings = storage._read_json(storage.UPDATE_SETTINGS_FILE, {})
    if not isinstance(settings, dict):
        settings = {}
    settings['experience_program'] = image['label'].startswith('bata.')
    storage._write_json(storage.UPDATE_SETTINGS_FILE, settings)
    if job_status() in ACTIVE_JOB_STATUSES:
        set_job('interrupted', '镜像已更换，已停止旧更新并使用镜像自带版本')
    save_state(state)
    storage._write_json(IMAGE_FILE, image)
    return state


def root_for(label):
    if not label:
        return BASE_ROOT
    if not re.fullmatch(r'(?:bata\.\d{14}|v?\d+\.\d+\.\d+)', label):
        raise ValueError('更新版本标识无效')
    root = APP_DIR / label
    if not (root / 'javsp_web' / 'server.py').is_file():
        raise ValueError('更新文件不完整')
    try:
        same_files = all((root / filename).read_bytes() == (BASE_ROOT / filename).read_bytes()
                         for filename in ('Dockerfile', 'requirements.txt'))
    except OSError as exc:
        # A copy missing its image declarations is incomplete, not incompatible.
        raise ValueError('更新文件不完整') from exc
    if not same_files:
        raise ValueError('更新文件需要新的 Docker 镜像或依赖，请手动更新镜像')
    return root


def job_status():
    job = storage._read_json(JOB_FILE, {})
    return job.get('status') if job.get('mode') == 'app' else None


def set_job(status, message):
    job = storage._read_json(JOB_FILE, {})
    if job.get('mode') == 'app':
        job.update(status=status, message=message)
        storage._write_json(JOB_FILE, job)


def reconcile_job(state):
    """Fail an update that no live process can finish any more.

    The supervisor only reaches this point after a child exited or at its own
    start-up, so a job still marked active cannot belong to a running worker.
    An installed-but-unverified update (``pending``) is left to the health check.
    """
    job = storage._read_json(JOB_FILE, {})
    status = job.get('status')
    if job.get('mode') != 'app' or status not in ACTIVE_JOB_STATUSES or state.get('pending'):
        return job
    phase = JOB_PHASES.get(status, str(status))
    failed = dict(job, status='interrupted', message=f'上次更新在{phase}阶段中断（进程已重新启动），更新未安装；请重新检查更新')
    storage._write_json(JOB_FILE, failed)
    return failed


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
    image = image_identity(parent=True)
    while True:
        state = reconcile_image_state(read_state(), image)
        reconcile_job(state)
        label = state.get('current')
        try:
            root = root_for(label)
        except (ValueError, OSError) as exc:
            # A damaged copy must not keep the container on the image when the
            # previous installed version is still complete.
            fallback = state.get('previous')
            try:
                root = root_for(fallback) if fallback else BASE_ROOT
            except (ValueError, OSError):
                fallback, root = None, BASE_ROOT
            state.update(current=fallback, commit=(state.get('previous_commit') or '') if fallback else '',
                         previous=None, previous_commit='', pending=False)
            save_state(state)
            target = '上一版本' if fallback else '镜像自带版本'
            set_job('rolled_back', f'更新文件不可用，已恢复{target}：{exc}')
            label = fallback
        environment = os.environ.copy()
        environment.update(JAVSP_WEB_DATA_DIR=str(storage.DATA_DIR), JAVSP_VENDOR_DIR=str(root / 'vendor' / 'JavSP'), JAVSP_WEB_APP_SUPERVISOR='1')
        environment.update(JAVSP_WEB_BASE_RELEASE_LABEL=image['label'], JAVSP_WEB_BASE_RELEASE_COMMIT=image['commit'])
        if label:
            environment['JAVSP_WEB_RELEASE_LABEL'] = label
            environment['JAVSP_WEB_RELEASE_COMMIT'] = state.get('commit', '')
        expected = (label or image['label']).lstrip('vV')
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
