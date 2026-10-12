"""Repeatable, read-only F01 acceptance. Prints no credentials."""
import json
import argparse
import os
import re
import stat
import subprocess
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

PRIVATE = Path('/srv/javsp-comments')
CURRENT = PRIVATE/'current'
OLD = Path('/data/docker/DPanel-data/JavSP-Comments')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def command(args):
    return subprocess.check_output(args, text=True, timeout=30)


def env(path):
    result = {}
    for line in path.read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def status(token=None):
    headers = {'User-Agent':'JavSP-F01-Acceptance'}
    if token:
        headers['Authorization'] = 'Bearer '+token
    request = Request('http://127.0.0.1:8095/api/admin/stats', headers=headers)
    try:
        with build_opener(NoRedirect).open(request, timeout=25) as response:
            return response.status
    except HTTPError as exc:
        return exc.code


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--accept-retained-github-token', action='store_true',
                        help='User explicitly accepted retention; does not assert revocation')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError('Root required for private deployment inspection')
    paths = [PRIVATE, *PRIVATE.rglob('*')]
    permissions = all(not p.is_symlink() and p.stat().st_uid == 0 and p.stat().st_gid == 0
        and stat.S_IMODE(p.stat().st_mode) == (0o700 if p.is_dir() else 0o600) for p in paths)
    acl = command(['getfacl','-Rcp',str(PRIVATE)])
    acl_ok = not any(line.startswith('default:') or re.match(r'^(?:user|group):[^:]+:',line)
                     for line in acl.splitlines())
    ids = command(['docker','ps','-aq']).split()
    containers = json.loads(command(['docker','inspect',*ids]))
    covered = []
    for container in containers:
        for mount in container.get('Mounts',[]):
            source = Path(mount['Source']).resolve()
            if source == PRIVATE or source in PRIVATE.parents or PRIVATE in source.parents:
                covered.append(container['Name'])
    admin = next(c for c in containers if c['Name']=='/javsp-comments-comments-1')
    current = env(CURRENT/'.env')
    previous = env(PRIVATE/'backups/pre-f01/.env')
    checks = {
        'private_permissions':permissions,
        'no_named_or_default_acl':acl_ok,
        'no_shared_mount_covers_private_path':not covered,
        'shared_old_path_absent':not os.path.lexists(OLD),
        'temporary_old_archives_absent':all(not os.path.lexists(Path('/tmp')/name) for name in
            ['javsp-comments-admin-before-moderation.tar.gz','javsp-comments-admin-moderation.tar.gz']),
        'private_backup_present':(PRIVATE/'backups/pre-f01/pre-cloudflare-20261012.tar.gz').is_file(),
        'compose_uses_private_directory':admin['Config']['Labels'].get('com.docker.compose.project.working_dir')==str(CURRENT),
        'container_healthy':admin['State'].get('Health',{}).get('Status')=='healthy',
        'admin_key_changed':current['ADMIN_TOKEN']!=previous['ADMIN_TOKEN'],
        'worker_key_preserved':current['COMMENTS_WORKER_TOKEN']==previous['COMMENTS_WORKER_TOKEN'],
        'new_key_accepted':status(current['ADMIN_TOKEN'])==200,
        'old_key_rejected':status(previous['ADMIN_TOKEN'])==401,
        'anonymous_rejected':status()==401,
    }
    revocation = PRIVATE/'f01-github-revocation.json'
    evidence = json.loads(revocation.read_text()) if revocation.exists() else {}
    revoked = evidence.get('revoked_confirmed') is True and evidence.get('verification_statuses',[])[-1:]==[401]
    result = {'infrastructure_checks':checks, 'infrastructure_passed':all(checks.values()),
              'github_revocation_evidence_present':revocation.exists(),
              'github_revocation_verified_by_recorded_api_check':revoked,
              'github_retention_exception_accepted':args.accept_retained_github_token,
              'gate_passed_with_user_exception':all(checks.values()) and (revoked or args.accept_retained_github_token),
              'f01_complete':all(checks.values()) and revoked}
    print(json.dumps(result,indent=2))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
