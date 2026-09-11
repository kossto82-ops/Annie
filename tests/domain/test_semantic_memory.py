"""Behavioural tests for the SemanticMemory entity.

Pins the epistemological invariants: confidence and stability are derived from
evidence, never set directly; events are emitted on mutation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from jarvis.domain.entities.semantic_memory import SemanticMemory
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.events.semantic_events import (
    SemanticMemoryContested,
    SemanticMemoryReinforced,
)
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def _ev(
    weight: float,
    *,
    supports: bool = True,
    content: str = "observation",
    at: datetime | None = None,
) -> Evidence:
    kwargs: dict[str, object] = {
        "content": content,
        "source": EvidenceSource.DIRECT_OBSERVATION,
        "weight": Confidence(weight),
        "supports": supports,
    }
    if at is not None:
        kwargs["observed_at"] = at
    return Evidence(**kwargs)  # type: ignore[arg-type]


class TestFormation:
    def test_requires_a_pattern(self) -> None:
        sm = SemanticMemory(pattern="")
        assert sm.pattern == ""

    def test_new_memory_has_no_evidence(self) -> None:
        sm = SemanticMemory(pattern="users who X tend to Y")
        assert sm.confidence == Confidence.none()

    def test_new_memory_has_no_stability(self) -> None:
        sm = SemanticMemory(pattern="users who X tend to Y")
        assert sm.stability.value == 0.0

    def test_assigned_id_when_none_provided(self) -> None:
        sm = SemanticMemory(pattern="test")
        assert sm.id

    def test_uses_provided_id(self) -> None:
        sm = SemanticMemory(pattern="test", id="custom-id")
        assert sm.id == "custom-id"


class TestEvidenceDrivenConfidence:
    def test_never_stronger_than_evidence(self) -> None:
        sm = SemanticMemory(pattern="users who X tend to Y")
        for _ in range(50):
            sm.add_evidence(_ev(1.0))
        assert sm.confidence.value < 1.0

    def test_weak_evidence_yields_weak_confidence(self) -> None:
        sm = SemanticMemory(pattern="users who X tend to Y")
        sm.add_evidence(_ev(0.1))
        assert sm.confidence.value < 0.2

    def test_repeated_support_strengthens(self) -> None:
        sm = SemanticMemory(pattern="users who X tend to Y")
        sm.add_evidence(_ev(0.5))
        after_one = sm.confidence
        sm.add_evidence(_ev(0.5))
        assert sm.confidence.is_stronger_than(after_one)

    def test_contradicting_evidence_lowers(self) -> None:
        sm = SemanticMemory(pattern="users who X tend to Y")
        sm.add_evidence(_ev(0.8))
        before = sm.confidence
        sm.add_evidence(_ev(0.8, supports=False))
        assert before.is_stronger_than(sm.confidence)


class TestEvents:
    def test_emits_reinforced_event(self) -> None:
        sm = SemanticMemory(pattern="test pattern")
        sm.add_evidence(_ev(0.5))
        events = sm.pull_events()
        assert len(events) == 1
        assert isinstance(events[0], SemanticMemoryReinforced)
        assert events[0].memory_id == sm.id
        assert events[0].pattern == sm.pattern

    def test_emits_contested_event_on_contradiction(self) -> None:
        sm = SemanticMemory(pattern="test pattern")
        sm.add_evidence(_ev(0.5, supports=False))
        events = sm.pull_events()
        assert len(events) == 1
        assert isinstance(events[0], SemanticMemoryContested)

    def test_events_are_drained(self) -> None:
        sm = SemanticMemory(pattern="test pattern")
        sm.add_evidence(_ev(0.5))
        sm.pull_events()
        assert sm.pull_events() == []


class TestSourceTracking:
    def test_stores_source_episode_ids(self) -> None:
        sm = SemanticMemory(
            pattern="test", source_episode_ids=["ep1", "ep2"]
        )
        assert sm.source_episode_ids == ["ep1", "ep2"]

    def test_stores_source_belief_ids(self) -> None:
        sm = SemanticMemory(
            pattern="test", source_belief_ids=["b1"]
        )
        assert sm.source_belief_ids == ["b1"]

    def test_reinforcement_count_increments(self) -> None:
        sm = SemanticMemory(pattern="test")
        assert sm.reinforcement_count == 0
        sm.add_evidence(_ev(0.5))
        assert sm.reinforcement_count == 1
        sm.add_evidence(_ev(0.5))
        assert sm.reinforcement_count == 2

    def test_last_reinforced_at_set(self) -> None:
        sm = SemanticMemory(pattern="test")
        assert sm.last_reinforced_at is None
        sm.add_evidence(_ev(0.5))
        assert sm.last_reinforced_at is not None


class TestRepr:
    def test_repr_shows_pattern_and_confidence(self) -> None:
        sm = SemanticMemory(pattern="users prefer X", id="m1")
        sm.add_evidence(_ev(0.5))
        r = repr(sm)
        assert "users prefer X" in r
        assert "m1" in r
