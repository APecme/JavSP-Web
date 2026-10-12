"""Use existing Cloudflare credentials without printing tokens or response secrets.

Default: inspect the exact zone and rate-limit rules. --apply adds the agreed
rule only when no equivalent rule exists; never replaces other rate limits.
"""
import argparse
import json
import os
from pathlib import Path
import tomllib

import requests

parser = argparse.ArgumentParser()
parser.add_argument('--apply', action='store_true')
parser.add_argument('--evidence', type=Path, required=True)
args = parser.parse_args()
token = os.environ.get('CLOUDFLARE_API_TOKEN')
token_file = Path(__file__).resolve().parents[3] / 'comments-service/.env.waf'
if not token and token_file.is_file():
    for line in token_file.read_text(encoding='utf-8-sig').splitlines():
        if line.strip().startswith('CLOUDFLARE_API_TOKEN='):
            token = line.strip().split('=', 1)[1].strip().strip('\"\'')
kind = 'api_token'
scopes = []
if not token:
    path = Path(os.environ['APPDATA']) / 'xdg.config/.wrangler/config/default.toml'
    config = tomllib.loads(path.read_text(encoding='utf8'))
    token = config['oauth_token']
    scopes = config.get('scopes', [])
    kind = 'wrangler_oauth'
session = requests.Session()
session.headers['Authorization'] = 'Bearer ' + token
evidence = {'credential_type': kind, 'scopes': scopes, 'host': 'comments.rtioo.com', 'applied': False}
desired = {'action': 'block', 'expression': '(http.host eq "comments.rtioo.com")',
           'description': 'JavSP comments: 60 requests per IP per 10 seconds', 'enabled': True,
           'ratelimit': {'characteristics': ['cf.colo.id', 'ip.src'], 'period': 10,
                         'requests_per_period': 60, 'mitigation_timeout': 10}}
evidence['desired_rule'] = desired


def call(method, path, body=None):
    response = session.request(method, 'https://api.cloudflare.com/client/v4' + path, json=body, timeout=30)
    data = response.json()
    if not response.ok or not data.get('success'):
        evidence.update(blocked=True, failed_operation=method + ' ' + path, http_status=response.status_code,
                        errors=[{'code': e.get('code'), 'message': e.get('message')} for e in data.get('errors', [])])
        finish(2)
    return data['result']


def finish(code=0):
    args.evidence.write_text(json.dumps(evidence, indent=2), encoding='utf8')
    print(json.dumps(evidence))
    raise SystemExit(code)


zones = call('GET', '/zones?name=rtioo.com')
assert len(zones) == 1, 'Expected exactly one rtioo.com zone'
zone = zones[0]['id']
evidence['zone_id'] = zone
rulesets = call('GET', f'/zones/{zone}/rulesets')
rate_sets = [r for r in rulesets if r.get('phase') == 'http_ratelimit' and r.get('kind') == 'zone']
assert len(rate_sets) <= 1, 'Unexpected multiple zone entrypoints'
ruleset = call('GET', f'/zones/{zone}/rulesets/{rate_sets[0]["id"]}') if rate_sets else None
rules = ruleset.get('rules', []) if ruleset else []
evidence['existing_rate_rules'] = len(rules)


def equivalent(rule):
    rate = rule.get('ratelimit', {})
    return (rule.get('enabled', True) and rule.get('action') == 'block'
            and rule.get('expression', '').replace('(', '').replace(')', '').strip() == 'http.host eq "comments.rtioo.com"'
            and set(rate.get('characteristics', [])) == {'cf.colo.id', 'ip.src'}
            and all(rate.get(key) == desired['ratelimit'][key] for key in ('period', 'requests_per_period', 'mitigation_timeout')))


matching = [r for r in rules if equivalent(r)]
if matching:
    evidence.update(verified=True, rule_id=matching[0]['id'])
elif args.apply:
    if ruleset:
        result = call('POST', f'/zones/{zone}/rulesets/{ruleset["id"]}/rules', desired)
    else:
        result = call('POST', f'/zones/{zone}/rulesets', {'name': 'JavSP comments rate limiting',
                      'description': 'Protect the public comments request budget', 'kind': 'zone',
                      'phase': 'http_ratelimit', 'rules': [desired]})
    observed = call('GET', f'/zones/{zone}/rulesets/{result["id"]}')
    matching = [r for r in observed.get('rules', []) if equivalent(r)]
    assert matching, 'Created rule could not be verified'
    evidence.update(applied=True, verified=True, rule_id=matching[0]['id'], ruleset_id=result['id'])
else:
    evidence['verified'] = False
finish()
