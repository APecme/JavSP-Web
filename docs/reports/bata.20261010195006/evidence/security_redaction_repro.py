"""Synthetic free-text redaction probe: no data files and no network."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "source"))
from javsp_web.ai import redact

cases = [
    {"input": "Authorization: Bearer SYNTHETIC_BEARER_CREDENTIAL", "marker": "SYNTHETIC_BEARER_CREDENTIAL"},
    {"input": "headers = {'Authorization': 'Bearer SYNTHETIC_BEARER_CREDENTIAL'}", "marker": "SYNTHETIC_BEARER_CREDENTIAL"},
    {"input": "Cookie: session=SYNTHETIC_COOKIE_CREDENTIAL", "marker": "SYNTHETIC_COOKIE_CREDENTIAL"},
]
results = []
for case in cases:
    output = redact({"source": case["input"]}, "different-llm-api-key")
    results.append({"input": case["input"], "output": output, "credential_remains": case["marker"] in output["source"]})
assert all(item["credential_remains"] for item in results)
(ROOT / "security-redaction-repro-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(results, ensure_ascii=False, indent=2))
