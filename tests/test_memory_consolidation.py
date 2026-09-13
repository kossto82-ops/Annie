"""Tests for Phase 11: memory decay and consolidation.

Proves that:
1. Beliefs with low effective confidence are identified as forgetting candidates
2. Beliefs with stale evidence are candidates
3. Beliefs with no evidence are candidates
4. Healthy beliefs are not candidates
5. `forget()` removes beliefs from all stores
6. Forgetting persists across JSON store restart
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.services.memory_consolidation import (
    identify_forgetting_candidates,
)
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.infrastructure.in_memory_belief_store import InMemoryBeliefStore


def _make_belief(
    statement: str,
    evidence_count: int = 0,
    confidence: float = 0.5,
    age_days: int = 0,
) -> Belief:
    belief = Belief(statement=statement)
    now = datetime.now(tz=UTC)
    for i in range(evidence_count):
        obs_time = now - timedelta(days=age_days, hours=i)
        belief.add_evidence(
            Evidence(
                content=f"evidence {i}",
                source=EvidenceSource.DIRECT_OBSERVATION,
                weight=Confidence(confidence),
                supports=True,
                context="test",
                observed_at=obs_time,
            )
        )
    return belief


class TestMemoryConsolidation:
    def test_stale_belief_is_candidate(self):
        """A belief not reinforced for 90+ days is a candidate."""
        store = InMemoryBeliefStore()
        belief = _make_belief("old topic", evidence_count=3, confidence=0.8, age_days=100)
        store.save(belief)

        candidates = identify_forgetting_candidates(
            store, now=datetime.now(tz=UTC), stale_after=timedelta(days=90)
        )

        assert len(candidates) == 1
        assert candidates[0].belief.statement == "old topic"
        assert "not reinforced" in candidates[0].reason

    def test_no_evidence_belief_is_candidate(self):
        """A belief with no evidence is a candidate."""
        store = InMemoryBeliefStore()
        belief = Belief(statement="empty belief")
        store.save(belief)

        candidates = identify_forgetting_candidates(store)

        assert len(candidates) == 1
        assert candidates[0].effective_confidence == 0.0

    def test_healthy_belief_not_candidate(self):
        """A recently reinforced, confident belief is not a candidate."""
        store = InMemoryBeliefStore()
        belief = _make_belief("solid topic", evidence_count=5, confidence=0.8, age_days=5)
        store.save(belief)

        candidates = identify_forgetting_candidates(
            store, now=datetime.now(tz=UTC), stale_after=timedelta(days=90)
        )

        assert len(candidates) == 0

    def test_low_confidence_is_candidate(self):
        """A belief with low effective confidence is a candidate."""
        store = InMemoryBeliefStore()
        belief = _make_belief("weak topic", evidence_count=1, confidence=0.1)
        store.save(belief)

        candidates = identify_forgetting_candidates(
            store, threshold=0.15
        )

        assert len(candidates) == 1
        assert candidates[0].effective_confidence < 0.15


class TestForgetMethod:
    def test_forget_removes_from_memory_store(self):
        """forget() removes a belief from the in-memory store."""
        store = InMemoryBeliefStore()
        belief = _make_belief("forgettable", evidence_count=2)
        store.save(belief)

        assert store.get_by_statement("forgettable") is not None
        result = store.forget("forgettable")
        assert result is True
        assert store.get_by_statement("forgettable") is None

    def test_forget_returns_false_when_not_found(self):
        """forget() returns False for unknown statements."""
        store = InMemoryBeliefStore()
        result = store.forget("nonexistent")
        assert result is False

    def test_forget_persists_in_json_store(self, tmp_path):
        """forget() persists to JSON file."""
        from jarvis.infrastructure.json_belief_store import JsonBeliefStore

        path = tmp_path / "beliefs.json"
        store = JsonBeliefStore(path)
        belief = _make_belief("to forget", evidence_count=1)
        store.save(belief)

        # Forget
        store.forget("to forget")
        assert store.get_by_statement("to forget") is None

        # Reload from disk
        store2 = JsonBeliefStore(path)
        assert store2.get_by_statement("to forget") is None
