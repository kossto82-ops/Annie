"""The contract for remembering completed cognitive episodes.

Continuity (Vision §3) and later self-modeling (Vision §6, §31) need a record of
past cognition. This domain interface persists episode records and returns the
history in order; concrete storage lives in ``jarvis.infrastructure``.
"""

from __future__ import annotations

from typing import Protocol

from jarvis.domain.value_objects.episode_record import EpisodeRecord


class EpisodeRepository(Protocol):
    """Persists episode records and returns them in the order they occurred."""

    def record(self, record: EpisodeRecord) -> None:
        """Append a completed episode to memory."""
        ...

    def history(self) -> tuple[EpisodeRecord, ...]:
        """All recorded episodes, oldest first."""
        ...
