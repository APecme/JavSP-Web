"""Short-lived Docker helper that survives replacement of the application container."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
import time

import docker

from . import storage


def now():
    return datetime.now(timezone.utc).isoformat()


def write_job(data):
    path = storage.DATA_DIR / 'updates'
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    storage._write_json(path / 'job.json', data)


def validate_container(attrs):
    labels = (attrs.get('Config') or {}).get('Labels') or {}
    if labels.get('io.javsp-web.self-update') != 'true':
        raise RuntimeError('当前容器没有 io.javsp-web.self-update=true 标签')
    binds = (attrs.get('HostConfig') or {}).get('Binds') or []
    if not any(len(bind.split(':')) >= 2 and bind.split(':')[1] == '/app/data' for bind in binds):
        raise RuntimeError('请先将 /app/data 挂载到持久化目录，已停止自更新')


def copied_config(attrs, image):
    config = attrs.get('Config') or {}
    allowed = ('Hostname', 'Domainname', 'User', 'AttachStdin', 'AttachStdout', 'AttachStderr', 'Tty', 'OpenStdin', 'StdinOnce', 'Env', 'Cmd', 'Image', 'Volumes', 'WorkingDir', 'Entrypoint', 'Labels', 'StopSignal', 'StopTimeout', 'Shell', 'ExposedPorts', 'Healthcheck')
    payload = {key: config[key] for key in allowed if key in config}
    payload['Image'] = image
    host = attrs.get('HostConfig') or {}
    allowed_host = ('Binds', 'Mounts', 'ContainerIDFile', 'LogConfig', 'NetworkMode', 'PortBindings', 'RestartPolicy', 'AutoRemove', 'VolumeDriver', 'VolumesFrom', 'CapAdd', 'CapDrop', 'Dns', 'DnsOptions', 'DnsSearch', 'ExtraHosts', 'GroupAdd', 'IpcMode', 'Links', 'Memory', 'MemorySwap', 'MemorySwappiness', 'OomKillDisable', 'Privileged', 'PublishAllPorts', 'ReadonlyRootfs', 'SecurityOpt', 'ShmSize', 'Runtime', 'Init')
    payload['HostConfig'] = {key: host[key] for key in allowed_host if key in host}
    return payload


def helper_config(attrs, job_id, source_id, target, data_dir):
    config = attrs.get('Config') or {}
    env = list(config.get('Env') or [])
    env.extend(['JAVSP_WEB_SELF_UPDATE=1', 'JAVSP_WEB_DOCKER_SOCKET=/var/run/docker.sock', f'JAVSP_WEB_UPDATE_SOURCE={source_id}', f'JAVSP_WEB_UPDATE_TARGET={target}'])
    source_image = str(config.get('Image') or attrs.get('Image') or '')
    if not source_image:
        raise RuntimeError('无法确定当前镜像')
    host = attrs.get('HostConfig') or {}
    binds = list(host.get('Binds') or [])
    socket_bind = '/var/run/docker.sock:/var/run/docker.sock'
    if not any(len(bind.split(':')) >= 2 and bind.split(':')[1] == '/var/run/docker.sock' for bind in binds):
        binds.append(socket_bind)
    return {
        'image': source_image,
        'command': ['python', '-m', 'javsp_web.update_worker', '--job', job_id],
        'environment': env,
        'host_config': docker.APIClient(base_url='unix:///var/run/docker.sock').create_host_config(binds=binds, network_mode=host.get('NetworkMode') or 'default', auto_remove=True, restart_policy={}),
        'labels': {'io.javsp-web.update-helper': 'true'},
    }


def wait_for_health(container, port):
    command = ['python', '-c', f'import urllib.request; urllib.request.urlopen("http://127.0.0.1:{port}/health", timeout=2).close()']
    for _ in range(15):
        container.reload()
        if container.status != 'running':
            raise RuntimeError('新容器启动后未保持运行')
        try:
            if container.exec_run(command).exit_code == 0:
                return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError('新容器未能通过健康检查')


def run(job_id):
    client = docker.from_env(timeout=30)
    record = storage._read_json(storage.DATA_DIR / 'updates' / 'job.json', {})
    backup_name = None
    source = None
    new_id = None
    old_name = None
    try:
        source_id = os.environ.get('JAVSP_WEB_UPDATE_SOURCE')
        target = os.environ.get('JAVSP_WEB_UPDATE_TARGET')
        if not source_id or not target:
            raise RuntimeError('更新参数不完整')
        source = client.containers.get(source_id)
        validate_container(source.attrs)
        record.update(status='pulling', message='正在拉取目标镜像')
        write_job(record)
        client.images.pull(target)
        record.update(status='waiting', message='等待旧容器停止')
        write_job(record)
        source.reload()
        old_name = source.name
        source.stop(timeout=20)
        source.reload()
        candidate_name = f'{old_name}.before-update-{job_id[:10]}'
        source.rename(candidate_name)
        backup_name = candidate_name
        record.update(status='replacing', message='正在创建新容器')
        write_job(record)
        new = client.api.create_container_from_config(copied_config(source.attrs, target), name=old_name)
        new_id = new['Id']
        client.api.start(new_id)
        record.update(status='verifying', message='新容器已启动，正在确认服务存活')
        write_job(record)
        fresh = client.containers.get(new_id)
        environment = (source.attrs.get('Config') or {}).get('Env') or []
        port = next((value.split('=', 1)[1] for value in environment if value.startswith('JAVSP_WEB_PORT=')), '8090')
        wait_for_health(fresh, port)
        try:
            source.remove(v=False, force=True)
            message = '更新完成'
        except Exception as cleanup_error:
            message = f'更新完成，但旧容器清理失败：{cleanup_error}'
        record.update(status='updated', message=message, completed_at=now(), new_container_id=new_id)
        write_job(record)
    except Exception as exc:  # noqa: BLE001
        errors = []
        if new_id:
            try:
                client.containers.get(new_id).remove(v=False, force=True)
            except Exception as cleanup_error:
                errors.append(f'新容器清理失败：{cleanup_error}')
        if source is not None and old_name is not None:
            try:
                source.reload()
                if backup_name and source.name == backup_name:
                    source.rename(old_name)
                source.reload()
                if source.status != 'running':
                    source.start()
            except Exception as rollback_error:
                errors.append(f'旧容器恢复失败：{rollback_error}')
        restored = backup_name is not None and not errors
        message = f'更新失败：{exc}'
        if restored:
            message += '；已恢复旧容器'
        if errors:
            message += '；' + '；'.join(errors)
        record.update(status='rolled_back' if restored else 'failed', message=message, error=str(exc), completed_at=now())
        write_job(record)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', required=True)
    args = parser.parse_args()
    run(args.job)
