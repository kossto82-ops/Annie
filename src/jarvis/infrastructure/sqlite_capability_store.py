"""SqliteCapabilityStore: a CapabilityRepository on a real database (Odysseus, D10).

Capability acquisition carries across restarts: candidate and acquired
capabilities are stored as JSON payloads in a SQLite table keyed by name and
rehydrated on load, so a need Jarvis already proposed a capability for is
remembered rather than re-proposed from scratch. Writes are transactional
SQLite commits rather than a whole-file rewrite; ``save`` upserts by name.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from jarvis.domain.value_objects.capability import Capability
from jarvis.infrastructure.json_capability_store import (
    deserialise_capability,
    serialise_capability,
)


class SqliteCapabilityStore:
    """A capability store in a SQLite table, keyed by name."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        self._by_name: dict[str, Capability] = {}
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS capabilities ("
            "name TEXT PRIMARY KEY, "
            "payload TEXT NOT NULL)"
        )
        self._load()

    def get_by_name(self, name: str) -> Capability | None:
        return self._by_name.get(name)

    def save(self, capability: Capability) -> None:
        self._by_name[capability.name] = capability
        payload = json.dumps(serialise_capability(capability), separators=(",", ":"))
        self._conn.execute(
            "INSERT INTO capabilities (name, payload) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET payload = excluded.payload",
            (capability.name, payload),
        )
        self._conn.commit()

    def all_capabilities(self) -> tuple[Capability, ...]:
        return tuple(self._by_name.values())

    def _load(self) -> None:
        rows: list[tuple[Any, ...]] = self._conn.execute(
            "SELECT payload FROM capabilities"
        ).fetchall()
        for (payload,) in rows:
            capability = deserialise_capability(json.loads(payload))
            self._by_name[capability.name] = capability