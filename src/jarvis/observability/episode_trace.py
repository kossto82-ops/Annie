"""EpisodeTrace: the structured provenance of an act of cognition (Vision §26).

The whole system emits immutable cognitive events through the NervousSystem, each
carrying a ``correlation_id`` that ties it to the process it belongs to. This
collector subscribes to those events and lets them be read back, grouped by
correlation, as an ordered trace of what happened inside one episode:
EpisodeStarted → EvidenceAdded/BeliefStrengthened/ContradictionDetected → …
→ EpisodeCompleted.

This is *internal* decision provenance (Vision §26), kept so Jarvis can account
for how a decision was reached -- not an exposure of hidden chain-of-thought.
"""

from __future__ import annotations

from jarvis.domain.events.domain_event import CognitiveEvent, DomainEvent


class EpisodeTrace:
    """Collects cognitive events and returns them grouped by correlation."""

    def __init__(self) -> None:
        self._events: list[CognitiveEvent] = []

    def handle(self, event: DomainEvent) -> None:
        """Record a cognitive event as it is dispatched (NervousSystem handler)."""
        if isinstance(event, CognitiveEvent):
            self._events.append(event)

    def for_correlation(self, correlation_id: str) -> tuple[CognitiveEvent, ...]:
        """Every recorded event belonging to one process, in occurrence order."""
        return tuple(e for e in self._events if e.correlation_id == correlation_id)

    def all_events(self) -> tuple[CognitiveEvent, ...]:
        return tuple(self._events)
