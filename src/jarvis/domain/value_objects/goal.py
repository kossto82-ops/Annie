"""Goal: what an episode is trying to achieve (Vision §12, §26).

An episode may be pursued *toward* something, not merely in reaction to a
trigger. A Goal names that intent and, optionally, what would count as success.
It is a first-class part of an episode's provenance (Vision §26: Goal → … →
Decision) -- a recorded intent here, not yet a planner or a decomposition.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class Goal:
    """What an episode is trying to achieve."""

    statement: str
    success_criterion: str | None = None

    def __post_init__(self) -> None:
        if not self.statement or not self.statement.strip():
            raise ValueError("A goal requires a non-empty statement")
