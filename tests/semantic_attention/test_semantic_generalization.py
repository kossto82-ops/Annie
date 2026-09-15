"""Part 10-12, 21: Semantic generalization, negative generalization,
contradiction-aware abstraction, and adversarial anti-cheating.

Tier 1: same structure, different wording (stemmed + synonym-normalized)
Tier 2: paraphrases with the same semantic field
Tier 3: structural analogies (different entities, same verb-frame)
Tier 4: abstract transfer across domains

Everything runs against the live lifecycle (think -> abstract -> consolidate
-> recall) with an in-memory semantic store, so a failure here means the
*behaviour* breaks, not a unit helper.
"""
from __future__ import annotations

from collections.abc import Sequence

from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.services.abstraction import consolidate_semantic_memories
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.infrastructure.in_memory_semantic_memory_store import InMemorySemanticMemoryStore
from jarvis.jarvis import Jarvis


def _evidence(text: str = "observed") -> Evidence:
    return Evidence(
        content=text,
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(1.0),
        supports=True,
    )


def _jarvis(
    store: InMemorySemanticMemoryStore | None = None,
) -> tuple[Jarvis, InMemorySemanticMemoryStore]:
    store = store or InMemorySemanticMemoryStore()
    return Jarvis(enable_recall=True, semantic_memory_store=store), store


def _feed_episodes(j: Jarvis, triggers: Sequence[str]) -> None:
    for t in triggers:
        j.think(t, evidence=[_evidence()])


class TestTier1LexicalVariation:
    """Tier 1: same meanings, different surface words -> one semantic memory."""

    def test_synonym_variation_clusters(self):
        j, store = _jarvis()
        _feed_episodes(j, [
            "supplier misses promised delivery dates",
            "vendor keeps missing delivery commitments",
            "contractor failed promised deliveries",
        ])
        memories = store.all_memories()
        assert len(memories) == 1, f"Expected 1 pattern, got {len(memories)}"
        assert "FAIL" in memories[0].pattern
        assert "PROMISE" in memories[0].pattern
        assert memories[0].source_episode_ids == [
            ep.episode_id for ep in j.episodes.history()
        ]

    def test_verb_forms_cluster(self):
        """promised / promising / promise all -> PROMISE."""
        j, store = _jarvis()
        _feed_episodes(j, [
            "he promised delivery",
            "he was promising delivery",
            "he keeps promising delivery",
        ])
        memories = store.all_memories()
        assert len(memories) >= 1, "Verb forms should share PROMISE concept"
        assert "PROMISE" in memories[0].pattern


class TestTier2Paraphrase:
    """Tier 2: paraphrases carrying the same semantic field -> one memory."""

    def test_paraphrases_share_meaning(self):
        j, store = _jarvis()
        _feed_episodes(j, [
            "repeatedly promised dates that then fail",
            "promises that keep failing",
            "committed to times that never hold",
        ])
        memories = store.all_memories()
        assert len(memories) >= 1
        # The concept shared across all three paraphrases is PROMISE (committed/promise)
        assert "PROMISE" in memories[0].pattern

    def test_semantic_recall_across_phrasing(self):
        """A lexically-different but conceptually-similar query surfaces the memory."""
        j, _ = _jarvis()
        _feed_episodes(j, [
            "supplier misses promised delivery dates",
            "vendor keeps missing delivery commitments",
            "contractor failed promised deliveries",
        ])
        recalled = j.recall("contractor keeps failing promises")
        kinds = {r.kind.value for r in recalled}
        assert "semantic" in kinds, "Conceptual recall should surface the semantic memory"
        assert any(r.relevance >= 0.2 for r in recalled if r.kind.value == "semantic")


class TestTier3StructuralAnalogy:
    """Tier 3: different entities, same verb-frame -> abstraction survives."""

    def test_role_words_do_not_fragment_clusters(self):
        """supplier/vendor/contractor/provider are ROLE, not cluster keys."""
        j, store = _jarvis()
        _feed_episodes(j, [
            "supplier missed promised delivery",
            "vendor missed promised delivery",
            "contractor missed promised delivery",
        ])
        memories = store.all_memories()
        assert len(memories) == 1, "Role words should not fragment the cluster"
        assert "ROLE" not in memories[0].pattern


