"""Bounded production WAF check: at most 74 requests to DB-free /health.

No credentials, comments, database queries, or writes. One bounded burst only;
an inconclusive result is recorded rather than escalating traffic volume.
"""
import concurrent.futures
import json
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

URL = 'https://comments.rtioo.com/health'
local = threading.local()


def probe(_=None):
    if not hasattr(local, 'session'):
        local.session = requests.Session()
        local.session.headers['User-Agent'] = 'JavSP-F04-WAF-Acceptance/1.0'
    started = time.monotonic()
    try:
        response = local.session.get(URL, timeout=10, allow_redirects=False)
        return {'status': response.status_code, 'seconds': round(time.monotonic() - started, 3),
                'colo': response.headers.get('CF-Ray', '').rsplit('-', 1)[-1],
                'cloudflare': response.headers.get('server', '').lower() == 'cloudflare',
                'worker_health': response.status_code == 200 and response.text.strip() == '{"ok":true}'}
    except requests.RequestException as exc:
        return {'status': 0, 'error_type': type(exc).__name__}


result = {'checked_at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(), 'url': URL,
          'request_cap': 74, 'database_free': True, 'baseline': probe(), 'verified': False}
if result['baseline'].get('worker_health'):
    start = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        replies = list(pool.map(probe, range(70)))
    result.update(burst_requests=70, burst_seconds=round(time.monotonic() - start, 3),
                  status_counts=dict(Counter(str(r['status']) for r in replies)),
                  colos=sorted({r.get('colo', '') for r in replies}),
                  edge_429_count=sum(r['status'] == 429 and r.get('cloudflare', False) for r in replies))
    # Fixed upper bound; allow the configured 10-second mitigation to expire.
    time.sleep(12)
    result['recovery'] = [probe() for _ in range(3)]
    result['verified'] = result['edge_429_count'] > 0 and all(r.get('worker_health') for r in result['recovery'])
path = Path(__file__).with_name('f04-waf-acceptance.json')
path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
print(json.dumps(result))
raise SystemExit(0 if result['verified'] else 1)
