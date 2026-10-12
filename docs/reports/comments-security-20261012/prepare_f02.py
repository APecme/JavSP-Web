"""Build a minimal image patch against the running release, preserving unrelated code.

Run locally with --bundle to generate a JSON payload. On the host, pass that
payload on stdin with --host. No secrets are included in the bundle.
"""
import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASELINE = '3cae32e854735b9c580b2be27f2e1c5ff78a16b4'
PATCHES = {'storage.py':['ensure_seed_data','upsert_user','list_users'], 'server.py':['login','google_cover_browser']}
STAGE = Path('/srv/javsp-web-security/f02-active')
ACTIVE_LABEL = 'bata.20261012033049'
ACTIVE_ROOT = '/app/data/updates/apps/'+ACTIVE_LABEL


def run(args, **kwargs):
    result = subprocess.run(args,capture_output=True,text=True,encoding='utf8',timeout=300,**kwargs)
    if result.returncode:
        raise RuntimeError('Command failed: '+args[0]+'; '+result.stderr[-2000:])
    return result.stdout


def nodes(source):
    return {n.name:n for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}


def fingerprint(node):
    # ast.dump formatting of empty fields differs between Python versions.
    def canonical(value):
        if isinstance(value, ast.AST):
            return [type(value).__name__, {key:canonical(item) for key,item in ast.iter_fields(value)
                                         if item is not None and item != []}]
        if isinstance(value,list):
            return [canonical(item) for item in value]
        if value is Ellipsis or isinstance(value,(bytes,complex)):
            return {'constant_type':type(value).__name__, 'value':repr(value)}
        return value
    return hashlib.sha256(json.dumps(canonical(node),sort_keys=True).encode()).hexdigest()


def bundle(root):
    output = {'patches':{}, 'auth':(root/'javsp_web/auth.py').read_text(encoding='utf8'),
              'tests':(root/'tests/test_auth_sessions.py').read_text(encoding='utf8')}
    original_auth = run(['git','-C',str(root),'show',BASELINE+':javsp_web/auth.py'])
    output['auth_before'] = hashlib.sha256(original_auth.replace('\r\n','\n').encode()).hexdigest()
    for filename, names in PATCHES.items():
        current = (root/'javsp_web'/filename).read_text(encoding='utf8')
        old = run(['git','-C',str(root),'show',BASELINE+':javsp_web/'+filename])
        old_nodes, new_nodes = nodes(old), nodes(current)
        output['patches'][filename] = {name:{'before':fingerprint(old_nodes[name]),
            'source':ast.get_source_segment(current,new_nodes[name]),
            'after':fingerprint(new_nodes[name])} for name in names}
    source = (root/'javsp_web/storage.py').read_text(encoding='utf8')
    output['storage_addition'] = ast.get_source_segment(source,nodes(source)['find_user_by_id'])
    return output


