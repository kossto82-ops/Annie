"""In-memory implementation of :class:`EpisodeRepository`.

Keeps completed episodes in order for the lifetime of the process. A durable
store can replace it behind the same interface later.
"""

from __future__ import annotations

from jarvis.domain.value_objects.episode_record import EpisodeRecord


class InMemoryEpisodeStore:
    """A process-lifetime, ordered store of episode records."""

    def __init__(self) -> None:
        self._records: list[EpisodeRecord] = []

    def record(self, record: EpisodeRecord) -> None:
        self._records.append(record)

    def history(self) -> tuple[EpisodeRecord, ...]:
        return tuple(self._records)
