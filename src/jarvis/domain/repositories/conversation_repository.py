"""The contract for persisting conversation turns across sessions.

Continuity (Vision §3) needs a record of past conversation. This domain
interface persists turns and returns them in order; concrete storage lives
in ``jarvis.infrastructure``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from jarvis.domain.value_objects.persisted_turn import PersistedTurn


class ConversationRepository(Protocol):
    """Persists conversation turns and retrieves them in temporal order."""

    def record_turn(self, turn: PersistedTurn) -> None:
        """Append a turn to the conversation history."""
        ...

    def recent_turns(self, limit: int = 20) -> tuple[PersistedTurn, ...]:
        """The most recent turns, oldest first."""
        ...

    def turns_in_range(
        self, start: datetime, end: datetime
    ) -> tuple[PersistedTurn, ...]:
        """Turns recorded between ``start`` and ``end`` (inclusive)."""
        ...

    def turns_about(
        self, subject: str, limit: int = 10
    ) -> tuple[PersistedTurn, ...]:
        """Turns whose text contains ``subject`` (case-insensitive)."""
        ...
