"""One-shot F01 migration. Requires root; defaults to a read-only preflight.

The original tree is preserved privately before shared copies are removed.
No credential values are printed or included in evidence JSON.
"""
import argparse
import hashlib
import json
import os
import secrets
import shutil
import stat
import subprocess
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

SOURCE = Path('/data/docker/DPanel-data/JavSP-Comments')
PRIVATE = Path('/srv/javsp-comments')
CURRENT = PRIVATE / 'current'
BACKUP = PRIVATE / 'backups/pre-f01'
CONTAINER = 'javsp-comments-comments-1'
EXPECTED = {
    'admin_proxy.py': 'f3419c38716ea80fe21238a17450a0c3aa5d534b2e25838e3446970399139292',
    'docker_start.py': 'a1336ce99c5739bc171481149d949f90175360eb805e5ed8814b60a91061470e',
    'static/admin.js': '66e029ea4779eacdc227beaa54b37f0f62465101baff681129d1c1e89b8d5681',
    'static/admin.html': 'c18a0c97d661a50b463a8281552c54f006b72cc9a24fe6090610dca605173543',
    'static/style.css': '7088a03da7f907aa40170554875b92bc6e17ce43aa6eeb155168858f503cb29a',
    'Dockerfile': 'fdbaeaf99dfe5190de5329d3cb2d88989c34222e064406b2a68432850d960d3f',
    'compose.yaml': '512ce70c3eef3abb77955d97769a753dd6dc6388cb16dde9504c6adf44f5ed6d',
    'requirements.txt': 'ed58f33ba0120a0986bdabd19a6be0c75ece9f7187abae199fadc122177a4879',
}


