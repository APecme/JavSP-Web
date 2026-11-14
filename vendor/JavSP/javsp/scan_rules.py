"""Directory filtering shared by Web scans and the core scanner."""
import os
from pathlib import Path
import re

def scan_candidates(root, scanner, progress=lambda: None):
    root = Path(root)
    patterns = [re.compile(p) for p in scanner.ignored_folder_name_pattern if p]
    if any(p.match(part) for part in root.parts for p in patterns):
        return
    def fail(error):
        raise error
    for folder, dirs, files in os.walk(root, onerror=fail, followlinks=False):
        progress()
        if scanner.skip_nfo_dir and any(name.lower().endswith('.nfo') for name in files):
            dirs[:] = []
            continue
        dirs[:] = [name for name in dirs if not any(p.match(name) for p in patterns)]
        for name in files:
            yield Path(folder) / name