class TestTier4CrossDomain:
    """Tier 4: abstract transfer — same concept frame, unrelated concrete nouns."""

    def test_cross_domain_sharing_verb_concept_clusters(self):
        j, store = _jarvis()
        _feed_episodes(j, [
            "IT department overpromised system uptime",
            "marketing team overpromised engagement",
            "logistics overpromised delivery speed",
        ])
        memories = store.all_memories()
        assert len(memories) >= 1, "Shared PROMISE concept should span domains"
        assert "PROMISE" in memories[0].pattern


class TestNegativeGeneralization:
    """Part 11: opposite — things that must NOT be conflated."""

    def test_disjoint_concepts_never_cluster(self):
        j, store = _jarvis()
        _feed_episodes(j, [
            "the rain affected the harvest",
            "the cat slept on the sofa",
            "two plus two equals four",
        ])
        assert len(store.all_memories()) == 0, "No shared concepts -> no pattern"

    def test_same_entity_different_situation_does_not_merge(self):
        """Same actor, unrelated concepts on different topics stay separate."""
        j, store = _jarvis()
        _feed_episodes(j, [
            "supplier delayed delivery",
            "supplier raised prices after the contract",
            "supplier offered training sessions for the tool",
        ])
        memories = store.all_memories()
        # The three share 'supplier' (ROLE) but no concept tokens -> nothing merges
        assert len(memories) == 0, "ROLE only is not a semantic cluster"

    def test_similar_events_opposite_outcomes_do_not_collapse(self):
        """A positive pattern must not be replaced by a negative one."""
        j, store = _jarvis()
        _feed_episodes(j, [
            "supplier delivered early",
            "supplier delivered early",
            "supplier delivered early",
        ])
        j.recall("supplier delivers on time")
        # DELIVER is shared, but the pattern is about success; no FAIL+... false claim
        assert len(store.all_memories()) >= 1
        assert "FAIL" not in store.all_memories()[0].pattern, "No negative overreach"


class TestContradictionAware:
    """Part 12: contradiction must remain representable, never collapsed."""

    def test_mixed_outcomes_keep_both_sides_in_evidence(self):
        j, store = _jarvis()
        _feed_episodes(j, [
            "supplier missed promised delivery dates",
            "supplier failed to meet delivery commitments",
            "supplier met the delivery commitment on time",
        ])
        memories = store.all_memories()
        assert len(memories) >= 1, "Recurrence patterns exist despite mixed outcomes"
        m = memories[0]
        contents = [e.content for e in m.evidence]
        assert any("outcome: negative" in c for c in contents), (
            "Negative outcome evidence must be preserved"
        )
        assert any("outcome: positive" in c for c in contents), (
            "Positive (contradicting) outcome evidence must be preserved"
        )

    def test_contradicting_episodes_constrain_recurrence_confidence(self):
        """Recurrence confidence rises with support but a real contradiction
        keeps it below the grounded threshold (never collapses to a certainty)."""
        j, store = _jarvis()
        _feed_episodes(j, [
            "supplier missed promised delivery",
            "supplier missed promised delivery",
            "supplier met the delivery commitment on time",
            "supplier met the delivery commitment on time",
            "supplier met the delivery commitment on time",
        ])
        memories = store.all_memories()
        assert memories, "A pattern should exist"
        # With 2 negative + 3 positive the 'positive outcome' contradicts the
        # negative framing in evidence; recurrence confidence stays < grounded.
        assert memories[0].confidence.value < 0.5, (
            "Contradicted recurrence must stay ungrounded, not a firm claim"
        )


