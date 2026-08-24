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
