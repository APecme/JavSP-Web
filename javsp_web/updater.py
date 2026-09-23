"""Persisted update preferences, registry checks and independent Docker helper."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import threading
import time
import uuid

import requests

from . import __version__, storage

REPOSITORY = 'apecme/javsp-web'
SOCKET = '/var/run/docker.sock'
ACTIVE = {'scheduled', 'pulling', 'waiting', 'backing_up', 'replacing', 'verifying', 'rolling_back'}
_lock = threading.RLock()
_check_lock = threading.Lock()
_scheduler_started = False


class UpdateError(RuntimeError):
    pass


def folder():
    path = storage.DATA_DIR / 'updates'
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def read_state(name):
    return storage._read_json(folder() / (name + '.json'), {})


def write_state(name, value):
    storage._write_json(folder() / (name + '.json'), value)


def now():
    return datetime.now(timezone.utc).isoformat()


def channel():
    return 'bata' if storage.get_update_settings()['experience_program'] else 'stable'


def current_version():
    return re.sub(r'^[vV]+', '', os.environ.get('JAVSP_WEB_RELEASE_LABEL') or __version__)


def docker_client():
    import docker
    return docker.DockerClient(base_url='unix://' + SOCKET, timeout=15)


def enabled():
    return os.environ.get('JAVSP_WEB_SELF_UPDATE') == '1' and Path(SOCKET).exists() and Path('/.dockerenv').exists()


def _docker_available():
    """Compatibility signal used by the lightweight update status endpoint."""
    return enabled()


def self_container(client):
    identity = os.environ.get('JAVSP_WEB_CONTAINER') or os.environ.get('HOSTNAME', '')
    if not identity:
        raise UpdateError('无法识别当前容器，请设置 JAVSP_WEB_CONTAINER 为容器名称')
    container = client.containers.get(identity)
    expected = (container.attrs.get('Config', {}).get('Labels') or {}).get('io.javsp-web.self-update')
    if expected != 'true':
        raise UpdateError('当前容器缺少 io.javsp-web.self-update=true 标签')
    return container


def capability():
    if not enabled():
        return {'supported': False, 'reason': '网页安装需要 Docker 自更新部署配置；请按 README 一次性启用。源码和 EXE 部署仅支持检测。'}
    try:
        with docker_client() as client:
            container = self_container(client)
            from .update_worker import validate_container
            validate_container(container.attrs)
        return {'supported': True, 'reason': '已接入 Docker 更新服务，安装时会短暂重启并保留旧容器。'}
    except Exception:
        return {'supported': False, 'reason': 'Docker 更新配置不可用，请检查容器名称、标签、持久化数据挂载和 Docker socket 权限。'}


@contextmanager
def update_lock():
    # Coordinates the API, scheduler and the replacement app process.
    with _lock:
        handle = (folder() / 'update.lock').open('a')
        try:
            if os.name != 'nt':
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX)
            yield
        finally:
            handle.close()


def job():
    result = read_state('job')
    if result.get('status') in ACTIVE and result.get('helper_id') and enabled():
        try:
            with docker_client() as client:
                helper = client.containers.get(result['helper_id'])
                alive = helper.status in {'running', 'created', 'restarting'}
        except Exception as exc:
            # Unreachable Docker is not evidence that a replacement stopped.
            alive = getattr(exc, 'status_code', None) != 404
        if not alive:
            result = dict(result, status='interrupted', message='更新进程已停止，请检查 Docker 中的旧容器和更新日志后重试。', finished_at=now())
            write_state('job', result)
    return result


def busy():
    return read_state('job').get('status') in ACTIVE


def ensure_not_updating():
    if busy():
        raise UpdateError('系统正在更新，暂不接受新任务；请等待更新完成')


def active_tasks():
    from .task_store import recoverable
    return bool(recoverable())


def _get_json(url, **kwargs):
    response = requests.get(url, timeout=(5, 15), **kwargs)
    response.raise_for_status()
    return response.json()


def registry_target(tag, architecture=None, variant=''):
    """Read the exact platform image config. No image layers are downloaded."""
    token = _get_json('https://auth.docker.io/token', params={'service': 'registry.docker.io', 'scope': 'repository:' + REPOSITORY + ':pull'})['token']
    base = 'https://registry-1.docker.io/v2/' + REPOSITORY
    headers = {'Authorization': 'Bearer ' + token, 'Accept': ', '.join([
        'application/vnd.oci.image.index.v1+json', 'application/vnd.docker.distribution.manifest.list.v2+json',
        'application/vnd.oci.image.manifest.v1+json', 'application/vnd.docker.distribution.manifest.v2+json'])}
    response = requests.get(base + '/manifests/' + tag, headers=headers, timeout=(5, 15))
    response.raise_for_status()
    manifest = response.json()
    digest = response.headers.get('Docker-Content-Digest', '')
    architecture = architecture or {'x86_64': 'amd64', 'AMD64': 'amd64', 'aarch64': 'arm64'}.get(platform.machine(), platform.machine())
    if 'manifests' in manifest:
        matches = [item for item in manifest['manifests'] if item.get('platform', {}).get('os') == 'linux' and item.get('platform', {}).get('architecture') == architecture and (not variant or item.get('platform', {}).get('variant', '') == variant)]
        if not matches:
            raise UpdateError('该版本尚未发布适合当前 CPU 架构的 Docker 镜像')
        digest = matches[0]['digest']
        manifest = _get_json(base + '/manifests/' + digest, headers=headers)
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
        raise UpdateError('更新源未返回有效镜像摘要')
    config_id = manifest['config']['digest']
    config = _get_json(base + '/blobs/' + config_id, headers=headers)
    env = dict(value.split('=', 1) for value in config.get('config', {}).get('Env', []) if '=' in value)
    version = re.sub(r'^[vV]+', '', env.get('JAVSP_WEB_RELEASE_LABEL', ''))
    if not version:
        raise UpdateError('更新镜像缺少版本标识，已停止自动安装')
    return {'target': version, 'image': REPOSITORY + '@' + digest, 'image_id': config_id, 'tag': tag}


def version_tuple(value):
    match = re.fullmatch(r'[vV]*(\d+)\.(\d+)\.(\d+)', value)
    return tuple(map(int, match.groups())) if match else None


def check(force=False):
    with _check_lock:
        selected = channel()
        cached = read_state('check')
        if not force and cached.get('channel') == selected and time.time() - cached.get('checked_epoch', 0) < 60:
            return cached
        result = {'channel': selected, 'current': current_version(), 'checked_at': now(), 'checked_epoch': time.time(), 'available': False, 'error': ''}
        try:
            image_id = ''
            architecture, variant = None, ''
            if enabled():
                with docker_client() as client:
                    current = self_container(client).image
                    image_id = current.id
                    architecture, variant = current.attrs.get('Architecture'), current.attrs.get('Variant', '')
            target = registry_target('bata' if selected == 'bata' else 'latest', architecture, variant)
            if selected == 'bata' and not re.fullmatch(r'bata\.\d{14}', target['target']):
                raise UpdateError('bata 镜像的版本标识无效')
            if selected == 'stable' and not version_tuple(target['target']):
                raise UpdateError('正式版镜像的版本标识无效')
            result.update(target)
            switching = result['current'].startswith('bata.') != (selected == 'bata')
            if image_id:
                result['available'] = image_id != target['image_id']
            elif switching:
                result['available'] = True
            elif selected == 'bata':
                result['available'] = target['target'] > result['current']
            else:
                left, right = version_tuple(result['current']), version_tuple(target['target'])
                result['available'] = bool(left and right and right > left)
            result['switching_channel'] = switching
        except Exception as exc:
            result['error'] = str(exc) if isinstance(exc, UpdateError) else '无法连接更新源，请检查服务器网络后重试'
        write_state('check', result)
        return result


def status(include_capability=True):
    selected = channel()
    result = read_state('check')
    if result.get('channel') != selected:
        result = {}
    response = {'settings': storage.get_update_settings(), 'result': result, 'job': job(), 'current': current_version(), 'channel': selected}
    if include_capability:
        response['capability'] = capability()
    return response


def apply(automatic=False):
    with update_lock():
        if job().get('status') in ACTIVE:
            raise UpdateError('已有更新正在执行')
        if automatic and not storage.get_update_settings()['auto_update']:
            raise UpdateError('自动更新已关闭')
        if active_tasks():
            raise UpdateError('当前还有刮削、排队或图片任务，请等待任务结束后更新')
        support = capability()
        if not support['supported']:
            raise UpdateError(support['reason'])
        info = check(force=True)
        if info.get('error'):
            raise UpdateError(info['error'])
        if not info['available']:
            return {'status': 'current', **info}
        previous = job()
        if automatic and previous.get('image') == info['image'] and previous.get('status') in {'failed', 'rolled_back', 'interrupted'}:
            raise UpdateError('该镜像上次更新失败，已暂停自动重试；请检查后手动重试')
        with docker_client() as client:
            current = self_container(client)
            from .update_worker import helper_config
            identity = uuid.uuid4().hex
            payload = helper_config(current.attrs, identity, current.id, info['image'], str(storage.DATA_DIR))
            created = client.api.create_container(**payload)
            record = dict(id=identity, helper_id=created['Id'], source_id=current.id, status='scheduled', message='更新已排队', image=info['image'], target=info['target'], channel=info['channel'], automatic=automatic, started_at=now())
            write_state('job', record)
            try:
                client.api.start(created['Id'])
            except Exception as exc:
                write_state('job', dict(record, status='failed', message='无法启动独立更新进程', finished_at=now()))
                raise UpdateError('无法启动独立更新进程') from exc
        return record


def scheduler_tick():
    settings = storage.get_update_settings()
    if not settings['check_enabled'] or busy():
        return
    last = read_state('check')
    due = last.get('channel') != channel() or time.time() - last.get('checked_epoch', 0) >= settings['check_interval_hours'] * 3600
    result = check() if due else last
    if settings['auto_update'] and result.get('available') and not result.get('error') and enabled() and not active_tasks():
        apply(automatic=True)


def start_scheduler():
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True
    def worker():
        while True:
            time.sleep(60)
            try:
                scheduler_tick()
            except Exception:
                # Check errors are exposed via the persisted result. Failed images
                # are not retried automatically on every scheduler tick.
                pass
    threading.Thread(target=worker, name='update-checker', daemon=True).start()
