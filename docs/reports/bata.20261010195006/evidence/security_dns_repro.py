"""Local-only DNS-rebinding probe; no DNS query or external connection is made."""
from pathlib import Path
import json
import os
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "source"))
os.environ["JAVSP_WEB_DATA_DIR"] = str(ROOT / "unused-dns-test-data")
from javsp_web import ai_scrape
import requests

seen = []
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        seen.append(self.path)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"SYNTHETIC_LOCAL_ONLY_SERVICE_RESPONSE")

    def log_message(self, *args):
        pass

dns_calls = []
real_resolve = socket.getaddrinfo
def rebind(host, port, *args, **kwargs):
    if host != "audit-rebind.invalid":
        raise AssertionError("Unexpected DNS/connection target")
    dns_calls.append({"hostname": host, "port": port})
    if port is None:
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 0))]
    return real_resolve("127.0.0.1", port, *args, **kwargs)

server = HTTPServer(("127.0.0.1", 80), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    with requests.Session() as client:
        client.trust_env = False
        with patch.object(socket, "getaddrinfo", side_effect=rebind), patch.object(ai_scrape.requests, "get", side_effect=client.get):
            final_url, response = ai_scrape._fetch("http://audit-rebind.invalid/synthetic-private-service", {})
    assert response == b"SYNTHETIC_LOCAL_ONLY_SERVICE_RESPONSE"
    report = {"dns_calls": dns_calls, "local_service_requests": seen, "private_response_returned": response.decode(),
              "note": "DNS resolver simulated public IP at validation and loopback at real HTTP connection; requests transport is real and proxy env disabled only for deterministic local test."}
    (ROOT / "security-dns-repro-results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
