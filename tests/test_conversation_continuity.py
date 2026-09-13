"""Conversation continuity: dialogue must survive restarts and matter (P1).

Required chain:

    conversation -> persistent storage -> restart
      -> conversation reconstruction -> context retrieval
      -> reasoning -> observable influence

Rows in SQLite are not enough: Session B must demonstrably answer from
Session A's words. The stub reasoner below echoes whatever dialogue the
cognitive path hands it, so the reply proves the whole chain; a second
probe records exactly what the reasoner received.
"""

from __future__ import annotations

from pathlib import Path

from jarvis.domain.conversation.conversation_context import Turn
from jarvis.domain.reasoning.reasoning_span import SpanThread
from jarvis.domain.value_objects.inference import Inference
from jarvis.domain.value_objects.recalled_memory import RecalledMemory
from jarvis.interface.command_center import handle
from jarvis.jarvis import Jarvis


class _EchoReasoner:
    """A reasoner that answers from the dialogue it was given (test seam)."""

    def __init__(self) -> None:
        self.seen: list[tuple[str, tuple[Turn, ...]]] = []

    def infer(
        self,
        query: str,
        memory: tuple[RecalledMemory, ...] = (),
        conversation: tuple[Turn, ...] = (),
        span: tuple[SpanThread, ...] = (),
    ) -> Inference | None:
        self.seen.append((query, conversation))
        if not conversation:
            return None
        quoted = " | ".join(turn.text for turn in conversation)
        return Inference(answer=f"going on what you said before ({quoted}), here goes.")


class TestConversationContinuity:
    def test_session_b_answers_from_session_a_words(self, tmp_path: Path) -> None:
        # Session A: ordinary conversation (a statement, not an explicit
        # "remember" -- this must not become a belief to count here).
        session_a = Jarvis.persistent(tmp_path)
        session_a.set_reasoner(_EchoReasoner())
        first = handle(session_a, "say", {"text": "my boat is called Seabird"})
        assert "reply" in first
        assert (tmp_path / "conversation.json").exists()

        # Restart: a brand-new runtime from the same directory.
        session_b = Jarvis.persistent(tmp_path)
        # 1. history was restored into short-term context...
        restored = [turn.text for turn in session_b.conversation.recent()]
        assert any("Seabird" in text for text in restored)

        # ...and reaches the cognitive path when Session B asks.
        probe = _EchoReasoner()
        session_b.set_reasoner(probe)
        answer = handle(session_b, "say", {"text": "what did I tell you about my boat?"})
        # 2+3. relevant history was selected and reached reasoning...
        assert probe.seen, "the reasoner was never consulted"
        heard = [turn.text for _, turns in probe.seen for turn in turns]
        assert any("Seabird" in text for text in heard)
        # 4. ...and it influenced the result.
        assert "Seabird" in str(answer["reply"])

    def test_database_backend_hydrates_context(self, tmp_path: Path) -> None:
        session_a = Jarvis.database(tmp_path)
        handle(session_a, "say", {"text": "my boat is called Seabird"})

        session_b = Jarvis.database(tmp_path)
        restored = [turn.text for turn in session_b.conversation.recent()]
        assert any("Seabird" in text for text in restored)

    def test_context_stays_bounded(self, tmp_path: Path) -> None:
        session_a = Jarvis.persistent(tmp_path)
        for index in range(30):
            handle(session_a, "say", {"text": f"small talk number {index}"})

        session_b = Jarvis.persistent(tmp_path)
        # Hydration respects the ring capacity: recent dialogue, never the
        # whole history dumped into every prompt.
        recent = session_b.conversation.recent()
        assert len(recent) <= 12
        assert any("small talk number 29" in turn.text for turn in recent)
        assert all("small talk number 0" not in turn.text for turn in recent)
