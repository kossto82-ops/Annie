"""Behavioural tests for the CognitiveEpisode aggregate."""

from __future__ import annotations

import pytest

from jarvis.domain.aggregates.cognitive_episode import (
    CognitiveEpisode,
    InvalidStateTransition,
)
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.events.belief_events import BeliefStrengthened
from jarvis.domain.events.episode_events import EpisodeCompleted, EpisodeStarted
from jarvis.domain.events.evidence_events import EvidenceAdded
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence


def _ev(weight: float = 0.7) -> Evidence:
    return Evidence(
        content="observation",
        source=EvidenceSource.DIRECT_OBSERVATION,
        weight=Confidence(weight),
    )


class TestCreation:
    def test_starts_in_created_state(self) -> None:
        assert CognitiveEpisode(trigger="t").state == EpisodeState.CREATED

    def test_records_episode_started_on_creation(self) -> None:
        episode = CognitiveEpisode(trigger="t")
        events = episode.pull_events()
        assert len(events) == 1
        assert isinstance(events[0], EpisodeStarted)
        assert events[0].trigger == "t"
        assert events[0].correlation_id == episode.id

    @pytest.mark.parametrize("trigger", ["", "   "])
    def test_rejects_empty_trigger(self, trigger: str) -> None:
        with pytest.raises(ValueError):
            CognitiveEpisode(trigger=trigger)


class TestTransitions:
    def test_full_legal_lifecycle(self) -> None:
        episode = CognitiveEpisode(trigger="t")
        episode.begin_reasoning()
        assert episode.state == EpisodeState.REASONING
        episode.begin_reflecting()
        assert episode.state == EpisodeState.REFLECTING
        episode.begin_deciding()
        assert episode.state == EpisodeState.DECIDING
        episode.complete("result")
        assert episode.state == EpisodeState.COMPLETED
        assert episode.result == "result"

    def test_illegal_transition_is_rejected(self) -> None:
        episode = CognitiveEpisode(trigger="t")
        # Cannot skip straight to deciding from CREATED.
        with pytest.raises(InvalidStateTransition):
            episode.begin_deciding()

    def test_cannot_complete_before_deciding(self) -> None:
        episode = CognitiveEpisode(trigger="t")
        episode.begin_reasoning()
        with pytest.raises(InvalidStateTransition):
            episode.complete("too early")


class TestCompletion:
    def _advance_to_deciding(self) -> CognitiveEpisode:
        episode = CognitiveEpisode(trigger="t")
        episode.begin_reasoning()
        episode.begin_reflecting()
        episode.begin_deciding()
        return episode

    def test_records_episode_completed(self) -> None:
        episode = self._advance_to_deciding()
        episode.pull_events()  # discard EpisodeStarted
        episode.complete("answer")
        events = episode.pull_events()
        assert len(events) == 1
        assert isinstance(events[0], EpisodeCompleted)
        assert events[0].result == "answer"
        assert events[0].correlation_id == episode.id


class TestFailure:
    def test_can_fail_from_non_terminal_state(self) -> None:
        episode = CognitiveEpisode(trigger="t")
        episode.begin_reasoning()
        episode.fail("boom")
        assert episode.state == EpisodeState.FAILED
        assert episode.result is None

    def test_cannot_fail_a_completed_episode(self) -> None:
        episode = CognitiveEpisode(trigger="t")
        episode.begin_reasoning()
        episode.begin_reflecting()
        episode.begin_deciding()
        episode.complete("done")
        with pytest.raises(InvalidStateTransition):
            episode.fail("too late")


class TestWorkingBelief:
    def test_has_no_working_belief_until_formed(self) -> None:
        assert CognitiveEpisode(trigger="t").working_belief is None

    def test_form_working_belief_attaches_it(self) -> None:
        episode = CognitiveEpisode(trigger="t")
        episode.begin_reasoning()
        belief = episode.form_working_belief("a conclusion")
        assert episode.working_belief is belief

    def test_observe_requires_a_working_belief(self) -> None:
        episode = CognitiveEpisode(trigger="t")
        with pytest.raises(ValueError):
            episode.observe(_ev())

    def test_observing_evidence_grounds_the_belief(self) -> None:
        episode = CognitiveEpisode(trigger="t")
        episode.begin_reasoning()
        episode.form_working_belief("a conclusion")
        episode.observe(_ev())
        assert episode.working_belief is not None
        assert episode.working_belief.confidence.value > 0.0

    def test_explain_is_none_before_a_belief_is_formed(self) -> None:
        assert CognitiveEpisode(trigger="t").explain() is None

    def test_explain_narrates_the_conclusion_once_grounded(self) -> None:
        episode = CognitiveEpisode(trigger="t")
        episode.begin_reasoning()
        episode.form_working_belief("a conclusion")
        episode.observe(_ev())
        explanation = episode.explain()
        assert explanation is not None
        assert "a conclusion" in explanation.narrate()

    def test_cannot_form_a_belief_after_completion(self) -> None:
        episode = CognitiveEpisode(trigger="t")
        episode.begin_reasoning()
        episode.begin_reflecting()
        episode.begin_deciding()
        episode.complete("done")
        with pytest.raises(InvalidStateTransition):
            episode.form_working_belief("too late")


class TestEventBuffer:
    def test_pull_events_clears_the_buffer(self) -> None:
        episode = CognitiveEpisode(trigger="t")
        assert episode.pull_events()  # EpisodeStarted present
        assert episode.pull_events() == []  # cleared

    def test_pull_events_includes_belief_events(self) -> None:
        episode = CognitiveEpisode(trigger="t")
        episode.begin_reasoning()
        episode.form_working_belief("a conclusion")
        episode.pull_events()  # discard EpisodeStarted
        episode.observe(_ev())
        kinds = [type(e) for e in episode.pull_events()]
        assert EvidenceAdded in kinds
        assert BeliefStrengthened in kinds
