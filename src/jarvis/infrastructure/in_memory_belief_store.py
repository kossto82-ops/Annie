"""In-memory implementation of :class:`BeliefRepository`.

The simplest storage that gives Jarvis continuity within a running process:
beliefs are kept by statement. Retrieval returns the *same* belief object, so a
later episode evolves the belief it already holds rather than a copy. A durable
(database-backed) store can replace this behind the same interface later.

It stores beliefs together with their evidence and never records a truth value;
confidence is always derived on read (Vision §22).
"""

from __future__ import annotations

from datetime import datetime

from jarvis.domain.entities.belief import Belief
from jarvis.domain.repositories.belief_repository import belief_registry


class InMemoryBeliefStore:
    """A process-lifetime belief store keyed by statement."""

    def __init__(self) -> None:
        self._by_statement: dict[str, Belief] = {}

    def get_by_topic(self, topic: str) -> Belief | None:
        return belief_registry(self._by_statement.values()).get(topic)

    def get_by_statement(self, statement: str) -> Belief | None:
        return self._by_statement.get(statement)

    def save(self, belief: Belief) -> None:
        self._retire_superseded_row(belief)
        self._by_statement[belief.statement] = belief

    def _retire_superseded_row(self, belief: Belief) -> None:
        """When a revision changes a belief's statement, retire the row that
        still holds the old stance (same belief ``id``, older statement).

        Keeping both would let the superseded text surface as a parallel
        "current" stance -- temporal resolution must hold within the process too.
        """
        for statement, candidate in list(self._by_statement.items()):
            if candidate.id == belief.id and statement != belief.statement:
                del self._by_statement[statement]
                return

    def all_beliefs(self) -> tuple[Belief, ...]:
        return tuple(self._by_statement.values())

    def beliefs_formed_between(
        self, start: datetime, end: datetime
    ) -> tuple[Belief, ...]:
        return tuple(
            b for b in self._by_statement.values()
            if start <= b.formed_at <= end
        )

    def beliefs_about(self, subject_pattern: str) -> tuple[Belief, ...]:
        pattern_lower = subject_pattern.lower()
        return tuple(
            b for b in self._by_statement.values()
            if pattern_lower in b.statement.lower()
        )

    def forget(self, statement: str) -> bool:
        if statement in self._by_statement:
            del self._by_statement[statement]
            return True
        return False
