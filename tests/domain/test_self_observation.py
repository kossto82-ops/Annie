"""Behavioural tests for self-observation over episode history (Vision §6, §31)."""

from __future__ import annotations

from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.services.self_observation import (
    INSUFFICIENT_EVIDENCE_HABIT,
    OVERCONFIDENCE_HABIT,
    observe_evidence_habit,
    observe_overconfidence,
)
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.temporal_stability import TemporalStability


def _record(
    confidence: float,
    trigger: str = "q",
    origin: TriggerOrigin = TriggerOrigin.COMPANION,
    stability: float = 0.5,
    kind: EpisodeKind = EpisodeKind.CONCLUSION,
) -> EpisodeRecord:
    return EpisodeRecord(
        episode_id="e",
        trigger=trigger,
        decision="d",
        working_belief_id="b",
        outcome=EpisodeState.COMPLETED,
        conclusion_confidence=Confidence(confidence),
        conclusion_stability=TemporalStability(stability),
        origin=origin,
        kind=kind,
    )


class TestObserveEvidenceHabit:
    def test_too_little_history_yields_no_self_belief(self) -> None:
        assert observe_evidence_habit([_record(0.0), _record(0.0)]) is None

    def test_a_history_of_ungrounded_conclusions_forms_the_self_belief(self) -> None:
        belief = observe_evidence_habit([_record(0.0), _record(0.1), _record(0.0)])
        assert belief is not None
        assert belief.statement == INSUFFICIENT_EVIDENCE_HABIT
        assert belief.confidence.value > 0.0

    def test_a_healthy_history_does_not_support_the_self_belief(self) -> None:
        belief = observe_evidence_habit([_record(0.7), _record(0.8), _record(0.9)])
        assert belief is not None
        # Grounded episodes contradict the habit -> confidence stays at zero.
        assert belief.confidence == Confidence.none()

    def test_the_self_belief_is_revisable_provenance(self) -> None:
        # It must emerge from evidence, not be asserted (Vision §6).
        belief = observe_evidence_habit([_record(0.0), _record(0.0), _record(0.0)])
        assert belief is not None
        assert len(belief.evidence) == 3
        assert "no evidence" not in belief.explain().narrate()  # it is grounded

    def test_self_triggered_episodes_are_excluded(self) -> None:
        # Curiosity (self-triggered) episodes must not feed the habit they answer.
        history = [
            _record(0.0, origin=TriggerOrigin.COMPANION),
            _record(0.0, origin=TriggerOrigin.COMPANION),
            _record(0.0, origin=TriggerOrigin.CURIOSITY),
        ]
        # Only 2 companion episodes -> below the minimum -> no self-belief.
        assert observe_evidence_habit(history) is None


class TestObserveOverconfidence:
    def test_too_few_grounded_conclusions_yields_nothing(self) -> None:
        # Ungrounded episodes are not candidates for overconfidence.
        assert observe_overconfidence([_record(0.0), _record(0.0), _record(0.0)]) is None

    def test_grounded_conclusions_on_thin_evidence_form_the_self_belief(self) -> None:
        history = [_record(0.7, stability=0.0) for _ in range(3)]
        belief = observe_overconfidence(history)
        assert belief is not None
        assert belief.statement == OVERCONFIDENCE_HABIT
        assert belief.confidence.value > 0.0

    def test_grounded_conclusions_on_stable_evidence_do_not(self) -> None:
        history = [_record(0.7, stability=0.8) for _ in range(3)]
        belief = observe_overconfidence(history)
        assert belief is not None
        assert belief.confidence == Confidence.none()
