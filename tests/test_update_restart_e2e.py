"""End-to-end restart test: a real supervisor process launches a real child.

The suite has no Docker access and no FastAPI here, so an "image" is a directory
holding the real supervisor/updater modules plus a stdlib server stand-in that
reports its release label. What is real: separate supervisor processes, the data
volume shared between them, files on disk, PID/restart handling and the HTTP
health check against a child process.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from javsp_web import app_supervisor, app_update, storage

REPO = Path(__file__).resolve().parent.parent
# The real supervisor polls /api/public-info, then keeps the child for 3s before
# accepting it; the stand-in server must outlive that window.
CHILD_LIFETIME = '5.5'
COPIED = ('__init__.py', 'storage.py', 'timeutils.py', 'app_supervisor.py', 'app_update.py', 'updater.py')

SERVER_STUB = '''\
import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REPORTED = {reported!r}
LABEL = (os.environ.get('JAVSP_WEB_RELEASE_LABEL') or {version!r}).lstrip('vV')
data = Path(os.environ.get('JAVSP_WEB_DATA_DIR') or 'data')
port = int(os.environ.get('JAVSP_WEB_PORT') or '8090')
lifetime = float(os.environ.get('E2E_CHILD_LIFETIME') or '5.5')
markers = data / 'e2e-launches'
markers.mkdir(parents=True, exist_ok=True)
(markers / (str(os.getpid()) + '.json')).write_text(json.dumps({{
    'cwd': os.getcwd(),
    'label': LABEL,
    'release': os.environ.get('JAVSP_WEB_RELEASE_LABEL', ''),
    'base': os.environ.get('JAVSP_WEB_BASE_RELEASE_LABEL', ''),
}}), encoding='utf-8')
VERSION = REPORTED or LABEL


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/api/public-info':
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps({{'name': 'e2e', 'version': VERSION}}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


server = HTTPServer(('127.0.0.1', port), Handler)
server.timeout = 0.2
deadline = time.time() + lifetime
while time.time() < deadline:
    server.handle_request()
server.server_close()
'''

BROKEN_STUB = '''\
import json
import os
from pathlib import Path

data = Path(os.environ.get('JAVSP_WEB_DATA_DIR') or 'data')
markers = data / 'e2e-launches'
markers.mkdir(parents=True, exist_ok=True)
(markers / (str(os.getpid()) + '.json')).write_text(json.dumps({
    'cwd': os.getcwd(),
    'label': (os.environ.get('JAVSP_WEB_RELEASE_LABEL') or '').lstrip('vV'),
    'release': os.environ.get('JAVSP_WEB_RELEASE_LABEL', ''),
    'base': os.environ.get('JAVSP_WEB_BASE_RELEASE_LABEL', ''),
}), encoding='utf-8')
raise SystemExit(1)
'''

DRIVER = '''\
import sys
from pathlib import Path
from javsp_web import app_supervisor
app_supervisor.BASE_ROOT = Path(sys.argv[1])
sys.exit(app_supervisor.run())
'''


class RestartEndToEndTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.volume = self.root / 'data'
        self.volume.mkdir()
        self.image = self.make_image(self.root / 'image-1', 'bata.20260923000000', 'b' * 40)
        self.commit = 'a' * 40
        self.target = 'bata.20260924044117'

    # -- fixtures -----------------------------------------------------------
    def make_image(self, root, label, commit, server_source=None):
        root.mkdir(parents=True)
        package = root / 'javsp_web'
        package.mkdir()
        for name in COPIED:
            shutil.copyfile(REPO / 'javsp_web' / name, package / name)
        (root / 'Dockerfile').write_bytes(b'FROM python:3.12-slim\n')
        (root / 'requirements.txt').write_bytes(b'fastapi==1\n')
        version = label
        (package / 'server.py').write_text(
            server_source or SERVER_STUB.format(reported='', version=version), encoding='utf-8')
        return root

    def free_port(self):
        import socket
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            return sock.getsockname()[1]

    def stage_overlay(self, server_source=None):
        files = {
            'Dockerfile': (self.image / 'Dockerfile').read_bytes(),
            'requirements.txt': (self.image / 'requirements.txt').read_bytes(),
            'javsp_web/server.py': (server_source or SERVER_STUB.format(reported='', version=self.target)).encode(),
            'javsp_web/app_supervisor.py': b'print("supervisor")\n',
            'vendor/JavSP/config.yml': b'scanner: {}\n',
        }
        import io
        import zipfile
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as package:
            for name, content in files.items():
                package.writestr('APecme-JavSP-Web-abc/' + name, content)
        archive = self.root / 'overlay.zip'
        archive.write_bytes(buffer.getvalue())
        tree = {'truncated': False, 'tree': [
            {'path': name, 'type': 'blob', 'sha': app_update.git_blob_sha(content)}
            for name, content in files.items()
        ]}

        def get_json(url):
            return {'sha': self.commit, 'tree': {'sha': 'c' * 40}} if '/commits/' in url else tree

        patches = [
            patch.object(app_supervisor, 'BASE_ROOT', self.image),
            patch.object(app_supervisor, 'APP_DIR', self.volume / 'updates' / 'apps'),
            patch.object(app_supervisor, 'STATE_FILE', self.volume / 'updates' / 'app-current.json'),
            patch.object(app_supervisor, 'IMAGE_FILE', self.volume / 'updates' / 'base-image.json'),
            patch.object(app_supervisor, 'JOB_FILE', self.volume / 'updates' / 'job.json'),
            patch.object(storage, 'DATA_DIR', self.volume),
            patch.object(storage, 'UPDATE_SETTINGS_FILE', self.volume / 'update-settings.json'),
            patch.object(storage, 'ensure_seed_data'),
            patch.object(app_update, 'get_json', side_effect=get_json),
            patch.object(app_update, 'download_archive', side_effect=lambda commit, path: shutil.copyfile(archive, path)),
            patch.dict(os.environ, {'JAVSP_WEB_BASE_RELEASE_LABEL': 'bata.20260923000000',
                                    'JAVSP_WEB_BASE_RELEASE_COMMIT': 'b' * 40}),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        app_update.install({'target': self.target, 'commit': self.commit})
        # The updater always records the job before installing and restarting.
        (self.volume / 'updates' / 'job.json').write_text(json.dumps({
            'mode': 'app', 'status': 'restarting', 'id': 'e2e', 'target': self.target,
            'image': 'example@sha256:' + 'e' * 64, 'message': '更新文件已就绪，正在重新启动服务',
        }), encoding='utf-8')
        return self.volume / 'updates' / 'apps' / self.target

    def clear_markers(self):
        shutil.rmtree(self.volume / 'e2e-launches', ignore_errors=True)

    def launches(self):
        found = sorted((self.volume / 'e2e-launches').glob('*.json'), key=lambda path: path.stat().st_mtime_ns)
        return [json.loads(path.read_text(encoding='utf-8')) for path in found]

    def start(self, image, label, commit):
        """One container start: a brand-new supervisor process on the same volume."""
        environment = {
            'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
            'HOME': str(self.root),
            'JAVSP_WEB_DATA_DIR': str(self.volume),
            'JAVSP_WEB_PORT': str(self.free_port()),
            'JAVSP_WEB_RELEASE_LABEL': label,
            'JAVSP_WEB_RELEASE_COMMIT': commit,
            'E2E_CHILD_LIFETIME': CHILD_LIFETIME,
        }
        result = subprocess.run(
            [sys.executable, '-c', DRIVER, str(image)],
            cwd=image, env=environment, capture_output=True, text=True, timeout=120,
        )
        return result

    def state(self):
        path = self.volume / 'updates' / 'app-current.json'
        return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}

    def job(self):
        path = self.volume / 'updates' / 'job.json'
        return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}

    # -- tests --------------------------------------------------------------
    def test_two_independent_restart_cycles_run_the_installed_update(self):
        overlay = self.stage_overlay()
        for cycle in (1, 2):
            self.clear_markers()
            result = self.start(self.image, 'bata.20260923000000', 'b' * 40)
            self.assertEqual(result.returncode, 0, result.stderr[-2000:])
            launched = self.launches()
            self.assertEqual(len(launched), 1, f'cycle {cycle}: {launched}')
            self.assertEqual(Path(launched[0]['cwd']), overlay)
            self.assertEqual(launched[0]['label'], self.target)
            self.assertEqual(launched[0]['base'], 'bata.20260923000000')
            self.assertEqual(self.state()['current'], self.target)
            self.assertEqual(self.state()['base_image']['label'], 'bata.20260923000000')
        self.assertEqual(self.job().get('status'), 'updated')

    def test_restart_after_a_crashed_download_leaves_updates_usable(self):
        first = self.start(self.image, 'bata.20260923000000', 'b' * 40)
        self.assertEqual(first.returncode, 0, first.stderr[-2000:])
        # The download worker died with the container: no install was recorded.
        (self.volume / 'updates' / 'job.json').write_text(json.dumps({
            'mode': 'app', 'status': 'downloading', 'id': 'crashed', 'target': self.target,
            'image': 'example@sha256:' + 'e' * 64, 'message': '正在下载并校验更新文件',
        }), encoding='utf-8')
        self.clear_markers()
        result = self.start(self.image, 'bata.20260923000000', 'b' * 40)
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        job = self.job()
        self.assertEqual(job['status'], 'interrupted')
        self.assertIn('中断', job['message'])
        self.assertIsNone(self.state()['current'])

    def test_pulled_image_replaces_the_persisted_overlay(self):
        overlay = self.stage_overlay()
        self.start(self.image, 'bata.20260923000000', 'b' * 40)
        self.assertEqual(Path(self.launches()[0]['cwd']), overlay)
        second = self.make_image(self.root / 'image-2', 'bata.20261012000000', 'd' * 40)
        self.clear_markers()
        result = self.start(second, 'bata.20261012000000', 'd' * 40)
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        launched = self.launches()
        self.assertEqual(len(launched), 1, launched)
        self.assertEqual(Path(launched[0]['cwd']), second)
        self.assertEqual(launched[0]['label'], 'bata.20261012000000')
        self.assertIsNone(self.state()['current'])
        self.assertEqual(self.state()['base_image']['label'], 'bata.20261012000000')

    def test_update_that_cannot_start_rolls_back_and_stays_back(self):
        overlay = self.stage_overlay(server_source=BROKEN_STUB)
        for cycle in (1, 2):
            self.clear_markers()
            result = self.start(self.image, 'bata.20260923000000', 'b' * 40)
            self.assertEqual(result.returncode, 0, result.stderr[-2000:])
            launched = self.launches()
            expected = [overlay, self.image] if cycle == 1 else [self.image]
            self.assertEqual([Path(item['cwd']) for item in launched], expected, f'cycle {cycle}')
            self.assertEqual(launched[-1]['label'], 'bata.20260923000000')
        self.assertIsNone(self.state()['current'])
        self.assertEqual(self.job()['status'], 'rolled_back')
        self.assertIn('启动', self.job()['message'])


if __name__ == '__main__':
    unittest.main()
