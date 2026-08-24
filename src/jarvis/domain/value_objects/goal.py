"""Goal: what an episode is trying to achieve (Vision §12, §26).

An episode may be pursued *toward* something, not merely in reaction to a
trigger. A Goal names that intent and, optionally, what would count as success.
It is a first-class part of an episode's provenance (Vision §26: Goal → … →
Decision) -- a recorded intent, not a planner or an executor.

A goal may name a larger goal it is *part of* (``part_of``): recorded structure,
not a plan. Progress on a part is honest evidence about the whole, but a parent
is never "done" because a child is -- its reachability stays derived from all its
own evidence (Vision §26). Ordering and execution are deliberately out of scope.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class Goal:
    """What an episode is trying to achieve."""

    statement: str
    success_criterion: str | None = None
    part_of: str | None = None  # the statement of a larger goal this is a part of

    def __post_init__(self) -> None:
        if not self.statement or not self.statement.strip():
            raise ValueError("A goal requires a non-empty statement")
        if self.part_of is not None and not self.part_of.strip():
            raise ValueError("A goal's parent, if given, must be a non-empty statement")
        if self.part_of is not None and self.part_of == self.statement:
            raise ValueError("A goal cannot be part of itself")
