"""SqliteCalendarStore: a CalendarStore on a real database at the edge (Odysseus #6, D10).

The local calendar is a bounded, reversible material capability: a time-bound store of
events the user asked Jarvis to keep or retrieve. This implementation persists those
events as JSON payloads in a SQLite table keyed by event id, so the same protocol the
Local store serves through a ``calendar.json`` file is served through transactional
commits instead. Like every edge store it only keeps and returns event content -- it
never reasons about the events (D6).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from jarvis.domain.value_objects.calendar_event import CalendarEvent

_Record = dict[str, Any]


def _now() -> datetime:
    return datetime.now(UTC)


def _overlaps(event: CalendarEvent, start: datetime, end: datetime) -> bool:
    return event.start <= end and event.end >= start


def _to_record(event: CalendarEvent) -> _Record:
    return {
        "title": event.title,
        "start": event.start.isoformat(),
        "end": event.end.isoformat(),
        "description": event.description,
        "location": event.location,
        "all_day": event.all_day,
        "created_at": event.created_at.isoformat(),
        "updated_at": event.updated_at.isoformat(),
    }


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


class SqliteCalendarStore:
    """A CalendarStore over calendar events keyed by id in a SQLite table."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._conn = connection
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self._events: dict[str, CalendarEvent] = {}
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS calendar_events ("
            "event_id TEXT PRIMARY KEY, "
            "payload TEXT NOT NULL)"
        )
        self._load()

    # -- CalendarStore --------------------------------------------------------

    def list_events(self, *, limit: int = 100) -> tuple[CalendarEvent, ...]:
        events = sorted(self._events.values(), key=lambda e: e.start)
        return tuple(events[:limit])

    def get_event(self, event_id: str) -> CalendarEvent:
        event = self._events.get(event_id)
        if event is None:
            raise KeyError(f"no calendar event with id {event_id!r}")
        return event

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
        self._upsert(event)
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
        current = self.get_event(event_id)
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
        self._upsert(constructed)
        return constructed

    def delete_event(self, event_id: str) -> None:
        if event_id not in self._events:
            raise KeyError(f"no calendar event with id {event_id!r}")
        self._events.pop(event_id)
        self._conn.execute(
            "DELETE FROM calendar_events WHERE event_id = ?", (event_id,)
        )
        self._conn.commit()

    def events_in_range(
        self, start: datetime, end: datetime, *, limit: int = 100
    ) -> tuple[CalendarEvent, ...]:
        events = tuple(
            e for e in self._events.values() if _overlaps(e, start, end)
        )
        return events[:limit]

    # -- storage helpers ------------------------------------------------------

    def _upsert(self, event: CalendarEvent) -> None:
        self._events[event.id] = event
        payload = json.dumps(_to_record(event), separators=(",", ":"))
        self._conn.execute(
            "INSERT INTO calendar_events (event_id, payload) VALUES (?, ?) "
            "ON CONFLICT(event_id) DO UPDATE SET payload = excluded.payload",
            (event.id, payload),
        )
        self._conn.commit()

    def _load(self) -> None:
        rows = self._conn.execute(
            "SELECT event_id, payload FROM calendar_events"
        ).fetchall()
        for event_id, payload in rows:
            self._events[event_id] = _from_record(event_id, json.loads(payload))