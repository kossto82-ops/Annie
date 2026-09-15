"""Retrieval-strategy selection (P2-C): routing evidence, consumed not kept.

Selection decides which retriever *surfaces candidates*, never what Jarvis
concludes (D20). The default is lexical; an embedding preference forms only
on well-sampled, meaningful gaps and must always be reversible by honest
counter-evidence. Recording is automatic through the recall paths but the
seam is public, so history can be replayed or corrected in tests.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.services.retrieval_strategy import (
    MIN_STRATEGY_SAMPLES,
    select_retrieval_strategy,
)
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.retrieval_strategy import (
    RetrievalStrategy,
    RetrievalStrategyStats,
    StrategyOutcome,
)
from jarvis.infrastructure.json_strategy_stats_store import (
    JsonStrategyStatsStore,
    deserialise_strategy_stats,
    serialise_strategy_stats,
)
from jarvis.infrastructure.sqlite_strategy_stats_store import SqliteStrategyStatsStore
from jarvis.jarvis import Jarvis


class _IdentityEmbedder:
    """Deterministic fake: identity-ish text -> one axis, everything else -> another."""

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        vectors: list[tuple[float, ...]] = []
        for text in texts:
            low = text.lower()
            identity = any(word in low for word in ("raul", "nombre", "llamo", "soy"))
            vectors.append((1.0, 0.0) if identity else (0.0, 1.0))
        return tuple(vectors)


def _outcome(strategy: RetrievalStrategy, success: bool, query: str = "q") -> StrategyOutcome:
    return StrategyOutcome(strategy=strategy, success=success, query=query)


class TestRetrievalStrategyStats:
    def test_recorded_is_bounded_to_the_latest_hundred(self) -> None:
        stats = RetrievalStrategyStats()
        for _ in range(150):
            stats = stats.recorded(_outcome(RetrievalStrategy.LEXICAL, True))
        assert len(stats.outcomes) == 100
        assert stats.count(RetrievalStrategy.LEXICAL) == 100

    def test_success_rate_counts_only_the_strategy_s_runs(self) -> None:
        stats = RetrievalStrategyStats()
        stats = stats.recorded(_outcome(RetrievalStrategy.LEXICAL, False))
        stats = stats.recorded(_outcome(RetrievalStrategy.LEXICAL, True))
        stats = stats.recorded(_outcome(RetrievalStrategy.EMBEDDING, False))
        assert stats.success_rate(RetrievalStrategy.LEXICAL) == 0.5
        assert stats.success_rate(RetrievalStrategy.EMBEDDING) == 0.0


class TestSelectRetrievalStrategy:
    def test_no_embedding_retriever_is_always_lexical(self) -> None:
        flooded = RetrievalStrategyStats(
            outcomes=tuple(
                _outcome(RetrievalStrategy.EMBEDDING, True) for _ in range(60)
            )
        )
        assert (
            select_retrieval_strategy(flooded, embedding_available=False)
            is RetrievalStrategy.LEXICAL
        )

    def test_thin_evidence_keeps_the_safe_default(self) -> None:
        stats = RetrievalStrategyStats()
        for _ in range(MIN_STRATEGY_SAMPLES - 1):
            stats = stats.recorded(_outcome(RetrievalStrategy.EMBEDDING, True, "hit"))
            stats = stats.recorded(_outcome(RetrievalStrategy.LEXICAL, False, "miss"))
        assert (
            select_retrieval_strategy(stats, embedding_available=True)
            is RetrievalStrategy.LEXICAL
        )

    def test_preference_requires_a_meaningful_gap(self) -> None:
        stats = RetrievalStrategyStats()
        # 5/5 embedding hits against 5/5 lexical misses clears both the sample
        # floor and the >= 0.15 success gap, so the preference forms.
        for _ in range(MIN_STRATEGY_SAMPLES):
            stats = stats.recorded(_outcome(RetrievalStrategy.EMBEDDING, True, "embed"))
            stats = stats.recorded(_outcome(RetrievalStrategy.LEXICAL, False, "lex"))
        assert (
            select_retrieval_strategy(stats, embedding_available=True)
            is RetrievalStrategy.EMBEDDING
        )

    def test_ties_keep_lexical(self) -> None:
        stats = RetrievalStrategyStats()
        for _ in range(MIN_STRATEGY_SAMPLES):
            stats = stats.recorded(_outcome(RetrievalStrategy.EMBEDDING, True))
            stats = stats.recorded(_outcome(RetrievalStrategy.LEXICAL, True))
        assert (
            select_retrieval_strategy(stats, embedding_available=True)
            is RetrievalStrategy.LEXICAL
        )

    def test_counter_evidence_reverses_the_preference(self) -> None:
        stats = RetrievalStrategyStats()
        # Establish an embedding preference: 5/5 hits vs 5/5 misses.
        for _ in range(MIN_STRATEGY_SAMPLES):
            stats = stats.recorded(_outcome(RetrievalStrategy.EMBEDDING, True))
            stats = stats.recorded(_outcome(RetrievalStrategy.LEXICAL, False))
        assert (
            select_retrieval_strategy(stats, embedding_available=True)
            is RetrievalStrategy.EMBEDDING
        )
        # Honest reversal: a long run of embedding miss-es and lexical hits.
        for _ in range(30):
            stats = stats.recorded(_outcome(RetrievalStrategy.EMBEDDING, False, "embed"))
            stats = stats.recorded(_outcome(RetrievalStrategy.LEXICAL, True, "lex"))
        after = select_retrieval_strategy(stats, embedding_available=True)
        assert after is RetrievalStrategy.LEXICAL


class TestStrategyWiring:
    def _jarvis(self) -> Jarvis:
        jarvis = Jarvis(enable_recall=True)
        jarvis.enable_embedding_recall(_IdentityEmbedder())
        return jarvis

    def test_fallback_earns_fresh_evidence_for_both_sides(self) -> None:
        jarvis = self._jarvis()
        jarvis.observe_companion(
            "is named Raúl",
            Evidence(content="me llamo Raúl", source=EvidenceSource.USER_STATEMENT,
                     weight=Confidence(0.9)),
        )
        # "el nombre" shares no surface tokens with the trait: lexical misses,
        # the miss-triggered fallback lets embedding earn its evidence.
        got = jarvis.recall("el nombre")
        assert any("is named Raúl" in m.content for m in got)
        stats = jarvis.strategy_stats()
        assert stats.count(RetrievalStrategy.LEXICAL) == 1
        assert stats.count(RetrievalStrategy.EMBEDDING) == 1
        assert stats.success_rate(RetrievalStrategy.LEXICAL) == 0.0
        assert stats.success_rate(RetrievalStrategy.EMBEDDING) == 1.0

    def test_preference_forms_through_the_public_seam(self) -> None:
        jarvis = self._jarvis()
        for _ in range(MIN_STRATEGY_SAMPLES):
            jarvis.record_retrieval_outcome(RetrievalStrategy.EMBEDDING, True, "p")
            jarvis.record_retrieval_outcome(RetrievalStrategy.LEXICAL, False, "p")
        assert (
            jarvis.retrieval_strategy_for("anything") is RetrievalStrategy.EMBEDDING
        )


class TestStrategyStatsStores:
    def test_json_store_roundtrips_and_recovers(self, tmp_path: Path) -> None:
        store = JsonStrategyStatsStore(tmp_path / "retrieval_strategy.json")
        assert store.load() is None  # missing -> nothing recorded
        stats = RetrievalStrategyStats(
            outcomes=(
                _outcome(RetrievalStrategy.EMBEDDING, True, "q"),
                _outcome(RetrievalStrategy.LEXICAL, False, "q"),
            )
        )
        store.save(stats)
        loaded = store.load()
        assert loaded is not None
        assert loaded == stats
        # A corrupt file reads as nothing recorded (recovery, not a crash).
        (tmp_path / "retrieval_strategy.json").write_text("{not json", encoding="utf-8")
        assert store.load() is None

    def test_sqlite_store_roundtrips(self) -> None:
        conn = sqlite3.connect(":memory:")
        store = SqliteStrategyStatsStore(conn)
        assert store.load() is None
        stats = RetrievalStrategyStats(
            outcomes=(
                _outcome(RetrievalStrategy.LEXICAL, True, "a"),
                _outcome(RetrievalStrategy.EMBEDDING, False, "b"),
            )
        )
        store.save(stats)
        loaded = store.load()
        assert loaded is not None
        assert loaded == stats

    def test_json_roundtrip_is_deterministic(self) -> None:
        stats = RetrievalStrategyStats(
            outcomes=(_outcome(RetrievalStrategy.EMBEDDING, True, "q"),)
        )
        rebuilt = deserialise_strategy_stats(
            json.loads(json.dumps(serialise_strategy_stats(stats)))
        )
        assert rebuilt == stats


class TestStrategyPreferencePersists:
    def test_persistent_factory_keeps_the_preference_across_restarts(
        self, tmp_path: Path
    ) -> None:
        directory = tmp_path / "home"
        first = Jarvis.persistent(directory)
        first.enable_embedding_recall(_IdentityEmbedder())  # makes the choice observable
        for _ in range(MIN_STRATEGY_SAMPLES):
            first.record_retrieval_outcome(RetrievalStrategy.EMBEDDING, True, "p")
            first.record_retrieval_outcome(RetrievalStrategy.LEXICAL, False, "p")
        assert first.retrieval_strategy_for("p") is RetrievalStrategy.EMBEDDING

        second = Jarvis.persistent(directory)
        second.enable_embedding_recall(_IdentityEmbedder())
        assert second.retrieval_strategy_for("p") is RetrievalStrategy.EMBEDDING
        assert second.strategy_stats() == first.strategy_stats()

    def test_database_factory_keeps_the_preference_across_restarts(
        self, tmp_path: Path
    ) -> None:
        directory = tmp_path / "db_home"
        first = Jarvis.database(directory)
        first.enable_embedding_recall(_IdentityEmbedder())
        for _ in range(MIN_STRATEGY_SAMPLES):
            first.record_retrieval_outcome(RetrievalStrategy.EMBEDDING, True, "p")
            first.record_retrieval_outcome(RetrievalStrategy.LEXICAL, False, "p")
        assert first.retrieval_strategy_for("p") is RetrievalStrategy.EMBEDDING

        second = Jarvis.database(directory)
        second.enable_embedding_recall(_IdentityEmbedder())
        assert second.retrieval_strategy_for("p") is RetrievalStrategy.EMBEDDING