"""Tests for CognitiveKnobs: the runtime-tunable cognition thresholds.

They were module constants owned by the executive and the Jarvis root, mirrored
in the domain services to avoid importing the application layer; making them one
validated value object (CognitiveKnobs) gives every consumer a single source of
truth and keeps them live-tunable from the command center (Increment 141).
"""

from __future__ import annotations

import pytest

from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.services.capability_gap_observation import detect_capability_gaps
from jarvis.domain.services.self_observation import observe_overconfidence
from jarvis.domain.value_objects.cognitive_knobs import CognitiveKnobs
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.temporal_stability import TemporalStability
from jarvis.jarvis import Jarvis


class TestCognitiveKnobsDefaultsAndValidation:
    def test_defaults_preserve_the_historical_constants(self) -> None:
        knobs = CognitiveKnobs()
        assert knobs.grounded_confidence == 0.5
        assert knobs.insight_confidence == 0.5
        assert knobs.max_goal_reflections == 3

    def test_a_confidence_knob_outside_unit_interval_is_rejected(self) -> None:
        for bad in (-0.1, 1.01):
            with pytest.raises(ValueError):
                CognitiveKnobs(grounded_confidence=bad)
        with pytest.raises(ValueError):
            CognitiveKnobs(insight_confidence=1.5)

    def test_goal_reflections_must_be_a_positive_top(self) -> None:
        with pytest.raises(ValueError):
            CognitiveKnobs(max_goal_reflections=0)


def _record(confidence: float, trigger: str = "q") -> EpisodeRecord:
    return EpisodeRecord(
        episode_id="e",
        trigger=trigger,
        decision="d",
        working_belief_id="b",
        outcome=EpisodeState.COMPLETED,
        conclusion_confidence=Confidence(confidence),
        conclusion_stability=TemporalStability(0.5),
        origin=TriggerOrigin.COMPANION,
        kind=EpisodeKind.CONCLUSION,
    )


class TestKnobsReachTheDomainObservers:
    def test_raising_the_grounded_knob_reclassifies_a_conclusion(self) -> None:
        # At the default 0.5 a 0.6 conclusion is grounded -> overconfidence is
        # judged. Raise the knob above 0.6 and the same history reads as
        # ungrounded -> there is nothing to judge (honest "not yet").
        history = [_record(0.6) for _ in range(3)]
        assert observe_overconfidence(history) is not None
        assert (
            observe_overconfidence(history, knobs=CognitiveKnobs(grounded_confidence=0.9))
            is None
        )

    def test_lowering_the_grounded_knob_stops_treating_answers_as_gaps(self) -> None:
        # Two 0.3-confidence conclusions are failures at the default 0.5 (a
        # recurring gap); with the knob at 0.1 they read as grounded answers.
        history = [
            _record(0.3, trigger="what is a quokka"),
            _record(0.3, trigger="are quokkas real"),
        ]
        assert len(detect_capability_gaps(history)) == 1
        assert (
            detect_capability_gaps(history, knobs=CognitiveKnobs(grounded_confidence=0.1))
            == ()
        )


class TestKnobsReachTheExecutiveAndRuntimeSwap:
    def test_the_grounded_knob_steers_the_decision_text(self) -> None:
        # Two supporting pieces at 0.9 -> confidence 1.8 / 2.8 ~ 0.64: grounded
        # at the default 0.5, tentatively below a 0.9 knob.
        pieces = [
            Evidence(
                content="observation one",
                source=EvidenceSource.SYSTEM_OBSERVATION,
                weight=Confidence(0.9),
            ),
            Evidence(
                content="observation two",
                source=EvidenceSource.SYSTEM_OBSERVATION,
                weight=Confidence(0.9),
            ),
        ]
        default = Jarvis()
        grounded_default = default.think("is the plan sound?", evidence=pieces)
        assert grounded_default.result is not None
        assert "Concluded about" in grounded_default.result

        strict = Jarvis(cognitive_knobs=CognitiveKnobs(grounded_confidence=0.9))
        tentative = strict.think("is the plan sound?", evidence=pieces)
        assert tentative.result is not None
        assert "Tentative" in tentative.result

    def test_set_knobs_swaps_every_gate_at_runtime(self) -> None:
        jarvis = Jarvis()
        assert jarvis.knobs() == CognitiveKnobs()
        jarvis.set_knobs(CognitiveKnobs(grounded_confidence=0.8, max_goal_reflections=5))
        assert jarvis.knobs().grounded_confidence == 0.8
        assert jarvis.knobs().max_goal_reflections == 5
        # The executive reads the same object, so the swap reaches cognition.
        episode = jarvis.think("anything at all")
        assert episode.result is not None