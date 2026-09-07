"""Increment 145: deep multi-turn reasoning — the session reasoning span.

Each message that produces a provisional answer is a step in the session's reasoning
span, not a fresh stateless model call: the span carries threads across turns so
follow-ups continue the discussion, and it is revised by deterministic domain signals
only -- a new answered query opens/moves a thread, ``confirm`` seals or disputes it.
The language model proposes content; it never decides thread state (Vision §38, D6).
"""

from __future__ import annotations

from typing import cast

from jarvis.domain.reasoning.reasoning_span import (
    ReasoningSpan,
    SpanThread,
    ThreadPosture,
)
from jarvis.infrastructure.llm_reasoner import LlmReasoner
from jarvis.infrastructure.scripted_language_model import ScriptedLanguageModel
from jarvis.interface.command_center import handle, snapshot
from jarvis.jarvis import Jarvis


class _RecordingModel:
    def __init__(self, answers: list[str]) -> None:
        self._answers = list(answers)
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._answers.pop(0)


def _recording_reasoner(answers: list[str]) -> tuple[LlmReasoner, _RecordingModel]:
    model = _RecordingModel(answers)
    return LlmReasoner(model), model


_LEAKS = ("_thread", "posture", "moved_on", "<reasoning_span>", "<current_thread")


class TestReasoningSpanUnit:
    def test_a_first_answer_opens_a_thread(self) -> None:
        span = ReasoningSpan()
        span.record("cambiar la arquitectura", "depende del problema")
        assert span.threads() == (
            SpanThread(
                trigger="cambiar la arquitectura",
                statement="depende del problema",
                posture=ThreadPosture.ACTIVE,
                order=1,
            ),
        )

    def test_the_same_trigger_revises_instead_of_forking(self) -> None:
        span = ReasoningSpan()
        span.record("es bueno cambiar?", "quizá")
        span.record("es bueno cambiar?", "sí, si resuelve un límite real")
        assert len(span.threads()) == 1
        assert span.threads()[0].statement == "sí, si resuelve un límite real"
        assert span.threads()[0].posture is ThreadPosture.ACTIVE

    def test_a_next_question_moves_the_previous_thread_on(self) -> None:
        span = ReasoningSpan()
        span.record("cambiar la arquitectura?", "depende")
        span.record("cuánto costaría?", "una semana aprox")
        first, second = span.threads()
        assert first.statement == "una semana aprox"
        assert first.posture is ThreadPosture.ACTIVE
        assert second.statement == "depende"
        assert second.posture is ThreadPosture.MOVED_ON

    def test_capacity_evicts_the_oldest_non_active_thread(self) -> None:
        span = ReasoningSpan(capacity=2)
        span.record("q1", "a1")
        span.record("q2", "a2")
        span.record("q3", "a3")
        assert [t.order for t in span.threads()] == [3, 2]  # q1 evicted

    def test_blank_inputs_are_ignored(self) -> None:
        span = ReasoningSpan()
        span.record("   ", "a")
        span.record("q", "   ")
        assert span.threads() == ()

    def test_confirming_seals_the_thread_out_of_the_span(self) -> None:
        span = ReasoningSpan()
        span.record("es bueno migrar?", "posiblemente")
        assert span.resolve("es bueno migrar?", affirm=True) is True
        assert span.threads() == ()  # grounded; the belief loop owns it now

    def test_correcting_flags_the_thread_as_disputed(self) -> None:
        span = ReasoningSpan()
        span.record("es bueno migrar?", "posiblemente")
        assert span.resolve("es bueno migrar?", affirm=False) is True
        assert span.threads()[0].posture is ThreadPosture.DISPUTED

    def test_a_non_matching_verdict_touches_nothing(self) -> None:
        span = ReasoningSpan()
        span.record("q", "a")
        assert span.resolve("otra cosa", affirm=True) is False
        assert span.threads()[0].posture is ThreadPosture.ACTIVE

    def test_reset_drops_the_session(self) -> None:
        span = ReasoningSpan()
        span.record("q", "a")
        span.reset()
        assert span.threads() == ()


