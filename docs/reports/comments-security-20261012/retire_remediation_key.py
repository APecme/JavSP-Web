"""Remove only the expired deployment key after verifying other SSH access.

Run as the deployment user. Does not print key material or retain an authorized
copy of the retired key. Writes only counts and fingerprints to stdout.
"""
import argparse
import base64
import hashlib
import json
import os
import shlex
import tempfile
from pathlib import Path

MARKER = 'claude-javsp-remediation-20261012'
parser = argparse.ArgumentParser()
parser.add_argument('--apply', action='store_true')
args = parser.parse_args()
path = Path.home() / '.ssh/authorized_keys'
assert not path.is_symlink(), 'Refusing symlink'
original = path.read_bytes()
lines = original.splitlines(keepends=True)
matched = []
for line in lines:
    fields = shlex.split(line.decode().strip(), comments=True)
    if fields and fields[-1] == MARKER:
        assert MARKER.encode() in line
        key_index = next(i for i, value in enumerate(fields) if value.startswith(('ssh-', 'ecdsa-', 'sk-')))
        digest = hashlib.sha256(base64.b64decode(fields[key_index + 1])).digest()
        matched.append((line, 'SHA256:' + base64.b64encode(digest).decode().rstrip('=')))
assert len(matched) <= 1, 'Unexpected duplicate marker; inspect first'
remaining = b''.join(line for line in lines if not any(line == found[0] for found in matched))
assert remaining.strip(), 'Refusing to remove last authorization'
result = {'marker': MARKER, 'matched': len(matched), 'fingerprints': [m[1] for m in matched], 'applied': False}
if args.apply and matched:
    assert path.read_bytes() == original, 'authorized_keys changed during inspection'
    fd, filename = tempfile.mkstemp(prefix='.authorized_keys-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(remaining)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(filename, 0o600)
        os.replace(filename, path)
    finally:
        if os.path.exists(filename):
            os.unlink(filename)
    result['applied'] = True
result['marker_remaining'] = MARKER.encode() in path.read_bytes()
result['other_lines_preserved'] = path.read_bytes() == (remaining if args.apply else original)
print(json.dumps(result))
