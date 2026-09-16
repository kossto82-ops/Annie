"""Negation v1 regression tests.

Recovers lost negation signal from contracted forms ("didn't" -> "did not")
before tokenization. Matter identity is untouched: negation only ever changes
polarity, never the signature -- because expansions insert only concept-free
words and the parity counter runs after expansion. Scope model: whole-input
parity of negation markers (no clause/sentence scoping).
"""
from jarvis.domain.services.abstraction import conceptual_tokens, episode_signature, valence
from jarvis.domain.services.topic_resolution import topic_id_of


def _sig(text: str) -> set[str]:
    return set(episode_signature(text))


class TestExplicitNegation:
    def test_did_not_fail_is_positive(self) -> None:
        assert _sig("supplier did not fail to deliver") == {"DELIVER", "FAIL"}
        assert valence("supplier did not fail to deliver") == "positive"

    def test_did_not_succeed_is_negative(self) -> None:
        assert valence("supplier did not succeed") == "negative"

    def test_never_marks_negation(self) -> None:
        assert valence("supplier never failed to deliver") == "positive"
        assert valence("supplier never succeeded") == "negative"

    def test_no_marks_negation(self) -> None:
        assert valence("supplier no longer succeeds") == "negative"

    def test_matter_only_negation_is_neutral(self) -> None:
        # No outcome token to flip: "not deliver" stays matter-only.
        assert _sig("supplier did not deliver") == {"DELIVER"}
        assert valence("supplier did not deliver") == "neutral"


class TestContractions:
    def test_didnt_fail_is_positive(self) -> None:
        assert _sig("supplier didn't fail to deliver") == {"DELIVER", "FAIL"}
        assert valence("supplier didn't fail to deliver") == "positive"

    def test_doesnt_fail_is_positive(self) -> None:
        assert valence("supplier doesn't fail") == "positive"
        assert _sig("supplier doesn't fail") == {"FAIL"}

    def test_contracted_success_openings_are_negative(self) -> None:
        assert valence("supplier didn't succeed") == "negative"
        assert valence("supplier doesn't succeed") == "negative"
        assert _sig("supplier didn't succeed") == {"SUCCEED"}

    def test_contracted_matter_only_is_neutral(self) -> None:
        for phrase in (
            "supplier didn't deliver",
            "supplier can't deliver",
            "supplier don't deliver",
        ):
            assert _sig(phrase) == {"DELIVER"}, phrase
            assert valence(phrase) == "neutral", phrase

    def test_wont_deliver_is_neutral_matter_only(self) -> None:
        # Without expansion the tokenizer splits "won't" -> "won" -> SUCCEED,
        # injecting false positive matter. Expansion must keep it {DELIVER}.
        assert _sig("supplier won't deliver") == {"DELIVER"}
        assert valence("supplier won't deliver") == "neutral"

    def test_unsupported_successful_stays_neutral_by_lexicon(self) -> None:
        # "successful" carries no SUCCEED matter in the current vocabulary, so
        # negation has no outcome token to flip: neutral is the documented
        # result (a lexical gap in the SUCCEED family, not a negation defect).
        for phrase in (
            "supplier isn't successful",
            "supplier wasn't successful",
            "supplier weren't successful",
        ):
            assert "SUCCEED" not in _sig(phrase), phrase
            assert valence(phrase) == "neutral", phrase


class TestDoubleNegation:
    def test_double_negation_is_positive(self) -> None:
        assert valence("supplier did not fail") == "positive"
        assert valence("supplier didn't fail") == "positive"
        assert valence("supplier did not fail to deliver") == "positive"
        assert valence("supplier didn't fail to deliver") == "positive"

    def test_contract_and_full_forms_agree(self) -> None:
        pairs = [
            ("supplier did not fail to deliver", "supplier didn't fail to deliver"),
            ("supplier did not succeed", "supplier didn't succeed"),
            ("supplier did not deliver", "supplier didn't deliver"),
        ]
        for explicit, contracted in pairs:
            assert _sig(explicit) == _sig(contracted), (explicit, contracted)
            assert valence(explicit) == valence(contracted), (explicit, contracted)


class TestMatterOrthogonality:
    def test_negation_never_enters_signature(self) -> None:
        assert conceptual_tokens("supplier didn't deliver") == frozenset({"DELIVER"})
        assert conceptual_tokens("didn't") == frozenset()
        assert conceptual_tokens("won't") == frozenset()

    def test_negation_preserves_matter_identity(self) -> None:
        assert _sig("supplier failed to deliver") == _sig(
            "supplier did not fail to deliver"
        ) == _sig("supplier didn't fail to deliver") == {"DELIVER", "FAIL"}

    def test_polarity_axis_orthogonal_to_matter(self) -> None:
        assert _sig("supplier failed to deliver") != _sig(
            "supplier succeeded in delivering"
        )
        assert valence("supplier failed to deliver") == "negative"
        assert valence("supplier did not fail to deliver") == "positive"
        assert valence("supplier succeeded in delivering") == "positive"


class TestTopicIdentity:
    def test_negation_does_not_create_a_topic(self) -> None:
        assert topic_id_of("supplier failed to deliver") == "DELIVER > FAIL"
        assert topic_id_of("supplier did not fail to deliver") == "DELIVER > FAIL"
        assert topic_id_of("supplier didn't fail to deliver") == "DELIVER > FAIL"

    def test_outcome_topics_stay_separate(self) -> None:
        assert topic_id_of("supplier succeeded in delivering") == "DELIVER > SUCCEED"
        assert topic_id_of("supplier failed to deliver") != topic_id_of(
            "supplier succeeded in delivering"
        )


class TestParity:
    def test_marker_parity_is_preserved(self) -> None:
        assert valence("he never not failed") == "negative"  # two markers, even
        assert valence("he didn't never fail") == "negative"
        assert valence("he has not succeeded") == "negative"