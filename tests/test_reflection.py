"""Tests for Reflect: noticing load-bearing observations (Vision §19, §31)."""

from __future__ import annotations

from jarvis import Jarvis
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence


def _ev(content: str) -> Evidence:
    return Evidence(
        content=content,
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(0.9),
    )


class TestReflect:
    def test_an_observation_grounding_two_beliefs_is_noticed(self) -> None:
        jarvis = Jarvis()
        shared = "the client moved the deadline up"
        jarvis.think("is the schedule at risk?", evidence=[_ev(shared)])
        jarvis.think("should we cut scope?", evidence=[_ev(shared)])

        findings = jarvis.reflect()
        assert len(findings) == 1
        assert findings[0].observation == shared
        assert findings[0].load == 2
        assert set(findings[0].beliefs) == {
            "Working conclusion about: is the schedule at risk?",
            "Working conclusion about: should we cut scope?",
        }

    def test_isolated_beliefs_yield_no_reflection(self) -> None:
        jarvis = Jarvis()
        jarvis.think("q1", evidence=[_ev("observation A")])
        jarvis.think("q2", evidence=[_ev("observation B")])
        assert jarvis.reflect() == ()

    def test_an_evidence_free_belief_contributes_nothing(self) -> None:
        jarvis = Jarvis()
        jarvis.think("grounded twice", evidence=[_ev("shared")])
        jarvis.think("also grounded", evidence=[_ev("shared")])
        jarvis.think("empty")  # no evidence
        findings = jarvis.reflect()
        assert len(findings) == 1
        assert findings[0].load == 2

    def test_the_most_load_bearing_observation_comes_first(self) -> None:
        jarvis = Jarvis()
        heavy = "the API changed"
        light = "the logo is blue"
        jarvis.think("a", evidence=[_ev(heavy)])
        jarvis.think("b", evidence=[_ev(heavy)])
        jarvis.think("c", evidence=[_ev(heavy)])
        jarvis.think("d", evidence=[_ev(light)])
        jarvis.think("e", evidence=[_ev(light)])

        findings = jarvis.reflect()
        assert findings[0].observation == heavy and findings[0].load == 3
        assert findings[1].observation == light and findings[1].load == 2

    def test_a_reflection_can_describe_itself(self) -> None:
        jarvis = Jarvis()
        jarvis.think("a", evidence=[_ev("the API changed")])
        jarvis.think("b", evidence=[_ev("the API changed")])
        described = jarvis.reflect()[0].describe()
        assert "the API changed" in described
        assert "load-bearing" in described


class TestHypothesise:
    def test_a_load_bearing_observation_brews_a_hypothesis(self) -> None:
        jarvis = Jarvis()
        cause = "the client moved the deadline up"
        jarvis.think("is the schedule at risk?", evidence=[_ev(cause)])
        jarvis.think("should we cut scope?", evidence=[_ev(cause)])

        hypotheses = jarvis.hypothesise()
        assert hypotheses is not None
        leading = hypotheses.leading()
        assert leading is not None
        assert cause in leading.statement
        assert "common cause" in leading.statement
        assert leading.confidence.value > 0.0

    def test_the_common_cause_leads_over_the_coincidence_null(self) -> None:
        jarvis = Jarvis()
        cause = "the API changed"
        for question in ("a", "b", "c"):
            jarvis.think(question, evidence=[_ev(cause)])

        hypotheses = jarvis.hypothesise()
        assert hypotheses is not None
        leading = hypotheses.leading()
        assert leading is not None and "common cause" in leading.statement
        # Seeded with one piece of evidence per belief resting on the observation.
        assert len(leading.evidence) == 3

    def test_nothing_load_bearing_yields_no_hypothesis(self) -> None:
        jarvis = Jarvis()
        jarvis.think("a", evidence=[_ev("observation A")])
        jarvis.think("b", evidence=[_ev("observation B")])
        assert jarvis.hypothesise() is None

    def test_more_beliefs_on_the_observation_make_a_more_confident_hypothesis(self) -> None:
        two = Jarvis()
        two.think("a", evidence=[_ev("X")])
        two.think("b", evidence=[_ev("X")])
        three = Jarvis()
        three.think("a", evidence=[_ev("X")])
        three.think("b", evidence=[_ev("X")])
        three.think("c", evidence=[_ev("X")])

        two_leading = two.hypothesise().leading()  # type: ignore[union-attr]
        three_leading = three.hypothesise().leading()  # type: ignore[union-attr]
        assert two_leading is not None and three_leading is not None
        assert three_leading.confidence.value > two_leading.confidence.value
