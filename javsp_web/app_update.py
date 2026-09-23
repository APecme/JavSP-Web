"""Verified, code-only updates for Docker containers without host Docker access."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import threading
import time
import zipfile

import requests

from . import storage
from . import app_supervisor


API = 'https://api.github.com/repos/APecme/JavSP-Web'
MAX_ARCHIVE = 100 * 1024 * 1024
MAX_EXTRACTED = 200 * 1024 * 1024
REQUIRED = {'Dockerfile', 'requirements.txt', 'javsp_web/server.py', 'javsp_web/app_supervisor.py', 'vendor/JavSP/config.yml'}


def enabled():
    return os.environ.get('JAVSP_WEB_APP_SUPERVISOR') == '1' and os.environ.get('JAVSP_WEB_UPDATE_MODE') != 'image' and app_supervisor.BASE_ROOT.joinpath('Dockerfile').is_file()


def git_blob_sha(content):
    return hashlib.sha1(b'blob ' + str(len(content)).encode('ascii') + b'\0' + content).hexdigest()


def get_json(url):
    response = requests.get(url, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'JavSP-Web-updater'}, timeout=(5, 20))
    response.raise_for_status()
    return response.json()


def download_archive(commit, destination):
    with requests.get(f'{API}/zipball/{commit}', headers={'User-Agent': 'JavSP-Web-updater'}, stream=True, timeout=(5, 60)) as response:
        response.raise_for_status()
        size = 0
        with destination.open('wb') as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                size += len(chunk)
                if size > MAX_ARCHIVE:
                    raise ValueError('应用包超过大小限制')
                output.write(chunk)


def allowed(path):
    parts = path.parts
    return path.as_posix() in {'Dockerfile', 'requirements.txt'} or parts[:1] in {('javsp_web',), ('scripts',)} or parts[:2] == ('vendor', 'JavSP')


def extract_verified(archive, destination, expected):
    seen = set()
    total = 0
    with zipfile.ZipFile(archive) as package:
        for item in package.infolist():
            parts = PurePosixPath(item.filename).parts
            if item.is_dir():
                continue
            if len(parts) < 2 or any(part in ('', '.', '..') for part in parts) or '\\' in item.filename or item.filename.startswith('/'):
                raise ValueError('应用包中存在不安全路径')
            path = PurePosixPath(*parts[1:])
            if not allowed(path):
                continue
            name = path.as_posix()
            if name in seen or name not in expected or stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError('应用包文件与 Git 提交不符')
            if item.file_size > MAX_EXTRACTED - total:
                raise ValueError('应用包解压大小超过限制')
            content = package.read(item)
            total += len(content)
            if git_blob_sha(content) != expected[name]:
                raise ValueError(f'应用包校验失败：{name}')
            target = destination.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            seen.add(name)
    if not REQUIRED.issubset(seen):
        raise ValueError('应用包缺少必需文件')


def stage(info):
    label, commit = info['target'], info.get('commit', '')
    if not re.fullmatch(r'(?:bata\.\d{14}|\d+\.\d+\.\d+)', label) or not re.fullmatch(r'[a-f0-9]{40}', commit):
        raise ValueError('目标镜像未提供有效的应用版本和提交标识；请手动更新镜像')
    app_supervisor.APP_DIR.mkdir(parents=True, exist_ok=True)
    target = app_supervisor.APP_DIR / label
    if target.is_dir():
        app_supervisor.root_for(label)
        return
    commit_info = get_json(f'{API}/git/commits/{commit}')
    if commit_info.get('sha') != commit:
        raise ValueError('Git 提交标识不匹配')
    tree = get_json(f"{API}/git/trees/{commit_info['tree']['sha']}?recursive=1")
    if tree.get('truncated'):
        raise ValueError('Git 文件清单不完整')
    expected = {item['path']: item['sha'] for item in tree['tree'] if item['type'] == 'blob' and allowed(PurePosixPath(item['path']))}
    with tempfile.TemporaryDirectory(dir=app_supervisor.APP_DIR) as temporary:
        temporary_path = Path(temporary)
        archive = temporary_path / 'source.zip'
        extracted = temporary_path / 'app'
        extracted.mkdir()
        download_archive(commit, archive)
        extract_verified(archive, extracted, expected)
        for name in ('Dockerfile', 'requirements.txt'):
            if (extracted / name).read_bytes() != (app_supervisor.BASE_ROOT / name).read_bytes():
                raise ValueError('新版本修改了镜像或依赖；请手动更新 Docker 镜像')
        archive.unlink()
        extracted.rename(target)


def install(info):
    stage(info)
    current = app_supervisor.read_state()
    app_supervisor.save_state({
        'current': info['target'], 'commit': info['commit'], 'previous': current.get('current'),
        'previous_commit': current.get('commit', ''), 'pending': True,
    })


def schedule(info, record, write_job):
    def worker():
        previous = app_supervisor.read_state()
        switched = False
        try:
            write_job(dict(record, status='downloading', message='正在下载并校验应用包'))
            install(info)
            switched = True
            write_job(dict(record, status='restarting', message='应用包已就绪，正在重启服务'))
            time.sleep(2)
            os._exit(app_supervisor.RESTART_CODE)
        except Exception as exc:
            if switched:
                app_supervisor.save_state(previous)
            write_job(dict(record, status='failed', message=f'应用更新失败：{exc}', error=str(exc)))
    threading.Thread(target=worker, name='app-updater', daemon=True).start()
