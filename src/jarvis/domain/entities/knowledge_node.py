"""KnowledgeNode: an entity in the knowledge graph.

Represents a person, project, concept, decision, or event with explicit
properties and evidence grounding. Confidence is derived from evidence,
never set directly — exactly like Belief.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

from jarvis.domain.enums.node_kind import NodeKind
from jarvis.domain.entities.belief import derive_confidence

if TYPE_CHECKING:
    from jarvis.domain.services.evidence_weighting import EvidenceWeightingPolicy
    from jarvis.domain.value_objects.confidence import Confidence
    from jarvis.domain.value_objects.evidence import Evidence
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


class KnowledgeNode:
    """An entity in the knowledge graph: person, project, concept, decision, or event.

    ``kind`` classifies the entity type. ``name`` is the human-readable label.
    ``properties`` holds free-form key-value attributes. Evidence grounds the
    node's existence and properties, with confidence derived from that evidence.
    """

    def __init__(
        self,
        kind: NodeKind,
        name: str,
        *,
        id: str | None = None,
        description: str | None = None,
        properties: dict[str, str] | None = None,
        weighting_policy: EvidenceWeightingPolicy | None = None,
        created_at: datetime | None = None,
    ) -> None:
        self.id: str = id or _new_id()
        self.kind: NodeKind = kind
        self.name: str = name
        self.description: str | None = description
        self.properties: dict[str, str] = properties or {}
        self._weighting_policy: EvidenceWeightingPolicy = weighting_policy or DEFAULT_WEIGHTING
        self.created_at: datetime = created_at or _now()
        self._evidence: list[Evidence] = _empty_evidence()
        self._pending_events: list[CognitiveEvent] = _empty_event_buffer()

    @property
    def confidence(self) -> Confidence:
        """Confidence derived from the evidence supporting this node."""
        return derive_confidence(tuple(self._evidence), self._weighting_policy)

    @property
    def evidence(self) -> tuple[Evidence, ...]:
        """Immutable view of the evidence supporting this node."""
        return tuple(self._evidence)

    def add_evidence(
        self,
        evidence: Evidence,
        correlation_id: str | None = None,
    ) -> None:
        """Add evidence supporting this node's existence or properties."""
        self._evidence.append(evidence)

    def pull_events(self) -> list[CognitiveEvent]:
        """Drain buffered domain events."""
        events = list(self._pending_events)
        self._pending_events.clear()
        return events

    def __repr__(self) -> str:
        return (
            f"KnowledgeNode(id={self.id!r}, kind={self.kind!r}, "
            f"name={self.name!r}, confidence={self.confidence.value:.2f})"
        )
