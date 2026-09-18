"""Polarity semantics gate v1: H3 + H4 + M1 corrections, M2 preserved.

Focused tests for the implementation gate (2026-09-18), after the audit verdict
PASS WITH FINDINGS:

- **H3 — negation handling**: cannot/can't/couldn't/shouldn't/wouldn't/mustn't
  normalize to their negated forms and flip explicit polarity correctly, while
  "won't" (already correct) stays stable.
- **H4 — cross-layer consistency**: the keyword perception seam reads the
  abstraction layer's single normalization contract and agrees with it on
  polarity/evidence direction (no second negation interpretation).
- **M1 — vocabulary correction**: action/state verbs (restart/restarted/...) no
  longer fabricate SUCCEED matter; success must be explicit ("successfully").
- **M2 — preservation**: negated dimension verbs stay neutral in valence and in
  evidence, and are skipped by confidence.
"""
from datetime import UTC, datetime

from jarvis.domain.enums.episode_kind import EpisodeKind
from jarvis.domain.enums.episode_state import EpisodeState
from jarvis.domain.enums.trigger_origin import TriggerOrigin
from jarvis.domain.services.abstraction import (
    abstract_patterns,
    conceptual_tokens,
    episode_signature,
    valence,
)
from jarvis.domain.services.topic_resolution import signature_of, topic_id_of
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.episode_record import EpisodeRecord
from jarvis.domain.value_objects.temporal_stability import TemporalStability
from jarvis.infrastructure.keyword_perception import KeywordPerception


def _ep(trigger: str) -> EpisodeRecord:
    """Helper to create a COMPANION episode record from a trigger string."""
    return EpisodeRecord(
        episode_id=f"ep-{hash(trigger) & 0xFFFFFFFF:08x}",
        trigger=trigger,
        decision="concluded",
        working_belief_id="b1",
        outcome=EpisodeState.COMPLETED,
        conclusion_confidence=Confidence(0.7),
        conclusion_stability=TemporalStability(0.7),
        origin=TriggerOrigin.COMPANION,
        kind=EpisodeKind.CONCLUSION,
        recorded_at=datetime.now(UTC),
    )


class TestNegatedPolarity:
    """H3: negation of an explicit polarity cue flips its direction."""

    def test_negated_polarity_matrix(self) -> None:
        cases = {
            "did not fail": "positive",
            "did not succeed": "negative",
            "cannot fail": "positive",
            "cannot succeed": "negative",
            "can't fail": "positive",
            "can't succeed": "negative",
            "couldn't fail": "positive",
            "couldn't succeed": "negative",
            "shouldn't fail": "positive",
            "shouldn't succeed": "negative",
            "wouldn't fail": "positive",
            "wouldn't succeed": "negative",
            "won't fail": "positive",
            "won't succeed": "negative",
            "never fail": "positive",
            "never succeed": "negative",
            "mustn't fail": "positive",
            "mustn't succeed": "negative",
        }
        for phrase, expected in cases.items():
            assert valence(phrase) == expected, phrase

    def test_cannot_was_a_missing_marker(self) -> None:
        # Regression: "cannot" was absent from the marker set, so "cannot fail"
        # read negative and "cannot succeed" read positive (both wrong).
        assert valence("cannot fail") == "positive"
        assert valence("cannot succeed") == "negative"

    def test_contracted_and_full_forms_agree(self) -> None:
        # Every contracted form must normalize to the same reading as its
        # explicit spelling (the gate's normalization target table).
        pairs = [
            ("did not fail", "didn't fail"),
            ("did not succeed", "didn't succeed"),
            ("cannot fail", "can't fail"),
            ("cannot succeed", "can't succeed"),
            ("could not fail", "couldn't fail"),
            ("could not succeed", "couldn't succeed"),
            ("should not fail", "shouldn't fail"),
            ("should not succeed", "shouldn't succeed"),
            ("would not fail", "wouldn't fail"),
            ("would not succeed", "wouldn't succeed"),
            ("must not fail", "mustn't fail"),
            ("must not succeed", "mustn't succeed"),
            ("will not fail", "won't fail"),
            ("will not succeed", "won't succeed"),
        ]
        for full, contracted in pairs:
            assert valence(full) == valence(contracted), (full, contracted)
            assert conceptual_tokens(full) == conceptual_tokens(contracted), (
                full,
                contracted,
            )

    def test_parity_still_holds_across_new_markers(self) -> None:
        assert valence("he never not failed") == "negative"
        assert valence("he didn't never fail") == "negative"
        assert valence("he has not succeeded") == "negative"


