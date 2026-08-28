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
from pathlib import Path


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write ``content`` to ``path`` atomically, creating parent dirs as needed.

    The write goes to ``<path>.tmp`` first and is then renamed over ``path`` in a
    single atomic step, so an interrupted write can never corrupt the existing file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding=encoding)
    os.replace(tmp, path)
