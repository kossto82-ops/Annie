"""SQLite EpisodeTrace: decision provenance that survives a restart (Vision §26).

The in-memory :class:`~jarvis.observability.episode_trace.EpisodeTrace` loses every
trace on process exit, so Jarvis could not account for *how* a past decision was reached
across restarts. The file twin (:class:`JsonEpisodeTrace`) appends JSON lines; this
SQLite variant appends each event to a ``trace_events`` table in the same ``jarvis.db``
as the rest of the memory, so ``Jarvis.database()`` keeps both the memory *and* its
provenance in one database. It keeps the same read API and tolerance as the file twin:
a row a newer Jarvis wrote (unknown event type) is skipped, so an old log never blocks
startup, and a corrupt payload is skipped too.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from jarvis.domain.events.domain_event import CognitiveEvent, DomainEvent
from jarvis.infrastructure.json_event_serialization import (
    deserialise_event,
    serialise_event,
)


class SqliteEpisodeTrace:
    """An EpisodeTrace whose events are appended to, and replayed from, a SQLite table."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._events: list[CognitiveEvent] = []
        self._ensure_schema()
        self._load()

    @property
    def connection(self) -> sqlite3.Connection:
        """The shared database the trace lives in (an infrastructure peer, for tests)."""
        return self._connection

    def handle(self, event: DomainEvent) -> None:
        """Record a cognitive event in memory and append it to the table."""
        if not isinstance(event, CognitiveEvent):
            return
        self._events.append(event)
        self._connection.execute(
            "INSERT INTO trace_events (correlation_id, payload) VALUES (?, ?)",
            (
                event.correlation_id,
                json.dumps(serialise_event(event), separators=(",", ":")),
            ),
        )
        self._connection.commit()

    def for_correlation(self, correlation_id: str) -> tuple[CognitiveEvent, ...]:
        """Every recorded event belonging to one process, in occurrence order."""
        return tuple(e for e in self._events if e.correlation_id == correlation_id)

    def all_events(self) -> tuple[CognitiveEvent, ...]:
        return tuple(self._events)

    def _ensure_schema(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS trace_events (
                seq            INTEGER PRIMARY KEY AUTOINCREMENT,
                correlation_id TEXT,
                payload        TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    def _load(self) -> None:
        rows: list[tuple[Any, str]] = self._connection.execute(
            "SELECT correlation_id, payload FROM trace_events ORDER BY seq"
        ).fetchall()
        for _, payload in rows:
            try:
                event = deserialise_event(json.loads(payload))
            except (json.JSONDecodeError, KeyError):
                continue  # a corrupt payload -- skip it
            if event is not None:  # None == an event type this version does not know
                self._events.append(event)