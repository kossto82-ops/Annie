"""Protocol for semantic memory persistence."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from jarvis.domain.entities.semantic_memory import SemanticMemory


@runtime_checkable
class SemanticMemoryRepository(Protocol):
    """Structural contract for stores that persist semantic memories."""

    def get_by_pattern(self, pattern: str) -> SemanticMemory | None: ...

    def get_by_id(self, memory_id: str) -> SemanticMemory | None: ...

    def save(self, memory: SemanticMemory) -> None: ...

    def all_memories(self) -> tuple[SemanticMemory, ...]: ...

    def search(self, query: str, limit: int = 5) -> tuple[SemanticMemory, ...]: ...
