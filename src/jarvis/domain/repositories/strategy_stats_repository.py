"""Repository contract for durable retrieval-strategy experience (P2-C).

A wired store lets the accumulated routing evidence survive restarts; an
absent store keeps the evidence session-local (still consumed, lost on
restart). Like every store, ``load`` reads as "nothing recorded" when the
surface is missing or unreadable (recovery, never a crash).
"""

from __future__ import annotations

from typing import Protocol

from jarvis.domain.value_objects.retrieval_strategy import RetrievalStrategyStats


class StrategyStatsRepository(Protocol):
    """Persists (or forgets) the bounded retrieval-strategy record."""

    def load(self) -> RetrievalStrategyStats | None:
        """The recorded outcome history, or None when nothing is recorded."""
        ...

    def save(self, stats: RetrievalStrategyStats) -> None:
        """Persist the whole record atomically."""
        ...