"""SqliteEpisodeStore: an EpisodeRepository on a real database (Vision §3, D10).

Persists completed episodes as JSON payloads in a SQLite table so the record of
Jarvis's past cognition survives a restart -- with SQLite's transactional
durability instead of a whole-file rewrite. A monotonically increasing ``seq``
column keeps records in the order they occurred; ``record_id`` makes a replay of
an existing record idempotent within the table.

The live records are cached in memory in order, matching the session semantics
of the in-memory and JSON stores. Each ``record`` lands as one committed
transaction.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.infrastructure.json_episode_store import (
    deserialise_record,
    serialise_record,
)


class SqliteEpisodeStore:
    """An ordered episode store in a SQLite table, persisted transactionally."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        self._records: list[EpisodeRecord] = []
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS episodes ("
            "seq INTEGER PRIMARY KEY AUTOINCREMENT, "
            "record_id TEXT NOT NULL UNIQUE, "
            "payload TEXT NOT NULL)"
        )
        self._load()

    def record(self, record: EpisodeRecord) -> None:
        self._records.append(record)
        payload = json.dumps(serialise_record(record), separators=(",", ":"))
        self._conn.execute(
            "INSERT INTO episodes (record_id, payload) VALUES (?, ?) "
            "ON CONFLICT(record_id) DO UPDATE SET payload = excluded.payload",
            (record.record_id, payload),
        )
        self._conn.commit()

    def history(self) -> tuple[EpisodeRecord, ...]:
        return tuple(self._records)

    def history_in_range(
        self, start: datetime, end: datetime
    ) -> tuple[EpisodeRecord, ...]:
        return tuple(
            r for r in self._records
            if start <= r.recorded_at <= end
        )

    def history_about(
        self, subject: str, start: datetime | None = None, end: datetime | None = None
    ) -> tuple[EpisodeRecord, ...]:
        subject_lower = subject.lower()
        results = []
        for r in self._records:
            if subject_lower not in r.trigger.lower():
                continue
            if start is not None and r.recorded_at < start:
                continue
            if end is not None and r.recorded_at > end:
                continue
            results.append(r)
        return tuple(results)

    def _load(self) -> None:
        rows: list[tuple[Any, ...]] = self._conn.execute(
            "SELECT payload FROM episodes ORDER BY seq"
        ).fetchall()
        self._records = [deserialise_record(json.loads(payload)) for (payload,) in rows]