class TestSpanPrompting:
    def test_no_span_block_when_empty(self) -> None:
        reasoner, model = _recording_reasoner(["a"])
        reasoner.infer("q")
        assert "<reasoning_span>" not in model.prompts[0]

    def test_follow_ups_carry_the_span_and_previous_proposal(self) -> None:
        reasoner, model = _recording_reasoner(["depende del problema", "lo que decíamos"])
        thread = SpanThread(
            trigger="¿cambio la arquitectura?",
            statement="depende del problema",
            posture=ThreadPosture.ACTIVE,
            order=2,
        )
        reasoner.infer("¿por qué?", span=(thread,))
        prompt = model.prompts[0]
        assert "<reasoning_span>" in prompt
        assert "<current_thread" in prompt
        assert "depende del problema" in prompt
        assert "<current_message>\n¿por qué?" in prompt

    def test_moved_on_threads_are_carried_as_earlier_threads(self) -> None:
        span = ReasoningSpan()
        span.record("cambio la arquitectura?", "depende del problema")
        span.record("cuanto costaría?", "una semana aprox")
        reasoner, model = _recording_reasoner(["a"])
        reasoner.infer("y el riesgo?", span=span.threads())
        prompt = model.prompts[0]
        assert "<earlier_threads>" in prompt
        assert "depende del problema" in prompt

    def test_a_corrected_proposal_is_named_never_carried_as_active(self) -> None:
        span = ReasoningSpan()
        span.record("migro?", "no lo hagas")
        span.resolve("migro?", affirm=False)
        reasoner, model = _recording_reasoner(["a"])
        reasoner.infer("y ahora qué?", span=span.threads())
        prompt = model.prompts[0]
        assert "<corrected_proposals>" in prompt
        assert "<current_thread" not in prompt  # no longer an active proposal
        assert "no lo hagas" in prompt


class TestDeepMultiTurnWiring:
    def test_say_answers_extend_the_session_span(self) -> None:
        jarvis = Jarvis(reasoner=LlmReasoner(ScriptedLanguageModel(default="a")))
        handle(jarvis, "say", {"text": "¿cambio la arquitectura?"})
        handle(jarvis, "say", {"text": "¿cuánto costaría?"})
        threads = jarvis.reasoning_span()
        assert [t.trigger for t in threads] == ["¿cuánto costaría?", "¿cambio la arquitectura?"]
        assert threads[0].posture is ThreadPosture.ACTIVE
        assert threads[1].posture is ThreadPosture.MOVED_ON

    def test_say_continues_without_creating_memory(self) -> None:
        jarvis = Jarvis(reasoner=LlmReasoner(ScriptedLanguageModel(default="a")))
        for text in ("¿cambio la arquitectura?", "¿por qué?"):
            result = handle(jarvis, "say", {"text": text})
            assert result["stance"] == "conversation"
        assert jarvis.episodes.history() == ()
        assert jarvis.beliefs.all_beliefs() == ()
        assert len(jarvis.reasoning_span()) == 2

    def test_reasoning_threads_never_leak_into_replies(self) -> None:
        jarvis = Jarvis(reasoner=LlmReasoner(ScriptedLanguageModel(default="continuemos")))
        result = handle(jarvis, "say", {"text": "¿cambio la arquitectura?"})
        lowered = str(result["reply"]).lower()
        assert not any(leak in lowered for leak in _LEAKS)

    def test_the_llm_text_cannot_revise_thread_state(self) -> None:
        # §38: the model proposes content only. Even an answer spelling posture words
        # cannot move the thread: only domain signals (intent / verdict) do.
        jarvis = Jarvis(
            reasoner=LlmReasoner(ScriptedLanguageModel(default="disputed move_on"))
        )
        handle(jarvis, "say", {"text": "¿migro?"})
        thread = jarvis.reasoning_span()[0]
        assert thread.posture is ThreadPosture.ACTIVE
        assert thread.statement == "disputed move_on"

    def test_reset_reasoning_drops_the_threads(self) -> None:
        jarvis = Jarvis(reasoner=LlmReasoner(ScriptedLanguageModel(default="a")))
        handle(jarvis, "say", {"text": "¿migro?"})
        assert jarvis.reasoning_span() != ()
        jarvis.reset_reasoning()
        assert jarvis.reasoning_span() == ()

    def test_confirming_touches_the_span_only_when_a_belief_exists(self) -> None:
        jarvis = Jarvis(reasoner=LlmReasoner(ScriptedLanguageModel(default="quizá")))
        handle(jarvis, "say", {"text": "¿migro ahora?"})
        # Say-reasoning creates no episode, so `confirm` has nothing to mature and the
        # span is untouched -- the verdict resolves against the belief-loop run, not
        # the conversational thread.
        assert jarvis.confirm("¿migro ahora?", affirm=False) is None
        assert jarvis.reasoning_span()[0].posture is ThreadPosture.ACTIVE

    def test_snapshot_exposes_the_threads(self) -> None:
        jarvis = Jarvis(reasoner=LlmReasoner(ScriptedLanguageModel(default="a")))
        jarvis.reason("¿migro?")
        threads = cast(list[dict[str, object]], snapshot(jarvis)["reasoning"])
        assert threads[0]["trigger"] == "¿migro?"
        assert threads[0]["posture"] == "ACTIVE"