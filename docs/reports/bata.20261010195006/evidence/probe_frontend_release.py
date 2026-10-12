"""Read-only production-module probes with isolated fake storage/process/network."""
from pathlib import Path
import io
import json
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'source'))
os.environ['JAVSP_WEB_DATA_DIR'] = str(ROOT / 'frontend-probe-data')
from javsp_web import app_supervisor as supervisor, updater, app_update, storage, __version__

def run_probes():
    with tempfile.TemporaryDirectory(dir=ROOT) as directory:
        data = Path(directory)
        base = data / 'base'
        apps = data / 'updates' / 'apps'
        base.mkdir()
        for filename in ('Dockerfile', 'requirements.txt'):
            (base / filename).write_text('same-dependencies\n')
        patches = [patch.object(storage, 'DATA_DIR', data), patch.object(supervisor, 'BASE_ROOT', base),
                   patch.object(supervisor, 'APP_DIR', apps), patch.object(supervisor, 'STATE_FILE', data / 'updates' / 'app-current.json'),
                   patch.object(supervisor, 'JOB_FILE', data / 'updates' / 'job.json'), patch.object(supervisor.signal, 'signal')]
        for p in patches: p.start()
        try:
            child = MagicMock()
            child.wait.return_value = 0
            child.poll.return_value = None
            # Container stopped while the updater's daemon worker was downloading.
            updater.write_state('job', {'id': 'interrupted-download', 'mode': 'app', 'status': 'downloading'})
            with patch.object(supervisor.subprocess, 'Popen', return_value=child), patch.object(supervisor, 'health_ready', return_value=True):
                assert supervisor.run() == 0
            assert updater.busy() is True
            try:
                updater.apply()
            except updater.UpdateError as exc:
                print('CONFIRMED interrupted download survives healthy restart: status=', updater.job()['status'], '; reapply=', str(exc))
            else:
                raise AssertionError('expected stale busy block')

            # Same persisted data volume after pulling a newer image, with unchanged deps.
            old_label = 'bata.20260924044117'
            new_label = 'bata.20261010195006'
            old_root = apps / old_label
            (old_root / 'javsp_web').mkdir(parents=True)
            (old_root / 'javsp_web' / 'server.py').write_text('# old code')
            for filename in ('Dockerfile', 'requirements.txt'):
                (old_root / filename).write_bytes((base / filename).read_bytes())
            supervisor.save_state({'current': old_label, 'commit': 'a' * 40, 'pending': False})
            with patch.dict(os.environ, {'JAVSP_WEB_RELEASE_LABEL': new_label, 'JAVSP_WEB_RELEASE_COMMIT': 'b' * 40}), patch.object(supervisor.subprocess, 'Popen', return_value=child) as popen, patch.object(supervisor, 'health_ready', return_value=True):
                supervisor.run()
            assert popen.call_args.kwargs['cwd'] == old_root
            assert popen.call_args.kwargs['env']['JAVSP_WEB_RELEASE_LABEL'] == old_label
            print('CONFIRMED new base image', new_label, 'launches persisted old app', old_label)

            # Plain docker build without release build args: actual child version falls back to __version__.
            supervisor.save_state({})
            with patch.dict(os.environ, {'JAVSP_WEB_RELEASE_LABEL': ''}), patch.object(supervisor.subprocess, 'Popen', return_value=child), patch.object(supervisor, 'health_ready', return_value=True) as ready:
                supervisor.run()
            expected = ready.call_args.args[1]
            assert expected == ''
            response = MagicMock()
            response.status = 200
            response.read.side_effect = lambda *args: json.dumps({'version': __version__}).encode()
            response.__enter__.return_value = response
            opener = MagicMock()
            opener.open.return_value = response
            with patch.object(supervisor.urllib.request, 'build_opener', return_value=opener), patch.object(supervisor.time, 'sleep'):
                is_ready = supervisor.health_ready(child, expected, '8090')
            assert not is_ready and opener.open.call_count == 45
            print('CONFIRMED unlabeled build: expected=', repr(expected), 'healthy API version=', __version__, '; rejected after', opener.open.call_count, 'polls')

            # apply checked once before asynchronous download; no second task check is in schedule worker.
            updater.write_state('job', {})
            info = {'available': True, 'target': new_label, 'commit': 'b' * 40, 'image': 'test@sha256:' + 'b' * 64, 'channel': 'bata'}
            with patch.object(updater, 'capability', return_value={'supported': True}), patch.object(updater, 'check', return_value=info), patch.object(updater, 'active_tasks', side_effect=[False, True]) as active, patch.object(app_update, 'schedule') as scheduled:
                record = updater.apply()
            assert active.call_count == 1
            writes = []
            class FakeThread:
                def __init__(self, target, **kwargs): self.target = target
                def start(self): self.target()
            with patch.object(app_update, 'install'), patch.object(app_update.threading, 'Thread', FakeThread), patch.object(app_update.time, 'sleep'), patch.object(app_update.os, '_exit') as exit_app, patch.object(updater, 'active_tasks', return_value=True) as active:
                app_update.schedule(info, record, writes.append)
            assert active.call_count == 0 and exit_app.call_args.args[0] == 75
            print('CONFIRMED updater worker exits with code 75 without rechecking newly active tasks; ensure_not_updating has zero repository callers')
        finally:
            for p in reversed(patches): p.stop()

if __name__ == '__main__': run_probes()
