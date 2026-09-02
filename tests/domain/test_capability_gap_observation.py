"""Behavioural tests for capability-gap observation over episode history
(Odysseus, Vision §34 — Jarvis noticing what it keeps failing to answer)."""

from __future__ import annotations

from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.services.capability_gap_observation import (
    CapabilityGap,
    detect_capability_gaps,
)
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.temporal_stability import TemporalStability


def _record(
    trigger: str,
    confidence: float,
    origin: TriggerOrigin = TriggerOrigin.COMPANION,
) -> EpisodeRecord:
    return EpisodeRecord(
        episode_id="e",
        trigger=trigger,
        decision="d",
        working_belief_id="b",
        outcome=EpisodeState.COMPLETED,
        conclusion_confidence=Confidence(confidence),
        conclusion_stability=TemporalStability(0.5),
        origin=origin,
        kind=EpisodeKind.CONCLUSION,
    )


class TestDetectCapabilityGaps:
    def test_too_few_failed_episodes_yields_no_gap(self) -> None:
        # One failure is not yet a recurring gap.
        history = [_record("what is a quokka", 0.1)]
        assert detect_capability_gaps(history) == ()

    def test_recurring_failure_on_one_subject_yields_a_gap(self) -> None:
        history = [
            _record("what is a quokka", 0.1),
            _record("are quokkas real", 0.2),
        ]
        gaps = detect_capability_gaps(history)
        assert len(gaps) == 1
        assert gaps[0].subject == "quokka"
        assert len(gaps[0].episodes) == 2

    def test_grounded_episodes_do_not_feed_the_gap(self) -> None:
        # A confidently-concluded episode is an answer, not a gap.
        history = [
            _record("what is a quokka", 0.1),
            _record("are quokkas real", 0.3),
            _record("name another marsupial", 0.8),
        ]
        gaps = detect_capability_gaps(history)
        assert len(gaps) == 1  # only the two ungrounded 'quokka' episodes
        assert gaps[0].subject == "quokka"

    def test_distinct_subjects_form_distinct_gaps(self) -> None:
        history = [
            _record("what is a quokka", 0.0),
            _record("are quokkas real", 0.0),
            _record("who is the minister", 0.0),
            _record("is the minister in", 0.0),
        ]
        gaps = detect_capability_gaps(history)
        subjects = {gap.subject for gap in gaps}
        assert subjects == {"quokka", "minister"}

    def test_gaps_are_strongest_first(self) -> None:
        # quokka fails three times, flag twice -> quokka first.
        history = [
            _record("what is a quokka", 0.0),
            _record("are quokkas real", 0.0),
            _record("where do quokkas live", 0.0),
            _record("what is a flag", 0.0),
            _record("what does a flag look like", 0.0),
        ]
        gaps = detect_capability_gaps(history)
        assert [gap.subject for gap in gaps] == ["quokka", "flag"]

    def test_curiosity_failures_also_feed_the_gap(self) -> None:
        # Self-triggered failure to answer is still a gap (Vision §34).
        history = [
            _record("what is a quokka", 0.0),
            _record("what is a quokka", 0.0, origin=TriggerOrigin.CURIOSITY),
        ]
        gaps = detect_capability_gaps(history)
        assert len(gaps) == 1
        assert gaps[0].subject == "quokka"
        assert len(gaps[0].episodes) == 2  # curiosity failure is evidence too

    def test_one_episode_counting_is_a_gap(self) -> None:
        # When the same content word appears in both failed episodes, the gap is
        # counted from how many episodes failed about it.
        history = [
            _record("what is a quokka", 0.0),
            _record("are quokkas real", 0.0),
        ]
        gap = detect_capability_gaps(history)[0]
        assert isinstance(gap, CapabilityGap)
        assert gap.subject == "quokka"
        assert len(gap.episodes) == 2
