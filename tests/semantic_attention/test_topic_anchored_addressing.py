"""Topic-anchored belief addressing v1 (Model B) gate tests.

The belief's *identity* is its canonical topic identity; the statement is
representative/display metadata; each episode's trigger stays the original
immutable observation.  Different surface forms of the same matter converge on
one belief while remaining individually readable through their statements.

Coverage (gate A–L):
  A  five-trigger convergence — the DELIVER unit from its paraphrases
  B  the atomic four-piece gate sample (1 FAIL + 1 SUCCEED + 1 NEUTRAL + 1 FAIL)
  C  paraphrase contradiction ("failed to deliver" / "succeeded in delivering")
  D  neutral evidence ("didn't deliver") — kept, never counts toward strength
  E  different-topic isolation (DELIVER vs a concept-free matter)
  F  concept-free fallback — raw-trigger addressing is preserved
  G  persistence round trip: in-memory, JSON file, SQLite
  H  legacy reconciliation of statement-keyed fragments + idempotence
  I  deterministic representative (earliest formed_at, statement tie-break)
  K  chronological evidence — four pieces, order preserved
  L  semantic-memory regression — recall is unaffected by the addressing layer

Frozen-geometry note (branch decision, reported): the literal five-trigger list
in the gate includes "supplier keeps promising delivery dates that fail", whose
signature {PROMISE, DELIVER, TIME} is a *distinct topic family*: Topic Identity
geometry pins that a shared single concept never unites different matters
(|S ∩ T| >= 2 is required for a nested join, see topic_resolution._compatible
and tests/semantic_attention/test_topic_identity_v3.py::TestICrossMatterStability).
The four {DELIVER}-signature triggers converge into the DELIVER unit; the
composite trigger keeps its own sibling belief (test A asserts exactly that).
"""
from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from jarvis.domain.entities.belief import Belief
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.repositories.belief_repository import (
    BeliefRepository,
    belief_registry,
    belief_topic_id,
    reconcile_topic,
    working_statement,
)
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.infrastructure.in_memory_belief_store import InMemoryBeliefStore
from jarvis.infrastructure.json_belief_store import JsonBeliefStore
from jarvis.infrastructure.sqlite_belief_store import SqliteBeliefStore
from jarvis.jarvis import Jarvis

# -- the DELIVER matter -------------------------------------------------------

_S1 = "supplier failed to deliver"
_S2 = "supplier succeeded in delivering"
_S3 = "delivery from the supplier failed"
_S4 = "the supplier did not deliver"
_S5 = "supplier keeps promising delivery dates that fail"

_DELIVER_TRIGGERS = (_S1, _S2, _S3, _S4)

_CONCEPT_FREE_A = "billing reconciliation drifted after the quarter end"
_CONCEPT_FREE_B = "invoice differed from receipt"


def _evidence(
    content: str,
    *,
    supports: bool = True,
    neutral: bool = False,
    weight: float = 1.0,
    observed_at: datetime | None = None,
) -> Evidence:
    return Evidence(
        content=content,
        source=EvidenceSource.USER_STATEMENT,
        weight=Confidence(weight),
        supports=supports,
        is_neutral=neutral,
        observed_at=observed_at or datetime.now(UTC),
    )


def _think_all(
    jarvis: Jarvis, triggers: Sequence[str], evidence_list: Sequence[Evidence]
) -> None:
    for trigger, evidence in zip(triggers, evidence_list, strict=False):
        jarvis.think(trigger, evidence=[evidence])


