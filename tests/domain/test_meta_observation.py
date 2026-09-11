"""Tests for second-order reflection: meta-observation and meta-knowledge."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from jarvis.domain.entities.meta_knowledge import MetaKnowledge
from jarvis.domain.enums.meta_knowledge_kind import MetaKnowledgeKind
from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.services.meta_observation import (
    observe_reasoning_effectiveness,
    observe_retrieval_quality,
    observe_attention_allocation,
)
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.recalled_memory import RecalledMemory
from jarvis.domain.enums.memory_kind import MemoryKind
from jarvis.domain.value_objects.temporal_stability import TemporalStability

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def _ep(
    trigger: str = "test",
    kind: EpisodeKind = EpisodeKind.CONCLUSION,
    confidence: float = 0.5,
) -> EpisodeRecord:
    return EpisodeRecord(
        episode_id="test",
        trigger=trigger,
        decision="test",
        working_belief_id="test",
        outcome=EpisodeState.COMPLETED,
        conclusion_confidence=Confidence(confidence),
        conclusion_stability=TemporalStability(0.5),
        origin=TriggerOrigin.COMPANION,
        kind=kind,
    )


def _recalled(
    content: str = "test memory",
    relevance: float = 0.5,
) -> RecalledMemory:
    return RecalledMemory(
        content=content,
        kind=MemoryKind.WORLD_BELIEF,
        provenance="test",
        relevance=relevance,
    )


# --- MetaKnowledge entity tests ---

class TestMetaKnowledge:
    def test_requires_kind_and_statement(self) -> None:
        mk = MetaKnowledge(
            kind=MetaKnowledgeKind.REASONING_STRATEGY,
            statement="I reason better with think",
        )
        assert mk.kind == MetaKnowledgeKind.REASONING_STRATEGY
        assert "reason better" in mk.statement

    def test_confidence_none_without_evidence(self) -> None:
        mk = MetaKnowledge(
            kind=MetaKnowledgeKind.REASONING_STRATEGY,
            statement="test",
        )
        assert mk.confidence == Confidence.none()

    def test_confidence_increases_with_evidence(self) -> None:
        mk = MetaKnowledge(
            kind=MetaKnowledgeKind.REASONING_STRATEGY,
            statement="test",
        )
        mk.add_evidence(
            Evidence(
                content="observation",
                source=EvidenceSource.SYSTEM_OBSERVATION,
                weight=Confidence(0.6),
                supports=True,
            )
        )
        assert mk.confidence.value > 0.0


# --- observe_reasoning_effectiveness tests ---

class TestObserveReasoningEffectiveness:
    def test_returns_none_with_insufficient_history(self) -> None:
        episodes = [_ep(kind=EpisodeKind.CONCLUSION) for _ in range(3)]
        result = observe_reasoning_effectiveness(episodes)
        assert result is None

    def test_returns_none_with_balanced_performance(self) -> None:
        episodes = [
            _ep(kind=EpisodeKind.CONCLUSION, confidence=0.6) for _ in range(8)
        ] + [
            _ep(kind=EpisodeKind.DELIBERATION, confidence=0.6) for _ in range(8)
        ]
        result = observe_reasoning_effectiveness(episodes)
        assert result is None

    def test_detects_conclusions_better_than_deliberations(self) -> None:
        episodes = [
            _ep(kind=EpisodeKind.CONCLUSION, confidence=0.8) for _ in range(8)
        ] + [
            _ep(kind=EpisodeKind.DELIBERATION, confidence=0.4) for _ in range(8)
        ]
        result = observe_reasoning_effectiveness(episodes)
        assert result is not None
        assert result.kind == MetaKnowledgeKind.REASONING_STRATEGY
        assert "conclusions" in result.statement.lower()

    def test_detects_deliberations_better_than_conclusions(self) -> None:
        episodes = [
            _ep(kind=EpisodeKind.CONCLUSION, confidence=0.3) for _ in range(8)
        ] + [
            _ep(kind=EpisodeKind.DELIBERATION, confidence=0.8) for _ in range(8)
        ]
        result = observe_reasoning_effectiveness(episodes)
        assert result is not None
        assert "deliberations" in result.statement.lower()


# --- observe_retrieval_quality tests ---

class TestObserveRetrievalQuality:
    def test_returns_none_with_insufficient_data(self) -> None:
        result = observe_retrieval_quality([], [_recalled()])
        assert result is None

    def test_returns_none_with_no_recalled(self) -> None:
        episodes = [_ep() for _ in range(5)]
        result = observe_retrieval_quality(episodes, [])
        assert result is None

    def test_detects_good_retrieval(self) -> None:
        episodes = [_ep(confidence=0.8) for _ in range(8)]
        recalled = [_recalled(relevance=0.8) for _ in range(5)]
        result = observe_retrieval_quality(episodes, recalled)
        assert result is not None
        assert result.kind == MetaKnowledgeKind.RETRIEVAL_QUALITY
        assert "relevant" in result.statement.lower()

    def test_detects_noisy_retrieval(self) -> None:
        episodes = [_ep(confidence=0.8) for _ in range(8)]
        recalled = [_recalled(relevance=0.2) for _ in range(5)]
        result = observe_retrieval_quality(episodes, recalled)
        assert result is not None
        assert "noisy" in result.statement.lower()


# --- observe_attention_allocation tests ---

class TestObserveAttentionAllocation:
    def test_returns_none_with_insufficient_history(self) -> None:
        result = observe_attention_allocation([])
        assert result is None

    def test_detects_insufficient_attention(self) -> None:
        episodes = [_ep(confidence=0.2) for _ in range(8)]
        result = observe_attention_allocation(episodes)
        assert result is not None
        assert result.kind == MetaKnowledgeKind.ATTENTION_PATTERN
        assert "insufficient" in result.statement.lower()

    def test_detects_appropriate_attention(self) -> None:
        episodes = [_ep(confidence=0.8) for _ in range(8)]
        result = observe_attention_allocation(episodes)
        assert result is not None
        assert "appropriately" in result.statement.lower()

    def test_returns_none_with_mixed_performance(self) -> None:
        # Exactly 50% grounded means ungrounded_ratio = 0.5, which is between 0.3 and 0.7
        episodes = [_ep(confidence=0.6) for _ in range(4)] + [_ep(confidence=0.3) for _ in range(4)]
        result = observe_attention_allocation(episodes)
        assert result is None