class TestAdversarial:
    """Part 21: behavioural honesty — the system must not cheat."""

    def test_abstraction_uses_vocabulary_not_hardcoded_pairs(self):
        """Concepts come from a general vocabulary, not memorised trigger pairs."""
        from jarvis.domain.services.abstraction import CONCEPT_MAP
        # The map is used for new, unseen text too — not keyed to specific phrases.
        assert CONCEPT_MAP.get("promise") == "PROMISE"
        assert CONCEPT_MAP.get("missing") == "FAIL"
        # And a completely unrelated sentence produces no concepts at all.
        from jarvis.domain.services.abstraction import conceptual_tokens
        assert conceptual_tokens("the zebra wrote a poem about quantum spin") == frozenset()

    def test_recall_is_retrieval_not_evidence(self):
        """Recalled semantic memory is context, never automatic belief grounding."""
        j, _ = _jarvis()
        _feed_episodes(j, [
            "supplier misses promised delivery dates",
            "vendor keeps missing delivery commitments",
            "contractor failed promised deliveries",
        ])
        # Evidence count stays 0 for a query with no user evidence: recall alone
        # doesn't fabricate grounds.
        ep = j.think("some unrelated trigger with fresh evidence", evidence=[_evidence()])
        assert ep.working_belief is not None
        belief = ep.working_belief
        assert all(e.source == EvidenceSource.USER_STATEMENT for e in belief.evidence)

    def test_no_embedding_decides_alone(self):
        """Without an embedder there is no embedding path; retrieval stays lexical."""
        j, _ = _jarvis()
        from jarvis.infrastructure.embedding_memory_retriever import EmbeddingMemoryRetriever
        assert not isinstance(
            j.executive.memory_retriever, EmbeddingMemoryRetriever
        ), "Embedding retriever not installed by default"

    def test_lexically_similar_but_conceptually_different_no_conflate(self):
        """Surface overlap alone is not the match criterion."""
        j, store = _jarvis()
        _feed_episodes(j, [
            "the cat missed the cereal bowl",
            "the dog missed the leash hook",
            "the parrot missed the perch",
        ])
        # 'missed' -> FAIL in each, but no shared *second* concept. Cluster requires
        # Jaccard >= 0.3 AND shared concepts. Single-concept clusters still form
        # (recurring FAIL alone), but they never claim a false tie to delivery.
        memories = store.all_memories()
        for m in memories:
            assert "DELIVER" not in m.pattern, "Must not overreach into delivery"


class TestBoundedConsolidation:
    """Part 22: consolidation never rescales with the whole history."""

    def _episodes(self, triggers: Sequence[str]) -> list[EpisodeRecord]:
        from jarvis.domain.enums.episode_kind import EpisodeKind
        from jarvis.domain.enums.episode_state import EpisodeState
        from jarvis.domain.enums.trigger_origin import TriggerOrigin
        from jarvis.domain.value_objects.temporal_stability import TemporalStability

        records: list[EpisodeRecord] = []
        for i, trigger in enumerate(triggers):
            records.append(
                EpisodeRecord(
                    episode_id=f"bounded-{i}",
                    trigger=trigger,
                    decision="decided",
                    working_belief_id=f"b-{i}",
                    outcome=EpisodeState.COMPLETED,
                    conclusion_confidence=Confidence(0.8),
                    conclusion_stability=TemporalStability(0.5),
                    origin=TriggerOrigin.COMPANION,
                    kind=EpisodeKind.CONCLUSION,
                )
            )
        return records

    def test_window_bounds_clustering(self):
        store = InMemorySemanticMemoryStore()
        # Three identical-topic episodes exist, but a window of 2 sees only two
        # recent ones -- min_sources is not met, so no memory is claimed.
        episodes = self._episodes([
            "the supplier failed to deliver",
            "the supplier failed to deliver",
            "the supplier failed to deliver",
        ])
        stored = consolidate_semantic_memories(episodes, store, min_sources=3, window=2)
        assert stored == []
        assert store.all_memories() == ()

    def test_default_window_clusters_recent_history(self):
        store = InMemorySemanticMemoryStore()
        episodes = self._episodes([
            "the supplier failed to deliver",
            "the supplier failed to deliver",
            "the supplier failed to deliver",
        ])
        stored = consolidate_semantic_memories(episodes, store, min_sources=3)
        assert len(stored) == 1
        assert "FAIL" in stored[0].pattern