def host(payload):
    if os.geteuid()!=0 or STAGE.exists():
        raise RuntimeError('Requires root and unused staging path')
    for part in [STAGE.parent,STAGE]:
        if part.is_symlink():
            raise RuntimeError('Unexpected staging symlink')
    os.umask(0o077)
    STAGE.mkdir(parents=True,mode=0o700)
    inspect = json.loads(run(['docker','inspect','javsp-web']))[0]
    state=json.loads(run(['docker','exec','javsp-web','cat','/app/data/updates/app-current.json']))
    if state.get('current')!=ACTIVE_LABEL or state.get('commit')!=BASELINE or state.get('pending'):
        raise RuntimeError('Active application changed since inspection')
    run(['docker','cp','javsp-web:'+ACTIVE_ROOT,str(STAGE/'active')])
    for name in ['Dockerfile','requirements.txt']:
        image_value=run(['docker','exec','javsp-web','sha256sum','/app/'+name]).split()[0]
        if hashlib.sha256((STAGE/'active'/name).read_bytes()).hexdigest()!=image_value:
            raise RuntimeError('Active application requires different base dependencies')
    (STAGE/'baseline.json').write_text(json.dumps({'image':inspect['Image'], 'config_image':inspect['Config']['Image']},indent=2))
    files = STAGE/'patched'
    files.mkdir(mode=0o700)
    for name in ['auth.py','storage.py','server.py']:
        source = (STAGE/'active/javsp_web'/name).read_text()
        (STAGE/name).write_text(source)
        if name=='auth.py':
            if hashlib.sha256(source.replace('\r\n','\n').encode()).hexdigest()!=payload['auth_before']:
                raise RuntimeError('Online auth differs from audited baseline')
            result=payload['auth']
        else:
            original = nodes(source)
            replacements=[]
            for function, patch in payload['patches'][name].items():
                node=original[function]
                if fingerprint(node)!=patch['before']:
                    raise RuntimeError('Online function differs from audited baseline: '+function)
                replacements.append((node.lineno-1,node.end_lineno,patch['source']+'\n'))
            lines=source.splitlines(keepends=True)
            for start,end, replacement in sorted(replacements,reverse=True):
                lines[start:end]=[replacement]
            result=''.join(lines)
            if name=='storage.py':
                if 'find_user_by_id' in original:
                    raise RuntimeError('Unexpected identity lookup already present')
                result+='\n\n'+payload['storage_addition']+'\n'
            changed=nodes(result)
            for function,node in original.items():
                if function not in payload['patches'][name] and fingerprint(changed[function])!=fingerprint(node):
                    raise RuntimeError('Unrelated function changed: '+function)
            for function,patch in payload['patches'][name].items():
                if fingerprint(changed[function])!=patch['after']:
                    raise RuntimeError('Patched function mismatch')
        compile(result,name,'exec')
        (files/name).write_text(result)
    (STAGE/'test_auth_sessions.py').write_text(payload['tests'])
    run(['docker','tag',inspect['Image'],'javsp-web-security:f02-base'])
    (STAGE/'Dockerfile').write_text('FROM javsp-web-security:f02-base AS runtime\nCOPY active/ /app/\n'
        'ENV JAVSP_WEB_RELEASE_LABEL='+ACTIVE_LABEL+' JAVSP_WEB_RELEASE_COMMIT='+BASELINE+'-security-f02\n'
        'COPY patched/ /app/javsp_web/\n'
        'FROM runtime AS acceptance\nRUN pip install --no-cache-dir httpx==0.28.1\n'
        'COPY test_auth_sessions.py /app/test_auth_sessions.py\n')
    run(['docker','build','--target','runtime','-t','javsp-web-security:f02',str(STAGE)])
    run(['docker','build','--target','acceptance','-t','javsp-web-security:f02-test',str(STAGE)])
    # No production mounts, network or live accounts in the test container.
    tests=run(['docker','run','--rm','--network','none','--entrypoint','python','javsp-web-security:f02-test',
               '-m','unittest','test_auth_sessions','-v'])
    (STAGE/'prepare-evidence.json').write_text(json.dumps({'tests_passed':True,'test_count':9,
        'image':'javsp-web-security:f02','only_selected_functions_changed':True},indent=2))
    print(json.dumps({'prepared':True,'test_count':9,'image':'javsp-web-security:f02','stage':str(STAGE)}))


