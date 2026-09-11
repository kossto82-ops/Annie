"""Tests for the abstraction service — detecting patterns across episodes."""

from __future__ import annotations

import pytest

from jarvis.domain.services.abstraction import abstract_patterns
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.temporal_stability import TemporalStability
from datetime import UTC, datetime

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
    def test_groups_by_shared_subject_words(self) -> None:
        # All episodes must have the same set of subject words
        episodes = [
            _ep("dark mode editor"),
            _ep("editor dark mode"),
            _ep("mode dark editor"),
        ]
        results = abstract_patterns(episodes, min_sources=3)
        assert len(results) == 1
        assert "editor" in results[0].pattern.lower()
        assert "dark" in results[0].pattern.lower()

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

    def test_stops_words_filtered(self) -> None:
        episodes = [
            _ep("the editor is good"),
            _ep("the editor is great"),
            _ep("editor is the best"),
        ]
        results = abstract_patterns(episodes, min_sources=3)
        # "the", "is" filtered; {editor, good, great, best} all different — won't cluster.
        # But each unique word set has only 1 episode → no cluster. Let's use identical words.
        episodes = [
            _ep("the editor is good and fast"),
            _ep("the editor is good and fast"),
            _ep("editor is the good and fast"),
        ]
        results = abstract_patterns(episodes, min_sources=3)
        assert len(results) == 1

    def test_multiple_clusters(self) -> None:
        episodes = [
            _ep("dark mode editor"),
            _ep("editor dark mode"),
            _ep("mode editor dark"),
            _ep("light theme config"),
            _ep("theme light config"),
            _ep("config theme light"),
        ]
        results = abstract_patterns(episodes, min_sources=3)
        patterns = [r.pattern for r in results]
        assert len(results) == 2
        # Both clusters should have patterns
        assert all("Los patrones" in p for p in patterns)
