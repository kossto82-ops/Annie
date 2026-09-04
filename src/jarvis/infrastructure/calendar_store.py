"""LocalCalendarStore: a file-backed CalendarStore at the edge (Odysseus #6).

A calendar is a bounded, file-backed store of events -- the simplest local
representation of time-bound entries the user asked Jarvis to keep or retrieve.
Like ``LocalNotesStore``, the actual disk access is an injectable ``io``
callable so offline tests run deterministically without touching the filesystem
(D8). The store only keeps and returns event content -- it never reasons about
the events (D6), and creating, updating or deleting are reversible material
actions the surface requests.

The store serialises its events to a single ``calendar.json`` document inside
``root``, keyed by event id. ``build_calendar_store()`` returns ``None``
without the ``JARVIS_CALENDAR_ROOT`` directory, so a Jarvis built from it
stays offline by default (D7/D8).
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from jarvis.domain.value_objects.calendar_event import CalendarEvent

_IO = Callable[[str, str, str], str]
_Record = dict[str, Any]


def _now() -> datetime:
    return datetime.now(UTC)


def _overlaps(event: CalendarEvent, start: datetime, end: datetime) -> bool:
    """True when the event's time range overlaps ``[start, end]``."""
    return event.start <= end and event.end >= start


class LocalCalendarStore:
    """A bounded, file-backed store of calendar events with an injectable ``io`` driver."""

    _FILENAME = "calendar.json"

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
            raise ValueError("path escapes the calendar sandbox")
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

    def _read_event(self, event_id: str) -> CalendarEvent:
        event = self._load().get(event_id)
        if event is None:
            raise KeyError(f"no calendar event with id {event_id!r}")
        return self._from_record(event_id, event)

    # -- CalendarStore --------------------------------------------------------

    def list_events(self, *, limit: int = 100) -> tuple[CalendarEvent, ...]:
        data = self._load()
        events = sorted(
            (self._from_record(eid, rec) for eid, rec in data.items()),
            key=lambda e: e.start,
        )
        return tuple(events[:limit])

    def get_event(self, event_id: str) -> CalendarEvent:
        return self._read_event(event_id)

    def create_event(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
        description: str = "",
        location: str = "",
        all_day: bool = False,
    ) -> CalendarEvent:
        event_id = self._id_factory()
        now = _now()
        event = CalendarEvent(
            id=event_id,
            title=title,
            start=start,
            end=end,
            description=description,
            location=location,
            all_day=all_day,
            created_at=now,
            updated_at=now,
        )
        data = self._load()
        data[event_id] = self._to_record(event)
        self._save(data)
        return event

    def update_event(
        self,
        event_id: str,
        *,
        title: str,
        start: datetime,
        end: datetime,
        description: str,
        location: str,
        all_day: bool,
    ) -> CalendarEvent:
        current = self._read_event(event_id)
        constructed = CalendarEvent(
            id=event_id,
            title=title if title else current.title,
            start=start if start else current.start,
            end=end if end else current.end,
            description=description if description else current.description,
            location=location if location else current.location,
            all_day=all_day,
            created_at=current.created_at,
            updated_at=_now(),
        )
        data = self._load()
        data[event_id] = self._to_record(constructed)
        self._save(data)
        return constructed

    def delete_event(self, event_id: str) -> None:
        data = self._load()
        if event_id not in data:
            raise KeyError(f"no calendar event with id {event_id!r}")
        del data[event_id]
        self._save(data)

    def events_in_range(
        self, start: datetime, end: datetime, *, limit: int = 100
    ) -> tuple[CalendarEvent, ...]:
        events = self.list_events()
        return tuple(e for e in events if _overlaps(e, start, end))[:limit]

    # -- record mapping -------------------------------------------------------

    @staticmethod
    def _to_record(event: CalendarEvent) -> _Record:
        rec: _Record = {
            "title": event.title,
            "start": event.start.isoformat(),
            "end": event.end.isoformat(),
            "description": event.description,
            "location": event.location,
            "all_day": event.all_day,
            "created_at": event.created_at.isoformat(),
            "updated_at": event.updated_at.isoformat(),
        }
        return rec

    @staticmethod
    def _from_record(event_id: str, rec: _Record) -> CalendarEvent:
        return CalendarEvent(
            id=event_id,
            title=rec.get("title", ""),
            start=datetime.fromisoformat(rec["start"]),
            end=datetime.fromisoformat(rec["end"]),
            description=rec.get("description", ""),
            location=rec.get("location", ""),
            all_day=rec.get("all_day", False),
            created_at=datetime.fromisoformat(rec["created_at"]),
            updated_at=datetime.fromisoformat(rec["updated_at"]),
        )


def build_calendar_store() -> LocalCalendarStore | None:
    """Build the default file-backed calendar store, or ``None`` when not configured.

    Wireless when the ``JARVIS_CALENDAR_ROOT`` directory is unset, so a Jarvis
    built from this factory stays offline by default (D7/D8).
    """
    root = os.environ.get("JARVIS_CALENDAR_ROOT")
    if not root:
        return None
    return LocalCalendarStore(root)
