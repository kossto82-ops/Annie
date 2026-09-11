"""PersistedTurn: a single turn of conversation that survives restarts.

Unlike the in-memory ``Turn`` (which is ephemeral), a ``PersistedTurn`` carries
timestamps and intent, and is stored in a repository so conversation history
can be recalled across sessions.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from jarvis.domain.conversation.intent import ConversationIntent


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class PersistedTurn:
    """A single conversation turn that persists across restarts."""

    speaker: str  # "companion" | "jarvis"
    text: str
    timestamp: datetime = field(default_factory=_now)
    intent: ConversationIntent | None = None
    turn_id: str = field(default_factory=_new_id)
