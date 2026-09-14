"""UnresolvedItem: first-class open cognitive state.

Some questions cannot be settled when first raised -- evidence is thin,
contradictory, or simply absent. Instead of dropping them (or answering
anyway), Jarvis records them as unresolved items with a real lifecycle:

    noted -> open across restarts -> retrieved as an attention candidate
      -> investigated -> resolved -> history preserved

Resolution grounds the answer as ordinary evidence on a belief (via a real
episode), so a resolved question keeps informing future cognition instead
of rotting in a log.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4


def _new_id() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class UnresolvedStatus(Enum):
    """Whether the question is still open."""

    OPEN = "open"
    RESOLVED = "resolved"


@dataclass(frozen=True, slots=True, kw_only=True)
class UnresolvedItem:
    """An open question Jarvis has not yet settled."""

    question: str
    id: str = field(default_factory=_new_id)
    opened_at: datetime = field(default_factory=_now)
    status: UnresolvedStatus = UnresolvedStatus.OPEN
    resolution: str | None = None
    resolved_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.question or not self.question.strip():
            raise ValueError("An unresolved item requires a non-empty question")

    def resolved(self, resolution: str) -> UnresolvedItem:
        """A copy marked resolved with its answer and timestamp."""
        if not resolution or not resolution.strip():
            raise ValueError("Resolving requires a non-empty resolution")
        return UnresolvedItem(
            question=self.question,
            id=self.id,
            opened_at=self.opened_at,
            status=UnresolvedStatus.RESOLVED,
            resolution=resolution,
            resolved_at=_now(),
        )
