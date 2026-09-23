"""Export a consistent read-only SQLite snapshot for rollback to JSON releases."""
import argparse
import json
from pathlib import Path
import sqlite3


def export(database: Path, destination: Path):
    db = sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        rows = db.execute('SELECT t.payload,l.lines FROM tasks t LEFT JOIN task_logs l ON l.id=t.id ORDER BY t.created_at,t.id').fetchall()
        records = [json.loads(payload) | {'log_tail': json.loads(lines or '[]')} for payload, lines in rows]
        # Never overwrite an existing backup or production history.
        with destination.open('x', encoding='utf-8') as output:
            json.dump(records, output, ensure_ascii=False, indent=2)
        return len(records)
    finally:
        db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print(f'Exported {export(args.database, args.destination)} tasks to {args.destination}')
