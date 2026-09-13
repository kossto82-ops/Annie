"""LearnedStateRepository: persistence behind learned-threshold continuity.

The domain owns the contract; JSON and SQLite adapters implement it. Only one
record exists at a time (the latest justified adaptation wins); ``clear()``
reverts to untrained defaults.
"""

from __future__ import annotations

from typing import Protocol

from jarvis.domain.value_objects.learned_state import LearnedState


class LearnedStateRepository(Protocol):
    """Durable storage for the latest justified knob adaptation."""

    def load(self) -> LearnedState | None:
        """The stored adaptation, or None when nothing was ever learned."""
        ...

    def save(self, state: LearnedState) -> None:
        """Durably record an adaptation (replacing any previous one)."""
        ...

    def clear(self) -> None:
        """Forget learned tuning (recovery / operator reset)."""
        ...
