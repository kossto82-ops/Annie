"""Tests for temporal recall and temporal belief queries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from jarvis.domain.aggregates.companion_model import CompanionModel
from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.temporal_stability import TemporalStability
from jarvis.infrastructure.in_memory_belief_store import InMemoryBeliefStore
from jarvis.infrastructure.in_memory_episode_store import InMemoryEpisodeStore
from jarvis.infrastructure.lexical_memory_retriever import LexicalMemoryRetriever

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
_JAN_1 = datetime(2026, 1, 1, tzinfo=UTC)
_JAN_15 = datetime(2026, 1, 15, tzinfo=UTC)
_FEB_1 = datetime(2026, 2, 1, tzinfo=UTC)
_FEB_15 = datetime(2026, 2, 15, tzinfo=UTC)
_MAR_1 = datetime(2026, 3, 1, tzinfo=UTC)


def _ep(trigger: str, at: datetime | None = None) -> EpisodeRecord:
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
        recorded_at=at or _EPOCH,
    )


def _belief(statement: str, formed_at: datetime | None = None) -> Belief:
    b = Belief(
        statement=statement,
        formed_at=formed_at or _EPOCH,
    )
    b.add_evidence(
        Evidence(
            content="observation",
            source=EvidenceSource.DIRECT_OBSERVATION,
            weight=Confidence(0.5),
            supports=True,
        )
    )
    return b


class TestTemporalEpisodeQueries:
    def test_history_in_range(self) -> None:
        store = InMemoryEpisodeStore()
        store.record(_ep("jan topic", at=_JAN_15))
        store.record(_ep("feb topic", at=_FEB_15))
        store.record(_ep("mar topic", at=_MAR_1))
        results = store.history_in_range(_FEB_1, _MAR_1)
        assert len(results) == 2
        assert all(_FEB_1 <= r.recorded_at <= _MAR_1 for r in results)

    def test_history_about(self) -> None:
        store = InMemoryEpisodeStore()
        store.record(_ep("dark mode config", at=_JAN_15))
        store.record(_ep("dark mode toggle", at=_FEB_15))
        store.record(_ep("light theme", at=_MAR_1))
        results = store.history_about("dark")
        assert len(results) == 2

    def test_history_about_with_time_range(self) -> None:
        store = InMemoryEpisodeStore()
        store.record(_ep("dark mode config", at=_JAN_15))
        store.record(_ep("dark mode toggle", at=_FEB_15))
        store.record(_ep("dark theme", at=_MAR_1))
        results = store.history_about("dark", start=_FEB_1, end=_MAR_1)
        assert len(results) == 2
        assert all(_FEB_1 <= r.recorded_at <= _MAR_1 for r in results)


class TestTemporalBeliefQueries:
    def test_beliefs_formed_between(self) -> None:
        store = InMemoryBeliefStore()
        store.save(_belief("jan belief", formed_at=_JAN_15))
        store.save(_belief("feb belief", formed_at=_FEB_15))
        store.save(_belief("mar belief", formed_at=_MAR_1))
        results = store.beliefs_formed_between(_FEB_1, _MAR_1)
        assert len(results) == 2
        assert all(_FEB_1 <= b.formed_at <= _MAR_1 for b in results)

    def test_beliefs_about(self) -> None:
        store = InMemoryBeliefStore()
        store.save(_belief("dark mode is preferred", formed_at=_JAN_15))
        store.save(_belief("dark theme works well", formed_at=_FEB_15))
        store.save(_belief("light theme is nice", formed_at=_MAR_1))
        results = store.beliefs_about("dark")
        assert len(results) == 2


class TestTemporalRecall:
    def test_recall_with_since(self) -> None:
        beliefs = InMemoryBeliefStore()
        beliefs.save(_belief("dark mode is preferred", formed_at=_JAN_15))
        episodes = InMemoryEpisodeStore()
        episodes.record(_ep("dark mode config", at=_FEB_15))
        companion_beliefs = InMemoryBeliefStore()
        companion = CompanionModel(companion_beliefs)
        goals = InMemoryBeliefStore()
        retriever = LexicalMemoryRetriever(beliefs, episodes, companion, goals)
        results = retriever.recall("dark mode", since=_FEB_1)
        assert len(results) >= 1
        assert all(
            r.observed_at is not None and r.observed_at >= _FEB_1 for r in results
        )

    def test_recall_with_until(self) -> None:
        beliefs = InMemoryBeliefStore()
        beliefs.save(_belief("dark mode is preferred", formed_at=_JAN_15))
        episodes = InMemoryEpisodeStore()
        episodes.record(_ep("dark mode config", at=_FEB_15))
        companion_beliefs = InMemoryBeliefStore()
        companion = CompanionModel(companion_beliefs)
        goals = InMemoryBeliefStore()
        retriever = LexicalMemoryRetriever(beliefs, episodes, companion, goals)
        results = retriever.recall("dark mode", until=_FEB_1)
        assert len(results) >= 1
        assert all(
            r.observed_at is not None and r.observed_at <= _FEB_1 for r in results
        )

    def test_recall_with_time_range(self) -> None:
        beliefs = InMemoryBeliefStore()
        beliefs.save(_belief("dark mode is preferred", formed_at=_JAN_15))
        episodes = InMemoryEpisodeStore()
        episodes.record(_ep("dark mode config", at=_FEB_15))
        companion_beliefs = InMemoryBeliefStore()
        companion = CompanionModel(companion_beliefs)
        goals = InMemoryBeliefStore()
        retriever = LexicalMemoryRetriever(beliefs, episodes, companion, goals)
        results = retriever.recall("dark mode", since=_JAN_1, until=_MAR_1)
        assert len(results) >= 1
        assert all(
            _JAN_1 <= r.observed_at <= _MAR_1
            for r in results
            if r.observed_at is not None
        )

    def test_recalled_memory_has_observed_at(self) -> None:
        beliefs = InMemoryBeliefStore()
        beliefs.save(_belief("dark mode is preferred", formed_at=_JAN_15))
        episodes = InMemoryEpisodeStore()
        companion_beliefs = InMemoryBeliefStore()
        companion = CompanionModel(companion_beliefs)
        goals = InMemoryBeliefStore()
        retriever = LexicalMemoryRetriever(beliefs, episodes, companion, goals)
        results = retriever.recall("dark mode")
        assert len(results) == 1
        assert results[0].observed_at == _JAN_15
