"""EmailMessage: a mailbox message retrieved or sent via the mail capability.

This is deliberately a *retrieval/outbox* artifact with provenance -- who sent
it, to whom, when, the subject and body -- not a conclusion. Reading an email is
input for Jarvis's reasoning (D6): it becomes candidate evidence the core weighs,
never a fact Jarvis adopts just because it was in an inbox. Sending is a material
action the user requests; Jarvis only ever performs it behind the controlled
autonomy gate (ask-first for outbound, per `09_CONTROLLED_AUTONOMY`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class EmailMessage:
    """One email: its mailbox identity and content, unvetted."""

    subject: str
    body: str
    sender: str = ""
    recipients: tuple[str, ...] = ()
    message_id: str = ""
    folder: str = "inbox"
    retrieved_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not self.subject and not self.body:
            raise ValueError("an EmailMessage requires a subject and/or a body")

    @property
    def provenance(self) -> str:
        """A plain description of the message's origin, for the episode trace."""
        who = self.sender or "(unknown sender)"
        return f"email in {self.folder} from {who}"
