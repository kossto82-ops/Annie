"""Serialise cognitive events to/from JSON so a trace can survive a restart (Vision §26).

The trace is a log of heterogeneous :class:`CognitiveEvent` subclasses. Persisting it
means turning each event into a plain dict and back. A small registry names, per event
type, the fields to carry beyond the shared base (event_id, occurred_at, correlation_id,
causation_id, episode_id). The one value-object field in play is ``confidence`` (a
:class:`Confidence`), stored as its float and rehydrated on read.

Read is tolerant of the future: an event type this version does not know is skipped, so
an old trace file never blocks a newer Jarvis from starting. Write is strict: emitting an
unregistered event type raises, so a newly-added event can't be silently dropped from the
record -- add it to ``_EXTRA_FIELDS`` (a test enforces that every subclass is registered).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from jarvis.domain.events.action_events import ActionOutcomeRecorded
from jarvis.domain.events.belief_events import (
    BeliefStrengthened,
    BeliefWeakened,
    ContradictionDetected,
)
from jarvis.domain.events.domain_event import CognitiveEvent
from jarvis.domain.events.episode_events import (
    EpisodeCompleted,
    EpisodeFailed,
    EpisodeReflected,
    EpisodeStarted,
)
from jarvis.domain.events.evidence_events import EvidenceAdded
from jarvis.domain.events.hypothesis_events import HypothesisCreated
from jarvis.domain.value_objects.confidence import Confidence

# Per event type, the fields to persist beyond the shared base. Every concrete
# CognitiveEvent subclass MUST appear here (test_json_event_serialization enforces it).
_EXTRA_FIELDS: dict[type[CognitiveEvent], tuple[str, ...]] = {
    EpisodeStarted: ("trigger",),
    EpisodeReflected: ("note", "contested"),
    EpisodeCompleted: ("result",),
    EpisodeFailed: ("reason",),
    EvidenceAdded: ("subject_id", "evidence_id", "supports"),
    BeliefStrengthened: ("belief_id", "confidence"),
    BeliefWeakened: ("belief_id", "confidence"),
    ContradictionDetected: ("belief_id", "evidence_id"),
    HypothesisCreated: ("hypothesis_id", "statement"),
    ActionOutcomeRecorded: ("action_id", "description", "met_expectation"),
}

_BY_NAME: dict[str, type[CognitiveEvent]] = {cls.__name__: cls for cls in _EXTRA_FIELDS}


class UnregisteredEventError(RuntimeError):
    """Raised when serialising a CognitiveEvent type absent from ``_EXTRA_FIELDS``."""


def serialise_event(event: CognitiveEvent) -> dict[str, Any]:
    """Turn a cognitive event into a JSON-ready dict. Unknown types fail loud."""
    extra = _EXTRA_FIELDS.get(type(event))
    if extra is None:
        raise UnregisteredEventError(
            f"{type(event).__name__} is not registered for trace persistence"
        )
    data: dict[str, Any] = {
        "type": type(event).__name__,
        "event_id": event.event_id,
        "occurred_at": event.occurred_at.isoformat(),
        "correlation_id": event.correlation_id,
        "causation_id": event.causation_id,
        "episode_id": event.episode_id,
    }
    for name in extra:
        value = getattr(event, name)
        data[name] = value.value if isinstance(value, Confidence) else value
    return data


def deserialise_event(data: dict[str, Any]) -> CognitiveEvent | None:
    """Rebuild a cognitive event from a dict, or None for an unknown type (tolerant)."""
    cls = _BY_NAME.get(data.get("type", ""))
    if cls is None:
        return None
    kwargs: dict[str, Any] = {
        "event_id": data["event_id"],
        "occurred_at": datetime.fromisoformat(data["occurred_at"]),
        "correlation_id": data["correlation_id"],
        "causation_id": data["causation_id"],
        "episode_id": data["episode_id"],
    }
    for name in _EXTRA_FIELDS[cls]:
        raw = data[name]
        kwargs[name] = Confidence(raw) if name == "confidence" else raw
    return cls(**kwargs)
