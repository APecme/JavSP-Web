"""Keep relative organization templates idempotent when re-scraping outputs."""
import os
from pathlib import Path
import re
from string import Formatter


def output_directory(source, formatted, pattern, identifier):
    if os.path.isabs(formatted):
        return formatted
    parent = Path(os.path.abspath(source)).parent
    # Metadata alone is insufficient: incoming files can ship with an NFO.
    # Require the configured directory structure and the exact movie number.
    parts = []
    has_num = False
    for literal, field, spec, conversion in Formatter().parse(os.path.normpath(pattern).strip().replace('\\', '/')):
        if field in ('title', 'rawtitle') and literal.rstrip() != literal:
            # Older path-length truncation can leave just "[NUMBER]".
            suffix = literal[len(literal.rstrip()):]
            parts.append(re.escape(literal.rstrip()) + '(?:' + re.escape(suffix) + '[^/]+)?')
            continue
        parts.append(re.escape(literal))
        if field is not None:
            has_num |= field == 'num'
            parts.append(re.escape(identifier) if field == 'num' else '[^/]+')
    if has_num and re.search(r'(?:^|/)' + ''.join(parts).rstrip('/') + r'$', parent.as_posix(), re.IGNORECASE):
        return str(parent)
    return formatted