class TestAFiveTriggerConvergence:
    def test_paraphrases_of_the_deliver_matter_form_the_deliver_unit(self) -> None:
        jarvis = Jarvis()
        _think_all(
            jarvis,
            _DELIVER_TRIGGERS,
            [
                _evidence("observed a failed delivery", supports=False),
                _evidence("observed a successful delivery"),
                _evidence("observed a failed delivery again", supports=False),
                _evidence("observed no delivery at all", neutral=True),
            ],
        )
        unified = jarvis.beliefs.get_by_topic("DELIVER")
        assert unified is not None
        assert len(jarvis.beliefs.all_beliefs()) == 1, (
            "every surface form of the DELIVER matter addresses ONE belief"
        )
        assert belief_topic_id(unified.statement) == "DELIVER"
        assert len(unified.evidence) == 4, "all four observations are preserved"
        assert jarvis.beliefs.get_by_statement(
            working_statement(_S1)
        ) is unified, "the belief is still readable through its stored statement"

    def test_composite_trigger_keeps_the_frozen_geometry(self) -> None:
        """{PROMISE, DELIVER, TIME} is a distinct topic family: a shared single
        concept never unites different matters (pinned topic identity rule)."""
        jarvis = Jarvis()
        jarvis.think(_S1, evidence=[_evidence("observed a failed delivery", supports=False)])
        jarvis.think(_S5, evidence=[_evidence("observed dates slipping")])
        composite = jarvis.beliefs.get_by_topic("DELIVER > PROMISE > TIME")
        assert composite is not None
        assert jarvis.beliefs.get_by_topic("DELIVER") is not None
        assert len(jarvis.beliefs.all_beliefs()) == 2, (
            "composite and single-concept matters stay sibling beliefs (stored rules)"
        )


class TestBAtomicFourPieceGateSample:
    def test_the_four_piece_sample_is_one_qualified_belief(self) -> None:
        jarvis = Jarvis()
        _think_all(
            jarvis,
            (_S1, _S2, _S4, _S3),
            [
                _evidence("observed a failed delivery", supports=False),
                _evidence("observed a successful delivery"),
                _evidence("observed no delivery at all", neutral=True),
                _evidence("observed a failed delivery again", supports=False),
            ],
        )
        unified = jarvis.beliefs.get_by_topic("DELIVER")
        assert unified is not None
        assert len(jarvis.beliefs.all_beliefs()) == 1
        explanation = unified.explain()
        assert len(explanation.supporting) == 1
        assert len(explanation.contradicting) == 2
        assert len(unified.evidence) == 4, "the neutral piece is kept, not dropped"
        assert unified.confidence == Confidence(0.25), (
            "1 SUCCEED vs 2 FAIL with a neutral prior -> 1/(1+2+1), below threshold"
        )


class TestCParaphraseContradiction:
    def test_contradiction_machinery_spans_paraphrases(self) -> None:
        jarvis = Jarvis()
        jarvis.think(_S1, evidence=[_evidence("observed a failed delivery", supports=False)])
        jarvis.think(
            _S2, evidence=[_evidence("observed a successful delivery")]
        )
        unified = jarvis.beliefs.get_by_topic("DELIVER")
        assert unified is not None
        explanation = unified.explain()
        assert explanation.supporting, "the SUCCEED paraphrase supports"
        assert explanation.contradicting, "the FAIL paraphrase contradicts"
        assert jarvis.executive.should_reflect(
            unified
        ), "contradiction becomes a reflection signal"

    def test_confirm_reaches_the_same_matter_through_a_different_surface(self) -> None:
        jarvis = Jarvis()
        jarvis.think(_S1, evidence=[_evidence("observed a failed delivery", supports=False)])
        confirmed = jarvis.confirm(_S2)
        assert confirmed is not None
        assert confirmed is jarvis.beliefs.get_by_topic("DELIVER")


