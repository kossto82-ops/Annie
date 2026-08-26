"""Tests for the LLM→perception seam (Vision §32, §38) — no live API involved."""

from __future__ import annotations

import json

from jarvis import Jarvis
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.perception.perception_source import PerceptionSource
from jarvis.infrastructure.language_model import LanguageModel
from jarvis.infrastructure.llm_perception import LlmPerception
from jarvis.infrastructure.scripted_language_model import ScriptedLanguageModel


def _model(claims: list[object]) -> ScriptedLanguageModel:
    return ScriptedLanguageModel(default=json.dumps(claims))


class TestSeamContracts:
    def test_the_stub_is_a_language_model(self) -> None:
        assert isinstance(ScriptedLanguageModel(), LanguageModel)

    def test_llm_perception_is_a_perception_source(self) -> None:
        assert isinstance(LlmPerception(ScriptedLanguageModel()), PerceptionSource)


class TestLlmPerception:
    def test_it_turns_model_claims_into_evidence(self) -> None:
        model = _model(
            [
                {"content": "the deal is closing", "supports": True, "weight": 0.9},
                {"content": "the client is unhappy", "supports": False, "weight": 0.4},
            ]
        )
        evidence = LlmPerception(model).perceive("some report")
        assert len(evidence) == 2
        assert evidence[0].content == "the deal is closing"
        assert evidence[0].supports is True
        assert evidence[0].weight.value == 0.9
        assert evidence[0].source is EvidenceSource.EXTERNAL_SOURCE
        assert evidence[0].context == "perceived via language model"
        assert evidence[1].supports is False

    def test_an_empty_observation_calls_no_model(self) -> None:
        evidence = LlmPerception(ScriptedLanguageModel(default="boom")).perceive("   ")
        assert evidence == ()

    def test_unreadable_model_output_yields_silence(self) -> None:
        evidence = LlmPerception(ScriptedLanguageModel(default="not json")).perceive("x")
        assert evidence == ()

    def test_no_claims_yields_silence(self) -> None:
        assert LlmPerception(_model([])).perceive("small talk") == ()

    def test_malformed_claims_are_skipped_not_fabricated(self) -> None:
        model = _model(
            [
                {"content": "valid", "supports": True, "weight": 0.8},
                {"content": "", "weight": 0.8},  # empty content
                {"content": "bad weight", "weight": 5},  # out of range
                {"content": "no weight"},  # missing weight
                "not an object",
            ]
        )
        evidence = LlmPerception(model).perceive("mixed")
        assert [e.content for e in evidence] == ["valid"]


class TestJarvisWithAnLlmPerceiver:
    def test_a_provider_is_a_drop_in_perception_source(self) -> None:
        model = _model([{"content": "the market is rising", "supports": True, "weight": 0.9}])
        jarvis = Jarvis(perception=LlmPerception(model))
        episode = jarvis.perceive("today's market note")
        belief = episode.working_belief
        assert belief is not None
        assert belief.confidence.value > 0.0

    def test_swapping_the_model_needs_no_core_change(self) -> None:
        # The same LlmPerception, two different models -> two different readings,
        # with no change anywhere in Jarvis or the domain.
        optimist = _model([{"content": "growth ahead", "supports": True, "weight": 0.9}])
        skeptic = _model([{"content": "growth ahead", "supports": False, "weight": 0.9}])

        a = Jarvis(perception=LlmPerception(optimist)).perceive("q", trigger="outlook?")
        b = Jarvis(perception=LlmPerception(skeptic)).perceive("q", trigger="outlook?")
        a_belief, b_belief = a.working_belief, b.working_belief
        assert a_belief is not None and b_belief is not None
        assert bool(a_belief.explain().supporting)
        assert bool(b_belief.explain().contradicting)
