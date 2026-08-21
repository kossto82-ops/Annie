"""Tests for per-episode decision provenance (Vision §26)."""

from __future__ import annotations

from jarvis import Jarvis
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.events.belief_events import (
    BeliefStrengthened,
    ContradictionDetected,
)
from jarvis.domain.events.episode_events import EpisodeCompleted, EpisodeStarted
from jarvis.domain.events.evidence_events import EvidenceAdded
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence


def _ev(weight: float, *, supports: bool = True) -> Evidence:
    return Evidence(
        content="an observation",
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(weight),
        supports=supports,
    )


class TestTrace:
    def test_a_grounded_episode_has_an_ordered_trace(self) -> None:
        jarvis = Jarvis()
        episode = jarvis.think("does my companion prefer simplicity?", evidence=[_ev(0.9)])
        trace = jarvis.trace_of(episode)
        kinds = [type(e) for e in trace]
        assert kinds[0] is EpisodeStarted
        assert kinds[-1] is EpisodeCompleted
        assert EvidenceAdded in kinds
        assert BeliefStrengthened in kinds

    def test_a_contested_episode_records_the_contradiction(self) -> None:
        jarvis = Jarvis()
        episode = jarvis.think(
            "does my companion prefer simplicity?",
            evidence=[_ev(0.9), _ev(0.9, supports=False)],
        )
        kinds = [type(e) for e in jarvis.trace_of(episode)]
        assert ContradictionDetected in kinds

    def test_the_trace_belongs_to_exactly_one_episode(self) -> None:
        jarvis = Jarvis()
        first = jarvis.think("question one", evidence=[_ev(0.9)])
        second = jarvis.think("question two", evidence=[_ev(0.9)])
        assert all(e.correlation_id == first.id for e in jarvis.trace_of(first))
        assert all(e.correlation_id == second.id for e in jarvis.trace_of(second))
        assert jarvis.trace_of(first) != jarvis.trace_of(second)

    def test_an_ungrounded_episode_traces_start_and_completion(self) -> None:
        jarvis = Jarvis()
        episode = jarvis.think("a question with no evidence")
        kinds = [type(e) for e in jarvis.trace_of(episode)]
        assert kinds == [EpisodeStarted, EpisodeCompleted]
