"""MetaKnowledge: knowledge about one's own cognitive process.

Captures insights about reasoning strategies, retrieval quality, and attention
patterns. Confidence is derived from evidence, never set directly — exactly
like Belief. This enables second-order reflection: noticing patterns in how
Jarvis knows, not just what it knows.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from jarvis.domain.entities.belief import derive_confidence
from jarvis.domain.enums.meta_knowledge_kind import MetaKnowledgeKind
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


class MetaKnowledge:
    """Knowledge about one's own cognitive process.

    ``kind`` classifies the type of meta-knowledge (reasoning strategy,
    retrieval quality, attention pattern). ``statement`` is a natural-language
    description of the insight. Evidence grounds the statement, with
    confidence derived from that evidence.
    """

    def __init__(
        self,
        kind: MetaKnowledgeKind,
        statement: str,
        *,
        id: str | None = None,
        weighting_policy: EvidenceWeightingPolicy | None = None,
        formed_at: datetime | None = None,
    ) -> None:
        self.id: str = id or _new_id()
        self.kind: MetaKnowledgeKind = kind
        self.statement: str = statement
        self._weighting_policy: EvidenceWeightingPolicy = weighting_policy or DEFAULT_WEIGHTING
        self.formed_at: datetime = formed_at or _now()
        self._evidence: list[Evidence] = _empty_evidence()
        self._pending_events: list[CognitiveEvent] = _empty_event_buffer()

    @property
    def confidence(self) -> Confidence:
        """Confidence derived from the evidence supporting this meta-knowledge."""
        return derive_confidence(tuple(self._evidence), self._weighting_policy)

    @property
    def evidence(self) -> tuple[Evidence, ...]:
        """Immutable view of the evidence supporting this meta-knowledge."""
        return tuple(self._evidence)

    def add_evidence(
        self,
        evidence: Evidence,
        correlation_id: str | None = None,
    ) -> None:
        """Add evidence supporting this meta-knowledge."""
        self._evidence.append(evidence)

    def pull_events(self) -> list[CognitiveEvent]:
        """Drain buffered domain events."""
        events = list(self._pending_events)
        self._pending_events.clear()
        return events

    def __repr__(self) -> str:
        return (
            f"MetaKnowledge(id={self.id!r}, kind={self.kind!r}, "
            f"statement={self.statement!r}, confidence={self.confidence.value:.2f})"
        )
