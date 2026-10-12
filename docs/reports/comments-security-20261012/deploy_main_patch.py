"""Host-side helper: layer tested file patches on the running JavSP-Web image.

Usage on the server (root):
  python3 deploy_main_patch.py prepare --item f03 --base javsp-web-security:f02 --stage DIR
  python3 deploy_main_patch.py deploy  --item f03 --stage DIR

DIR contains `files.json` ({"relative/path/in/app": "local file name"}), the
patched files, and `tests/` with unittest modules run offline before deploy.
An optional `acceptance.py` is executed inside the new container after the
switch; it must print a JSON object with "ok": true.
"""
import argparse
import hashlib
import ipaddress
import json
import os
import re
import sqlite3
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

COMPOSE = Path('/data/docker/dpanel/compose/javsp-web/docker-compose.yaml')
COMPOSE_ARGS = ['docker', 'compose', '-p', 'javsp-web', '--project-directory', str(COMPOSE.parent), '-f', str(COMPOSE)]


def run(args, include_stderr=False, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, timeout=900, **kwargs)
    if result.returncode:
        raise RuntimeError('Command failed: ' + ' '.join(args[:4]) + '\n' + (result.stdout + result.stderr)[-4000:])
    return result.stdout + result.stderr if include_stderr else result.stdout


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(item, base, stage, trusted_proxy=None):
    files = json.loads((stage / 'files.json').read_text())
    lines = ['FROM ' + base + ' AS runtime']
    if trusted_proxy:
        lines.append('ENV JAVSP_WEB_TRUSTED_PROXIES=' + str(ipaddress.ip_address(trusted_proxy)))
    for target, name in files.items():
        lines.append(f'COPY {name} /app/{target}')
    lines += ['ENV JAVSP_WEB_RELEASE_COMMIT=3cae32e854735b9c580b2be27f2e1c5ff78a16b4-security-' + item,
              'FROM runtime AS acceptance', 'RUN pip install --no-cache-dir httpx==0.28.1',
              'COPY tests/ /app/tests/']
    (stage / 'Dockerfile').write_text('\n'.join(lines) + '\n')
    run(['docker', 'build', '--target', 'runtime', '-t', 'javsp-web-security:' + item, str(stage)])
    run(['docker', 'build', '--target', 'acceptance', '-t', 'javsp-web-security:' + item + '-test', str(stage)])
    modules = sorted('tests.' + p.stem for p in (stage / 'tests').glob('test_*.py'))
    output = run(['docker', 'run', '--rm', '--network', 'none', '--workdir', '/app', '--entrypoint', 'python',
                  'javsp-web-security:' + item + '-test', '-m', 'unittest', '-v', *modules], include_stderr=True)
    hashes = {}
    for target, name in files.items():
        observed = run(['docker', 'run', '--rm', '--network', 'none', '--entrypoint', 'sha256sum',
                        'javsp-web-security:' + item, '/app/' + target]).split()[0]
        hashes[target] = observed == sha(stage / name)
    evidence = {'item': item, 'base': base, 'trusted_proxy': trusted_proxy, 'tests_passed': True, 'test_modules': modules, 'image_hashes_match': hashes,
                'test_summary': [line for line in (output or '').splitlines() if line.startswith(('Ran ', 'OK'))]}
    (stage / 'prepare-evidence.json').write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence, indent=2))


def http(path):
    try:
        with urlopen(Request('http://127.0.0.1:8590' + path, headers={'User-Agent': 'JavSP-Security-Acceptance'}), timeout=4) as response:
            return response.status
    except HTTPError as exc:
        return exc.code
    except (URLError, OSError):
        return 0


