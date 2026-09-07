"""SqliteNotesStore: a NotesStore on a real database at the edge (Odysseus #8, D10).

Notes are the most purely-local, reversible material capability Jarvis can gain:
plain text the user asked Jarvis to keep. This implementation persists those notes
as JSON payloads in a SQLite table keyed by note id, so the seam that the Local
store serves through a ``notes.json`` file is served through transactional commits
instead. It only keeps and returns note content -- it never reasons about the notes
(D6).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from jarvis.domain.value_objects.note import Note

_Record = dict[str, Any]


def _now() -> datetime:
    return datetime.now(UTC)


def _matches(note: Note, query: str) -> bool:
    lowered = query.lower()
    haystack = " ".join((note.title, note.body, *note.tags)).lower()
    return all(part in haystack for part in lowered.split())


def _to_record(note: Note) -> _Record:
    return {
        "title": note.title,
        "body": note.body,
        "tags": list(note.tags),
        "created_at": note.created_at.isoformat(),
        "updated_at": note.updated_at.isoformat(),
    }


def _from_record(note_id: str, rec: _Record) -> Note:
    return Note(
        id=note_id,
        title=rec.get("title", ""),
        body=rec.get("body", ""),
        tags=tuple(rec.get("tags", ())),
        created_at=datetime.fromisoformat(rec["created_at"]),
        updated_at=datetime.fromisoformat(rec["updated_at"]),
    )


class SqliteNotesStore:
    """A NotesStore over notes keyed by id in a SQLite table."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._conn = connection
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self._notes: dict[str, Note] = {}
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS notes ("
            "note_id TEXT PRIMARY KEY, "
            "payload TEXT NOT NULL)"
        )
        self._load()

    # -- NotesStore -----------------------------------------------------------

    def list_notes(self, *, limit: int = 100) -> tuple[Note, ...]:
        notes = sorted(
            self._notes.values(), key=lambda n: n.updated_at, reverse=True
        )
        return tuple(notes[:limit])

    def get_note(self, note_id: str) -> Note:
        note = self._notes.get(note_id)
        if note is None:
            raise KeyError(f"no note with id {note_id!r}")
        return note

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
        self._upsert(note)
        return note

    def update_note(
        self,
        note_id: str,
        *,
        title: str,
        body: str,
        tags: tuple[str, ...],
    ) -> Note:
        current = self.get_note(note_id)
        constructed = Note(
            id=note_id,
            title=title if title else current.title,
            body=body if body else current.body,
            tags=tuple(tags) if tags else current.tags,
            created_at=current.created_at,
            updated_at=_now(),
        )
        self._upsert(constructed)
        return constructed

    def delete_note(self, note_id: str) -> None:
        if note_id not in self._notes:
            raise KeyError(f"no note with id {note_id!r}")
        self._notes.pop(note_id)
        self._conn.execute("DELETE FROM notes WHERE note_id = ?", (note_id,))
        self._conn.commit()

    def search_notes(self, query: str, *, limit: int = 10) -> tuple[Note, ...]:
        notes = self.list_notes()
        return tuple(n for n in notes if _matches(n, query))[:limit]

    # -- storage helpers ------------------------------------------------------

    def _upsert(self, note: Note) -> None:
        self._notes[note.id] = note
        payload = json.dumps(_to_record(note), separators=(",", ":"))
        self._conn.execute(
            "INSERT INTO notes (note_id, payload) VALUES (?, ?) "
            "ON CONFLICT(note_id) DO UPDATE SET payload = excluded.payload",
            (note.id, payload),
        )
        self._conn.commit()

    def _load(self) -> None:
        rows = self._conn.execute(
            "SELECT note_id, payload FROM notes"
        ).fetchall()
        for note_id, payload in rows:
            self._notes[note_id] = _from_record(note_id, json.loads(payload))