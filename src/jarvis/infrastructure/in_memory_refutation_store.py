"""In-memory RefutationRepository (the ephemeral default)."""

from __future__ import annotations


class InMemoryRefutationStore:
    """Holds refuted (observation, belief) pairs for the life of the process."""

    def __init__(self) -> None:
        self._pairs: set[tuple[str, str]] = set()

    def add(self, observation: str, belief_statement: str) -> None:
        self._pairs.add((observation, belief_statement))

    def all(self) -> frozenset[tuple[str, str]]:
        return frozenset(self._pairs)
