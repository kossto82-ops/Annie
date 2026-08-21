"""Belief: a provisional conclusion whose confidence is *derived from* evidence.

This is the epistemological core of Jarvis (Vision §7-§9). The invariant "a
belief must never be stronger than the evidence supporting it" is not enforced
by a check that could be forgotten -- it is structural. A belief has no way to
set its own confidence; confidence is always recomputed from the evidence
attached to it. You cannot make a belief stronger than its evidence because the
belief does not own its strength.

Confidence is derived with an additive, evidence-counting estimator:

    confidence = supporting_mass / (supporting_mass + contradicting_mass + 1)

The ``+ 1`` is a neutral prior. Its consequences match the vision exactly:

* No evidence            -> 0.0  (Vision §37: "I have insufficient evidence.")
* Weak support           -> weak confidence (Vision §9: weak evidence, weak belief)
* Repeated support       -> higher confidence, but it approaches 1.0 and never
                            reaches it (evidence alone never yields certainty)
* Contradicting evidence -> confidence falls (Vision §18)

Temporal stability (Vision §10) -- how *stable* a belief has been over time, as
distinct from how confident it is now -- is intentionally not modelled yet;
``Evidence.observed_at`` is retained so it can be computed in a later increment.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from jarvis.domain.events.belief_events import (
    BeliefStrengthened,
    BeliefWeakened,
    ContradictionDetected,
)
from jarvis.domain.events.domain_event import CognitiveEvent
from jarvis.domain.events.evidence_events import EvidenceAdded
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.temporal_stability import TemporalStability

_PRIOR = 1.0

# A month of sustained support reads as solidly stable; the exact scale is tunable
# (D18). Stability is span / (span + reference), so span == reference -> 0.5.
STABILITY_REFERENCE = timedelta(days=30)


def derive_confidence(evidence: tuple[Evidence, ...]) -> Confidence:
    """Compute a belief's confidence purely from the evidence supporting it."""
    supporting = sum(e.weight.value for e in evidence if e.supports)
    contradicting = sum(e.weight.value for e in evidence if e.contradicts)
    return Confidence(supporting / (supporting + contradicting + _PRIOR))


def derive_stability(evidence: tuple[Evidence, ...]) -> TemporalStability:
    """Compute how spread out over time a belief's *supporting* evidence is.

    A single supporting observation (or several at the same instant) has no
    temporal spread and is not stable. Support accumulated over a long period is
    stable. This is distinct from confidence: it depends on *when* evidence
    arrived, not how much of it there is (Vision §10, §11).
    """
    times = sorted(e.observed_at for e in evidence if e.supports)
    if len(times) < 2:
        return TemporalStability.none()
    span = (times[-1] - times[0]).total_seconds()
    reference = STABILITY_REFERENCE.total_seconds()
    return TemporalStability(span / (span + reference))


@dataclass(frozen=True, slots=True)
class BeliefExplanation:
    """The reconstructed provenance of a belief (Vision §8, §26).

    Answers "Why do you believe this?" by exposing the statement, the current
    confidence, and the evidence for and against it.
    """

    statement: str
    confidence: Confidence
    supporting: tuple[Evidence, ...]
    contradicting: tuple[Evidence, ...]


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


def _empty_evidence() -> list[Evidence]:
    return []


def _empty_event_buffer() -> list[CognitiveEvent]:
    return []


@dataclass(slots=True, eq=False)
class Belief:
    """A provisional conclusion grounded in, and revisable by, evidence."""

    statement: str
    id: str = field(default_factory=_new_id)
    formed_at: datetime = field(default_factory=_now)
    _evidence: list[Evidence] = field(default_factory=_empty_evidence, repr=False)
    _pending_events: list[CognitiveEvent] = field(
        default_factory=_empty_event_buffer, repr=False
    )

    def __post_init__(self) -> None:
        if not self.statement or not self.statement.strip():
            raise ValueError("A belief requires a non-empty statement")

    @property
    def confidence(self) -> Confidence:
        """The belief's strength, always derived from its current evidence."""
        return derive_confidence(tuple(self._evidence))

    @property
    def stability(self) -> TemporalStability:
        """How steadily over time the belief has been supported (Vision §10).

        A separate axis from ``confidence``: high confidence with low stability
        signals a recent burst that may be overfitting (Vision §11).
        """
        return derive_stability(tuple(self._evidence))

    @property
    def evidence(self) -> tuple[Evidence, ...]:
        return tuple(self._evidence)

    def add_evidence(self, evidence: Evidence) -> None:
        """Attach evidence and revise confidence, recording what changed."""
        before = self.confidence
        self._evidence.append(evidence)
        after = self.confidence

        self._record(
            EvidenceAdded(
                subject_id=self.id,
                correlation_id=self.id,
                evidence_id=evidence.id,
                supports=evidence.supports,
            )
        )
        # A contradiction is only meaningful against a belief actually held.
        if evidence.contradicts and before.is_stronger_than(Confidence.none()):
            self._record(
                ContradictionDetected(
                    belief_id=self.id, correlation_id=self.id, evidence_id=evidence.id
                )
            )
        if after.is_stronger_than(before):
            self._record(
                BeliefStrengthened(belief_id=self.id, correlation_id=self.id, confidence=after)
            )
        elif before.is_stronger_than(after):
            self._record(
                BeliefWeakened(belief_id=self.id, correlation_id=self.id, confidence=after)
            )

    def explain(self) -> BeliefExplanation:
        """Reconstruct why this belief is held, and how strongly."""
        return BeliefExplanation(
            statement=self.statement,
            confidence=self.confidence,
            supporting=tuple(e for e in self._evidence if e.supports),
            contradicting=tuple(e for e in self._evidence if e.contradicts),
        )

    def pull_events(self) -> list[CognitiveEvent]:
        """Return and clear the events recorded since the last pull."""
        events = self._pending_events[:]
        self._pending_events.clear()
        return events

    def _record(self, event: CognitiveEvent) -> None:
        self._pending_events.append(event)
