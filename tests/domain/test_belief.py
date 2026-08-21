"""Behavioural tests for the Belief entity and evidence-derived confidence.

These tests pin the epistemological invariants from the vision, not the exact
arithmetic of the estimator.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def _ev(
    weight: float,
    *,
    supports: bool = True,
    content: str = "observation",
    at: datetime | None = None,
) -> Evidence:
    kwargs: dict[str, object] = {
        "content": content,
        "source": EvidenceSource.DIRECT_OBSERVATION,
        "weight": Confidence(weight),
        "supports": supports,
    }
    if at is not None:
        kwargs["observed_at"] = at
    return Evidence(**kwargs)  # type: ignore[arg-type]


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


class TestTemporalStability:
    def test_a_single_observation_is_not_stable(self) -> None:
        belief = Belief(statement="x")
        belief.add_evidence(_ev(0.9))
        assert belief.stability.value == 0.0

    def test_simultaneous_evidence_is_not_stable(self) -> None:
        belief = Belief(statement="x")
        belief.add_evidence(_ev(0.9, at=_EPOCH))
        belief.add_evidence(_ev(0.9, at=_EPOCH))
        assert belief.stability.value == 0.0

    def test_support_spread_over_time_is_more_stable(self) -> None:
        narrow = Belief(statement="x")
        narrow.add_evidence(_ev(0.5, at=_EPOCH))
        narrow.add_evidence(_ev(0.5, at=_EPOCH + timedelta(hours=1)))

        wide = Belief(statement="y")
        wide.add_evidence(_ev(0.5, at=_EPOCH))
        wide.add_evidence(_ev(0.5, at=_EPOCH + timedelta(days=90)))

        assert wide.stability.is_more_stable_than(narrow.stability)

    def test_stability_is_independent_of_confidence(self) -> None:
        # Same evidence weights and count -> equal confidence; different time
        # spans -> different stability. The two axes do not collapse (Vision §10).
        burst = Belief(statement="x")
        burst.add_evidence(_ev(0.6, at=_EPOCH))
        burst.add_evidence(_ev(0.6, at=_EPOCH))

        sustained = Belief(statement="y")
        sustained.add_evidence(_ev(0.6, at=_EPOCH))
        sustained.add_evidence(_ev(0.6, at=_EPOCH + timedelta(days=60)))

        assert burst.confidence == sustained.confidence
        assert sustained.stability.is_more_stable_than(burst.stability)

    def test_contradicting_evidence_does_not_count_toward_stability(self) -> None:
        belief = Belief(statement="x")
        belief.add_evidence(_ev(0.9, at=_EPOCH))
        belief.add_evidence(_ev(0.9, supports=False, at=_EPOCH + timedelta(days=90)))
        # Only one *supporting* observation -> no temporal spread of support.
        assert belief.stability.value == 0.0


class TestSourceWeighting:
    def _belief_with(self, source: EvidenceSource) -> Belief:
        belief = Belief(statement="the user prefers simplicity")
        belief.add_evidence(
            Evidence(content="obs", source=source, weight=Confidence(0.8))
        )
        return belief

    def test_source_shapes_confidence_for_equal_raw_weight(self) -> None:
        # Same raw weight (0.8), different source -> different confidence (Vision §11).
        confirmed = self._belief_with(EvidenceSource.USER_STATEMENT)
        observed = self._belief_with(EvidenceSource.DIRECT_OBSERVATION)
        assert confirmed.confidence.is_stronger_than(observed.confidence)

    def test_weighting_policy_is_injectable(self) -> None:
        from jarvis.domain.services.evidence_weighting import SourceWeightingPolicy

        sceptical = Belief(
            statement="x",
            weighting_policy=SourceWeightingPolicy(
                factors={EvidenceSource.USER_STATEMENT: 0.1}
            ),
        )
        trusting = Belief(statement="y")  # default policy
        piece = dict(source=EvidenceSource.USER_STATEMENT, weight=Confidence(0.8))
        sceptical.add_evidence(Evidence(content="o", **piece))  # type: ignore[arg-type]
        trusting.add_evidence(Evidence(content="o", **piece))  # type: ignore[arg-type]
        assert trusting.confidence.is_stronger_than(sceptical.confidence)


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
        assert explanation.stability == belief.stability
        assert explanation.supporting == (supporting,)
        assert explanation.contradicting == (contradicting,)


class TestNarration:
    def test_ungrounded_belief_admits_it_has_no_evidence(self) -> None:
        narration = Belief(statement="the sky is green").explain().narrate()
        assert "no evidence" in narration

    def test_grounded_belief_states_confidence_and_reasons(self) -> None:
        belief = Belief(statement="the user prefers simplicity")
        belief.add_evidence(
            Evidence(
                content="chose the simpler design",
                source=EvidenceSource.USER_STATEMENT,
                weight=Confidence(0.9),
            )
        )
        narration = belief.explain().narrate()
        assert "the user prefers simplicity" in narration
        assert "chose the simpler design" in narration
        assert "user statement" in narration  # source is named

    def test_contested_belief_names_the_contradiction(self) -> None:
        belief = Belief(statement="the user prefers dark mode")
        belief.add_evidence(_ev(0.8, content="enabled dark mode"))
        belief.add_evidence(_ev(0.8, supports=False, content="switched back to light"))
        narration = belief.explain().narrate()
        assert "contradicts" in narration
        assert "may be wrong" in narration
