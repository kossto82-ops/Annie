"""SQLite implementation of :class:`UnresolvedRepository` (D10).

Keeps open questions (and their resolutions) in an ``unresolved_items``
table inside the shared ``jarvis.db``, transactionally. Malformed rows are
skipped on load, like the JSON twin.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, cast

from jarvis.domain.value_objects.unresolved_item import UnresolvedItem, UnresolvedStatus
from jarvis.infrastructure.json_unresolved_store import (
    deserialise_item,
    serialise_item,
)


class SqliteUnresolvedStore:
    """Open questions in the shared database."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS unresolved_items ("
            "id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
        )

    def save(self, item: UnresolvedItem) -> None:
        self._conn.execute(
            "INSERT INTO unresolved_items (id, payload) VALUES (?, ?) "
            "ON CONFLICT(id) DO UPDATE SET payload = excluded.payload",
            (item.id, json.dumps(serialise_item(item))),
        )
        self._conn.commit()

    def get(self, item_id: str) -> UnresolvedItem | None:
        row = self._conn.execute(
            "SELECT payload FROM unresolved_items WHERE id = ?", (item_id,)
        ).fetchone()
        if row is None:
            return None
        try:
            data = json.loads(row[0])
        except ValueError:
            return None
        if not isinstance(data, dict):
            return None
        return deserialise_item(cast(dict[str, Any], data))

    def open_items(self) -> tuple[UnresolvedItem, ...]:
        return tuple(
            item for item in self.all_items() if item.status is UnresolvedStatus.OPEN
        )

    def all_items(self) -> tuple[UnresolvedItem, ...]:
        rows = self._conn.execute("SELECT payload FROM unresolved_items").fetchall()
        items: list[UnresolvedItem] = []
        for (payload,) in rows:
            try:
                data = json.loads(payload)
            except ValueError:
                continue
            if not isinstance(data, dict):
                continue
            item = deserialise_item(cast(dict[str, Any], data))
            if item is not None:
                items.append(item)
        items.sort(key=lambda i: i.opened_at)
        return tuple(items)
