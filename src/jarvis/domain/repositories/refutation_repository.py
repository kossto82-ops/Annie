"""RefutationRepository: where the reflective cycle's counterexamples live.

Challenge (Increment 77) records that a belief would hold *without* a load-bearing
observation, so it no longer rests on it. Those ``(observation, belief)`` pairs are
memory like any other (Vision §21): a dethroned hypothesis must stay dethroned
across a restart. This Protocol is that store; implementations live in
infrastructure.
"""

from __future__ import annotations

from typing import Protocol


class RefutationRepository(Protocol):
    """Stores the (observation, belief statement) pairs Challenge has refuted."""

    def add(self, observation: str, belief_statement: str) -> None:
        """Record that ``belief_statement`` would hold without ``observation``."""
        ...

    def all(self) -> frozenset[tuple[str, str]]:
        """Every refuted pair."""
        ...
