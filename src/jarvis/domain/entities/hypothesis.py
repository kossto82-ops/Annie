"""Hypothesis: a candidate explanation whose confidence is derived from evidence.

A hypothesis sits earlier in the epistemic hierarchy than a settled belief
(Vision §7: Observation -> Pattern -> Hypothesis -> Mental Model). Like a belief,
it never owns its own strength -- confidence is always ``derive_confidence`` over
its evidence (D11). Unlike a belief, a hypothesis is meant to coexist with rivals
inside a :class:`HypothesisSet`; the point is comparison, not standalone truth.

The estimator is deliberately shared with :mod:`jarvis.domain.entities.belief`
via ``derive_confidence`` -- the one thing that must never diverge. The thin
structural similarity (an evidence list, a confidence property) is left
duplicated on purpose (D12): it is cheaper and less risky than a premature base
class, and extraction waits for a genuine third case.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from jarvis.domain.entities.belief import derive_confidence
from jarvis.domain.events.domain_event import CognitiveEvent
from jarvis.domain.events.evidence_events import EvidenceAdded
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence


def _new_id() -> str:
    return str(uuid.uuid4())


def _empty_evidence() -> list[Evidence]:
    return []


def _empty_event_buffer() -> list[CognitiveEvent]:
    return []


@dataclass(slots=True, eq=False)
class Hypothesis:
    """A candidate explanation competing to explain an observation."""

    statement: str
    id: str = field(default_factory=_new_id)
    _evidence: list[Evidence] = field(default_factory=_empty_evidence, repr=False)
    _pending_events: list[CognitiveEvent] = field(
        default_factory=_empty_event_buffer, repr=False
    )

    def __post_init__(self) -> None:
        if not self.statement or not self.statement.strip():
            raise ValueError("A hypothesis requires a non-empty statement")

    @property
    def confidence(self) -> Confidence:
        return derive_confidence(tuple(self._evidence))

    @property
    def evidence(self) -> tuple[Evidence, ...]:
        return tuple(self._evidence)

    def add_evidence(self, evidence: Evidence, correlation_id: str | None = None) -> None:
        """Attach evidence; its effect on relative confidence is read via the set.

        ``correlation_id`` lets a wider process (a deliberation episode) group
        this event with it; defaults to the hypothesis's own id.
        """
        self._evidence.append(evidence)
        self._record(
            EvidenceAdded(
                subject_id=self.id,
                correlation_id=correlation_id or self.id,
                evidence_id=evidence.id,
                supports=evidence.supports,
            )
        )

    def pull_events(self) -> list[CognitiveEvent]:
        events = self._pending_events[:]
        self._pending_events.clear()
        return events

    def _record(self, event: CognitiveEvent) -> None:
        self._pending_events.append(event)
