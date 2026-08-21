"""HypothesisSet: competing explanations for one observation (Vision §17).

Jarvis should hold multiple hypotheses at once and let evidence shift their
relative confidence, rather than collapsing an observation into a single
explanation prematurely. This aggregate owns that set: it proposes hypotheses,
routes evidence to them, and ranks them -- but it refuses to declare a leader
while the top two are tied, because a tie is genuine uncertainty, not an answer.

It is the consistency boundary for its hypotheses: evidence only reaches a
hypothesis through the set, and the set collects every event (its own and its
hypotheses') for a single orchestrator to dispatch.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from jarvis.domain.entities.hypothesis import Hypothesis
from jarvis.domain.events.domain_event import CognitiveEvent
from jarvis.domain.events.hypothesis_events import HypothesisCreated
from jarvis.domain.value_objects.evidence import Evidence


class UnknownHypothesis(KeyError):
    """Raised when evidence is routed to a hypothesis not in the set."""


def _new_id() -> str:
    return str(uuid.uuid4())


def _empty_hypotheses() -> list[Hypothesis]:
    return []


def _empty_event_buffer() -> list[CognitiveEvent]:
    return []


@dataclass(slots=True, eq=False)
class HypothesisSet:
    """A set of competing hypotheses for a single observation."""

    observation: str
    id: str = field(default_factory=_new_id)
    _hypotheses: list[Hypothesis] = field(default_factory=_empty_hypotheses, repr=False)
    _pending_events: list[CognitiveEvent] = field(
        default_factory=_empty_event_buffer, repr=False
    )

    def __post_init__(self) -> None:
        if not self.observation or not self.observation.strip():
            raise ValueError("A hypothesis set requires a non-empty observation")

    def propose(self, statement: str, correlation_id: str | None = None) -> Hypothesis:
        """Add a competing explanation and return it."""
        hypothesis = Hypothesis(statement=statement)
        self._hypotheses.append(hypothesis)
        self._record(
            HypothesisCreated(
                hypothesis_id=hypothesis.id,
                correlation_id=correlation_id or self.id,
                statement=hypothesis.statement,
            )
        )
        return hypothesis

    def add_evidence(
        self, hypothesis_id: str, evidence: Evidence, correlation_id: str | None = None
    ) -> None:
        """Route evidence to one hypothesis, shifting its relative standing."""
        hypothesis = self._require(hypothesis_id)
        hypothesis.add_evidence(evidence, correlation_id=correlation_id)

    def ranked(self) -> list[Hypothesis]:
        """Hypotheses ordered by descending confidence (ties keep insertion order).

        A fresh list each call, so callers cannot mutate the set's internal order.
        """
        return sorted(self._hypotheses, key=lambda h: h.confidence.value, reverse=True)

    def leading(self) -> Hypothesis | None:
        """The single strongest hypothesis, or None if empty or the top two tie.

        A tie is unresolved uncertainty -- the set refuses to name a winner rather
        than collapse prematurely (Vision §17).
        """
        ranked = self.ranked()
        if not ranked:
            return None
        top = ranked[0]
        if len(ranked) >= 2 and top.confidence == ranked[1].confidence:
            return None
        return top

    def pull_events(self) -> list[CognitiveEvent]:
        """Return and clear this set's events and those of its hypotheses."""
        events = self._pending_events[:]
        self._pending_events.clear()
        for hypothesis in self._hypotheses:
            events.extend(hypothesis.pull_events())
        return events

    def _require(self, hypothesis_id: str) -> Hypothesis:
        for hypothesis in self._hypotheses:
            if hypothesis.id == hypothesis_id:
                return hypothesis
        raise UnknownHypothesis(hypothesis_id)

    def _record(self, event: CognitiveEvent) -> None:
        self._pending_events.append(event)
