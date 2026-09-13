"""Tests for temporal reasoning — belief evolution and change detection."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.services.temporal_reasoning import (
    TemporalPattern,
    belief_snapshot_at,
    belief_timeline,
    detect_pattern,
    what_changed,
)
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.temporal_stability import TemporalStability


def _make_record(
    trigger: str,
    confidence: float,
    stability: float,
    recorded_at: datetime,
    *,
    decision: str = "concluded",
    episode_id: str | None = None,
    outcome: EpisodeState = EpisodeState.COMPLETED,
) -> EpisodeRecord:
    return EpisodeRecord(
        episode_id=episode_id or f"ep-{trigger}-{recorded_at.timestamp()}",
        trigger=trigger,
        decision=decision,
        working_belief_id="bel-1",
        outcome=outcome,
        conclusion_confidence=Confidence(confidence),
        conclusion_stability=TemporalStability(stability),
        origin=TriggerOrigin.COMPANION,
        kind=EpisodeKind.CONCLUSION,
        recorded_at=recorded_at,
    )


class TestBeliefTimeline:
    def test_returns_time_ordered_snapshots(self):
        t1 = datetime(2026, 1, 1, tzinfo=UTC)
        t2 = datetime(2026, 6, 1, tzinfo=UTC)
        t3 = datetime(2026, 9, 1, tzinfo=UTC)
        history = [
            _make_record("weather", 0.3, 0.2, t1, decision="rains sometimes"),
            _make_record("weather", 0.6, 0.5, t2, decision="often rains"),
            _make_record("weather", 0.8, 0.7, t3, decision="usually rains"),
        ]

        timeline = belief_timeline("weather", history)

        assert len(timeline) == 3
        assert timeline[0].confidence.value == 0.3
        assert timeline[1].confidence.value == 0.6
        assert timeline[2].confidence.value == 0.8

    def test_filters_by_subject(self):
        t1 = datetime(2026, 1, 1, tzinfo=UTC)
        history = [
            _make_record("weather", 0.3, 0.2, t1),
            _make_record("temperature", 0.7, 0.6, t1),
            _make_record("weather patterns", 0.5, 0.4, t1),
        ]

        timeline = belief_timeline("weather", history)

        assert len(timeline) == 2

    def test_excludes_self_triggered_episodes(self):
        t1 = datetime(2026, 1, 1, tzinfo=UTC)
        history = [
            _make_record("weather", 0.3, 0.2, t1),
            EpisodeRecord(
                episode_id="ep-self",
                trigger="weather",
                decision="curiosity",
                working_belief_id="bel-1",
                outcome=EpisodeState.COMPLETED,
                conclusion_confidence=Confidence(0.4),
                conclusion_stability=TemporalStability(0.3),
                origin=TriggerOrigin.CURIOSITY,
                kind=EpisodeKind.CONCLUSION,
                recorded_at=t1,
            ),
        ]

        timeline = belief_timeline("weather", history)

        assert len(timeline) == 1

    def test_empty_when_no_match(self):
        t1 = datetime(2026, 1, 1, tzinfo=UTC)
        history = [_make_record("temperature", 0.3, 0.2, t1)]

        timeline = belief_timeline("weather", history)

        assert len(timeline) == 0


class TestWhatChanged:
    def test_detects_confidence_increase(self):
        t1 = datetime(2026, 1, 1, tzinfo=UTC)
        t2 = datetime(2026, 6, 1, tzinfo=UTC)
        history = [
            _make_record("weather", 0.3, 0.2, t1),
            _make_record("weather", 0.7, 0.6, t2),
        ]

        changes = what_changed(
            "weather",
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 12, 31, tzinfo=UTC),
            history,
        )

        assert len(changes) == 1
        change = changes[0]
        assert change.confidence_delta == pytest.approx(0.4, abs=0.01)
        assert change.stability_delta == pytest.approx(0.4, abs=0.01)

    def test_ignores_small_changes(self):
        t1 = datetime(2026, 1, 1, tzinfo=UTC)
        t2 = datetime(2026, 6, 1, tzinfo=UTC)
        history = [
            _make_record("weather", 0.5, 0.4, t1),
            _make_record("weather", 0.55, 0.45, t2),
        ]

        changes = what_changed(
            "weather",
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 12, 31, tzinfo=UTC),
            history,
        )

        assert len(changes) == 0

    def test_filters_by_time_window(self):
        t1 = datetime(2026, 1, 1, tzinfo=UTC)
        t2 = datetime(2026, 6, 1, tzinfo=UTC)
        t3 = datetime(2026, 9, 1, tzinfo=UTC)
        history = [
            _make_record("weather", 0.3, 0.2, t1),
            _make_record("weather", 0.7, 0.6, t2),
            _make_record("weather", 0.9, 0.8, t3),
        ]

        # Only look at June-September
        changes = what_changed(
            "weather",
            datetime(2026, 5, 1, tzinfo=UTC),
            datetime(2026, 10, 1, tzinfo=UTC),
            history,
        )

        # Should only see the t2->t3 change (June to September)
        assert len(changes) == 1
        assert changes[0].earlier.recorded_at == t2
        assert changes[0].later.recorded_at == t3


class TestBeliefSnapshotAt:
    def test_returns_most_recent_before_time(self):
        t1 = datetime(2026, 1, 1, tzinfo=UTC)
        t2 = datetime(2026, 6, 1, tzinfo=UTC)
        t3 = datetime(2026, 9, 1, tzinfo=UTC)
        history = [
            _make_record("weather", 0.3, 0.2, t1),
            _make_record("weather", 0.6, 0.5, t2),
            _make_record("weather", 0.8, 0.7, t3),
        ]

        # Query at July — should return June snapshot
        snapshot = belief_snapshot_at(
            "weather",
            datetime(2026, 7, 1, tzinfo=UTC),
            history,
        )

        assert snapshot is not None
        assert snapshot.confidence.value == 0.6
        assert snapshot.recorded_at == t2

    def test_returns_none_when_no_history(self):
        snapshot = belief_snapshot_at(
            "weather",
            datetime(2026, 7, 1, tzinfo=UTC),
            [],
        )

        assert snapshot is None

    def test_returns_none_when_all_episodes_are_after_query_time(self):
        t1 = datetime(2026, 6, 1, tzinfo=UTC)
        history = [_make_record("weather", 0.3, 0.2, t1)]

        snapshot = belief_snapshot_at(
            "weather",
            datetime(2026, 1, 1, tzinfo=UTC),
            history,
        )

        assert snapshot is None


class TestDetectPattern:
    def test_detects_stable_preference(self):
        t1 = datetime(2026, 1, 1, tzinfo=UTC)
        t2 = datetime(2026, 6, 1, tzinfo=UTC)
        t3 = datetime(2026, 9, 1, tzinfo=UTC)
        history = [
            _make_record("weather", 0.5, 0.4, t1),
            _make_record("weather", 0.52, 0.41, t2),
            _make_record("weather", 0.48, 0.39, t3),
        ]

        result = detect_pattern("weather", history)

        assert result is not None
        assert result.pattern == TemporalPattern.STABLE
        assert result.episode_count == 3

    def test_detects_strengthening(self):
        t1 = datetime(2026, 1, 1, tzinfo=UTC)
        t2 = datetime(2026, 6, 1, tzinfo=UTC)
        t3 = datetime(2026, 9, 1, tzinfo=UTC)
        t4 = datetime(2026, 12, 1, tzinfo=UTC)
        history = [
            _make_record("weather", 0.3, 0.2, t1),
            _make_record("weather", 0.5, 0.3, t2),
            _make_record("weather", 0.7, 0.5, t3),
            _make_record("weather", 0.9, 0.7, t4),
        ]

        result = detect_pattern("weather", history)

        assert result is not None
        assert result.pattern == TemporalPattern.STRENGTHENING

    def test_detects_weakening(self):
        t1 = datetime(2026, 1, 1, tzinfo=UTC)
        t2 = datetime(2026, 6, 1, tzinfo=UTC)
        t3 = datetime(2026, 9, 1, tzinfo=UTC)
        t4 = datetime(2026, 12, 1, tzinfo=UTC)
        history = [
            _make_record("weather", 0.9, 0.7, t1),
            _make_record("weather", 0.7, 0.5, t2),
            _make_record("weather", 0.5, 0.3, t3),
            _make_record("weather", 0.3, 0.2, t4),
        ]

        result = detect_pattern("weather", history)

        assert result is not None
        assert result.pattern == TemporalPattern.WEAKENING

    def test_detects_recurring_contradiction(self):
        t1 = datetime(2026, 1, 1, tzinfo=UTC)
        t2 = datetime(2026, 3, 1, tzinfo=UTC)
        t3 = datetime(2026, 6, 1, tzinfo=UTC)
        t4 = datetime(2026, 9, 1, tzinfo=UTC)
        history = [
            _make_record("weather", 0.6, 0.5, t1, outcome=EpisodeState.COMPLETED),
            _make_record("weather", 0.4, 0.3, t2, outcome=EpisodeState.FAILED),
            _make_record("weather", 0.7, 0.6, t3, outcome=EpisodeState.COMPLETED),
            _make_record("weather", 0.3, 0.2, t4, outcome=EpisodeState.FAILED),
        ]

        result = detect_pattern("weather", history)

        assert result is not None
        assert result.pattern == TemporalPattern.RECURRING_CONTRADICTION

    def test_returns_none_with_insufficient_data(self):
        t1 = datetime(2026, 1, 1, tzinfo=UTC)
        t2 = datetime(2026, 6, 1, tzinfo=UTC)
        history = [
            _make_record("weather", 0.5, 0.4, t1),
            _make_record("weather", 0.6, 0.5, t2),
        ]

        result = detect_pattern("weather", history)

        assert result is None

    def test_returns_none_when_no_match(self):
        t1 = datetime(2026, 1, 1, tzinfo=UTC)
        history = [_make_record("temperature", 0.5, 0.4, t1)]

        result = detect_pattern("weather", history)

        assert result is None
