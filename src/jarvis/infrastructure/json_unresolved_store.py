"""File-backed implementation of :class:`UnresolvedRepository`.

Keeps open questions (and their resolutions) in one JSON file with crash-safe
atomic writes. A missing file reads as empty; malformed entries are skipped.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from jarvis.domain.value_objects.unresolved_item import UnresolvedItem, UnresolvedStatus
from jarvis.infrastructure.atomic_write import atomic_write_text


def serialise_item(item: UnresolvedItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "question": item.question,
        "opened_at": item.opened_at.isoformat(),
        "status": item.status.value,
        "resolution": item.resolution,
        "resolved_at": item.resolved_at.isoformat() if item.resolved_at is not None else None,
    }


def deserialise_item(data: dict[str, Any]) -> UnresolvedItem | None:
    """Rebuild an item, or None when the record is malformed (recovery)."""
    try:
        question = data["question"]
        if not isinstance(question, str) or not question.strip():
            return None
        resolved_at = data.get("resolved_at")
        return UnresolvedItem(
            question=question,
            id=str(data["id"]),
            opened_at=datetime.fromisoformat(data["opened_at"]),
            status=UnresolvedStatus(data["status"]),
            resolution=data.get("resolution"),
            resolved_at=datetime.fromisoformat(resolved_at) if resolved_at else None,
        )
    except (KeyError, TypeError, ValueError):
        return None


class JsonUnresolvedStore:
    """Open questions persisted to a JSON file, oldest first."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._items: dict[str, UnresolvedItem] = {}
        self._load()

    def save(self, item: UnresolvedItem) -> None:
        self._items[item.id] = item
        self._flush()

    def get(self, item_id: str) -> UnresolvedItem | None:
        return self._items.get(item_id)

    def open_items(self) -> tuple[UnresolvedItem, ...]:
        return tuple(
            item for item in self._ordered() if item.status is UnresolvedStatus.OPEN
        )

    def all_items(self) -> tuple[UnresolvedItem, ...]:
        return self._ordered()

    def _ordered(self) -> tuple[UnresolvedItem, ...]:
        return tuple(sorted(self._items.values(), key=lambda i: i.opened_at))

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw: Any = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(raw, list):
            return
        for entry in cast(list[Any], raw):
            if not isinstance(entry, dict):
                continue
            item = deserialise_item(cast(dict[str, Any], entry))
            if item is not None:
                self._items[item.id] = item

    def _flush(self) -> None:
        atomic_write_text(
            self._path, json.dumps([serialise_item(i) for i in self._ordered()])
        )
