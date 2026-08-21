"""Cognitive events emitted as a belief evolves.

These are the epistemic heartbeat of Jarvis. When incoming evidence opposes a
held belief, that is not silently absorbed: a ``ContradictionDetected`` is
recorded as a first-class fact (Vision §18) alongside the resulting
``BeliefWeakened``. The belief is never overwritten -- the contradiction becomes
information.

(The evidence-attachment event, ``EvidenceAdded``, lives in ``evidence_events``
because it is shared with hypotheses.)
"""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.domain.events.domain_event import CognitiveEvent
from jarvis.domain.value_objects.confidence import Confidence


@dataclass(frozen=True, slots=True, kw_only=True)
class BeliefStrengthened(CognitiveEvent):
    """New evidence raised a belief's confidence."""

    belief_id: str
    confidence: Confidence


@dataclass(frozen=True, slots=True, kw_only=True)
class BeliefWeakened(CognitiveEvent):
    """New (often contradicting) evidence lowered a belief's confidence."""

    belief_id: str
    confidence: Confidence


@dataclass(frozen=True, slots=True, kw_only=True)
class ContradictionDetected(CognitiveEvent):
    """Incoming evidence opposed a belief that was actually held (Vision §18)."""

    belief_id: str
    evidence_id: str
