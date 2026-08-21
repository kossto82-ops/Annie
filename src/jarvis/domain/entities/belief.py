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

Confidence is one axis; temporal stability (Vision §10) -- how *steadily* a belief
has been supported over time -- is a separate one, derived in ``derive_stability``.
``BeliefExplanation.narrate`` turns both, plus the evidence, into a plain-language
"why do you believe this?" account (Vision §26, §40).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.events.belief_events import (
    BeliefStrengthened,
    BeliefWeakened,
    ContradictionDetected,
)
from jarvis.domain.events.domain_event import CognitiveEvent
from jarvis.domain.events.evidence_events import EvidenceAdded
from jarvis.domain.services.evidence_weighting import (
    DEFAULT_WEIGHTING,
    EvidenceWeightingPolicy,
)
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.temporal_stability import TemporalStability

_PRIOR = 1.0

# A month of sustained support reads as solidly stable; the exact scale is tunable
# (D18). Stability is span / (span + reference), so span == reference -> 0.5.
STABILITY_REFERENCE = timedelta(days=30)


def derive_confidence(
    evidence: tuple[Evidence, ...],
    policy: EvidenceWeightingPolicy = DEFAULT_WEIGHTING,
) -> Confidence:
    """Compute a belief's confidence from its evidence, weighted by source.

    Each piece contributes its *effective* weight (raw weight scaled by ``policy``
    from its source), so explicit confirmation counts for more than an isolated
    observation (Vision §11) without altering the raw evidence.
    """
    supporting = sum(policy.effective_weight(e) for e in evidence if e.supports)
    contradicting = sum(policy.effective_weight(e) for e in evidence if e.contradicts)
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


def _readable_source(source: EvidenceSource) -> str:
    return source.value.replace("_", " ")


@dataclass(frozen=True, slots=True)
class BeliefExplanation:
    """The reconstructed provenance of a belief (Vision §8, §26).

    Answers "Why do you believe this?" by exposing the statement, the current
    confidence and stability, and the evidence for and against it. ``narrate``
    renders that structure into the plain-language self-explanation the vision
    holds up as the goal (Vision §40).
    """

    statement: str
    confidence: Confidence
    stability: TemporalStability
    supporting: tuple[Evidence, ...]
    contradicting: tuple[Evidence, ...]

    def narrate(self) -> str:
        """Render a human-readable account of why the belief is held."""
        if not self.supporting and not self.contradicting:
            return (
                f'I don\'t hold a view on "{self.statement}" yet — I have no '
                "evidence. I would need observations before concluding."
            )

        confidence = self.confidence.value
        confidence_label = (
            "high" if confidence >= 0.8 else "moderate" if confidence >= 0.5 else "low"
        )
        stability = self.stability.value
        stability_label = (
            "consistently over a long time"
            if stability >= 0.7
            else "over some time"
            if stability >= 0.3
            else "within a narrow time window"
            if stability > 0.0
            else "with no track record yet"
        )

        parts = [
            f'I hold "{self.statement}" with {confidence_label} confidence '
            f"({confidence:.2f}), {stability_label}."
        ]
        if self.supporting:
            strongest = sorted(
                self.supporting, key=lambda e: e.weight.value, reverse=True
            )[:3]
            reasons = "; ".join(
                f"{e.content} ({_readable_source(e.source)})" for e in strongest
            )
            parts.append(f"I believe this because: {reasons}.")
        if self.contradicting:
            against = "; ".join(
                f"{e.content} ({_readable_source(e.source)})"
                for e in self.contradicting[:3]
            )
            parts.append(f"But some evidence contradicts it: {against}. I may be wrong.")

        if confidence < 0.5:
            parts.append("I am not certain — more evidence would help.")
        elif stability < 0.3:
            parts.append("This rests on a short span of evidence, so I hold it tentatively.")
        else:
            parts.append("I am fairly confident, though I remain open to revision.")
        return " ".join(parts)


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
    weighting_policy: EvidenceWeightingPolicy = DEFAULT_WEIGHTING
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
        return derive_confidence(tuple(self._evidence), self.weighting_policy)

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

    def add_evidence(self, evidence: Evidence, correlation_id: str | None = None) -> None:
        """Attach evidence and revise confidence, recording what changed.

        ``correlation_id`` lets a caller (e.g. an episode) group these events with
        the wider process they belong to; it defaults to the belief's own id when
        the belief evolves outside any larger process.
        """
        correlation = correlation_id or self.id
        before = self.confidence
        self._evidence.append(evidence)
        after = self.confidence

        self._record(
            EvidenceAdded(
                subject_id=self.id,
                correlation_id=correlation,
                evidence_id=evidence.id,
                supports=evidence.supports,
            )
        )
        # A contradiction is only meaningful against a belief actually held.
        if evidence.contradicts and before.is_stronger_than(Confidence.none()):
            self._record(
                ContradictionDetected(
                    belief_id=self.id, correlation_id=correlation, evidence_id=evidence.id
                )
            )
        if after.is_stronger_than(before):
            self._record(
                BeliefStrengthened(
                    belief_id=self.id, correlation_id=correlation, confidence=after
                )
            )
        elif before.is_stronger_than(after):
            self._record(
                BeliefWeakened(
                    belief_id=self.id, correlation_id=correlation, confidence=after
                )
            )

    def explain(self) -> BeliefExplanation:
        """Reconstruct why this belief is held, and how strongly."""
        return BeliefExplanation(
            statement=self.statement,
            confidence=self.confidence,
            stability=self.stability,
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
