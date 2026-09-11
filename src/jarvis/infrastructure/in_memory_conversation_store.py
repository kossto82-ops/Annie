"""In-memory implementation of :class:`ConversationRepository`.

Keeps conversation turns in order for the lifetime of the process. A durable
store can replace it behind the same interface later.
"""

from __future__ import annotations

from datetime import datetime

from jarvis.domain.value_objects.persisted_turn import PersistedTurn


class InMemoryConversationStore:
    """A process-lifetime, ordered store of conversation turns."""

    def __init__(self) -> None:
        self._turns: list[PersistedTurn] = []

    def record_turn(self, turn: PersistedTurn) -> None:
        self._turns.append(turn)

    def recent_turns(self, limit: int = 20) -> tuple[PersistedTurn, ...]:
        return tuple(self._turns[-limit:])

    def turns_in_range(
        self, start: datetime, end: datetime
    ) -> tuple[PersistedTurn, ...]:
        return tuple(
            t for t in self._turns
            if start <= t.timestamp <= end
        )

    def turns_about(
        self, subject: str, limit: int = 10
    ) -> tuple[PersistedTurn, ...]:
        subject_lower = subject.lower()
        matches = [
            t for t in self._turns
            if subject_lower in t.text.lower()
        ]
        return tuple(matches[-limit:])
