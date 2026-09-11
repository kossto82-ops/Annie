"""KnowledgeEdge: a relationship between two knowledge nodes.

Represents a directed relationship (e.g., "works_on", "knows", "decided",
"caused") between a source and target node. Weight is derived from evidence,
never set directly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from jarvis.domain.entities.belief import derive_confidence
from jarvis.domain.services.evidence_weighting import DEFAULT_WEIGHTING

if TYPE_CHECKING:
    from jarvis.domain.events.domain_event import CognitiveEvent
    from jarvis.domain.services.evidence_weighting import EvidenceWeightingPolicy
    from jarvis.domain.value_objects.confidence import Confidence
    from jarvis.domain.value_objects.evidence import Evidence


def _new_id() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


def _empty_evidence() -> list[Evidence]:
    return []


def _empty_event_buffer() -> list[CognitiveEvent]:
    return []


class KnowledgeEdge:
    """A directed relationship between two knowledge nodes.

    ``source_id`` and ``target_id`` reference the connected nodes.
    ``relation`` is the type of relationship (e.g., "works_on", "knows").
    Weight is derived from the supporting evidence.
    """

    def __init__(
        self,
        source_id: str,
        target_id: str,
        relation: str,
        *,
        id: str | None = None,
        weighting_policy: EvidenceWeightingPolicy | None = None,
        created_at: datetime | None = None,
    ) -> None:
        self.id: str = id or _new_id()
        self.source_id: str = source_id
        self.target_id: str = target_id
        self.relation: str = relation
        self._weighting_policy: EvidenceWeightingPolicy = weighting_policy or DEFAULT_WEIGHTING
        self.created_at: datetime = created_at or _now()
        self._evidence: list[Evidence] = _empty_evidence()
        self._pending_events: list[CognitiveEvent] = _empty_event_buffer()

    @property
    def weight(self) -> Confidence:
        """Weight derived from the evidence supporting this edge."""
        return derive_confidence(tuple(self._evidence), self._weighting_policy)

    @property
    def evidence(self) -> tuple[Evidence, ...]:
        """Immutable view of the evidence supporting this edge."""
        return tuple(self._evidence)

    def add_evidence(
        self,
        evidence: Evidence,
        correlation_id: str | None = None,
    ) -> None:
        """Add evidence supporting this relationship."""
        self._evidence.append(evidence)

    def pull_events(self) -> list[CognitiveEvent]:
        """Drain buffered domain events."""
        events = list(self._pending_events)
        self._pending_events.clear()
        return events

    def __repr__(self) -> str:
        return (
            f"KnowledgeEdge(id={self.id!r}, {self.source_id!r} "
            f"--[{self.relation}]--> {self.target_id!r}, "
            f"weight={self.weight.value:.2f})"
        )
