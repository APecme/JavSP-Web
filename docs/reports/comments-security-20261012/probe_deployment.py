"""Read-only host audit. Run via SSH stdin; never print secret values."""
import hashlib
import json
import os
import stat
import subprocess
import tarfile
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

root = Path('/data/docker/DPanel-data/JavSP-Comments')
container_ids = subprocess.check_output(['docker','ps','-q'],text=True).split()
containers = json.loads(subprocess.check_output(['docker','inspect',*container_ids],text=True))
relevant_mounts = []
for container in containers:
    for mount in container.get('Mounts', []):
        source = Path(mount['Source'])
        if source == root or source in root.parents:
            relevant_mounts.append({'container':container['Name'], 'source':str(source), 'destination':mount['Destination'], 'writable':mount['RW']})
def parse_env(raw):
    return dict(line.split('=', 1) for line in raw.splitlines() if '=' in line and not line.lstrip().startswith('#'))
current = parse_env((root / '.env').read_text())
result = {'paths': [], 'backup': {}, 'http': [], 'source_sha256': {}, 'ancestor_mounts':relevant_mounts}
for path in [Path('/data'), Path('/data/docker'), root.parent, root, root/'pre-cloudflare-20261012.tar.gz']:
    st = path.stat()
    result['paths'].append({'path': str(path), 'mode': oct(stat.S_IMODE(st.st_mode))})
with tarfile.open(root/'pre-cloudflare-20261012.tar.gz') as archive:
    for member in archive:
        if member.name.lstrip('./') == 'env' or member.name in ('.env', './.env'):
            old = parse_env(archive.extractfile(member).read().decode())
            result['backup'] = {k: {'present':bool(v), 'matches_current':bool(v) and current.get(k)==v}
                                for k,v in old.items() if any(part in k for part in ('TOKEN','SECRET','KEY'))}
for name in ['admin_proxy.py','static/admin.js','compose.yaml']:
    result['source_sha256'][name] = hashlib.sha256((root/name).read_bytes()).hexdigest()
for key in ['ADMIN_TOKEN','COMMENTS_WORKER_TOKEN','GITHUB_TOKEN']:
    result.setdefault('environment', {})[key] = {'present':bool(current.get(key)), 'length':len(current.get(key,''))}
result['environment']['admin_worker_different'] = current.get('ADMIN_TOKEN') != current.get('COMMENTS_WORKER_TOKEN')
for path in ['/admin','/api/admin/stats','/.env','/static/../.env']:
    req=Request('http://127.0.0.1:8095'+path, headers={'User-Agent':'JavSP-Security-Audit/1.0'})
    try:
        response=urlopen(req,timeout=10)
    except HTTPError as exc:
        response=exc
    result['http'].append({'path':path,'status':response.status,
       'csp':response.headers.get('Content-Security-Policy'), 'redirect':response.headers.get('Location')})
    response.close()
req=Request('http://127.0.0.1:8095/api/admin/stats',headers={'Authorization':'Bearer '+current['ADMIN_TOKEN']})
with urlopen(req,timeout=25) as response:
    result['authenticated_plain_http_status']=response.status
main_probe = '''
import hashlib,json
from pathlib import Path
from javsp_web import storage,auth
users=json.loads(storage.USERS_FILE.read_text())
print(json.dumps({'default_admin_password_active':any(u.get('username')=='admin' and storage.verify_password('admin',u.get('password','')) for u in users),
 'source_sha256':{name:hashlib.sha256((Path(storage.__file__).parent/name).read_bytes()).hexdigest() for name in ['server.py','auth.py','storage.py']}}))
'''
main = subprocess.run(['docker','exec','-i','javsp-web','python','-'],input=main_probe,text=True,capture_output=True)
result['main_application'] = json.loads(main.stdout) if main.returncode == 0 else {'inspection_failed':True}
print(json.dumps(result,indent=2))
