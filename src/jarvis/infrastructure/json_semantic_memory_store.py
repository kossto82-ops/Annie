"""File-backed implementation of :class:`SemanticMemoryRepository` (Vision §3).

Persists semantic abstractions to a JSON file with crash-safe atomic writes,
reusing the canonical serialisers shared with the SQLite twin -- confidence
and stability are re-derived from the recorded evidence on load, never
persisted as assertions. A missing file reads as empty; malformed entries
are skipped (recovery, not a crash).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from jarvis.domain.entities.semantic_memory import SemanticMemory
from jarvis.domain.services.evidence_weighting import (
    DEFAULT_WEIGHTING,
    EvidenceWeightingPolicy,
)
from jarvis.infrastructure.atomic_write import atomic_write_text
from jarvis.infrastructure.sqlite_semantic_memory_store import (
    deserialise_memory,
    serialise_memory,
)


class JsonSemanticMemoryStore:
    """Semantic abstractions persisted to a JSON file, keyed by pattern."""

    def __init__(
        self,
        path: str | Path,
        weighting_policy: EvidenceWeightingPolicy | None = None,
    ) -> None:
        self._path = Path(path)
        self._weighting_policy = weighting_policy or DEFAULT_WEIGHTING
        self._by_pattern: dict[str, SemanticMemory] = {}
        self._by_id: dict[str, SemanticMemory] = {}
        self._load()

    def get_by_pattern(self, pattern: str) -> SemanticMemory | None:
        return self._by_pattern.get(pattern)

    def get_by_id(self, memory_id: str) -> SemanticMemory | None:
        return self._by_id.get(memory_id)

    def save(self, memory: SemanticMemory) -> None:
        self._by_pattern[memory.pattern] = memory
        self._by_id[memory.id] = memory
        self._flush()

    def all_memories(self) -> tuple[SemanticMemory, ...]:
        return tuple(self._by_id.values())

    def search(self, query: str, limit: int = 5) -> tuple[SemanticMemory, ...]:
        """Substring search over patterns, ordered by confidence descending."""
        query_lower = query.lower()
        matches = [
            mem
            for mem in self._by_id.values()
            if query_lower in mem.pattern.lower()
        ]
        matches.sort(key=lambda m: m.confidence.value, reverse=True)
        return tuple(matches[:limit])

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
            try:
                memory = deserialise_memory(
                    cast(dict[str, Any], entry), self._weighting_policy
                )
            except (KeyError, TypeError, ValueError):
                continue
            self._by_pattern[memory.pattern] = memory
            self._by_id[memory.id] = memory

    def _flush(self) -> None:
        atomic_write_text(
            self._path,
            json.dumps([serialise_memory(m) for m in self._by_id.values()]),
        )
