"""In-memory implementation of SemanticMemoryRepository for testing."""

from __future__ import annotations

from jarvis.domain.entities.semantic_memory import SemanticMemory


class InMemorySemanticMemoryStore:
    """A trivial in-memory store for semantic memories (tests and defaults)."""

    def __init__(self) -> None:
        self._by_pattern: dict[str, SemanticMemory] = {}
        self._by_id: dict[str, SemanticMemory] = {}

    def get_by_pattern(self, pattern: str) -> SemanticMemory | None:
        return self._by_pattern.get(pattern)

    def get_by_id(self, memory_id: str) -> SemanticMemory | None:
        return self._by_id.get(memory_id)

    def save(self, memory: SemanticMemory) -> None:
        self._by_pattern[memory.pattern] = memory
        self._by_id[memory.id] = memory

    def all_memories(self) -> tuple[SemanticMemory, ...]:
        return tuple(self._by_id.values())

    def search(self, query: str, limit: int = 5) -> tuple[SemanticMemory, ...]:
        """Simple substring search over patterns."""
        query_lower = query.lower()
        matches = [
            mem for mem in self._by_id.values()
            if query_lower in mem.pattern.lower()
        ]
        matches.sort(key=lambda m: m.confidence.value, reverse=True)
        return tuple(matches[:limit])