def retest(payload):
    if os.geteuid()!=0 or not (STAGE/'Dockerfile').is_file():
        raise RuntimeError('Prepared image stage required')
    # Re-test exactly the already-built runtime, changing only test code.
    for name in ['auth.py','storage.py','server.py']:
        expected=hashlib.sha256((STAGE/'patched'/name).read_bytes()).hexdigest()
        actual=run(['docker','run','--rm','--network','none','--entrypoint','sha256sum',
                    'javsp-web-security:f02','/app/javsp_web/'+name]).split()[0]
        if expected!=actual:
            raise RuntimeError('Prepared runtime image changed')
    (STAGE/'test_auth_sessions.py').write_text(payload['tests'])
    run(['docker','build','--target','acceptance','-t','javsp-web-security:f02-test',str(STAGE)])
    run(['docker','run','--rm','--network','none','--entrypoint','python','javsp-web-security:f02-test',
         '-m','unittest','test_auth_sessions','-v'])
    evidence={'tests_passed':True,'test_count':9,'image':'javsp-web-security:f02',
              'only_selected_functions_changed':True,'runtime_hashes_verified':True}
    (STAGE/'prepare-evidence.json').write_text(json.dumps(evidence,indent=2))
    print(json.dumps(evidence))


def deploy():
    if os.geteuid()!=0:
        raise RuntimeError('Root required')
    evidence=json.loads((STAGE/'prepare-evidence.json').read_text())
    baseline=json.loads((STAGE/'baseline.json').read_text())
    if not evidence.get('tests_passed'):
        raise RuntimeError('Image tests are not complete')
    live=json.loads(run(['docker','inspect','javsp-web']))[0]
    if live['Image']!=baseline['image']:
        raise RuntimeError('Production image changed since preparation')
    state=json.loads(run(['docker','exec','javsp-web','cat','/app/data/updates/app-current.json']))
    if state.get('current')!=ACTIVE_LABEL or state.get('commit')!=BASELINE or state.get('pending'):
        raise RuntimeError('Active application changed since preparation')
    check='''import sqlite3
from pathlib import Path
p=Path('/app/data/tasks.db')
if not p.exists(): raise RuntimeError('Task database missing')
c=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True)
print(c.execute("SELECT count(*) FROM tasks WHERE status IN ('running','queued') OR json_extract(payload,'$.image_retry_running')=1").fetchone()[0])
'''
    if int(run(['docker','exec','-i','javsp-web','python','-'],input=check).strip())!=0:
        raise RuntimeError('Active tasks exist; deployment deferred')
    compose=Path('/data/docker/dpanel/compose/javsp-web/docker-compose.yaml')
    original=compose.read_text()
    updated,count=re.subn(r'(?m)^(\s*image:\s*)apecme/javsp-web:latest\s*$',r'\g<1>javsp-web-security:f02',original)
    if count!=1:
        raise RuntimeError('Unexpected Compose image definition')
    os.umask(0o077)
    backup=STAGE/('deployment-backup-'+str(time.time_ns()))
    backup.mkdir(mode=0o700)
    (backup/'docker-compose.yaml').write_text(original)
    # Never overwrite the user store during rollback: migration is additive.
    run(['docker','cp','javsp-web:/app/data/users.json',str(backup/'users.json')])
    (backup/'users.json').chmod(0o600)
    before=json.loads((backup/'users.json').read_text())
    saved_state={}
    for relative in ['updates/app-current.json','updates/base-image.json','update-settings.json']:
        saved=backup/relative.replace('/','-')
        run(['docker','cp','javsp-web:/app/data/'+relative,str(saved)])
        saved.chmod(0o600)
        saved_state[relative]=saved
    compose_args=['docker','compose','-p','javsp-web','--project-directory',str(compose.parent),'-f',str(compose)]
    result={'image':'javsp-web-security:f02','predeploy_active_tasks':0,'old_sessions_cleared_by_restart':False}
    def http(path):
        try:
            with urlopen(Request('http://127.0.0.1:8590'+path,headers={'User-Agent':'JavSP-F02-Acceptance'}),timeout=4) as response:
                return response.status
        except HTTPError as exc:
            return exc.code
        except (URLError,OSError):
            return 0
    try:
        compose.write_text(updated)
        run([*compose_args,'up','-d','--no-build','--pull','never','--force-recreate','javsp-web'])
        for attempt in range(30):
            if http('/health')==200:
                break
            time.sleep(1)
        running=json.loads(run(['docker','inspect','javsp-web']))[0]
        target=json.loads(run(['docker','image','inspect','javsp-web-security:f02']))[0]['Id']
        # Compose may reorder equivalent bind entries during recreation. Compare
        # normalized entries so the acceptance gate checks the values, not order.
        old_binds=sorted(live['HostConfig'].get('Binds') or [])
        new_binds=sorted(running['HostConfig'].get('Binds') or [])
        old_ports=json.dumps(live['HostConfig'].get('PortBindings') or {},sort_keys=True)
        new_ports=json.dumps(running['HostConfig'].get('PortBindings') or {},sort_keys=True)
        result.update(health_status=http('/health'),anonymous_status=http('/api/auth/me'),
            image_matches=running['Image']==target,ports_preserved=new_ports==old_ports,
            mounts_preserved=new_binds==old_binds)
        after=json.loads(run(['docker','exec','javsp-web','python','-c',
            "from javsp_web import storage; print(storage.USERS_FILE.read_text())"]))
        clean=lambda users:[{k:v for k,v in user.items() if k not in ('user_id','auth_version')} for user in users]
        result['user_data_preserved']=clean(before)==clean(after)
        result['stable_ids_migrated']=all(u.get('user_id') and u.get('auth_version') for u in after) and len({u['user_id'] for u in after})==len(after)
        hashes={}
        for name in ['auth.py','storage.py','server.py']:
            expected=hashlib.sha256((STAGE/'patched'/name).read_bytes()).hexdigest()
            observed=run(['docker','exec','javsp-web','sha256sum','/app/javsp_web/'+name]).split()[0]
            hashes[name]=observed==expected
        result['deployed_sources_match_tested_image']=hashes
        with urlopen('http://127.0.0.1:8590/api/public-info',timeout=5) as response:
            result['active_version_preserved']=json.load(response).get('version')==ACTIVE_LABEL
        probe="""import os,json,pathlib
roots=[]
for p in pathlib.Path('/proc').iterdir():
 if p.name.isdigit():
  try:
   if b'-m\\x00javsp_web.server' in (p/'cmdline').read_bytes(): roots.append(os.readlink(p/'cwd'))
  except (FileNotFoundError,ProcessLookupError): pass
print(json.dumps(roots))
"""
        result['running_process_uses_patched_root']=json.loads(run(['docker','exec','-i','javsp-web','python','-'],input=probe))==['/app']
        if result['health_status']!=200 or result['anonymous_status']!=401 or not all(
            result[key] for key in ['image_matches','ports_preserved','mounts_preserved','user_data_preserved','stable_ids_migrated','active_version_preserved','running_process_uses_patched_root']) or not all(hashes.values()):
            raise RuntimeError('Production acceptance failed')
        result['old_sessions_cleared_by_restart']=True
        result['accepted']=True
    except Exception:
        run([*compose_args,'stop','javsp-web'])
        for relative,saved in saved_state.items():
            run(['docker','cp',str(saved),'javsp-web:/app/data/'+relative])
        compose.write_text(original)
        run([*compose_args,'up','-d','--no-build','--pull','never','--force-recreate','javsp-web'])
        result['accepted']=False
        result['rolled_back']=True
        (STAGE/'deployment-evidence.json').write_text(json.dumps(result,indent=2))
        raise
    (STAGE/'deployment-evidence.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--bundle',type=Path)
    parser.add_argument('--host',action='store_true')
    parser.add_argument('--deploy',action='store_true')
    parser.add_argument('--retest',action='store_true')
    args=parser.parse_args()
    if args.bundle:
        root=Path(__file__).resolve().parents[3]
        args.bundle.write_text(json.dumps(bundle(root)),encoding='utf8')
    elif args.host:
        host(json.load(sys.stdin))
    elif args.deploy:
        deploy()
    elif args.retest:
        retest(json.load(sys.stdin))
    else:
        parser.error('Specify --bundle PATH or --host')
