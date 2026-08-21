"""Behavioural tests for curiosity (Vision §16)."""

from __future__ import annotations

from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.services.curiosity import wonder
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence


def _confident_self_belief() -> Belief:
    belief = Belief(statement="I tend to conclude without sufficient evidence")
    for _ in range(4):
        belief.add_evidence(
            Evidence(
                content="an ungrounded conclusion",
                source=EvidenceSource.USER_STATEMENT,
                weight=Confidence(1.0),
            )
        )
    return belief


class TestWonder:
    def test_a_confident_self_belief_raises_an_impulse(self) -> None:
        impulse = wonder(_confident_self_belief())
        assert impulse is not None
        assert "I tend to conclude without sufficient evidence" in impulse.rationale

    def test_impulse_names_an_internal_trigger(self) -> None:
        impulse = wonder(_confident_self_belief())
        assert impulse is not None
        assert impulse.trigger  # something to pursue
        assert impulse.prompted_by_belief_id

    def test_a_weak_self_belief_raises_nothing(self) -> None:
        weak = Belief(statement="I might be slightly biased")
        weak.add_evidence(
            Evidence(
                content="one hint",
                source=EvidenceSource.DIRECT_OBSERVATION,
                weight=Confidence(0.1),
            )
        )
        assert wonder(weak) is None