class TestDNeutralEvidence:
    def test_neutral_evidence_contributes_no_strength(self) -> None:
        jarvis = Jarvis()
        jarvis.think(
            _S4,
            evidence=[
                _evidence("observed no delivery at all", neutral=True, weight=0.9)
            ],
        )
        neutral_only = jarvis.beliefs.get_by_topic("DELIVER")
        assert neutral_only is not None
        assert len(neutral_only.evidence) == 1, "neutral evidence is preserved"
        assert neutral_only.confidence == Confidence(0.0), (
            "a valence-less observation changes nothing (skipped by confidence)"
        )

    def test_neutral_and_supporting_equal_supporting_alone(self) -> None:
        base = Belief(statement=working_statement(_S1))
        base.add_evidence(_evidence("a plain supporting observation", weight=0.5))

        with_neutral = Belief(statement=working_statement(_S1))
        with_neutral.add_evidence(
            _evidence("a plain supporting observation", weight=0.5)
        )
        with_neutral.add_evidence(
            _evidence("observed no delivery at all", neutral=True, weight=0.9)
        )

        assert with_neutral.confidence == base.confidence
        assert with_neutral.stability == base.stability
        assert len(with_neutral.evidence) == 2


class TestEDifferentTopicIsolation:
    def test_deliver_and_a_concept_free_matter_stay_apart(self) -> None:
        jarvis = Jarvis()
        jarvis.think(_S1, evidence=[_evidence("observed a failed delivery", supports=False)])
        jarvis.think(
            _CONCEPT_FREE_B, evidence=[_evidence("observed an invoice mismatch")]
        )
        assert len(jarvis.beliefs.all_beliefs()) == 2
        assert jarvis.beliefs.get_by_topic("DELIVER") is not None
        assert jarvis.beliefs.get_by_topic(_CONCEPT_FREE_B) is not None

    def test_two_unrelated_concept_free_triggers_never_collide(self) -> None:
        jarvis = Jarvis()
        jarvis.think(_CONCEPT_FREE_A, evidence=[_evidence("observed drift")])
        jarvis.think(_CONCEPT_FREE_B, evidence=[_evidence("observed mismatch")])
        assert len(jarvis.beliefs.all_beliefs()) == 2


class TestFConceptFreeFallback:
    def test_raw_trigger_addressing_is_preserved(self) -> None:
        jarvis = Jarvis()
        jarvis.think("restarted", evidence=[_evidence("observed a restart")])
        jarvis.think(
            "restarted successfully", evidence=[_evidence("observed a clean restart")]
        )
        assert len(jarvis.beliefs.all_beliefs()) == 2, (
            "concept-free triggers address as their own raw trigger, not a shared topic"
        )
        first = jarvis.beliefs.get_by_statement(working_statement("restarted"))
        assert first is not None


class TestGPersistenceRoundTrip:
    def _unified(self, store: BeliefRepository) -> None:
        jarvis = Jarvis()
        _think_all(
            jarvis,
            (_S1, _S2),
            [
                _evidence("observed a failed delivery", supports=False),
                _evidence("observed a successful delivery"),
            ],
        )
        for belief in jarvis.beliefs.all_beliefs():
            store.save(belief)

    def test_in_memory_round_trip_of_the_unified_belief(self) -> None:
        store = InMemoryBeliefStore()
        self._unified(store)
        reloaded = store.get_by_topic("DELIVER")
        assert reloaded is not None
        assert len(reloaded.evidence) == 2
        assert len(reloaded.explain().contradicting) == 1
        assert len(reloaded.explain().supporting) == 1

    def test_json_round_trip_preserves_the_addressable_belief(self, tmp_path: Path) -> None:
        path = tmp_path / "beliefs.json"
        self._unified(JsonBeliefStore(path))

        reloaded = JsonBeliefStore(path)
        unified = reloaded.get_by_topic("DELIVER")
        assert unified is not None
        assert len(unified.evidence) == 2
        assert len(unified.explain().contradicting) == 1
        assert reloaded.get_by_statement(working_statement(_S1)) is not None

    def test_sqlite_round_trip_preserves_the_addressable_belief(self, tmp_path: Path) -> None:
        path = tmp_path / "jarvis.db"
        connection = sqlite3.connect(path)
        self._unified(SqliteBeliefStore(connection))
        connection.close()

        reloaded = SqliteBeliefStore(sqlite3.connect(path))
        unified = reloaded.get_by_topic("DELIVER")
        assert unified is not None
        assert len(unified.evidence) == 2
        assert len(unified.explain().contradicting) == 1