def deploy(item, stage):
    evidence = json.loads((stage / 'prepare-evidence.json').read_text())
    if not evidence.get('tests_passed') or not all(evidence['image_hashes_match'].values()):
        raise RuntimeError('Prepared image is not verified')
    files = json.loads((stage / 'files.json').read_text())
    live = json.loads(run(['docker', 'inspect', 'javsp-web']))[0]
    if live['Config']['Image'] != evidence['base']:
        raise RuntimeError('Running image changed since preparation; refusing to overwrite')
    check = ("import sqlite3;c=sqlite3.connect('file:/app/data/tasks.db?mode=ro',uri=True);"
             "print(c.execute(\"SELECT count(*) FROM tasks WHERE status IN ('running','queued') OR json_extract(payload,'$.image_retry_running')=1\").fetchone()[0])")
    if int(run(['docker', 'exec', 'javsp-web', 'python', '-c', check]).strip()) != 0:
        raise RuntimeError('Active tasks exist; deployment deferred')
    original = COMPOSE.read_text()
    updated, count = re.subn(r'(?m)^(\s*image:\s*)javsp-web-security:[\w.-]+\s*$', r'\g<1>javsp-web-security:' + item, original)
    if count != 1:
        raise RuntimeError('Unexpected Compose image definition')
    os.umask(0o077)
    backup = stage / ('compose-backup-' + str(time.time_ns()) + '.yaml')
    backup.write_text(original)
    result = {'item': item, 'image': 'javsp-web-security:' + item, 'previous_image': live['Config']['Image']}
    try:
        COMPOSE.write_text(updated)
        run([*COMPOSE_ARGS, 'up', '-d', '--no-build', '--pull', 'never', '--force-recreate', 'javsp-web'])
        for _ in range(60):
            if http('/health') == 200:
                break
            time.sleep(1)
        running = json.loads(run(['docker', 'inspect', 'javsp-web']))[0]
        target = json.loads(run(['docker', 'image', 'inspect', 'javsp-web-security:' + item]))[0]['Id']
        result.update(
            health_status=http('/health'), anonymous_status=http('/api/auth/me'),
            image_matches=running['Image'] == target,
            ports_preserved=json.dumps(live['HostConfig'].get('PortBindings'), sort_keys=True) == json.dumps(running['HostConfig'].get('PortBindings'), sort_keys=True),
            mounts_preserved=sorted(live['HostConfig'].get('Binds') or []) == sorted(running['HostConfig'].get('Binds') or []),
        )
        result['deployed_files_match'] = {t: run(['docker', 'exec', 'javsp-web', 'sha256sum', '/app/' + t]).split()[0] == sha(stage / n)
                                          for t, n in files.items()}
        probe = ("import os,json,pathlib\nroots=[]\nfor p in pathlib.Path('/proc').iterdir():\n if p.name.isdigit():\n  try:\n"
                 "   if b'javsp_web.server' in (p/'cmdline').read_bytes(): roots.append(os.readlink(p/'cwd'))\n"
                 "  except (FileNotFoundError,ProcessLookupError,PermissionError): pass\nprint(json.dumps(sorted(set(roots))))\n")
        result['server_process_roots'] = json.loads(run(['docker', 'exec', '-i', 'javsp-web', 'python', '-'], input=probe))
        if (stage / 'acceptance.py').is_file():
            out = run(['docker', 'exec', '-i', '-w', '/app', 'javsp-web', 'python', '-'], input=(stage / 'acceptance.py').read_text())
            result['acceptance'] = json.loads(out.strip().splitlines()[-1])
        ok = (result['health_status'] == 200 and result['anonymous_status'] == 401 and result['image_matches']
              and result['ports_preserved'] and result['mounts_preserved'] and all(result['deployed_files_match'].values())
              and result['server_process_roots'] == ['/app'] and result.get('acceptance', {'ok': True}).get('ok') is True)
        if not ok:
            raise RuntimeError('Production acceptance failed: ' + json.dumps(result))
        result['accepted'] = True
    except Exception as exc:
        COMPOSE.write_text(original)
        run([*COMPOSE_ARGS, 'up', '-d', '--no-build', '--pull', 'never', '--force-recreate', 'javsp-web'])
        result.update(accepted=False, rolled_back=True, error=str(exc)[-2000:])
        (stage / 'deployment-evidence.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        raise SystemExit(1)
    (stage / 'deployment-evidence.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    if os.geteuid() != 0:
        raise SystemExit('root required')
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'deploy'])
    parser.add_argument('--item', required=True)
    parser.add_argument('--base')
    parser.add_argument('--trusted-proxy', help='Exact trusted reverse-proxy IP baked into the patch image')
    parser.add_argument('--stage', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare(args.item, args.base, args.stage, args.trusted_proxy)
    else:
        deploy(args.item, args.stage)
