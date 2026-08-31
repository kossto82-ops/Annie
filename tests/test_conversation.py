"""The conversational core: conversation drives memory, not memory drives conversation.

These are the minimal end-to-end cases proving the reported failure is fixed: greetings,
small talk, feedback and instructions are answered as conversation and never turned into
beliefs or metadata dumps; only an explicit "remember this" becomes memory; and recent
turns are kept as short-term context, separate from long-term memory.
"""

from __future__ import annotations

from jarvis.interface.command_center import handle
from jarvis.jarvis import Jarvis

# Internal metadata that must never leak into a conversational reply.
_LEAKS = ("confidence", "i hold", "lo creo porque", "baja confianza", "external source")


def _reply(jarvis: Jarvis, text: str) -> dict[str, object]:
    return handle(jarvis, "say", {"text": text})


def _reply_text(result: dict[str, object]) -> str:
    return str(result["reply"]).lower()


class TestConversationFirst:
    def test_a_greeting_is_answered_as_conversation(self) -> None:  # Test A
        jarvis = Jarvis()
        result = _reply(jarvis, "Hola Jarvis!")
        assert result["stance"] == "greeting"
        # No belief, no memory, no metadata — and no episode was even run.
        assert "confidence" not in result
        assert "learned" not in result
        assert "recalled" not in result
        assert jarvis.episodes.history() == ()
        assert not any(leak in _reply_text(result) for leak in _LEAKS)

    def test_greeting_then_smalltalk_keeps_continuity(self) -> None:  # Test B
        jarvis = Jarvis()
        _reply(jarvis, "Hola Jarvis!")
        result = _reply(jarvis, "Que tal?")
        assert result["stance"] == "smalltalk"
        # Both user turns are held in short-term conversational context.
        said = [turn.text for turn in jarvis.conversation.recent() if turn.speaker == "companion"]
        assert said == ["Hola Jarvis!", "Que tal?"]

    def test_feedback_is_heard_not_stored_as_a_belief(self) -> None:  # Test C
        jarvis = Jarvis()
        result = _reply(jarvis, "No funcionas muy bien.")
        assert result["stance"] == "feedback"
        assert "confidence" not in result
        assert jarvis.companion.beliefs() == ()  # not learned as a trait
        assert not any(leak in _reply_text(result) for leak in _LEAKS)

    def test_feedback_is_not_mistaken_for_a_bare_no(self) -> None:  # Test C (regression)
        jarvis = Jarvis()
        # Prior history means a stray leading "no" could hijack the confirmation path.
        _reply(jarvis, "Estoy pensando en cambiar la arquitectura.")
        result = _reply(jarvis, "No funcionas muy bien.")
        assert result["stance"] == "feedback"  # not "confirmation"
        assert "confidence" not in result

    def test_an_instruction_after_feedback_is_not_memory(self) -> None:  # Test D
        jarvis = Jarvis()
        _reply(jarvis, "No funcionas muy bien.")
        result = _reply(jarvis, "pues habla con la IA para estar seguro")
        assert result["stance"] == "instruction"
        assert "learned" not in result
        assert "remember this about you" not in _reply_text(result)
        assert jarvis.companion.beliefs() == ()  # nothing was stored

    def test_an_explicit_remember_becomes_memory(self) -> None:  # Test E
        jarvis = Jarvis()
        result = _reply(jarvis, "Recuerda que prefiero trabajar por la noche.")
        assert result["stance"] == "memory"
        traits = [belief.explain().statement for belief in jarvis.companion.beliefs()]
        assert traits == ["prefiero trabajar por la noche"]

    def test_a_statement_and_follow_ups_stay_conversational(self) -> None:  # Test F
        jarvis = Jarvis()
        turns = [
            "Estoy pensando en cambiar la arquitectura.",
            "¿Crees que debería?",
            "¿Por qué?",
        ]
        for text in turns:
            result = _reply(jarvis, text)
            assert not any(leak in _reply_text(result) for leak in _LEAKS)
            assert "confidence" not in result
        # The whole exchange is retained as short-term context for follow-ups.
        said = [turn.text for turn in jarvis.conversation.recent() if turn.speaker == "companion"]
        assert said == turns
