"""ScheduledTask: a task stored or retrieved through the task-scheduler capability (Odysseus #7).

A scheduled task is a *material*, low-risk, reversible artifact -- a named action
with a schedule that the user asked Jarvis to manage. It is deliberately plain
content with provenance and a stable identity (``id``), never a conclusion. The
task itself does not execute here; this is bookkeeping for *what* to run and
*when*. Creating/updating/deleting/enabling/disabling are reversible material
actions the surface requests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class ScheduledTask:
    """One scheduled task: identity, name, command, schedule, and state."""

    id: str
    name: str
    command: str
    cron: str = ""
    description: str = ""
    enabled: bool = True
    next_run: datetime | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("a ScheduledTask requires a name")
        if not self.command:
            raise ValueError("a ScheduledTask requires a command")

    @property
    def provenance(self) -> str:
        """A plain description of the task's origin, for the episode trace."""
        return f"scheduled task {self.id} '{self.name}'"
