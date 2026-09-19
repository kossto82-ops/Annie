"""SQLite-backed SemanticMemoryRepository (Vision §3, D10).

Semantic memories are stored as JSON payloads keyed by pattern, rehydrated
on load exactly like beliefs — confidence and stability are re-derived from
the recorded evidence, never persisted as an assertion.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any, cast

from jarvis.domain.entities.semantic_memory import SemanticMemory
from jarvis.domain.services.evidence_weighting import (
    DEFAULT_WEIGHTING,
    EvidenceWeightingPolicy,
)
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.evidence_provenance import EvidenceProvenance


def _provenance_dict(
    provenance: EvidenceProvenance | None,
) -> dict[str, object] | None:
    if provenance is None:
        return None
    return {
        "provider": provenance.provider,
        "backend": provenance.backend,
        "channel": provenance.channel,
        "url": provenance.url,
        "retrieved_at": (
            provenance.retrieved_at.isoformat()
            if provenance.retrieved_at is not None
            else None
        ),
        "published_at": (
            provenance.published_at.isoformat()
            if provenance.published_at is not None
            else None
        ),
        "updated_at": (
            provenance.updated_at.isoformat()
            if provenance.updated_at is not None
            else None
        ),
    }


def _provenance_from(data: object) -> EvidenceProvenance | None:
    if not isinstance(data, dict):
        return None
    raw = cast(dict[str, object], data)

    def _s(key: str) -> str | None:
        value = raw.get(key)
        return value if isinstance(value, str) else None

    def _dt(value: object) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    return EvidenceProvenance(
        provider=_s("provider"),
        backend=_s("backend"),
        channel=_s("channel"),
        url=_s("url"),
        retrieved_at=_dt(raw.get("retrieved_at")),
        published_at=_dt(raw.get("published_at")),
        updated_at=_dt(raw.get("updated_at")),
    )


def serialise_memory(memory: SemanticMemory) -> dict[str, Any]:
    return {
        "id": memory.id,
        "pattern": memory.pattern,
        "source_episode_ids": memory.source_episode_ids,
        "source_belief_ids": memory.source_belief_ids,
        "formed_at": memory.formed_at.isoformat(),
        "last_reinforced_at": (
            memory.last_reinforced_at.isoformat()
            if memory.last_reinforced_at is not None
            else None
        ),
        "reinforcement_count": memory.reinforcement_count,
        "evidence": [
            {
                "content": e.content,
                "source": e.source.value,
                "weight": e.weight.value,
                "supports": e.supports,
                "is_neutral": e.is_neutral,
                "context": e.context,
                "provenance": _provenance_dict(e.provenance),
                "observed_at": e.observed_at.isoformat(),
                "id": e.id,
            }
            for e in memory.evidence
        ],
    }


def deserialise_memory(
    data: dict[str, Any],
    weighting_policy: EvidenceWeightingPolicy | None = None,
) -> SemanticMemory:
    policy = weighting_policy or DEFAULT_WEIGHTING
    memory = SemanticMemory(
        pattern=data["pattern"],
        id=data["id"],
        source_episode_ids=data.get("source_episode_ids", []),
        source_belief_ids=data.get("source_belief_ids", []),
        weighting_policy=policy,
        formed_at=datetime.fromisoformat(data["formed_at"]),
        last_reinforced_at=(
            datetime.fromisoformat(data["last_reinforced_at"])
            if data.get("last_reinforced_at") is not None
            else None
        ),
        reinforcement_count=data.get("reinforcement_count", 0),
    )
    for e_data in data.get("evidence", []):
        from jarvis.domain.enums.evidence_source import EvidenceSource

        evidence = Evidence(
            content=e_data["content"],
            source=EvidenceSource(e_data["source"]),
            weight=Confidence(e_data["weight"]),
            supports=e_data["supports"],
            is_neutral=e_data.get("is_neutral", False),
            context=e_data.get("context"),
            provenance=_provenance_from(e_data.get("provenance")),
            observed_at=datetime.fromisoformat(e_data["observed_at"]),
            id=e_data.get("id", ""),
        )
        # Rehydrate without incrementing reinforcement_count on load.
        memory.restore_evidence(evidence)
    return memory


class SqliteSemanticMemoryStore:
    """A semantic memory store backed by SQLite."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        weighting_policy: EvidenceWeightingPolicy | None = None,
    ) -> None:
        self._conn = connection
        self._weighting_policy = weighting_policy or DEFAULT_WEIGHTING
        self._by_pattern: dict[str, SemanticMemory] = {}
        self._by_id: dict[str, SemanticMemory] = {}
        self._ensure_schema()
        self._load()

    def get_by_pattern(self, pattern: str) -> SemanticMemory | None:
        return self._by_pattern.get(pattern)

    def get_by_id(self, memory_id: str) -> SemanticMemory | None:
        return self._by_id.get(memory_id)

    def save(self, memory: SemanticMemory) -> None:
        self._by_pattern[memory.pattern] = memory
        self._by_id[memory.id] = memory
        payload = json.dumps(serialise_memory(memory), separators=(",", ":"))
        self._conn.execute(
            "INSERT INTO semantic_memories (id, pattern, payload) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET payload = excluded.payload",
            (memory.id, memory.pattern, payload),
        )
        self._conn.commit()

    def all_memories(self) -> tuple[SemanticMemory, ...]:
        return tuple(self._by_id.values())

    def search(self, query: str, limit: int = 5) -> tuple[SemanticMemory, ...]:
        """Substring search over patterns, ordered by confidence descending."""
        query_lower = query.lower()
        matches = [
            mem for mem in self._by_id.values()
            if query_lower in mem.pattern.lower()
        ]
        matches.sort(key=lambda m: m.confidence.value, reverse=True)
        return tuple(matches[:limit])

    def _ensure_schema(self) -> None:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS semantic_memories "
            "(id TEXT PRIMARY KEY, pattern TEXT NOT NULL, payload TEXT NOT NULL)"
        )
        self._conn.commit()

    def _load(self) -> None:
        cursor = self._conn.execute("SELECT payload FROM semantic_memories")
        for row in cursor:
            data = json.loads(row[0])
            memory = deserialise_memory(data, self._weighting_policy)
            self._by_pattern[memory.pattern] = memory
            self._by_id[memory.id] = memory
