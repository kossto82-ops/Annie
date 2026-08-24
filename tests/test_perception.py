"""Tests for the perception seam: raw observation → evidence (Vision §32, §8, §37)."""

from __future__ import annotations

from jarvis import Jarvis
from jarvis.domain.perception.perception_source import PerceptionSource
from jarvis.infrastructure.keyword_perception import KeywordPerception


class TestKeywordPerception:
    def test_it_satisfies_the_perception_source_protocol(self) -> None:
        assert isinstance(KeywordPerception(), PerceptionSource)

    def test_a_recognised_cue_becomes_supporting_evidence(self) -> None:
        evidence = KeywordPerception().perceive("This is definitely the base case")
        assert len(evidence) == 1
        assert evidence[0].supports is True
        assert evidence[0].weight.value == 1.0

    def test_a_negated_cue_becomes_contradicting_evidence(self) -> None:
        evidence = KeywordPerception().perceive("This is definitely not the base case")
        assert len(evidence) == 1
        assert evidence[0].supports is False

    def test_a_weaker_cue_carries_less_weight(self) -> None:
        strong = KeywordPerception().perceive("clearly true")[0].weight.value
        weak = KeywordPerception().perceive("maybe true")[0].weight.value
        assert weak < strong

    def test_an_observation_with_no_cue_is_not_perceived(self) -> None:
        assert KeywordPerception().perceive("the sky is a colour") == ()

    def test_an_empty_observation_is_not_perceived(self) -> None:
        assert KeywordPerception().perceive("   ") == ()

    def test_perceived_evidence_stamps_the_cue_as_provenance(self) -> None:
        evidence = KeywordPerception().perceive("this is definitely sound")
        assert evidence[0].context == "perceived via the cue 'definitely'"

    def test_a_multi_cue_observation_yields_one_evidence_per_cue(self) -> None:
        evidence = KeywordPerception().perceive(
            "the base case is definitely right but the step is maybe not ready"
        )
        assert len(evidence) == 2
        definitely, maybe = evidence
        assert definitely.weight.value == 1.0 and definitely.supports is True
        assert maybe.weight.value == 0.3 and maybe.supports is False
        assert definitely.context == "perceived via the cue 'definitely'"
        assert maybe.context == "perceived via the cue 'maybe'"

    def test_the_provenance_shows_in_the_belief_narration(self) -> None:
        jarvis = Jarvis()
        episode = jarvis.perceive("the approach is definitely sound")
        explanation = episode.explain()
        assert explanation is not None
        assert "perceived via the cue 'definitely'" in explanation.narrate()


class TestJarvisPerceive:
    def test_a_cue_bearing_observation_grounds_a_belief(self) -> None:
        jarvis = Jarvis()
        episode = jarvis.perceive("the approach is definitely sound")
        belief = episode.working_belief
        assert belief is not None
        assert belief.confidence.value >= 0.5

    def test_an_unperceived_observation_yields_an_honest_insufficient_conclusion(self) -> None:
        jarvis = Jarvis()
        episode = jarvis.perceive("a plain statement with no certainty cue")
        assert episode.result is not None
        assert "Insufficient evidence" in episode.result

    def test_a_custom_perception_source_can_be_injected(self) -> None:
        class SilentPerception:
            def perceive(self, observation: str) -> tuple[()]:
                return ()

        jarvis = Jarvis(perception=SilentPerception())
        episode = jarvis.perceive("the approach is definitely sound")
        assert episode.result is not None
        assert "Insufficient evidence" in episode.result


class TestPerceiveAboutCompanion:
    _TRAIT = "prefers simplicity"

    def test_a_perceived_observation_builds_a_companion_belief(self) -> None:
        jarvis = Jarvis()
        belief = jarvis.perceive_about_companion(
            self._TRAIT, "you definitely prefer simplicity"
        )
        assert belief is not None and belief.confidence.value >= 0.5
        assert jarvis.companion.belief_about(self._TRAIT) is belief
        assert self._TRAIT in jarvis.explain_companion(self._TRAIT)

    def test_a_perceived_denial_contradicts_the_belief(self) -> None:
        jarvis = Jarvis()
        jarvis.perceive_about_companion(self._TRAIT, "you definitely prefer simplicity")
        jarvis.perceive_about_companion(self._TRAIT, "you definitely prefer simplicity")
        strong = jarvis.companion.belief_about(self._TRAIT)
        assert strong is not None
        high = strong.confidence.value

        jarvis.perceive_about_companion(self._TRAIT, "you definitely do not prefer simplicity")
        weakened = jarvis.companion.belief_about(self._TRAIT)
        assert weakened is not None
        assert weakened.confidence.value < high

    def test_an_unperceived_observation_leaves_the_model_untouched(self) -> None:
        jarvis = Jarvis()
        result = jarvis.perceive_about_companion(self._TRAIT, "the weather is nice today")
        assert result is None
        assert jarvis.companion.belief_about(self._TRAIT) is None
