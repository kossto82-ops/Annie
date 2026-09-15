"""Tests for the abstraction service — detecting patterns across episodes."""

from __future__ import annotations

from datetime import UTC, datetime

from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.services.abstraction import abstract_patterns
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.temporal_stability import TemporalStability

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def _ep(trigger: str) -> EpisodeRecord:
    return EpisodeRecord(
        episode_id="test",
        trigger=trigger,
        decision="test",
        working_belief_id="test",
        outcome=EpisodeState.COMPLETED,
        conclusion_confidence=Confidence(0.5),
        conclusion_stability=TemporalStability(0.5),
        origin=TriggerOrigin.COMPANION,
        kind=EpisodeKind.CONCLUSION,
    )


class TestClusterEpisodes:
    def test_groups_by_shared_concepts(self) -> None:
        # Lexically distinct but conceptually identical episodes cluster: all
        # three carry the same conceptual signature {DELIVER, FAIL, TIME}.
        episodes = [
            _ep("the supplier failed to deliver on time"),
            _ep("another vendor failed to deliver by the deadline"),
            _ep("a contractor missed its delivery deadline"),
        ]
        results = abstract_patterns(episodes, min_sources=3)
        assert len(results) == 1
        pattern = results[0].pattern
        assert "FAIL" in pattern
        assert "DELIVER" in pattern
        assert "TIME" in pattern

    def test_requires_min_sources(self) -> None:
        episodes = [
            _ep("one unique topic A"),
            _ep("another unique topic B"),
        ]
        results = abstract_patterns(episodes, min_sources=3)
        assert len(results) == 0

    def test_empty_episodes(self) -> None:
        results = abstract_patterns([], min_sources=3)
        assert len(results) == 0

    def test_stop_words_do_not_form_a_cluster(self) -> None:
        # Filler words are no concepts: episodes sharing only them have empty
        # signatures, so no pattern can be abstracted from them.
        episodes = [
            _ep("the editor is good"),
            _ep("the editor is great"),
            _ep("editor is the best"),
            _ep("the best editor of them all"),
        ]
        results = abstract_patterns(episodes, min_sources=3)
        assert len(results) == 0

    def test_multiple_clusters(self) -> None:
        # Two conceptually disjoint groups abstract to two stable patterns.
        # (A carries DELIVER+FAIL, B carries only PROMISE -- no shared concept.)
        episodes = [
            _ep("the supplier failed to deliver"),
            _ep("a vendor failed to deliver"),
            _ep("another contractor failed to deliver"),
            _ep("the crew promised the work"),
            _ep("the vendor pledged the result"),
            _ep("the team committed to the effort"),
        ]
        results = abstract_patterns(episodes, min_sources=3)
        patterns = [r.pattern for r in results]
        assert len(results) == 2
        assert any("FAIL" in p and "DELIVER" in p for p in patterns)
        assert any("PROMISE" in p for p in patterns)
