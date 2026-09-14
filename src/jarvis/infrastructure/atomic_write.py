"""Crash-safe file writes for the JSON stores (Vision §3, §21 — memory must survive).

The JSON stores rewrite their whole file on every mutation. A plain
``Path.write_text`` truncates the target first, so a crash mid-write leaves a
half-written — corrupt — memory file. This helper writes to a sibling temp file
and then :func:`os.replace`\\s it into place: on every mainstream OS that rename
is atomic, so a reader (or the next run) sees either the complete old file or the
complete new one, never a torn one. The same temp+replace pattern already guards
the ``.env`` secrets file in :mod:`jarvis.infrastructure.llm_config_store`.
"""

from __future__ import annotations

import os
import time
from pathlib import Path


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write ``content`` to ``path`` atomically, creating parent dirs as needed.

    The write goes to ``<path>.tmp`` first and is then renamed over ``path`` in a
    single atomic step, so an interrupted write can never corrupt the existing file.
    On Windows the rename can transiently fail while an antivirus scanner holds the
    target open; the replace is retried briefly before giving up.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding=encoding)
    for attempt in range(_MAX_REPLACE_ATTEMPTS):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == _MAX_REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(_REPLACE_RETRY_DELAY_S)


# Windows scanners can briefly lock a file being overwritten; give them a moment.
_MAX_REPLACE_ATTEMPTS = 5
_REPLACE_RETRY_DELAY_S = 0.02