class TestHLegacyReconciliation:
    def fragments(self) -> list[Belief]:
        t1 = datetime(2026, 1, 3, tzinfo=UTC)
        t2 = datetime(2026, 1, 1, tzinfo=UTC)
        t3 = datetime(2026, 1, 2, tzinfo=UTC)
        s1 = Belief(statement=working_statement(_S1), formed_at=t1)
        s1.add_evidence(
            _evidence("observed a failed delivery", supports=False, observed_at=t1)
        )
        s2 = Belief(statement=working_statement(_S2), formed_at=t2)
        s2.add_evidence(_evidence("observed a successful delivery", observed_at=t2))
        s3 = Belief(statement=working_statement(_S4), formed_at=t3)
        s3.add_evidence(
            _evidence("observed no delivery at all", neutral=True, observed_at=t3)
        )
        return [s1, s2, s3]

    def test_fragments_reconstruct_one_topic_belief_without_loss(self, tmp_path: Path) -> None:
        store = JsonBeliefStore(tmp_path / "beliefs.json")
        fragments = self.fragments()
        for fragment in fragments:
            store.save(fragment)

        unified = store.get_by_topic("DELIVER")
        assert unified is not None
        assert unified.id == fragments[1].id, "leader = earliest formed_at (Jan 1)"
        assert unified.statement == fragments[1].statement
        assert len(unified.evidence) == 3, "every fragment's evidence survives"

    def test_reload_does_not_duplicate_evidence(self, tmp_path: Path) -> None:
        path = tmp_path / "beliefs.json"
        store = JsonBeliefStore(path)
        for fragment in self.fragments():
            store.save(fragment)
        unified = store.get_by_topic("DELIVER")
        assert unified is not None
        store.save(unified)

        again = JsonBeliefStore(path).get_by_topic("DELIVER")
        assert again is not None
        assert len(again.evidence) == 3, (
            "reconcile is a pure function: reloading and re-saving cannot duplicate"
        )
        assert again.id == unified.id

    def test_statements_remain_readable_after_reconciliation(self, tmp_path: Path) -> None:
        store = JsonBeliefStore(tmp_path / "beliefs.json")
        for fragment in self.fragments():
            store.save(fragment)
        assert store.get_by_statement(working_statement(_S2)) is not None
        assert store.get_by_statement(working_statement(_S4)) is not None

    def test_continued_episodes_evolve_the_reconciled_belief(self, tmp_path: Path) -> None:
        path = tmp_path / "beliefs.json"
        store = JsonBeliefStore(path)
        for fragment in self.fragments():
            store.save(fragment)
        unified = store.get_by_topic("DELIVER")
        assert unified is not None
        unified.add_evidence(_evidence("observed one more success"))
        store.save(unified)

        reloaded = JsonBeliefStore(path).get_by_topic("DELIVER")
        assert reloaded is not None
        assert len(reloaded.evidence) == 4


