"""LocalNotesStore: a file-backed NotesStore at the edge (Odysseus #8).

Notes are the most purely-local, reversible material capability Jarvis can gain:
plain text files under a bounded ``root`` directory. Like ``FileSystemTool``, the
actual disk access is an injectable ``io`` callable so offline tests run
deterministically without touching the filesystem (D8). The store only keeps and
returns note content -- it never reasons about the notes (D6), and creating,
updating or deleting are reversible material actions the surface requests.

The store serializes its notes to a single ``notes.json`` document inside
``root``, keyed by note id. ``build_notes_store()`` returns ``None`` without the
``JARVIS_NOTES_ROOT`` directory, so a Jarvis built from it stays offline by
default (D7/D8).
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from jarvis.domain.value_objects.note import Note

_IO = Callable[[str, str, str], str]
_Record = dict[str, Any]


def _now() -> datetime:
    return datetime.now(UTC)


def _matches(note: Note, query: str) -> bool:
    lowered = query.lower()
    haystack = " ".join((note.title, note.body, *note.tags)).lower()
    return all(part in haystack for part in lowered.split())


class LocalNotesStore:
    """A bounded, file-backed store of notes with an injectable ``io`` driver."""

    _FILENAME = "notes.json"

    def __init__(
        self,
        root: str | Path,
        io: _IO | None = None,
        *,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        """Bind the store to a sandbox ``root`` with an injectable ``io`` driver.

        ``io(operation, path, content)`` mirrors the filesystem protocol: ``read``
        returns file text, ``write`` writes ``content`` and returns ``""``,
        ``delete`` removes the file and returns ``""``. Defaults to real disk
        access through :func:`pathlib`; injecting a fake keeps tests offline (D8).
        """
        self._root = Path(root).resolve()
        self._io = io or self._default_io
        self._id_factory = id_factory or (lambda: str(uuid4()))

    # -- filesystem driver ----------------------------------------------------

    def _default_io(self, operation: str, path: str, content: str) -> str:
        resolved = (self._root / path).resolve()
        if not resolved.is_relative_to(self._root):
            raise ValueError("path escapes the notes sandbox")
        if operation == "read":
            return resolved.read_text(encoding="utf-8") if resolved.exists() else ""
        if operation == "delete":
            if resolved.exists():
                resolved.unlink()
            return ""
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return ""

    # -- storage helpers ------------------------------------------------------

    def _file(self) -> str:
        return self._FILENAME

    def _load(self) -> dict[str, _Record]:
        raw = self._io("read", self._file(), "")
        if not raw:
            return {}
        return json.loads(raw)

    def _save(self, data: dict[str, _Record]) -> None:
        self._io("write", self._file(), json.dumps(data))

    def _read_note(self, note_id: str) -> Note:
        note = self._load().get(note_id)
        if note is None:
            raise KeyError(f"no note with id {note_id!r}")
        return self._from_record(note_id, note)

    # -- NotesStore -----------------------------------------------------------

    def list_notes(self, *, limit: int = 100) -> tuple[Note, ...]:
        data = self._load()
        notes = sorted(
            (self._from_record(nid, rec) for nid, rec in data.items()),
            key=lambda n: n.updated_at,
            reverse=True,
        )
        return tuple(notes[:limit])

    def get_note(self, note_id: str) -> Note:
        return self._read_note(note_id)

    def create_note(
        self, *, title: str, body: str = "", tags: tuple[str, ...] = ()
    ) -> Note:
        note_id = self._id_factory()
        now = _now()
        note = Note(
            id=note_id,
            title=title,
            body=body,
            tags=tuple(tags),
            created_at=now,
            updated_at=now,
        )
        data = self._load()
        data[note_id] = self._to_record(note)
        self._save(data)
        return note

    def update_note(
        self,
        note_id: str,
        *,
        title: str,
        body: str,
        tags: tuple[str, ...],
    ) -> Note:
        current = self._read_note(note_id)
        constructed = Note(
            id=note_id,
            title=title if title else current.title,
            body=body if body else current.body,
            tags=tuple(tags) if tags else current.tags,
            created_at=current.created_at,
            updated_at=_now(),
        )
        data = self._load()
        data[note_id] = self._to_record(constructed)
        self._save(data)
        return constructed

    def delete_note(self, note_id: str) -> None:
        data = self._load()
        if note_id not in data:
            raise KeyError(f"no note with id {note_id!r}")
        del data[note_id]
        self._save(data)

    def search_notes(self, query: str, *, limit: int = 10) -> tuple[Note, ...]:
        notes = self.list_notes()
        return tuple(n for n in notes if _matches(n, query))[:limit]

    # -- record mapping -------------------------------------------------------

    @staticmethod
    def _to_record(note: Note) -> _Record:
        rec: _Record = {
            "title": note.title,
            "body": note.body,
            "tags": list(note.tags),
            "created_at": note.created_at.isoformat(),
            "updated_at": note.updated_at.isoformat(),
        }
        return rec

    @staticmethod
    def _from_record(note_id: str, rec: _Record) -> Note:
        return Note(
            id=note_id,
            title=rec.get("title", ""),
            body=rec.get("body", ""),
            tags=tuple(rec.get("tags", ())),
            created_at=datetime.fromisoformat(rec["created_at"]),
            updated_at=datetime.fromisoformat(rec["updated_at"]),
        )


def build_notes_store() -> LocalNotesStore | None:
    """Build the default file-backed notes store, or ``None`` when not configured.

    Wireless when the ``JARVIS_NOTES_ROOT`` directory is unset, so a Jarvis built
    from this factory stays offline by default (D7/D8).
    """
    root = os.environ.get("JARVIS_NOTES_ROOT")
    if not root:
        return None
    return LocalNotesStore(root)
