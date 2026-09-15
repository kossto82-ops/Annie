"""Semantic memory continuity: abstractions must form, persist and matter (P1).

Required lifecycle:

    experience -> episode -> abstraction -> persistence -> restart
      -> candidate retrieval -> recall -> reasoning -> observable influence

Conceptually similar experiences (lexically different, same canonical concepts)
consolidate into one abstraction inside ``_remember``. After a restart, a
related-but-novel situation must surface that abstraction as a recall candidate,
hand it to reasoning, and show it in the answer.
"""

from __future__ import annotations

from pathlib import Path

from jarvis.domain.conversation.conversation_context import Turn
from jarvis.domain.enums.memory_kind import MemoryKind
from jarvis.domain.reasoning.reasoning_span import SpanThread
from jarvis.domain.value_objects.inference import Inference
from jarvis.domain.value_objects.recalled_memory import RecalledMemory
from jarvis.interface.command_center import handle
from jarvis.jarvis import Jarvis


class _MemoryEchoReasoner:
    """Answers from the recalled memories it was handed (test seam)."""

    def __init__(self) -> None:
        self.seen: list[tuple[str, tuple[RecalledMemory, ...]]] = []

    def infer(
        self,
        query: str,
        memory: tuple[RecalledMemory, ...] = (),
        conversation: tuple[Turn, ...] = (),
        span: tuple[SpanThread, ...] = (),
    ) -> Inference | None:
        self.seen.append((query, memory))
        if not memory:
            return None
        quoted = " | ".join(item.content for item in memory)
        return Inference(answer=f"bearing in mind ({quoted}), here goes.")


class TestSemanticContinuity:
    def test_abstraction_forms_persists_and_influences(self, tmp_path: Path) -> None:
        # 1-2. Conceptually related experiences; the third completes a cluster of
        # three and ``_remember`` consolidates them into one abstraction.
        session_a = Jarvis.database(tmp_path)
        session_a.think("supplier failed to deliver")
        session_a.think("the vendor missed the delivery")
        session_a.think("provider delivery failure")
        abstractions = session_a.semantic_memories
        assert abstractions is not None
        assert len(abstractions.all_memories()) == 1
        pattern = abstractions.all_memories()[0].pattern
        assert "FAIL" in pattern and "DELIVER" in pattern

        # 3-4. Persisted, then a brand-new runtime reloads it.
        session_b = Jarvis.database(tmp_path)
        reloaded = session_b.semantic_memories
        assert reloaded is not None
        assert [m.pattern for m in reloaded.all_memories()] == [pattern]

        # 5-6. A related but novel situation surfaces it as a candidate...
        candidates = session_b.recall("why did the vendor fail to deliver?")
        kinds = [c.kind for c in candidates]
        assert MemoryKind.SEMANTIC in kinds
        # ...while an unrelated one does not select it.
        unrelated = session_b.recall("quantum entanglement tuna")
        assert all(c.kind is not MemoryKind.SEMANTIC for c in unrelated)

        # 7-9. It reaches reasoning and observably influences cognition.
        probe = _MemoryEchoReasoner()
        session_b.set_reasoner(probe)
        answer = handle(session_b, "say", {"text": "why did the vendor fail to deliver?"})
        assert probe.seen, "the reasoner was never consulted"
        heard_kinds = [c.kind for _, memories in probe.seen for c in memories]
        assert MemoryKind.SEMANTIC in heard_kinds
        assert "bearing in mind" in str(answer["reply"])

    def test_json_backend_persists_abstractions(self, tmp_path: Path) -> None:
        session_a = Jarvis.persistent(tmp_path)
        session_a.think("supplier failed to deliver")
        session_a.think("the vendor missed the delivery")
        session_a.think("provider delivery failure")
        assert (tmp_path / "semantic.json").exists()

        session_b = Jarvis.persistent(tmp_path)
        reloaded = session_b.semantic_memories
        assert reloaded is not None
        assert len(reloaded.all_memories()) == 1

    def test_no_abstraction_without_recurrent_pattern(self, tmp_path: Path) -> None:
        session_a = Jarvis.database(tmp_path)
        session_a.think("supplier failed to deliver")
        session_a.think("quantum entanglement tuna")
        session_a.reflect_cycle()
        assert session_a.semantic_memories is not None
        assert session_a.semantic_memories.all_memories() == ()
