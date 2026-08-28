"""File-backed EpisodeTrace: decision provenance that survives a restart (Vision §26).

The in-memory :class:`~jarvis.observability.episode_trace.EpisodeTrace` loses every
trace on process exit, so Jarvis could not account for *how* a past decision was reached
across restarts. This durable variant keeps the same read API but also appends each event
to a JSON-lines log as it arrives, and replays that log on startup.

Append-only JSONL is the right shape for an event log: one line per event is an O(1)
write (not an O(n) rewrite of the whole trace), and a run interrupted mid-append leaves at
most one torn final line, which the tolerant loader simply skips. Unknown event types (a
file written by a newer Jarvis) are skipped too, so an old log never blocks startup.
"""

from __future__ import annotations

import json
from pathlib import Path

from jarvis.domain.events.domain_event import CognitiveEvent, DomainEvent
from jarvis.infrastructure.json_event_serialization import (
    deserialise_event,
    serialise_event,
)


class JsonEpisodeTrace:
    """An EpisodeTrace whose events are appended to, and replayed from, a JSONL file."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._events: list[CognitiveEvent] = []
        self._load()

    def handle(self, event: DomainEvent) -> None:
        """Record a cognitive event in memory and append it to the log."""
        if not isinstance(event, CognitiveEvent):
            return
        self._events.append(event)
        self._append(event)

    def for_correlation(self, correlation_id: str) -> tuple[CognitiveEvent, ...]:
        """Every recorded event belonging to one process, in occurrence order."""
        return tuple(e for e in self._events if e.correlation_id == correlation_id)

    def all_events(self) -> tuple[CognitiveEvent, ...]:
        return tuple(self._events)

    def _load(self) -> None:
        if not self._path.exists():
            return
        for line in self._path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                event = deserialise_event(json.loads(stripped))
            except (json.JSONDecodeError, KeyError):
                continue  # a torn final line or malformed entry -- skip it
            if event is not None:  # None == an event type this version does not know
                self._events.append(event)

    def _append(self, event: CognitiveEvent) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(serialise_event(event)) + "\n"
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(line)
