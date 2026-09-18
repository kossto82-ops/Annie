"""Polarity Axis v1 -- implementation acceptance tests for Decision B.

Decision B (architecture gate, pass with findings): topic identity is
aboutness-only; polarity lives in evidence.  ``signature_of`` is the identity
projection -- aboutness concepts without the outcome tokens FAIL/SUCCEED --
while ``conceptual_tokens`` retains polarity for semantic-memory clustering and
pattern keys, and ``valence`` keeps reading the evidence.  So:

- Test 1  -- ``succeeded in delivering`` keeps its aboutness (DELIVER); the
             SUCCEED marker is preserved in evidence, not identity.
- Test 2  -- ``delivered`` is a dimension token.
- Test 3  -- ``delivering`` is a dimension token (no accidental SUCCEED).
- Test 4  -- ``succeeded in paying`` composition is a regression test.
- Test 5  -- negative critical pair: identity is DELIVER, polarity is evidence.
- Test 6  -- negated positive pair: polarity orthogonal to aboutness.
- Test 7  -- positive outcome critical pair: identity DELIVER, polarity positive.
- Test 8  -- outcome topics converge: failed and succeeded are ONE DELIVER topic.
- Test 9  -- the positive query still recalls the negative pattern (evidence).
- Corpus -- the gate's 13 regression examples: identity projection, evidence
             tokens, and valence.
- I*-guards -- the architectural invariants, where cheap to pin directly.
"""
from __future__ import annotations

from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.services.abstraction import conceptual_tokens, valence
from jarvis.domain.services.topic_resolution import resolve_episodes, signature_of
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.temporal_stability import TemporalStability
from jarvis.infrastructure.lexical_memory_retriever import concept_relevance


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
        assert signature_of("succeeded in delivering") == frozenset({"DELIVER"})

    def test_the_succeed_marker_lives_in_evidence(self):
        # Identity is aboutness-only; the positive marker stays in evidence.
        assert conceptual_tokens("succeeded in delivering") == frozenset(
            {"DELIVER", "SUCCEED"}
        )


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
        assert signature_of("succeeded in paying") == frozenset({"COST"})
        assert conceptual_tokens("succeeded in paying") == frozenset({"COST", "SUCCEED"})

    def test_succeeded_in_on_time_keeps_time(self):
        assert signature_of("succeeded in delivering on time") == frozenset(
            {"DELIVER", "TIME"}
        )
        assert conceptual_tokens("succeeded in delivering on time") == frozenset(
            {"DELIVER", "SUCCEED", "TIME"}
        )


class TestCriticalPairs:
    def test_negative_pair_unchanged(self):
        assert signature_of("supplier failed to deliver") == frozenset({"DELIVER"})
        assert conceptual_tokens("supplier failed to deliver") == frozenset(
            {"DELIVER", "FAIL"}
        )
        assert valence("supplier failed to deliver") == "negative"

    def test_negated_positive_pair_is_polarity_orthogonal(self):
        assert signature_of("supplier did not fail to deliver") == frozenset({"DELIVER"})
        assert valence("supplier did not fail to deliver") == "positive"

    def test_positive_outcome_pair(self):
        assert signature_of("supplier succeeded in delivering") == frozenset({"DELIVER"})
        assert valence("supplier succeeded in delivering") == "positive"


class TestTopicConvergence:
    def test_outcome_forms_share_one_aboutness_topic(self):
        topics = resolve_episodes(
            [
                _external("1", "supplier failed to deliver"),
                _external("2", "supplier succeeded in delivering"),
            ]
        )
        # Identity is aboutness: fail/succeed never fork the topic (Decision B).
        assert [t.topic_id for t in topics] == ["DELIVER"]
        assert [t.canonical_signature for t in topics] == [frozenset({"DELIVER"})]
        assert topics[0].source_episode_ids == ("1", "2")


class TestSemanticRecall:
    def test_positive_query_recalls_negative_pattern(self):
        # Evidence tokens {DELIVER, SUCCEED} ∩ {DELIVER, FAIL} = {DELIVER} -> > 0.
        assert concept_relevance("succeeded in delivering", "recurrence: DELIVER, FAIL") > 0


class TestRegressionCorpus:
    """The gate's 13 regression examples: identity, evidence tokens, valence."""

    CASES: list[tuple[str, frozenset[str], frozenset[str], str]] = [
        (
            "supplier failed to deliver",
            frozenset({"DELIVER"}),
            frozenset({"DELIVER", "FAIL"}),
            "negative",
        ),
        (
            "supplier did not fail to deliver",
            frozenset({"DELIVER"}),
            frozenset({"DELIVER", "FAIL"}),
            "positive",
        ),
        (
            "supplier succeeded in delivering",
            frozenset({"DELIVER"}),
            frozenset({"DELIVER", "SUCCEED"}),
            "positive",
        ),
        (
            "supplier delivered",
            frozenset({"DELIVER"}),
            frozenset({"DELIVER"}),
            "neutral",
        ),
        (
            "supplier delivered on time",
            frozenset({"DELIVER", "TIME"}),
            frozenset({"DELIVER", "TIME"}),
            "neutral",
        ),
        (
            "supplier failed to pay",
            frozenset({"COST"}),
            frozenset({"COST", "FAIL"}),
            "negative",
        ),
        (
            "supplier succeeded in paying",
            frozenset({"COST"}),
            frozenset({"COST", "SUCCEED"}),
            "positive",
        ),
        (
            "customer failed to deliver",
            frozenset({"DELIVER"}),
            frozenset({"DELIVER", "FAIL"}),
            "negative",
        ),
        (
            "the vendor missed the delivery deadline",
            frozenset({"DELIVER", "TIME"}),
            frozenset({"DELIVER", "FAIL", "TIME"}),
            "negative",
        ),
        (
            "supplier failed to respond",
            frozenset(),
            frozenset({"FAIL"}),
            "negative",
        ),
        ("supplier failed to refund", frozenset(), frozenset({"FAIL"}), "negative"),
        ("supplier did not succeed", frozenset(), frozenset({"SUCCEED"}), "negative"),
        (
            "supplier didn't deliver",
            frozenset({"DELIVER"}),
            frozenset({"DELIVER"}),
            "neutral",
        ),
    ]

    def test_corpus_identity_signature(self):
        for trigger, expected_identity, _tokens, _valence in self.CASES:
            assert signature_of(trigger) == expected_identity, trigger

    def test_corpus_evidence_and_valence(self):
        for trigger, _identity, expected_tokens, expected_valence in self.CASES:
            assert conceptual_tokens(trigger) == expected_tokens, trigger
            assert valence(trigger) == expected_valence, trigger


class TestAGuards:
    def test_outcome_distinction_lives_in_evidence(self):
        assert conceptual_tokens("supplier failed to deliver") != conceptual_tokens(
            "supplier succeeded in delivering"
        )

    def test_actor_independence(self):
        assert signature_of("supplier failed to deliver") == signature_of(
            "customer failed to deliver"
        )

    def test_founder_anchor_unaffected(self):
        # A nested join keeps the founder universal: the {DELIVER, TIME} matter
        # absorbs the broader mention {DELIVER, TIME, COST}.
        topics = resolve_episodes(
            [
                _external("1", "supplier delivered on time"),
                _external("2", "the delayed delivery cost us"),
            ]
        )
        assert len(topics) == 1
        assert topics[0].topic_id == "DELIVER > TIME"

    def test_determinism(self):
        text = "supplier succeeded in delivering"
        assert signature_of(text) == signature_of(text)
        assert conceptual_tokens(text) == conceptual_tokens(text)