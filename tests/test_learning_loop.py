"""Inc G: the learning loop — remember what was reasoned, mature it on confirmation.

A reasoned answer is kept as the weakest, clearly-sourced evidence (so it is recalled,
not re-asked), and the companion confirming or correcting it moves the derived
confidence — the LLM proposes, Jarvis (and the companion) decide (Vision §20, §38, D6).
"""

from __future__ import annotations

from jarvis import Jarvis
from jarvis.domain.conversation.conversation_context import Turn
from jarvis.domain.enums.evidence_source import EvidenceSource
from jarvis.domain.value_objects.inference import Inference
from jarvis.domain.value_objects.recalled_memory import RecalledMemory
from jarvis.executive.executive_controller import remembered_inference, working_statement
from jarvis.interface.command_center import handle

_Q = "como funciona el filtrado"


class CountingReasoner:
    """A reasoner that returns a fixed answer and counts how often it is asked."""

    def __init__(self, answer: str = "Use an input and filter the list.") -> None:
        self.answer = answer
        self.calls = 0

    def infer(
        self,
        query: str,
        memory: tuple[RecalledMemory, ...] = (),
        conversation: tuple[Turn, ...] = (),
    ) -> Inference | None:
        _ = (memory, conversation)
        self.calls += 1
        return Inference(answer=self.answer)


def _learner(answer: str = "Use an input and filter the list.") -> tuple[Jarvis, CountingReasoner]:
    reasoner = CountingReasoner(answer)
    return Jarvis(enable_recall=True, reasoner=reasoner), reasoner


class TestRemembering:
    def test_a_reasoned_answer_becomes_the_weakest_evidence(self) -> None:
        jarvis, _ = _learner("Use fetch and a filter.")
        episode = jarvis.perceive(_Q, trigger=_Q)
        belief = episode.working_belief
        assert belief is not None
        remembered = remembered_inference(belief)
        assert remembered is not None
        assert remembered.content == "Use fetch and a filter."
        assert remembered.source is EvidenceSource.INFERENCE
        assert 0.0 < belief.confidence.value < 0.5  # held faintly, unconfirmed

    def test_a_repeat_question_is_not_re_asked_of_the_model(self) -> None:
        jarvis, reasoner = _learner()
        jarvis.perceive(_Q, trigger=_Q)
        jarvis.perceive(_Q, trigger=_Q)
        assert reasoner.calls == 1  # the second time, the answer is remembered


class TestConfirming:
    def test_confirmation_matures_the_belief_to_grounded(self) -> None:
        jarvis, _ = _learner()
        jarvis.perceive(_Q, trigger=_Q)
        belief = jarvis.confirm(_Q, affirm=True)
        assert belief is not None
        assert belief.confidence.value >= 0.5  # a real confirmation grounds it

    def test_correction_weakens_the_belief(self) -> None:
        jarvis, _ = _learner()
        working = jarvis.perceive(_Q, trigger=_Q).working_belief
        assert working is not None
        before = working.confidence.value  # capture the value; the object is mutated
        belief = jarvis.confirm(_Q, affirm=False)
        assert belief is not None
        assert belief.confidence.value < before
        assert belief.explain().contradicting  # the correction is kept, not discarded

    def test_confirming_an_unknown_topic_is_a_no_op(self) -> None:
        assert Jarvis().confirm("something never discussed") is None


class TestSayLearningLoop:
    def test_ordinary_reasoning_is_conversational_and_not_persisted(self) -> None:
        jarvis, reasoner = _learner("Use an input and filter the list.")
        first = handle(jarvis, "say", {"text": _Q})
        second = handle(jarvis, "say", {"text": _Q})
        assert first["stance"] == "conversation"
        assert second["stance"] == "conversation"
        assert reasoner.calls == 2
        assert jarvis.beliefs.get_by_statement(working_statement(_Q)) is None
        assert jarvis.episodes.history() == ()

    def test_a_short_no_without_a_persisted_reasoning_episode_is_conversation(self) -> None:
        jarvis, _ = _learner()
        handle(jarvis, "say", {"text": _Q})
        correction = handle(jarvis, "say", {"text": "no"})
        assert correction["stance"] == "conversation"

    def test_a_long_sentence_with_no_is_not_a_correction(self) -> None:
        jarvis, _ = _learner()
        handle(jarvis, "say", {"text": _Q})
        reply = handle(jarvis, "say", {"text": "no estoy seguro de cómo empezar con esto"})
        assert reply.get("stance") != "confirmation"
