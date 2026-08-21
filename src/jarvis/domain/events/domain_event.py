"""Base event types.

An event is an immutable record of a fact that has already happened. Every
event carries enough metadata to reconstruct causal chains later:

* ``event_id``      -- unique identity of this event
* ``occurred_at``   -- when the fact happened (UTC)
* ``correlation_id``-- groups all events belonging to one logical process
* ``causation_id``  -- the event that directly caused this one, if any

``DomainEvent`` is the root of all events. ``CognitiveEvent`` narrows it to
events produced by cognition and binds them to the episode that produced them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class DomainEvent:
    """An immutable fact that occurred within the domain."""

    event_id: str = field(default_factory=_new_id)
    occurred_at: datetime = field(default_factory=_now)
    correlation_id: str | None = None
    causation_id: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class CognitiveEvent(DomainEvent):
    """A domain event produced by cognition.

    ``episode_id`` is optional: not all cognition is bound to a single episode.
    A belief, for example, persists across many episodes (Vision §3, §21), so a
    belief-related event may be emitted without episode context. When an
    operation happens inside an episode, the emitter sets ``episode_id``;
    otherwise ``correlation_id`` still groups the logical process.
    """

    episode_id: str | None = None
