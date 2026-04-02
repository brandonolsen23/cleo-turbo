"""
Shared I/O utilities for pipeline stages.

Provides atomic file writes and safe JSON reads to prevent
data corruption from killed processes.
"""

import json
import os


def safe_write_json(path, data, indent=2, compact=False):
    """Write JSON atomically — temp file + rename.

    If the process is killed mid-write, the original file stays intact.
    The temp file gets cleaned up on next write.
    """
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        if compact:
            json.dump(data, f, separators=(',', ':'))
        else:
            json.dump(data, f, indent=indent, ensure_ascii=False)
    os.replace(tmp, path)  # atomic on same filesystem


def safe_read_json(path):
    """Read JSON with error handling for corrupted files.

    Returns None if file doesn't exist or is corrupted.
    """
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
