"""In-memory implementation of :class:`EpisodeRepository`.

Keeps completed episodes in order for the lifetime of the process. A durable
store can replace it behind the same interface later.
"""

from __future__ import annotations

from datetime import datetime

from jarvis.domain.value_objects.episode_record import EpisodeRecord


class InMemoryEpisodeStore:
    """A process-lifetime, ordered store of episode records."""

    def __init__(self) -> None:
        self._records: list[EpisodeRecord] = []

    def record(self, record: EpisodeRecord) -> None:
        self._records.append(record)

    def history(self) -> tuple[EpisodeRecord, ...]:
        return tuple(self._records)

    def history_in_range(
        self, start: datetime, end: datetime
    ) -> tuple[EpisodeRecord, ...]:
        return tuple(
            r for r in self._records
            if start <= r.recorded_at <= end
        )

    def history_about(
        self, subject: str, start: datetime | None = None, end: datetime | None = None
    ) -> tuple[EpisodeRecord, ...]:
        subject_lower = subject.lower()
        results = []
        for r in self._records:
            if subject_lower not in r.trigger.lower():
                continue
            if start is not None and r.recorded_at < start:
                continue
            if end is not None and r.recorded_at > end:
                continue
            results.append(r)
        return tuple(results)
