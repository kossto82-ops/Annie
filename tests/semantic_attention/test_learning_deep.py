"""Part 5–9: Semantic generalization depth (recurrence, analogies, transfer, lateral, categorical).

These tests probe whether Jarvo generalizes MEANING or only matches WORDS.
"""
from datetime import UTC, datetime

from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.services.abstraction import abstract_patterns
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.infrastructure.in_memory_semantic_memory_store import InMemorySemanticMemoryStore
from jarvis.jarvis import Jarvis


def _ep(trigger: str) -> EpisodeRecord:
    now = datetime.now(UTC)
    return EpisodeRecord(
        episode_id=f"ep-{hash(trigger) & 0xFFFFFFFF:08x}",
        trigger=trigger,
        decision="concluded",
        working_belief_id="b1",
        outcome=EpisodeState.COMPLETED,
        conclusion_confidence=Confidence(0.7),
        conclusion_stability=Confidence(0.7),
        origin=TriggerOrigin.COMPANION,
        kind=EpisodeKind.CONCLUSION,
        recorded_at=now,
    )


def _jarvo_with_store() -> tuple[Jarvis, InMemorySemanticMemoryStore]:
    store = InMemorySemanticMemoryStore()
    return Jarvis(enable_recall=True, semantic_memory_store=store), store


class TestRecurrenceAcrossSessions:
    """Part 5: Does a new day's trigger surface yesterday's conclusion?"""

    def test_different_phrasing_reuses_conclusion(self):
        """Same topic, different words — does recall surface the prior belief?"""
        j, store = _jarvo_with_store()
        # Day 1: establish belief with exact evidence
        j.think(
            "supplier broke its delivery promise",
            evidence=[
                Evidence(
                    content="missed delivery",
                    source=EvidenceSource.USER_STATEMENT,
                    weight=Confidence(1.0),
                    supports=True,
                )
            ],
        )
        # Day 2: same meaning, different words
        ep2 = j.think("the vendor failed to honor the committed date")
        # Lexical recall looks for token overlap: "delivery"/"promise" absent in day-2 trigger
        recalled = ep2.recalled_memories
        has_episodic = any(m.kind.value == "episode" for m in recalled)
        assert not has_episodic, (
            "Day-2 paraphrase shares no content tokens with day-1 trigger → no recall"
        )

    def test_same_trigger_reuses_conclusion(self):
        """Identical trigger → BRIEF attention reuses prior belief (TRUE positive)."""
        j, store = _jarvo_with_store()
        j.think(
            "supplier broke its delivery promise",
            evidence=[
                Evidence(
                    content="missed delivery",
                    source=EvidenceSource.USER_STATEMENT,
                    weight=Confidence(1.0),
                    supports=True,
                )
            ],
        )
        ep2 = j.think("supplier broke its delivery promise")
        assert ep2.attention.value == "brief", "Identical trigger should reuse conclusion"


class TestCrossDomainAnalogies:
    """Part 4: Same structural pattern across different entities/domains."""

    def test_exact_same_words(self):
        """Control case: identical words → cluster."""
        j, store = _jarvo_with_store()
        j.think(
            "overpromising without evidence leads to disappointment",
            evidence=[
                Evidence(
                    content="a",
                    source=EvidenceSource.USER_STATEMENT,
                    weight=Confidence(1.0),
                    supports=True,
                )
            ],
        )
        ep2 = j.think("overpromising without evidence leads to disappointment")
        assert ep2.attention.value == "brief"

    def test_structurally_analogous_episodes_with_shared_concepts_abstract(self):
        """Tier 3 analogies: 'overpromised' maps to PROMISE in all three triggers,
        so they correctly cluster under conceptual vocabulary."""
        j, store = _jarvo_with_store()
        for trigger in [
            "the startup overpromised its launch timeline",
            "the contractor overpromised its build schedule",
            "the vendor overpromised its delivery window",
        ]:
            j.think(
                trigger,
                evidence=[
                    Evidence(
                        content="disappointed",
                        source=EvidenceSource.USER_STATEMENT,
                        weight=Confidence(1.0),
                        supports=True,
                    )
                ],
            )
        records = list(j.episodes.history())
        patterns = abstract_patterns(records, min_sources=3)
        assert len(patterns) >= 1, (
            "Shared PROMISE concept should cluster these"
        )
        assert "PROMISE" in patterns[0].pattern


