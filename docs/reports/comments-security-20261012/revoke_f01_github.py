"""Revoke only the legacy GitHub token after explicit user authorization."""
import argparse
import json
import time
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError

PRIVATE = Path('/srv/javsp-comments')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    raw = (PRIVATE/'backups/pre-f01/.env.pre-cloudflare').read_text()
    values = dict(line.split('=', 1) for line in raw.splitlines() if '=' in line and not line.lstrip().startswith('#'))
    token = values['GITHUB_TOKEN'].strip().strip('"').strip("'")
    supported = token.startswith(('ghp_', 'github_pat_', 'gho_', 'ghu_', 'ghr_'))
    result = {'credential_source':'private legacy backup', 'credential_count':1, 'supported':supported, 'apply':args.apply}
    if not supported:
        raise RuntimeError('Unsupported credential type; no request sent')
    if not args.apply:
        print(json.dumps(result))
        return
    opener = build_opener(NoRedirect)
    request = Request('https://api.github.com/credentials/revoke', method='POST',
        headers={'Accept':'application/vnd.github+json','Content-Type':'application/json',
                 'X-GitHub-Api-Version':'2026-03-10','User-Agent':'JavSP-F01-Remediation'},
        data=json.dumps({'credentials':[token]}).encode())
    try:
        with opener.open(request, timeout=20) as response:
            result['revocation_status'] = response.status
    except HTTPError as exc:
        result['revocation_status'] = exc.code
    if result['revocation_status'] == 202:
        checks = []
        for attempt in range(3):
            if attempt:
                time.sleep(5)
            request = Request('https://api.github.com/user', headers={
                'Authorization':'Bearer '+token, 'User-Agent':'JavSP-F01-Acceptance',
                'Accept':'application/vnd.github+json'})
            try:
                with opener.open(request, timeout=15) as response:
                    code = response.status
            except HTTPError as exc:
                code = exc.code
            checks.append(code)
            if code == 401:
                break
        result['verification_statuses'] = checks
        result['revoked_confirmed'] = checks[-1] == 401
    path = PRIVATE/'f01-github-revocation.json'
    path.touch(mode=0o600, exist_ok=True)
    path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
