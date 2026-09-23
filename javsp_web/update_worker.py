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
    if not (attrs.get('Mounts') or []):
        raise RuntimeError('当前容器没有持久化挂载，已停止自更新')


def copied_config(attrs, image):
    config = attrs.get('Config') or {}
    allowed = ('Hostname', 'Domainname', 'User', 'AttachStdin', 'AttachStdout', 'AttachStderr', 'Tty', 'OpenStdin', 'StdinOnce', 'Env', 'Cmd', 'Image', 'Volumes', 'WorkingDir', 'Entrypoint', 'Labels', 'StopSignal', 'StopTimeout', 'Shell', 'ExposedPorts')
    payload = {key: config[key] for key in allowed if key in config}
    payload['Image'] = image
    host = attrs.get('HostConfig') or {}
    allowed_host = ('Binds', 'ContainerIDFile', 'LogConfig', 'NetworkMode', 'PortBindings', 'RestartPolicy', 'AutoRemove', 'VolumeDriver', 'VolumesFrom', 'CapAdd', 'CapDrop', 'Dns', 'DnsOptions', 'DnsSearch', 'ExtraHosts', 'GroupAdd', 'IpcMode', 'Links', 'Memory', 'MemorySwap', 'MemorySwappiness', 'OomKillDisable', 'Privileged', 'PublishAllPorts', 'ReadonlyRootfs', 'SecurityOpt', 'ShmSize', 'Runtime', 'Init')
    payload['host_config'] = {key: host[key] for key in allowed_host if key in host}
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
    if socket_bind not in binds:
        binds.append(socket_bind)
    return {
        'image': source_image,
        'command': ['python', '-m', 'javsp_web.update_worker', '--job', job_id],
        'environment': env,
        'host_config': docker.APIClient(base_url='unix:///var/run/docker.sock').create_host_config(binds=binds, network_mode=host.get('NetworkMode') or 'default', auto_remove=True, restart_policy={}),
        'labels': {'io.javsp-web.update-helper': 'true'},
    }


def run(job_id):
    client = docker.from_env(timeout=30)
    job_path = storage.DATA_DIR / 'updates' / 'job.json'
    record = storage._read_json(job_path, {})
    backup_name = None
    source = None
    try:
        source_id = os.environ.get('JAVSP_WEB_UPDATE_SOURCE')
        target = os.environ.get('JAVSP_WEB_UPDATE_TARGET')
        if not source_id or not target:
            raise RuntimeError('更新参数不完整')
        source = client.containers.get(source_id)
        validate_container(source.attrs)
        record.update(status='waiting', message='等待旧容器停止', helper_id=job_id)
        write_job(record)
        source.reload()
        source.stop(timeout=20)
        source.reload()
        old_name = source.name
        backup_name = f'{old_name}.before-update-{job_id[:10]}'
        source.rename(backup_name)
        record.update(status='replacing', message='正在创建新容器')
        write_job(record)
        new = client.api.create_container(**copied_config(source.attrs, target), name=old_name)
        client.api.start(new['Id'])
        record.update(status='verifying', message='新容器已启动，正在确认服务存活')
        write_job(record)
        time.sleep(5)
        fresh = client.containers.get(new['Id'])
        fresh.reload()
        if fresh.status != 'running':
            raise RuntimeError('新容器启动后未保持运行')
        source.remove(v=True, force=True)
        record.update(status='updated', message='更新完成', completed_at=now(), new_container_id=new['Id'])
        write_job(record)
    except Exception as exc:  # noqa: BLE001
        if source is not None and backup_name:
            try:
                source.reload()
                if source.name == backup_name:
                    source.rename(old_name)
                    source.start()
                    record['message'] = '新容器启动失败，已恢复旧容器'
            except Exception as rollback_exc:  # noqa: BLE001
                record['message'] = f'{record.get("message", str(exc))}；旧容器恢复失败：{rollback_exc}'
        record.update(status='failed', message=record.get('message') or str(exc), error=str(exc), completed_at=now())
        write_job(record)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', required=True)
    args = parser.parse_args()
    run(args.job)
