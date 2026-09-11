"""Short-term conversational context -- recent turns, distinct from long-term memory.

The audit noted working memory was only implicit. This makes it explicit and, above
all, *separate* from long-term memory (Vision §3): follow-up questions, pronouns and
"why?" resolve against the last few turns of THIS conversation, not against the belief
store. Long-term memory holds what deserves to persist; this holds what was just said.

It is a small, bounded ring of turns -- not persisted, not evidence, never a belief.

When a ``ConversationRepository`` is injected, turns are also persisted so that
conversation history survives restarts and can be recalled across sessions.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from jarvis.domain.conversation.intent import ConversationIntent

if TYPE_CHECKING:
    from jarvis.domain.repositories.conversation_repository import (
        ConversationRepository,
    )


@dataclass(frozen=True, slots=True)
class Turn:
    """One thing said in the conversation, by the companion or by Jarvis."""

    speaker: str  # "companion" or "jarvis"
    text: str


class ConversationContext:
    """The last few turns of the current conversation, oldest first."""

    def __init__(
        self,
        capacity: int = 12,
        repository: ConversationRepository | None = None,
    ) -> None:
        self._turns: deque[Turn] = deque(maxlen=capacity)
        self._repository = repository

    def record(
        self,
        speaker: str,
        text: str,
        intent: ConversationIntent | None = None,
    ) -> None:
        """Append a turn; the oldest is dropped once capacity is reached.

        When a repository is injected, the turn is also persisted.
        """
        cleaned = text.strip()
        if cleaned:
            self._turns.append(Turn(speaker=speaker, text=cleaned))
            if self._repository is not None:
                from jarvis.domain.value_objects.persisted_turn import PersistedTurn
                turn = PersistedTurn(speaker=speaker, text=cleaned, intent=intent)
                self._repository.record_turn(turn)

    def recent(self, limit: int | None = None) -> tuple[Turn, ...]:
        """The most recent turns, oldest first (all of them when ``limit`` is None)."""
        turns = tuple(self._turns)
        return turns if limit is None else turns[-limit:]

    def before_current(self, limit: int = 8) -> tuple[Turn, ...]:
        """Recent dialogue before the user turn currently being handled.

        The command center records incoming text before classification. Keeping this read
        explicit prevents the current message being duplicated in a reasoner's query and
        preserves speaker attribution for follow-ups.
        """
        turns = tuple(self._turns)
        if turns and turns[-1].speaker == "companion":
            turns = turns[:-1]
        return turns[-limit:]

    def is_empty(self) -> bool:
        return not self._turns
