"""The contract for persisting and retrieving beliefs across episodes.

Continuity is the point of Jarvis (Vision §3): a belief must be able to outlive
the episode that formed it, so a later episode can retrieve it and add new
evidence rather than starting from zero.

This is a domain-level *interface* (a Protocol). Concrete storage lives in
``jarvis.infrastructure``. Crucially, a repository stores beliefs *with their
evidence* -- it never stores a truth flag. Confidence is always re-derived from
that evidence, so "memory" never becomes "truth" (Vision §22).
"""

from __future__ import annotations

from typing import Protocol

from jarvis.domain.entities.belief import Belief


class BeliefRepository(Protocol):
    """Persists beliefs and retrieves them by their statement."""

    def get_by_statement(self, statement: str) -> Belief | None:
        """Return the stored belief with this statement, or None if unknown."""
        ...

    def save(self, belief: Belief) -> None:
        """Persist (insert or update) a belief."""
        ...

    def all_beliefs(self) -> tuple[Belief, ...]:
        """Every belief currently stored."""
        ...
