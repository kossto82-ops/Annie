"""TaskResult: the outcome of a task Jarvis delegated to an edge agent.

Delegation (D1-revised) sends a *material* task to an agent at the edge -- never
cognition. The agent acts (files, email, web, tools) and returns a ``TaskResult``:
what it was asked, whether it succeeded, and its plain-language account. That
account is candidate evidence for the core (D6): Jarvis may weigh it, not adopt
it as fact, and the decision to delegate was already gated by the
controlled-autonomy policy before the agent ever ran.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskResult:
    """One delegated task's material outcome, described, not concluded upon."""

    task: str
    summary: str
    success: bool
    completed_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not self.task and not self.summary:
            raise ValueError("a TaskResult requires a task and/or a summary")

    @property
    def provenance(self) -> str:
        """A plain description of the outcome, for the episode trace."""
        state = "completed" if self.success else "failed"
        return f"delegated task {state}: {self.task}"
