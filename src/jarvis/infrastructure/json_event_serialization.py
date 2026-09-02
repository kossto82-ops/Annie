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

from jarvis.domain.enums.permission_level import PermissionLevel
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
from jarvis.domain.events.tool_events import ToolCallRecorded
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.tool_call import ToolCall

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
    ToolCallRecorded: ("call",),
}

_BY_NAME: dict[str, type[CognitiveEvent]] = {cls.__name__: cls for cls in _EXTRA_FIELDS}


def _tool_call_to_dict(call: ToolCall) -> dict[str, Any]:
    return {
        "tool": call.tool,
        "arguments": call.arguments,
        "permission": call.permission.value,
        "duration_seconds": call.duration_seconds,
        "ok": call.ok,
        "error": call.error,
        "started_at": call.started_at.isoformat(),
    }


def _tool_call_from_dict(data: dict[str, Any]) -> ToolCall:
    return ToolCall(
        tool=data["tool"],
        arguments=dict(data.get("arguments") or {}),
        permission=PermissionLevel(data["permission"]),
        duration_seconds=data.get("duration_seconds", 0.0),
        ok=data.get("ok", True),
        error=data.get("error", ""),
        started_at=datetime.fromisoformat(data["started_at"]),
    )


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
        if isinstance(value, Confidence):
            data[name] = value.value
        elif isinstance(value, ToolCall):
            data[name] = _tool_call_to_dict(value)
        else:
            data[name] = value
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
        if name == "confidence":
            kwargs[name] = Confidence(raw)
        elif name == "call":
            kwargs[name] = _tool_call_from_dict(raw)
        else:
            kwargs[name] = raw
    return cls(**kwargs)