class TestIDeterministicRepresentative:
    def test_earliest_formed_at_wins(self) -> None:
        earlier = Belief(
            statement=working_statement("matter keep the original phrasing"),
            formed_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        later = Belief(
            statement=working_statement("matter rephrased afterwards"),
            formed_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
        for first, second in ((earlier, later), (later, earlier)):
            merged = reconcile_topic([first, second])
            assert merged is not None
            assert merged.id == earlier.id
            assert merged.statement == earlier.statement

    def test_statement_tie_break_is_lexical(self) -> None:
        a = Belief(
            statement=working_statement("beta phrasing"),
            formed_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        b = Belief(
            statement=working_statement("alpha phrasing"),
            formed_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        for first, second in ((a, b), (b, a)):
            merged = reconcile_topic([first, second])
            assert merged is not None
            assert merged.id == b.id, "lexical tie-break picks the earliest statement"


class TestKChronologicalEvidence:
    def test_four_pieces_keep_their_chronology(self) -> None:
        jarvis = Jarvis()
        day1 = datetime(2026, 1, 1, tzinfo=UTC)
        day2 = datetime(2026, 1, 2, tzinfo=UTC)
        day3 = datetime(2026, 1, 3, tzinfo=UTC)
        day4 = datetime(2026, 1, 4, tzinfo=UTC)
        _think_all(
            jarvis,
            (_S1, _S2, _S4, _S3),
            [
                _evidence("observed a failed delivery", supports=False, observed_at=day1),
                _evidence("observed a successful delivery", observed_at=day2),
                _evidence("observed no delivery at all", neutral=True, observed_at=day3),
                _evidence(
                    "observed a failed delivery again", supports=False, observed_at=day4
                ),
            ],
        )
        unified = jarvis.beliefs.get_by_topic("DELIVER")
        assert unified is not None
        stamps = [e.observed_at for e in unified.evidence]
        assert stamps == sorted(stamps), "evidence keeps its chronological order"
        assert unified.evidence[3].observed_at == day4

    def test_reconciliation_orders_evidence_chronologically(self) -> None:
        fragments = [
            Belief(
                statement=working_statement(_S2),
                formed_at=datetime(2026, 1, 2, tzinfo=UTC),
            ),
            Belief(
                statement=working_statement(_S1),
                formed_at=datetime(2026, 1, 1, tzinfo=UTC),
            ),
        ]
        fragments[0].add_evidence(
            _evidence(
                "observed a successful delivery",
                observed_at=datetime(2026, 1, 2, tzinfo=UTC),
            )
        )
        fragments[1].add_evidence(
            _evidence(
                "observed a failed delivery",
                supports=False,
                observed_at=datetime(2026, 1, 3, tzinfo=UTC),
            )
        )
        merged = reconcile_topic(fragments)
        assert merged is not None
        stamps = [e.observed_at for e in merged.evidence]
        assert stamps == sorted(stamps)


class TestLSemanticMemoryRegression:
    def test_recall_is_unaffected_by_unified_addressing(self) -> None:
        """the DELIVER unit's evidence is still recallable and the semantic store
        stays read-only (mirrors test_semantic_store_not_updated_by_think)."""
        from jarvis.domain.entities.semantic_memory import SemanticMemory
        from jarvis.infrastructure.in_memory_semantic_memory_store import (
            InMemorySemanticMemoryStore,
        )

        store = InMemorySemanticMemoryStore()
        memory = SemanticMemory(pattern="delivery promises tend to fail")
        memory.add_evidence(_evidence("supplier missed a promise", weight=0.5))
        store.save(memory)

        jarvis = Jarvis(enable_recall=True, semantic_memory_store=store)
        jarvis.think(_S1, evidence=[_evidence("observed a failed delivery", supports=False)])
        assert len(store.all_memories()) == 1, "think never writes the semantic store"
        recalled = jarvis.recall("supplier failed to deliver")
        assert any(m.kind.value == "semantic" for m in recalled)
        assert len(jarvis.beliefs.all_beliefs()) == 1


# -- registry-level guarantees ------------------------------------------------


class TestBeliefRegistry:
    def test_registry_indexes_one_belief_per_topic(self) -> None:
        store = InMemoryBeliefStore()
        fragments = TestHLegacyReconciliation().fragments()
        for fragment in fragments:
            store.save(fragment)
        registry = belief_registry(store.all_beliefs())
        assert set(registry) == {"DELIVER"}
        assert registry["DELIVER"].id == fragments[1].id
        index = store.get_by_topic("DELIVER")
        assert index is not None
        assert index.id == registry["DELIVER"].id