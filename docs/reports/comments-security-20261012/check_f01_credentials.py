"""Read-only verification of legacy GitHub credentials; never print values."""
import json
import tarfile
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

root = Path('/data/docker/DPanel-data/JavSP-Comments')
sources = {'.env.pre-cloudflare': (root/'.env.pre-cloudflare').read_text()}
with tarfile.open(root/'pre-cloudflare-20261012.tar.gz') as archive:
    sources['pre-cloudflare archive'] = archive.extractfile('.env').read().decode()
seen = {}
results = []
for source, raw in sources.items():
    values = dict(line.split('=', 1) for line in raw.splitlines() if '=' in line and not line.lstrip().startswith('#'))
    token = values.get('GITHUB_TOKEN', '').strip().strip('"').strip("'")
    if not token:
        results.append({'source':source,'present':False})
        continue
    if token not in seen:
        req = Request('https://api.github.com/user', headers={'Authorization':'Bearer '+token,
            'Accept':'application/vnd.github+json','User-Agent':'JavSP-F01-Remediation'})
        try:
            with urlopen(req,timeout=15) as response:
                seen[token] = response.status
        except HTTPError as exc:
            seen[token] = exc.code
        except Exception:
            seen[token] = 'network_failure'
    results.append({'source':source,'present':True,'github_user_status':seen[token]})
print(json.dumps(results))
