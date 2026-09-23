"""SQLite task records, separate logs and small indexed list summaries."""
from contextlib import contextmanager
import json
import shutil
import sqlite3
import threading

_init_lock = threading.RLock()
_ready = set()


def _dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def _write(db, item):
    from .tasks import summary_for_storage
    task_id = str(item['id'])
    summary = summary_for_storage(item)
    payload = {key: value for key, value in item.items() if key not in {'log_tail', 'list_summary'}}
    output = str((summary.get('progress') or {}).get('output', {}).get('save_dir') or '')
    group = ('output:' + output.lower()) if output else 'input:' + str(item.get('input_directory') or task_id).lower()
    db.execute('''INSERT INTO tasks(id, created_at, payload, summary, status, group_key)
        VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
        created_at=excluded.created_at, payload=excluded.payload, summary=excluded.summary,
        status=excluded.status, group_key=excluded.group_key''',
        (task_id, str(item.get('created_at') or ''), _dump(payload), _dump(summary), str(item.get('status') or ''), group))
    db.execute('INSERT INTO task_logs(id, lines) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET lines=excluded.lines',
               (task_id, _dump(item.get('log_tail') or [])))


@contextmanager
def connection():
    from .storage import TASKS_DB_FILE, TASKS_FILE
    TASKS_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    key = str(TASKS_DB_FILE.resolve())
    db = sqlite3.connect(TASKS_DB_FILE, timeout=30)
    db.row_factory = sqlite3.Row
    db.create_function('casefold', 1, lambda value: str(value or '').casefold(), deterministic=True)
    try:
        with _init_lock:
            if key not in _ready or not db.execute("SELECT 1 FROM sqlite_master WHERE name='task_store_meta'").fetchone():
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('PRAGMA foreign_keys=ON')
                db.execute('BEGIN IMMEDIATE')
                db.execute('CREATE TABLE IF NOT EXISTS task_store_meta (key TEXT PRIMARY KEY, value TEXT)')
                db.execute('CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL)')
                columns = {row['name'] for row in db.execute('PRAGMA table_info(tasks)')}
                for name in ('summary', 'status', 'group_key'):
                    if name not in columns:
                        db.execute(f"ALTER TABLE tasks ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
                db.execute('CREATE TABLE IF NOT EXISTS task_logs (id TEXT PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE, lines TEXT NOT NULL)')
                db.execute('CREATE INDEX IF NOT EXISTS tasks_created ON tasks(created_at DESC, id)')
                db.execute('CREATE INDEX IF NOT EXISTS tasks_status ON tasks(status, created_at, id)')
                if not db.execute("SELECT 1 FROM task_store_meta WHERE key='json_imported'").fetchone():
                    if not db.execute('SELECT 1 FROM tasks LIMIT 1').fetchone() and TASKS_FILE.exists():
                        # Fail closed: corrupt or duplicate-ID history must not become an empty store.
                        raw = TASKS_FILE.read_text(encoding='utf-8')
                        items = json.loads(raw)
                        if not isinstance(items, list) or any(not isinstance(item, dict) or not item.get('id') for item in items):
                            raise ValueError('tasks.json 格式无效，已停止数据库迁移')
                        if len({item['id'] for item in items}) != len(items):
                            raise ValueError('tasks.json 有重复任务 ID，已停止数据库迁移')
                        if items:
                            backup = TASKS_FILE.with_name('tasks.pre-sqlite.json')
                            if not backup.exists():
                                with backup.open('xb') as target, TASKS_FILE.open('rb') as source:
                                    shutil.copyfileobj(source, target)
                            for item in items:
                                _write(db, item)
                    db.execute("INSERT INTO task_store_meta VALUES('json_imported','1')")
                for row in db.execute("SELECT payload FROM tasks WHERE summary='' ").fetchall():
                    _write(db, json.loads(row['payload']))
                if not db.execute("SELECT 1 FROM task_store_meta WHERE key='sources_migrated'").fetchone():
                    from .storage import list_auto_scrape_schedules, load_auto_scrape_history
                    sources = {str(task_id): 'schedule' for schedule in list_auto_scrape_schedules()
                               for run in schedule.get('runs') or [] for task_id in run.get('task_ids') or []}
                    sources.update({str(task_id): 'download' for entry in load_auto_scrape_history().values()
                                    if isinstance(entry, dict) for task_id in entry.get('task_ids') or []})
                    for row in db.execute("SELECT id,payload,summary FROM tasks WHERE json_extract(summary,'$.source') IS NULL").fetchall():
                        payload, summary = json.loads(row['payload']), json.loads(row['summary'])
                        payload['source'] = summary['source'] = sources.get(row['id'], 'manual')
                        db.execute('UPDATE tasks SET payload=?,summary=? WHERE id=?', (_dump(payload), _dump(summary), row['id']))
                    db.execute("INSERT INTO task_store_meta VALUES('sources_migrated','1')")
                db.commit()
                _ready.add(key)
        db.execute('PRAGMA foreign_keys=ON')
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def load(ids=None):
    with connection() as db:
        if ids is not None and not ids:
            return []
        where = ' WHERE t.id IN (' + ','.join('?' for _ in ids) + ')' if ids is not None else ''
        rows = db.execute('SELECT t.payload,l.lines FROM tasks t LEFT JOIN task_logs l ON l.id=t.id' + where + ' ORDER BY t.created_at,t.id', tuple(ids or [])).fetchall()
        return [json.loads(row['payload']) | {'log_tail': json.loads(row['lines'] or '[]')} for row in rows]


def recoverable():
    with connection() as db:
        rows = db.execute("""SELECT t.payload,l.lines FROM tasks t LEFT JOIN task_logs l ON l.id=t.id
            WHERE t.status IN ('queued','running') OR json_extract(t.payload,'$.image_retry_running')=1
            OR json_extract(t.payload,'$.google_cover_search_running')=1 ORDER BY t.created_at,t.id""").fetchall()
        return [json.loads(row['payload']) | {'log_tail': json.loads(row['lines'] or '[]')} for row in rows]


def upsert(item):
    with connection() as db:
        _write(db, item)


def upsert_many(items):
    with connection() as db:
        for item in items:
            _write(db, item)


def replace(items):
    with connection() as db:
        db.execute('DELETE FROM tasks')
        for item in items:
            _write(db, item)


def delete(task_id):
    with connection() as db:
        return db.execute('DELETE FROM tasks WHERE id=?', (task_id,)).rowcount > 0


def record(task_id, logs=True):
    if logs:
        return next(iter(load([task_id])), None)
    with connection() as db:
        row = db.execute('SELECT payload FROM tasks WHERE id=?', (task_id,)).fetchone()
        return json.loads(row[0]) if row else None


def summaries():
    with connection() as db:
        return [json.loads(row[0]) for row in db.execute('SELECT summary FROM tasks ORDER BY created_at DESC,id')]


def run_counts(runs):
    ids = list({str(task_id) for run in runs for task_id in run.get('task_ids') or []})
    statuses = {}
    with connection() as db:
        for start in range(0, len(ids), 500):
            batch = ids[start:start + 500]
            statuses.update(dict(db.execute('SELECT id,status FROM tasks WHERE id IN (' + ','.join('?' for _ in batch) + ')', batch)))
    result = []
    for run in runs:
        counts = dict(total=len(run.get('task_ids') or []), succeeded=0, failed=0, running=0, queued=0)
        for task_id in run.get('task_ids') or []:
            state = statuses.get(str(task_id))
            state = 'failed' if state == 'cancelled' else state
            if state in counts and state != 'total':
                counts[state] += 1
        result.append(run | {'counts': counts})
    return result


def page(limit=50, offset=0, view='all', query='', field='all', status='', size_min=None,
         size_max=None, date_from='', date_to='', sort='created_at', direction='desc'):
    # All SQL fragments come from this fixed vocabulary; user values are bound.
    conditions, params = [], []
    if view == 'manual':
        conditions.append("(coalesce(json_extract(summary,'$.source'),'manual')='manual' OR json_extract(summary,'$.image_retry_started_at') IS NOT NULL)")
    if status:
        conditions.append('status=?')
        params.append(status)
    fields = {'path': '$.input_directory', 'title': '$.title', 'dvdid': '$.progress.metadata.dvdid', 'actress': '$.progress.metadata.actress'}
    if query:
        paths = [fields[field]] if field in fields else list(fields.values())
        expression = " || ' ' || ".join(f"coalesce(json_extract(summary,'{path}'),'')" for path in paths)
        conditions.append(f'instr(casefold({expression}),?)>0')
        params.append(query.casefold())
    for value, op in ((size_min, '>='), (size_max, '<=')):
        if value is not None:
            conditions.append(f"coalesce(json_extract(summary,'$.size_bytes'),0){op}?")
            params.append(value * 1024 * 1024)
    for value, op in ((date_from, '>='), (date_to, '<=')):
        if value:
            conditions.append(f'julianday(created_at){op}julianday(?)')
            params.append(value)
    where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
    with connection() as db:
        db.execute('BEGIN')
        metrics = dict(db.execute("SELECT count(*) AS total, coalesce(sum(status IN ('queued','running')),0) AS running FROM tasks").fetchone())
        latest = db.execute('SELECT status FROM tasks ORDER BY created_at DESC,id LIMIT 1').fetchone()
        metrics['latest_status'] = latest[0] if latest else ''
        if view == 'overview':
            cte = """WITH eligible AS (SELECT id,created_at,summary,status,group_key, json_group_array(id) OVER (PARTITION BY group_key) AS task_ids, row_number() OVER (
                PARTITION BY group_key ORDER BY (status='succeeded') DESC,created_at DESC,id) AS rank
                FROM tasks WHERE status IN ('succeeded','failed','cancelled') AND
                (json_extract(summary,'$.cover_count')>0 OR json_extract(summary,'$.fanart_count')>0 OR json_extract(summary,'$.has_artwork_sources')=1)) """
            total = db.execute(cte + 'SELECT count(*) FROM eligible WHERE rank=1').fetchone()[0]
            order = "coalesce(json_extract(summary,'$.progress.metadata.publish_date'),'')" if sort == 'publish_date' else 'created_at'
            order += ' ASC' if direction == 'asc' else ' DESC'
            offset = min(offset, max(0, ((total - 1) // limit) * limit))
            rows = db.execute(cte + f'SELECT summary,task_ids FROM eligible WHERE rank=1 ORDER BY {order},id LIMIT ? OFFSET ?', (limit, offset)).fetchall()
            items = []
            for row in rows:
                item = json.loads(row['summary'])
                item['task_ids'] = json.loads(row['task_ids'])
                items.append(item)
        else:
            total = db.execute('SELECT count(*) FROM tasks' + where, params).fetchone()[0]
            offset = min(offset, max(0, ((total - 1) // limit) * limit))
            order = " ORDER BY (status IN ('queued','running')) DESC, CASE WHEN status IN ('queued','running') THEN created_at END ASC, created_at DESC,id"
            items = [json.loads(row[0]) for row in db.execute('SELECT summary FROM tasks' + where + order + ' LIMIT ? OFFSET ?', [*params, limit, offset])]
        return {'items': items, 'total': total, 'limit': limit, 'offset': offset, 'metrics': metrics}
