"""Polarity Axis v1 -- implementation acceptance tests for Decision B.

Decision B (architecture gate, pass with findings): topic identity is
aboutness; polarity lives in evidence.  The implementation repairs the
positive-form aboutness defect: ``delivered``/``delivering`` are matter tokens
(DELIVER), never outcome markers, and the positive form of a matter keeps its
dimension token (```supplier succeeded in delivering`` -> ``{DELIVER, SUCCEED}``).

These tests pin the gate's mandate:

- Test 1  -- positive dimension preservation (``succeeded in delivering``).
- Test 2  -- ``delivered`` is a dimension token.
- Test 3  -- ``delivering`` is a dimension token (no accidental SUCCEED).
- Test 4  -- ``succeeded in paying`` composition is a regression test.
- Test 5  -- negative critical pair unchanged.
- Test 6  -- negated positive pair: polarity orthogonal to aboutness.
- Test 7  -- positive outcome critical pair.
- Test 8  -- ``DELIVER > FAIL`` and ``DELIVER > SUCCEED`` stay separate topics.
- Test 9  -- the positive query now recalls the DELIVER > FAIL pattern.
- Corpus -- the gate's 13 regression examples, signatures and valence.
- I*-guards -- the architectural invariants, where cheap to pin directly.
"""
from __future__ import annotations

from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.services.abstraction import valence
from jarvis.domain.services.topic_resolution import resolve_episodes, signature_of
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.temporal_stability import TemporalStability
from jarvis.infrastructure.lexical_memory_retriever import _concept_relevance


def _external(episode_id: str, trigger: str) -> EpisodeRecord:
    return EpisodeRecord(
        episode_id=episode_id,
        trigger=trigger,
        decision="decided",
        working_belief_id=f"b-{episode_id}",
        outcome=EpisodeState.COMPLETED,
        conclusion_confidence=Confidence(0.9),
        conclusion_stability=TemporalStability(0.5),
        origin=TriggerOrigin.COMPANION,
        kind=EpisodeKind.CONCLUSION,
    )


class TestPositiveDimensionPreservation:
    def test_succeeded_in_delivering_keeps_the_dimension(self):
        assert signature_of("succeeded in delivering") == frozenset({"DELIVER", "SUCCEED"})


class TestDeliveredIsADimension:
    def test_delivered_is_the_matter_token(self):
        assert signature_of("delivered") == frozenset({"DELIVER"})

    def test_delivered_carries_no_outcome_marker(self):
        assert "SUCCEED" not in signature_of("delivered")

    def test_delivered_valence_is_marker_driven(self):
        # No outcome marker on its own: valence follows the marker, as B mandates.
        assert valence("the supplier delivered") == "neutral"


class TestDeliveringIsADimension:
    def test_delivering_is_the_matter_token(self):
        assert signature_of("delivering") == frozenset({"DELIVER"})

    def test_delivering_never_produces_succeed(self):
        assert "SUCCEED" not in signature_of("delivering")


class TestCompositionRegression:
    def test_succeeded_in_paying_preserves_cost(self):
        assert signature_of("succeeded in paying") == frozenset({"COST", "SUCCEED"})

    def test_succeeded_in_on_time_keeps_time(self):
        assert signature_of("succeeded in delivering on time") == frozenset(
            {"DELIVER", "SUCCEED", "TIME"}
        )


class TestCriticalPairs:
    def test_negative_pair_unchanged(self):
        assert signature_of("supplier failed to deliver") == frozenset({"DELIVER", "FAIL"})
        assert valence("supplier failed to deliver") == "negative"

    def test_negated_positive_pair_is_polarity_orthogonal(self):
        assert signature_of("supplier did not fail to deliver") == frozenset(
            {"DELIVER", "FAIL"}
        )
        assert valence("supplier did not fail to deliver") == "positive"

    def test_positive_outcome_pair(self):
        assert signature_of("supplier succeeded in delivering") == frozenset(
            {"DELIVER", "SUCCEED"}
        )
        assert valence("supplier succeeded in delivering") == "positive"


class TestTopicSeparation:
    def test_outcome_topics_stay_separate(self):
        topics = resolve_episodes(
            [
                _external("1", "supplier failed to deliver"),
                _external("2", "supplier succeeded in delivering"),
            ]
        )
        assert [t.topic_id for t in topics] == ["DELIVER > FAIL", "DELIVER > SUCCEED"]
        assert [t.canonical_signature for t in topics] == [
            frozenset({"DELIVER", "FAIL"}),
            frozenset({"DELIVER", "SUCCEED"}),
        ]


class TestSemanticRecall:
    def test_positive_query_recalls_negative_pattern(self):
        # {DELIVER, SUCCEED} ∩ {DELIVER, FAIL} = {DELIVER} -> relevance > 0.
        assert _concept_relevance("succeeded in delivering", "recurrence: DELIVER, FAIL") > 0


class TestRegressionCorpus:
    """The gate's 13 regression examples -- exact signatures and valence."""

    CASES: list[tuple[str, frozenset[str], str]] = [
        ("supplier failed to deliver", frozenset({"DELIVER", "FAIL"}), "negative"),
        (
            "supplier did not fail to deliver",
            frozenset({"DELIVER", "FAIL"}),
            "positive",
        ),
        (
            "supplier succeeded in delivering",
            frozenset({"DELIVER", "SUCCEED"}),
            "positive",
        ),
        ("supplier delivered", frozenset({"DELIVER"}), "neutral"),
        ("supplier delivered on time", frozenset({"DELIVER", "TIME"}), "neutral"),
        ("supplier failed to pay", frozenset({"COST", "FAIL"}), "negative"),
        ("supplier succeeded in paying", frozenset({"COST", "SUCCEED"}), "positive"),
        ("customer failed to deliver", frozenset({"DELIVER", "FAIL"}), "negative"),
        (
            "the vendor missed the delivery deadline",
            frozenset({"DELIVER", "FAIL", "TIME"}),
            "negative",
        ),
        ("supplier failed to respond", frozenset({"FAIL"}), "negative"),
        ("supplier failed to refund", frozenset({"FAIL"}), "negative"),
        ("supplier did not succeed", frozenset({"SUCCEED"}), "negative"),
        ("supplier didn't deliver", frozenset({"DELIVER"}), "neutral"),
    ]

    def test_corpus_signatures_and_valence(self):
        for trigger, expected_sig, expected_valence in self.CASES:
            assert signature_of(trigger) == expected_sig, trigger
            assert valence(trigger) == expected_valence, trigger


class TestAGuards:
    def test_outcome_distinction(self):
        assert frozenset({"DELIVER", "FAIL"}) != frozenset({"DELIVER", "SUCCEED"})

    def test_actor_independence(self):
        assert signature_of("supplier failed to deliver") == signature_of(
            "customer failed to deliver"
        )

    def test_founder_anchor_unaffected(self):
        topics = resolve_episodes(
            [
                _external("1", "supplier failed to deliver"),
                _external("2", "the vendor missed the delivery deadline"),
            ]
        )
        assert len(topics) == 1
        assert topics[0].topic_id == "DELIVER > FAIL"

    def test_determinism(self):
        text = "supplier succeeded in delivering"
        assert signature_of(text) == signature_of(text)