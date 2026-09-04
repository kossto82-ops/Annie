"""CalendarEvent: an event stored or retrieved through the calendar capability (Odysseus #6).

A calendar event is a *material*, low-risk, reversible artifact -- a time-bound
entry the user asked Jarvis to keep or retrieve. It is deliberately plain content
with provenance and a stable identity (``id``), never a conclusion. A retrieved
event becomes candidate evidence the core weighs (D6); creating/updating/deleting
are reversible material actions the surface requests, not decisions Jarvis makes
on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class CalendarEvent:
    """One calendar event: identity, title, time bounds, and optional metadata."""

    id: str
    title: str
    start: datetime
    end: datetime
    description: str = ""
    location: str = ""
    all_day: bool = False
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not self.title:
            raise ValueError("a CalendarEvent requires a title")
        if self.end < self.start:
            raise ValueError("end must not precede start")

    @property
    def provenance(self) -> str:
        """A plain description of the event's origin, for the episode trace."""
        return f"calendar event {self.id} '{self.title}'"