class TestLateralConnections:
    """Part 8: Non-adjacent, associative links."""

    def test_no_associative_link_across_domains(self):
        """No lateral connection forms across unrelated domains."""
        j, store = _jarvo_with_store()
        j.think(
            "rain season affects harvest yield",
            evidence=[
                Evidence(
                    content="data point 1",
                    source=EvidenceSource.USER_STATEMENT,
                    weight=Confidence(1.0),
                    supports=True,
                )
            ],
        )
        ep2 = j.think("the train to town is always late")
        recalled = ep2.recalled_memories
        assert len(recalled) == 0, "Unrelated trigger should recall nothing"


class TestCategorization:
    """Part 9: Does Jarvo group episodes into categories?"""

    def test_no_explicit_categories_exist(self):
        """No category field lives on episodes or bullets."""
        j = Jarvis()
        ep = j.think(
            "customers are complaining about onboarding time",
            evidence=[
                Evidence(
                    content="onboarding takes 3 weeks",
                    source=EvidenceSource.USER_STATEMENT,
                    weight=Confidence(1.0),
                    supports=True,
                )
            ],
        )
        attrs = [
            a
            for a in dir(ep)
            if "categ" in a.lower() or "tag" in a.lower() or "label" in a.lower()
        ]
        assert len(attrs) == 0, f"Episode has no category/tag/label surface: {attrs}"


class TestNoGroundingBeyondWords:
    """Part 6–7: semantic generalization needs NO embedding/LLM in the runtime path.

    The abstraction layer is a deterministic, offline conceptual vocabulary; the
    composition roots now wire the semantic store so the lifecycle can persist it.
    """

    def test_default_retriever_is_lexical_wrapped(self):
        """enable_recall=True wires DocumentMemoryRetriever over LexicalMemoryRetriever
        (documents layered onto the same lexical base) — still token overlap."""
        from jarvis.infrastructure.document_memory_retriever import DocumentMemoryRetriever
        from jarvis.infrastructure.lexical_memory_retriever import LexicalMemoryRetriever
        j = Jarvis(enable_recall=True)
        retriever = j._executive._memory_retriever
        assert type(retriever) is DocumentMemoryRetriever
        assert type(retriever._base) is LexicalMemoryRetriever

    def test_semantic_embedding_retriever_not_wired_by_default(self):
        """EmbeddingMemoryRetriever requires explicit wiring — not in composition root."""
        from jarvis.jarvis import Jarvis
        j = Jarvis()
        assert j._semantic_memory_store is None, "No semantic store in bare default composition"
        from jarvis.infrastructure.embedding_memory_retriever import EmbeddingMemoryRetriever
        r = j._executive._memory_retriever
        assert not isinstance(r, EmbeddingMemoryRetriever), "Embedding retriever not default"

    def test_abstract_patterns_called_from_lifecycle_when_store_wired(self):
        """abstract_patterns() is now reachable: _remember consolidates semantic
        memories whenever a store is wired (still no-LLM and deterministic)."""
        import pathlib
        src = pathlib.Path(__file__).resolve().parents[2] / "src" / "jarvis"
        # The lifecycle calls consolidate_semantic_memories -> abstract_patterns
        text = (src / "executive" / "executive_controller.py").read_text(encoding="utf-8")
        assert "consolidate_semantic_memories" in text, (
            "Lifecycle must consolidate semantic memories when a store is wired"
        )
        # But a bare Jarvis (no store) never touches the abstraction layer.
        j = Jarvis()
        j.think("supplier dismissed")
        assert j._semantic_memory_store is None

    def test_semantic_store_wired_by_composition_roots(self):
        """Server and database composition roots now wire the semantic store."""
        base = __import__("pathlib").Path(__file__).resolve().parents[2] / "src" / "jarvis"
        import re
        wired = []
        for rel in ("persistence.py", "interface/server.py", "infrastructure/sqlite_database.py"):
            text = (base / rel).read_text(encoding="utf-8")
            if re.search(r"semantic_memory_store", text) or re.search(r"SemanticMemoryStore", text):
                wired.append(rel)
        assert wired, "Composition roots must wire a semantic store"