"""Behavioural tests for the Belief entity and evidence-derived confidence.

These tests pin the epistemological invariants from the vision, not the exact
arithmetic of the estimator.
"""

from __future__ import annotations

import pytest

from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.events.belief_events import (
    BeliefStrengthened,
    BeliefWeakened,
    ContradictionDetected,
)
from jarvis.domain.events.evidence_events import EvidenceAdded
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence


def _ev(weight: float, *, supports: bool = True, content: str = "observation") -> Evidence:
    return Evidence(
        content=content,
        source=EvidenceSource.DIRECT_OBSERVATION,
        weight=Confidence(weight),
        supports=supports,
    )


class TestFormation:
    def test_requires_a_statement(self) -> None:
        with pytest.raises(ValueError):
            Belief(statement="  ")

    def test_ungrounded_belief_has_no_confidence(self) -> None:
        # A belief with no evidence is honestly worth nothing (Vision §37).
        assert Belief(statement="the sky is green").confidence == Confidence.none()


class TestEvidenceDrivenConfidence:
    def test_a_belief_is_never_stronger_than_its_evidence(self) -> None:
        # Even overwhelming, perfectly consistent support never reaches certainty.
        belief = Belief(statement="the user prefers simplicity")
        for _ in range(50):
            belief.add_evidence(_ev(1.0))
        assert belief.confidence.value < 1.0

    def test_weak_evidence_yields_weak_confidence(self) -> None:
        belief = Belief(statement="the user is in a hurry")
        belief.add_evidence(_ev(0.1))
        assert belief.confidence.value < 0.2

    def test_repeated_support_strengthens_the_belief(self) -> None:
        belief = Belief(statement="the user prefers simplicity")
        belief.add_evidence(_ev(0.5))
        after_one = belief.confidence
        belief.add_evidence(_ev(0.5))
        assert belief.confidence.is_stronger_than(after_one)

    def test_contradicting_evidence_lowers_confidence(self) -> None:
        belief = Belief(statement="the user prefers dark mode")
        belief.add_evidence(_ev(0.8))
        before = belief.confidence
        belief.add_evidence(_ev(0.8, supports=False))
        assert before.is_stronger_than(belief.confidence)

    def test_confidence_reflects_only_current_evidence(self) -> None:
        belief = Belief(statement="x")
        belief.add_evidence(_ev(0.6))
        recomputed = belief.confidence
        # Reading twice yields the same derived value; nothing is cached wrongly.
        assert belief.confidence == recomputed


class TestEvents:
    def test_supporting_evidence_emits_added_then_strengthened(self) -> None:
        belief = Belief(statement="x")
        belief.add_evidence(_ev(0.7))
        kinds = [type(e) for e in belief.pull_events()]
        assert kinds == [EvidenceAdded, BeliefStrengthened]

    def test_contradiction_is_first_class_then_weakens(self) -> None:
        # A contradiction against a held belief is recorded explicitly (Vision §18),
        # not silently absorbed into a bare weakening.
        belief = Belief(statement="x")
        belief.add_evidence(_ev(0.9))
        belief.pull_events()  # discard formation events
        belief.add_evidence(_ev(0.9, supports=False))
        kinds = [type(e) for e in belief.pull_events()]
        assert kinds == [EvidenceAdded, ContradictionDetected, BeliefWeakened]

    def test_no_contradiction_event_when_nothing_is_yet_believed(self) -> None:
        # Contradicting evidence against an ungrounded belief contradicts nothing.
        belief = Belief(statement="x")
        belief.add_evidence(_ev(0.9, supports=False))
        kinds = [type(e) for e in belief.pull_events()]
        assert ContradictionDetected not in kinds

    def test_events_reference_the_belief_and_carry_confidence(self) -> None:
        belief = Belief(statement="x")
        belief.add_evidence(_ev(0.7))
        strengthened = next(
            e for e in belief.pull_events() if isinstance(e, BeliefStrengthened)
        )
        assert strengthened.belief_id == belief.id
        assert strengthened.confidence == belief.confidence


class TestExplainability:
    def test_explain_reconstructs_supporting_and_contradicting_evidence(self) -> None:
        belief = Belief(statement="the user prefers simplicity")
        supporting = _ev(0.8, content="chose the simpler option")
        contradicting = _ev(0.4, supports=False, content="asked for an advanced mode")
        belief.add_evidence(supporting)
        belief.add_evidence(contradicting)

        explanation = belief.explain()
        assert explanation.statement == "the user prefers simplicity"
        assert explanation.confidence == belief.confidence
        assert explanation.supporting == (supporting,)
        assert explanation.contradicting == (contradicting,)