class TestNegatedDimensionVerbs:
    """M2: negation of a dimension verb must never manufacture an outcome."""

    def test_negated_dimension_verbs_stay_neutral(self) -> None:
        phrases = (
            "didn't deliver",
            "never delivered",
            "shouldn't deliver",
            "did not respond",
            "didn't refund",
            "didn't arrive",
            "didn't pay",
        )
        for phrase in phrases:
            assert valence(phrase) == "neutral", phrase
            assert "FAIL" not in conceptual_tokens(phrase), phrase
            assert "SUCCEED" not in conceptual_tokens(phrase), phrase

    def test_matter_still_survives_the_negation(self) -> None:
        # Matter identity is untouched: negation never enters the signature.
        assert conceptual_tokens("supplier didn't deliver") == frozenset({"DELIVER"})
        assert episode_signature("supplier didn't deliver") == frozenset({
            "DELIVER"
        })

    def test_neutral_episodes_stay_neutral_in_semantic_memory(self) -> None:
        memories = abstract_patterns(
            [
                _ep("the supplier didn't deliver"),
                _ep("the supplier never delivered"),
                _ep("the supplier shouldn't have delivered late"),
            ],
            min_sources=3,
        )
        assert len(memories) == 1
        memory = memories[0]
        assert memory.pattern == "recurrence: DELIVER"
        assert all(e.is_neutral for e in memory.evidence)
        # Neutral evidence contributes no supporting mass: the pattern derives
        # no confidence from un-poled observations (it reads the same as a
        # memory with no directional support at all).
        assert memory.confidence.value == 0.0

    def test_polar_episodes_still_reinforce_in_semantic_memory(self) -> None:
        # Contrast: explicit failure readings are directional, not neutral.
        memories = abstract_patterns(
            [
                _ep("the supplier failed to deliver"),
                _ep("the supplier missed the delivery"),
                _ep("the delivery was broken"),
            ],
            min_sources=3,
        )
        assert len(memories) == 1
        memory = memories[0]
        assert any(not e.is_neutral for e in memory.evidence)


class TestActionStateNeutrality:
    """M1: action/state verbs carry no SUCCEED matter unless success is explicit."""

    def test_action_and_state_verbs_are_neutral(self) -> None:
        for phrase in (
            "restart",
            "restarted",
            "restarting",
            "resumed",
            "recovered",
            "fixed",
            "worked again",
            "the server was restarted",
        ):
            assert valence(phrase) == "neutral", phrase
            assert "SUCCEED" not in conceptual_tokens(phrase), phrase

    def test_explicit_success_modifier_wins(self) -> None:
        assert valence("restarted successfully") == "positive"
        assert valence("fixed successfully") == "positive"
        assert conceptual_tokens("restarted successfully") == frozenset({"SUCCEED"})

    def test_explicit_failure_modifier_wins(self) -> None:
        assert valence("restarted but later failed") == "negative"
        assert conceptual_tokens("restarted but later failed") == frozenset({"FAIL"})


class TestCrossLayerAgreement:
    """H4: abstraction and keyword perception read the same phrase the same way."""

    def test_polarity_direction_agrees(self) -> None:
        # phrase -> (valence, expected supports, expected is_neutral) for the
        # perception reading of "the delivery definitely <phrase>".
        cases = {
            "cannot fail": ("positive", True, False),
            "cannot succeed": ("negative", False, False),
            "can't fail": ("positive", True, False),
            "can't succeed": ("negative", False, False),
            "didn't deliver": ("neutral", True, True),
            "never delivered": ("neutral", True, True),
            "shouldn't deliver": ("neutral", True, True),
            "restarted": ("neutral", True, False),
            "restarted successfully": ("positive", True, False),
        }
        perception = KeywordPerception()
        for phrase, (polar, exp_supports, exp_neutral) in cases.items():
            assert valence(phrase) == polar, phrase
            cued = f"the delivery definitely {phrase}"
            perceived = perception.perceive(cued)
            assert len(perceived) == 1, phrase
            evidence = perceived[0]
            assert evidence.supports is exp_supports, phrase
            assert evidence.is_neutral is exp_neutral, phrase

    def test_negated_outcome_flips_but_negated_action_does_not(self) -> None:
        perception = KeywordPerception()
        # Outcome verb: negation flips polarity and perception follows it.
        outcome = perception.perceive("the delivery definitely didn't fail")
        assert len(outcome) == 1 and outcome[0].supports is True
        assert valence("didn't fail") == "positive"
        # Action/state verb: no polarity to flip; the layers agree there is none,
        # and the uncued negation reads as a plain denial (contradiction).
        state = perception.perceive("the server definitely wasn't restarted")
        assert len(state) == 1 and state[0].supports is False
        assert valence("wasn't restarted") == "neutral"
        assert conceptual_tokens("wasn't restarted") == frozenset()

    def test_generic_denial_still_contradicts(self) -> None:
        # Non-polar, matter-less verbs keep the perception seam's denial
        # semantics: this is affirmation/denial detection, not polarity analysis.
        perception = KeywordPerception()
        evidence = perception.perceive("this is definitely not the base case")
        assert evidence[0].supports is False
        assert evidence[0].is_neutral is False
        # And the abstraction is orthogonal: valence has nothing to say either.
        assert valence("not the base case") == "neutral"


class TestTopicIdentityUnaffected:
    def test_outcome_forms_share_one_aboutness_topic(self) -> None:
        assert topic_id_of("supplier failed to deliver") == "DELIVER"
        assert topic_id_of("supplier succeeded in delivering") == "DELIVER"
        assert topic_id_of("supplier didn't deliver") == "DELIVER"

    def test_action_verbs_leak_no_polarity_into_aboutness(self) -> None:
        # M1: after removing the false SUCCEED reading, neither form carries any
        # aboutness matter (SUCCEED is projected out of identity anyway), so two
        # concept-free triggers never collapse into one topic.
        assert signature_of("restarted") == frozenset()
        assert signature_of("restarted successfully") == frozenset()
        assert topic_id_of("restarted") != topic_id_of("restarted successfully")