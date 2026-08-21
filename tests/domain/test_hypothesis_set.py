"""Behavioural tests for competing hypotheses (Vision §17)."""

from __future__ import annotations

import pytest

from jarvis.domain.aggregates.hypothesis_set import HypothesisSet, UnknownHypothesis
from jarvis.domain.entities.hypothesis import Hypothesis
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.events.evidence_events import EvidenceAdded
from jarvis.domain.events.hypothesis_events import HypothesisCreated
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence


def _ev(weight: float, *, supports: bool = True) -> Evidence:
    return Evidence(
        content="observation",
        source=EvidenceSource.DIRECT_OBSERVATION,
        weight=Confidence(weight),
        supports=supports,
    )


class TestHypothesis:
    def test_requires_a_statement(self) -> None:
        with pytest.raises(ValueError):
            Hypothesis(statement="  ")

    def test_confidence_is_derived_from_evidence(self) -> None:
        hypothesis = Hypothesis(statement="the change was caused by the deploy")
        assert hypothesis.confidence == Confidence.none()
        hypothesis.add_evidence(_ev(0.5))
        assert hypothesis.confidence.value > 0.0

    def test_adding_evidence_emits_evidence_added(self) -> None:
        hypothesis = Hypothesis(statement="h")
        hypothesis.add_evidence(_ev(0.5))
        events = hypothesis.pull_events()
        assert [type(e) for e in events] == [EvidenceAdded]
        assert events[0].subject_id == hypothesis.id  # type: ignore[attr-defined]


class TestSet:
    def test_requires_an_observation(self) -> None:
        with pytest.raises(ValueError):
            HypothesisSet(observation="   ")

    def test_proposing_emits_hypothesis_created(self) -> None:
        hypotheses = HypothesisSet(observation="something changed")
        hypotheses.propose("the deploy caused it")
        events = hypotheses.pull_events()
        assert [type(e) for e in events] == [HypothesisCreated]

    def test_holds_multiple_hypotheses_without_collapsing(self) -> None:
        hypotheses = HypothesisSet(observation="something changed")
        hypotheses.propose("A")
        hypotheses.propose("B")
        hypotheses.propose("C")
        assert len(hypotheses.ranked()) == 3
        # No evidence yet -> all tied -> no premature winner.
        assert hypotheses.leading() is None

    def test_evidence_reranks_hypotheses(self) -> None:
        hypotheses = HypothesisSet(observation="something changed")
        a = hypotheses.propose("A")
        b = hypotheses.propose("B")
        hypotheses.add_evidence(b.id, _ev(0.9))
        hypotheses.add_evidence(a.id, _ev(0.2))
        ranked = hypotheses.ranked()
        assert ranked[0] is b
        assert hypotheses.leading() is b

    def test_a_tie_yields_no_leader(self) -> None:
        hypotheses = HypothesisSet(observation="something changed")
        a = hypotheses.propose("A")
        b = hypotheses.propose("B")
        hypotheses.add_evidence(a.id, _ev(0.5))
        hypotheses.add_evidence(b.id, _ev(0.5))
        assert hypotheses.leading() is None

    def test_contradicting_evidence_lowers_a_hypothesis(self) -> None:
        hypotheses = HypothesisSet(observation="something changed")
        a = hypotheses.propose("A")
        b = hypotheses.propose("B")
        hypotheses.add_evidence(a.id, _ev(0.8))
        hypotheses.add_evidence(b.id, _ev(0.8))
        hypotheses.add_evidence(a.id, _ev(0.8, supports=False))
        assert hypotheses.leading() is b

    def test_routing_to_unknown_hypothesis_is_rejected(self) -> None:
        hypotheses = HypothesisSet(observation="x")
        with pytest.raises(UnknownHypothesis):
            hypotheses.add_evidence("missing", _ev(0.5))

    def test_set_collects_events_from_its_hypotheses(self) -> None:
        hypotheses = HypothesisSet(observation="x")
        a = hypotheses.propose("A")
        hypotheses.add_evidence(a.id, _ev(0.5))
        kinds = [type(e) for e in hypotheses.pull_events()]
        assert HypothesisCreated in kinds
        assert EvidenceAdded in kinds
