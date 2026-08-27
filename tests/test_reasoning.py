"""Inc D: reasoning gives a provisional answer when belief and memory have none.

The reasoner *proposes* (Vision §38, D6); the domain presents the result as an
Inference -- provisional, clearly labelled, carrying no derived confidence and never
becoming belief-evidence. Reasoning is opt-in and only fires when the belief is
ungrounded and no strong memory already answers the trigger.
"""

from __future__ import annotations

import pytest

from jarvis import Jarvis
from jarvis.domain.aggregates.cognitive_episode import (
    CognitiveEpisode,
    InvalidStateTransition,
)
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.reasoning.reasoner import Reasoner
from jarvis.domain.value_objects.confidence import Confidence
from jarvis.domain.value_objects.evidence import Evidence
from jarvis.domain.value_objects.inference import Inference
from jarvis.infrastructure.llm_reasoner import LlmReasoner
from jarvis.infrastructure.perceiver_factory import build_reasoner
from jarvis.infrastructure.scripted_language_model import ScriptedLanguageModel
from jarvis.infrastructure.silent_reasoner import SilentReasoner
from jarvis.interface.command_center import handle


class _FailingModel:
    def complete(self, prompt: str) -> str:
        raise RuntimeError("provider down")


def _reasoning_jarvis(answer: str = "Provisional answer.") -> Jarvis:
    return Jarvis(
        enable_recall=True,
        reasoner=LlmReasoner(ScriptedLanguageModel(default=answer)),
    )


def _knows_name(jarvis: Jarvis) -> None:
    jarvis.observe_companion(
        "is named Raúl",
        Evidence(
            content="me llamo Raúl",
            source=EvidenceSource.USER_STATEMENT,
            weight=Confidence(0.9),
        ),
    )


class TestReasoners:
    def test_both_reasoners_satisfy_the_protocol(self) -> None:
        assert isinstance(SilentReasoner(), Reasoner)
        assert isinstance(LlmReasoner(ScriptedLanguageModel()), Reasoner)

    def test_the_silent_reasoner_proposes_nothing(self) -> None:
        assert SilentReasoner().infer("what is recursion?") is None

    def test_the_llm_reasoner_proposes_an_answer(self) -> None:
        reasoner = LlmReasoner(ScriptedLanguageModel(default="Recursion calls itself."))
        inference = reasoner.infer("what is recursion?")
        assert inference is not None
        assert inference.answer == "Recursion calls itself."

    def test_an_empty_completion_yields_no_inference(self) -> None:
        assert LlmReasoner(ScriptedLanguageModel(default="   ")).infer("x?") is None

    def test_a_provider_failure_yields_no_inference(self) -> None:
        assert LlmReasoner(_FailingModel()).infer("x?") is None

    def test_the_offline_factory_builds_a_silent_reasoner(self) -> None:
        assert isinstance(build_reasoner("keyword"), SilentReasoner)


class TestEpisodeInference:
    def test_inference_defaults_to_none(self) -> None:
        assert CognitiveEpisode(trigger="x").inference is None

    def test_infer_attaches_an_inference(self) -> None:
        episode = CognitiveEpisode(trigger="x")
        episode.infer(Inference(answer="a"))
        assert episode.inference == Inference(answer="a")

    def test_reasoning_into_a_completed_episode_is_rejected(self) -> None:
        episode = CognitiveEpisode(trigger="x")
        episode.begin_reasoning()
        episode.begin_reflecting()
        episode.begin_deciding()
        episode.complete("done")
        with pytest.raises(InvalidStateTransition):
            episode.infer(Inference(answer="a"))


class TestReasoningWiring:
    def test_an_ungrounded_novel_question_gets_a_provisional_answer(self) -> None:
        jarvis = _reasoning_jarvis("Use an input and filter the list.")
        episode = jarvis.perceive("how do I build an HTML filter?", trigger="q")
        assert episode.inference is not None
        assert episode.inference.answer == "Use an input and filter the list."

    def test_reasoning_does_not_touch_belief_confidence(self) -> None:
        jarvis = _reasoning_jarvis()
        episode = jarvis.perceive("how do I build an HTML filter?", trigger="q")
        assert episode.working_belief is not None
        assert episode.working_belief.confidence.value == 0.0

    def test_a_strong_memory_suppresses_reasoning(self) -> None:
        jarvis = _reasoning_jarvis("SHOULD NOT APPEAR")
        _knows_name(jarvis)
        episode = jarvis.perceive("sabes mi nombre?", trigger="sabes mi nombre?")
        assert episode.inference is None

    def test_a_grounded_belief_suppresses_reasoning(self) -> None:
        jarvis = _reasoning_jarvis("SHOULD NOT APPEAR")
        # A certainty cue grounds the belief via the keyword perceiver.
        episode = jarvis.perceive("the plan is definitely ready")
        assert episode.working_belief is not None
        assert episode.working_belief.confidence.value >= 0.5
        assert episode.inference is None

    def test_without_a_reasoner_nothing_is_inferred(self) -> None:
        jarvis = Jarvis(enable_recall=True)
        episode = jarvis.perceive("how do I build an HTML filter?", trigger="q")
        assert episode.inference is None


class TestSayReasons:
    def test_say_reasons_a_provisional_answer_for_a_novel_question(self) -> None:
        jarvis = _reasoning_jarvis("Use an input and filter the list.")
        result = handle(jarvis, "say", {"text": "how do I build an HTML filter?"})
        assert result["stance"] == "inference"
        assert "reasoning from what I understand" in str(result["reply"])
        assert "Use an input and filter the list." in str(result["reply"])

    def test_a_remembered_question_prefers_memory_over_reasoning(self) -> None:
        jarvis = _reasoning_jarvis("SHOULD NOT APPEAR")
        _knows_name(jarvis)
        result = handle(jarvis, "say", {"text": "sabes mi nombre?"})
        assert result["stance"] == "memory"
        assert "Raúl" in str(result["reply"])
        assert "SHOULD NOT APPEAR" not in str(result["reply"])
