"""CapabilityNeed: a recognised gap in what Jarvis can do (Odysseus).

The first step of capability acquisition is noticing that Jarvis lacks some
ability. A need is a *request for capability*, named in terms the scout can
match: what Jarvis wants to do, why it matters (the gap it would close), and
what would count as having it. Like all of Jarvis's state it is provisional and
revisable -- a need is not an acquisition order, it is an opening for the scout.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class CapabilityNeed:
    """A recognised want for a capability Jarvis does not (yet) have."""

    statement: str  # what Jarvis wants to be able to do
    rationale: str  # why it matters -- the gap or goal it would close
    success_criterion: str | None = None  # what would count as having it

    def __post_init__(self) -> None:
        if not self.statement or not self.statement.strip():
            raise ValueError("A capability need requires a non-empty statement")
        if not self.rationale or not self.rationale.strip():
            raise ValueError("A capability need requires a rationale")
