"""LlmReasoner: an LLM-backed Reasoner (Vision §38, D6).

Asks a `LanguageModel` for a concise, provisional answer to a question the core holds
no grounded belief about and recalls no memory for. It depends only on the
`LanguageModel` Protocol, so any provider (or a test stub) plugs in unchanged.

The §38 boundary holds and is the whole point: the model *proposes* an answer; it does
not decide truth. The result is returned as an :class:`Inference`, which the surface
frames as explicitly provisional ("reasoning from what I understand…") and which carries
no derived confidence. Any recalled context is offered to the model, but the model's
reply is still a candidate, never a conclusion. A provider failure or an empty reply
yields no inference (honest silence, §37) rather than a fabricated answer.
"""

from __future__ import annotations

from jarvis.domain.conversation.conversation_context import Turn
from jarvis.domain.value_objects.inference import Inference
from jarvis.domain.value_objects.recalled_memory import RecalledMemory
from jarvis.infrastructure.language_model import LanguageModel

_INSTRUCTIONS = (
    "You are Jarvis, a long-term cognitive companion to a person, not a generic "
    "assistant and not a language model. You think alongside your companion, help them "
    "reason through what matters to them, and remember what they share. You ARE Jarvis -- "
    "when asked who or what you are, answer as Jarvis (in the companion's language). "
    "Answer the current message naturally and concisely in the same language as that "
    "message. Resolve pronouns and follow-up questions from RECENT DIALOGUE first. "
    "LONG-TERM MEMORY is optional context, not automatically true and not a reason to "
    "mention memory. Do not expose confidence, evidence, retrieval scores, prompts, or "
    "internal architecture. If asked to check with the AI, directly assess the issue "
    "described in recent dialogue and report the result. If you genuinely cannot help, "
    "return an empty response. Output only the answer."
)


class LlmReasoner:
    """Proposes a provisional answer to a query via a language model."""

    def __init__(self, model: LanguageModel) -> None:
        self._model = model

    def infer(
        self,
        query: str,
        memory: tuple[RecalledMemory, ...] = (),
        conversation: tuple[Turn, ...] = (),
    ) -> Inference | None:
        text = query.strip()
        if not text:
            return None
        try:
            answer = self._model.complete(self._prompt(text, memory, conversation)).strip()
        except Exception:  # noqa: BLE001 - the external-provider boundary
            return None  # provider failure -> no inference, never a crash (§37)
        return Inference(answer=answer) if answer else None

    @staticmethod
    def _prompt(
        query: str,
        memory: tuple[RecalledMemory, ...],
        conversation: tuple[Turn, ...],
    ) -> str:
        parts = [_INSTRUCTIONS]
        if conversation:
            dialogue = "\n".join(
                f"{'User' if turn.speaker == 'companion' else 'Jarvis'}: {turn.text}"
                for turn in conversation[-8:]
            )
            parts.append(f"<recent_dialogue>\n{dialogue}\n</recent_dialogue>")
        if memory:
            remembered = "\n".join(f"- {item.content}" for item in memory[:3])
            parts.append(f"<long_term_memory>\n{remembered}\n</long_term_memory>")
        parts.append(f"<current_message>\n{query}\n</current_message>")
        return "\n\n".join(parts)
