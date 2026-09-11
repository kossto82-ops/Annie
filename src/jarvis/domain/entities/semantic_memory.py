"""Semantic memory — patterns and abstractions derived from multiple episodes.

A semantic memory is a higher-order knowledge structure: it captures a pattern
observed across multiple episodes and beliefs, rather than a single observation.
Confidence and stability are *derived* from the supporting evidence, never set
directly — exactly like Belief.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

from jarvis.domain.entities.belief import derive_confidence, derive_stability

if TYPE_CHECKING:
    from jarvis.domain.services.evidence_weighting import EvidenceWeightingPolicy
    from jarvis.domain.value_objects.confidence import Confidence
    from jarvis.domain.value_objects.evidence import Evidence
    from jarvis.domain.value_objects.temporal_stability import TemporalStability
    from jarvis.domain.events.domain_event import CognitiveEvent


def _new_id() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _empty_evidence() -> list[Evidence]:
    return []


def _empty_event_buffer() -> list[CognitiveEvent]:
    return []


from jarvis.domain.services.evidence_weighting import DEFAULT_WEIGHTING


class SemanticMemory:
    """A pattern or abstraction derived from multiple episodes/beliefs.

    ``pattern`` is a natural-language statement of the generalised insight
    (e.g. "Los usuarios que X tienden a Y").  It is *grounded* in the
    ``source_episode_ids`` and ``source_belief_ids`` that produced it, and
    its confidence/stability are derived from the combined evidence — never
    stronger than the evidence that supports it.

    Domain events are buffered and drained via :meth:`pull_events`, exactly
    like :class:`Belief`.
    """

    def __init__(
        self,
        pattern: str,
        *,
        id: str | None = None,
        source_episode_ids: list[str] | None = None,
        source_belief_ids: list[str] | None = None,
        weighting_policy: EvidenceWeightingPolicy | None = None,
        formed_at: datetime | None = None,
        last_reinforced_at: datetime | None = None,
        reinforcement_count: int = 0,
    ) -> None:
        self.id: str = id or _new_id()
        self.pattern: str = pattern
        self.source_episode_ids: list[str] = source_episode_ids or []
        self.source_belief_ids: list[str] = source_belief_ids or []
        self._weighting_policy: EvidenceWeightingPolicy = weighting_policy or DEFAULT_WEIGHTING
        self.formed_at: datetime = formed_at or _now()
        self.last_reinforced_at: datetime | None = last_reinforced_at
        self.reinforcement_count: int = reinforcement_count
        self._evidence: list[Evidence] = _empty_evidence()
        self._pending_events: list[CognitiveEvent] = _empty_event_buffer()

    # ------------------------------------------------------------------
    # Derived properties (never stored, never set)
    # ------------------------------------------------------------------

    @property
    def confidence(self) -> Confidence:
        """Confidence derived from the evidence supporting this pattern."""
        return derive_confidence(tuple(self._evidence), self._weighting_policy)

    @property
    def stability(self) -> TemporalStability:
        """Temporal stability derived from the spread of evidence over time."""
        return derive_stability(tuple(self._evidence))

    @property
    def evidence(self) -> tuple[Evidence, ...]:
        """Immutable view of the evidence supporting this pattern."""
        return tuple(self._evidence)

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_evidence(
        self,
        evidence: Evidence,
        correlation_id: str | None = None,
    ) -> None:
        """Add a piece of evidence supporting this pattern.

        Emits :class:`SemanticMemoryReinforced` if the evidence strengthens
        the pattern, or :class:`SemanticMemoryContested` if it contradicts.
        """
        from jarvis.domain.events.semantic_events import (
            SemanticMemoryContested,
            SemanticMemoryReinforced,
        )

        self._evidence.append(evidence)
        self.last_reinforced_at = _now()
        self.reinforcement_count += 1

        if evidence.supports:
            event = SemanticMemoryReinforced(
                memory_id=self.id,
                pattern=self.pattern,
                evidence_content=evidence.content,
                correlation_id=correlation_id,
            )
        else:
            event = SemanticMemoryContested(
                memory_id=self.id,
                pattern=self.pattern,
                evidence_content=evidence.content,
                correlation_id=correlation_id,
            )
        self._pending_events.append(event)

    def pull_events(self) -> list[CognitiveEvent]:
        """Drain buffered domain events (read-model pattern)."""
        events = list(self._pending_events)
        self._pending_events.clear()
        return events

    def __repr__(self) -> str:
        return (
            f"SemanticMemory(id={self.id!r}, pattern={self.pattern!r}, "
            f"confidence={self.confidence.value:.2f})"
        )