def run(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError('Command failed: ' + args[0] + ', exit=' + str(result.returncode))
    return result.stdout


def manifest(root):
    result = {}
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError('Unsafe source directory')
    for path in root.rglob('*'):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise RuntimeError('Source contains a link or special file')
        if path.is_file():
            result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def environment(raw):
    result = {}
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        key, separator, value = line.partition('=')
        if not separator or key.strip() in result:
            raise RuntimeError('Unsupported or duplicate environment assignment')
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def http_status(token=None):
    headers = {'User-Agent': 'JavSP-F01-Acceptance'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = Request('http://127.0.0.1:8095/api/admin/stats', headers=headers)
    try:
        with urlopen(req, timeout=25) as response:
            return response.status
    except HTTPError as exc:
        return exc.code


def protect(root):
    run(['setfacl', '-Rb', str(root)])
    run(['setfacl', '-Rk', str(root)])
    for path in [root, *root.rglob('*')]:
        if path.is_symlink():
            raise RuntimeError('Unexpected link in private directory')
        os.chown(path, 0, 0)
        path.chmod(0o700 if path.is_dir() else 0o600)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError('Run as root')
    if SOURCE.resolve() != SOURCE or Path('/srv').resolve() != Path('/srv'):
        raise RuntimeError('Unexpected path resolution')
    if PRIVATE.exists() or PRIVATE.is_symlink():
        raise RuntimeError('Destination exists; inspect evidence before retrying')
    before = manifest(SOURCE)
    for name, expected in EXPECTED.items():
        if before.get(name) != expected:
            raise RuntimeError('Deployment differs from audited source: ' + name)
    ids = run(['docker', 'ps', '-aq']).split()
    containers = json.loads(run(['docker', 'inspect', *ids]))
    for container in containers:
        for mount in container.get('Mounts', []):
            source = Path(mount['Source']).resolve()
            if source == PRIVATE or source in PRIVATE.parents:
                raise RuntimeError('Private destination is covered by another container mount')
    live = next(c for c in containers if c['Name'] == '/' + CONTAINER)
    if live['Mounts'] or live['Config']['Labels'].get('com.docker.compose.project') != 'javsp-comments':
        raise RuntimeError('Unexpected management container ownership or volumes')
    image = live['Image']
    original_env = (SOURCE/'.env').read_text()
    values = environment(original_env)
    old_token = values['ADMIN_TOKEN']
    if len(old_token) < 32 or http_status(old_token) != 200:
        raise RuntimeError('Existing admin authentication is not healthy')
    evidence = {'preflight':'passed', 'source':str(SOURCE), 'destination':str(CURRENT),
                'source_files':len(before), 'image':image, 'apply':args.apply}
    if not args.apply:
        print(json.dumps(evidence, indent=2))
        return

    os.umask(0o077)
    PRIVATE.mkdir(mode=0o700)
    BACKUP.parent.mkdir(mode=0o700)
    shutil.copytree(SOURCE, BACKUP)
    if manifest(BACKUP) != before:
        raise RuntimeError('Backup verification failed; source retained')
    CURRENT.mkdir(mode=0o700)
    for name in [*EXPECTED, '.dockerignore']:
        destination = CURRENT/name
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copyfile(BACKUP/name, destination)
    new_token = secrets.token_hex(32)
    lines = [line for line in original_env.splitlines() if line.partition('=')[0].strip() != 'ADMIN_TOKEN']
    (CURRENT/'.env').write_text('\n'.join([*lines, 'ADMIN_TOKEN='+new_token, '']))
    protect(PRIVATE)
    compose = ['docker', 'compose', '-p', 'javsp-comments', '--project-directory', str(CURRENT),
               '--env-file', str(CURRENT/'.env'), '-f', str(CURRENT/'compose.yaml')]
    # Preserve the existing image and port. No other service is recreated.
    run([*compose, 'up', '-d', '--no-build', '--force-recreate', '--wait', '--wait-timeout', '60'])
    after = json.loads(run(['docker', 'inspect', CONTAINER]))[0]
    evidence.update(new_key_status=http_status(new_token), old_key_status=http_status(old_token),
                    anonymous_status=http_status(), image_unchanged=after['Image']==image,
                    ports_unchanged=after['HostConfig']['PortBindings']==live['HostConfig']['PortBindings'],
                    health=after['State'].get('Health',{}).get('Status'),
                    compose_directory=after['Config']['Labels']['com.docker.compose.project.working_dir'])
    if (evidence['new_key_status'] != 200 or evidence['old_key_status'] != 401 or
        evidence['anonymous_status'] != 401 or not evidence['image_unchanged'] or
        not evidence['ports_unchanged'] or evidence['health'] != 'healthy'):
        (PRIVATE/'f01-evidence.json').write_text(json.dumps(evidence, indent=2))
        raise RuntimeError('Acceptance failed; original tree and private backup retained')
    if manifest(SOURCE) != before:
        raise RuntimeError('Shared source changed; retained for manual investigation')
    # Both paths are fixed and checked above; verified private backup keeps all data.
    shutil.rmtree(SOURCE)
    evidence['shared_source_removed'] = not SOURCE.exists()
    extra_backups = []
    for name in ['javsp-comments-admin-before-moderation.tar.gz', 'javsp-comments-admin-moderation.tar.gz']:
        source = Path('/tmp')/name
        if source.exists():
            if source.is_symlink() or not source.is_file():
                raise RuntimeError('Unexpected temporary backup type')
            destination = BACKUP.parent/name
            shutil.copyfile(source, destination)
            destination.chmod(0o600)
            if hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(destination.read_bytes()).digest():
                raise RuntimeError('Temporary backup verification failed')
            source.unlink()
            extra_backups.append(name)
    evidence['temporary_backups_secured'] = extra_backups
    protect(PRIVATE)
    evidence['private_permissions_ok'] = all(
        stat.S_IMODE(p.stat().st_mode) == (0o700 if p.is_dir() else 0o600) and p.stat().st_uid == 0
        for p in [PRIVATE, *PRIVATE.rglob('*')])
    (PRIVATE/'f01-evidence.json').write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    main()
