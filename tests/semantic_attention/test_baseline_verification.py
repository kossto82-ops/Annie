"""Part 2 — Baseline reproduction: confirm the 5 known failures exist
before modifying any production code.

A — abstract_patterns() exists but is never called by normal cognition.
B — A normal think() creates an episode but does not create semantic memory.
C — A semantic memory manually inserted can participate in recall/reasoning.
D — Embedding retrieval reachable only through opt-in seam.
E — Attention is determined primarily by belief confidence + evidence presence.

All probes run against the live, unmodified package.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from datetime import UTC, datetime

from jarvis.domain.entities.semantic_memory import SemanticMemory
from jarvis.domain.enums.attention import Attention
from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.infrastructure.in_memory_semantic_memory_store import InMemorySemanticMemoryStore
from jarvis.jarvis import Jarvis


def _evidence() -> Evidence:
    return Evidence(content="observed", source=EvidenceSource.USER_STATEMENT,
                    weight=Confidence(1.0), supports=True)


def _rec(trigger: str) -> EpisodeRecord:
    return EpisodeRecord(
        episode_id=f"ep-{hash(trigger) & 0xFFFFFFFF:08x}",
        trigger=trigger, decision="concluded",
        working_belief_id="b1", outcome=EpisodeState.COMPLETED,
        conclusion_confidence=Confidence(0.7), conclusion_stability=Confidence(0.7),
        origin=TriggerOrigin.COMPANION, kind=EpisodeKind.CONCLUSION,
        recorded_at=datetime.now(UTC),
    )


def test_A_abstract_patterns_exists_but_is_dead_code():
    """A: abstract_patterns() has zero callers in src/."""
    import pathlib
    src = pathlib.Path(__file__).resolve().parent.parent.parent / "src"
    callers = []
    for p in src.rglob("*.py"):
        if "abstraction.py" in str(p):
            continue
        if "abstract_patterns" in p.read_text(encoding="utf-8"):
            callers.append(str(p.relative_to(src)))
    assert callers == [], f"abstract_patterns has callers: {callers}"


def test_B_think_creates_episode_but_not_semantic_memory():
    """B: think() with evidence records an episode, semantic store stays empty."""
    store = InMemorySemanticMemoryStore()
    j = Jarvis(enable_recall=True, semantic_memory_store=store)
    j.think("supplier repeatedly misses promised delivery dates", evidence=[_evidence()])
    records = j.episodes.history()
    assert len(records) == 1, f"Expected 1 episode record, got {len(records)}"
    assert len(store.all_memories()) == 0, "Semantic store should be empty after think()"


def test_C_manual_semantic_memory_participates_in_recall():
    """C: Hand-seeded semantic memory surfaces in recall when token overlap ≥ 0.2."""
    store = InMemorySemanticMemoryStore()
    sm = SemanticMemory(pattern="unsupported optimistic claims about deadlines fail")
    sm.add_evidence(Evidence(content="observed", source=EvidenceSource.SYSTEM_OBSERVATION,
                             weight=Confidence(0.5), supports=True))
    sm.pull_events()
    store.save(sm)
    j = Jarvis(enable_recall=True, semantic_memory_store=store)
    recalled = j.recall("contractor hypothesized optimistic schedules")
    assert len(recalled) > 0, "Semantic memory should surface"
    assert recalled[0].kind.value == "semantic"


def test_D_embedding_retrieval_only_via_opt_in_seam():
    """D: Without JARVIS_EMBED_* env, no embedder is built; embedding_recall not auto-wired."""
    from jarvis.infrastructure.perceiver_factory import build_embedder
    embedder = build_embedder({})
    assert embedder is None, "No embedder when JARVIS_EMBED_MODEL is absent"
    from jarvis.infrastructure.embedding_memory_retriever import EmbeddingMemoryRetriever
    j = Jarvis(enable_recall=True)
    assert not isinstance(j._executive._memory_retriever, EmbeddingMemoryRetriever)


def test_E_attention_derived_from_belief_confidence_not_learned():
    """E: Attention is FULL vs BRIEF based on belief grounded + new evidence."""
    j = Jarvis(enable_recall=True)
    ep1 = j.think("topic A", evidence=[_evidence()])
    assert ep1.attention == Attention.FULL, "New trigger should be FULL"
    ep2 = j.think("topic A")
    assert ep2.attention == Attention.BRIEF, "Grounded, no new evidence → BRIEF"
    ep3 = j.think("topic B")
    assert ep3.attention == Attention.FULL, "Different trigger → FULL"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
