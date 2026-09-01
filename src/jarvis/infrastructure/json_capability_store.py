"""File-backed implementation of :class:`CapabilityRepository` (Odysseus).

Gives capability acquisition continuity across restarts: candidate and acquired
capabilities are serialised to a JSON file under their name and rehydrated on
load, so a need Jarvis already proposed a capability for is remembered rather
than re-proposed from scratch. Uses atomic writes to avoid corrupting the store
on a crash mid-write.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from jarvis.domain.enums.capability_status import CapabilityStatus
from jarvis.domain.value_objects.capability import Capability
from jarvis.infrastructure.atomic_write import atomic_write_text


def _serialise_capability(capability: Capability) -> dict[str, Any]:
    return {
        "name": capability.name,
        "description": capability.description,
        "requirement": capability.requirement,
        "provenance": capability.provenance,
        "status": capability.status.value,
        "id": capability.id,
        "proposed_at": capability.proposed_at.isoformat(),
    }


def _deserialise_capability(data: dict[str, Any]) -> Capability:
    return Capability(
        name=data["name"],
        description=data["description"],
        requirement=data["requirement"],
        provenance=data["provenance"],
        status=CapabilityStatus(data["status"]),
        id=data["id"],
        proposed_at=datetime.fromisoformat(data["proposed_at"]),
    )


class JsonCapabilityStore:
    """A capability store persisted to a JSON file, keyed by name."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._by_name: dict[str, Capability] = {}
        self._load()

    def get_by_name(self, name: str) -> Capability | None:
        return self._by_name.get(name)

    def save(self, capability: Capability) -> None:
        self._by_name[capability.name] = capability
        self._flush()

    def all_capabilities(self) -> tuple[Capability, ...]:
        return tuple(self._by_name.values())

    def _load(self) -> None:
        if not self._path.exists():
            return
        raw: Any = json.loads(self._path.read_text(encoding="utf-8"))
        for entry in raw:
            capability = _deserialise_capability(entry)
            self._by_name[capability.name] = capability

    def _flush(self) -> None:
        payload = [_serialise_capability(c) for c in self._by_name.values()]
        atomic_write_text(self._path, json.dumps(payload, indent=2))
