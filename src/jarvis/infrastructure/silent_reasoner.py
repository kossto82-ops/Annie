"""The default reasoner: it reasons about nothing (Vision §37, §38).

Reasoning about a free-form question needs a language model. The offline default
therefore stays silent -- returning no inference -- rather than fabricating an answer
from a rule. Until a real reasoner is configured, an ungrounded question with no
recalled memory is answered honestly with "I don't have enough", exactly as before.
"""

from __future__ import annotations

from jarvis.domain.conversation.conversation_context import Turn
from jarvis.domain.value_objects.inference import Inference
from jarvis.domain.value_objects.recalled_memory import RecalledMemory


class SilentReasoner:
    """A reasoner that never proposes an answer (the offline default)."""

    def infer(
        self,
        query: str,
        memory: tuple[RecalledMemory, ...] = (),
        conversation: tuple[Turn, ...] = (),
    ) -> Inference | None:
        _ = (query, memory, conversation)
        return None
