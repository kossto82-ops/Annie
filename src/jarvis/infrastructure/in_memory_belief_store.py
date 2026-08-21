"""In-memory implementation of :class:`BeliefRepository`.

The simplest storage that gives Jarvis continuity within a running process:
beliefs are kept by statement. Retrieval returns the *same* belief object, so a
later episode evolves the belief it already holds rather than a copy. A durable
(database-backed) store can replace this behind the same interface later.

It stores beliefs together with their evidence and never records a truth value;
confidence is always derived on read (Vision §22).
"""

from __future__ import annotations

from jarvis.domain.entities.belief import Belief


class InMemoryBeliefStore:
    """A process-lifetime belief store keyed by statement."""

    def __init__(self) -> None:
        self._by_statement: dict[str, Belief] = {}

    def get_by_statement(self, statement: str) -> Belief | None:
        return self._by_statement.get(statement)

    def save(self, belief: Belief) -> None:
        self._by_statement[belief.statement] = belief
