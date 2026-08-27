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

from jarvis.domain.value_objects.inference import Inference
from jarvis.domain.value_objects.recalled_memory import RecalledMemory
from jarvis.infrastructure.language_model import LanguageModel

_INSTRUCTIONS = (
    "You are the reasoning faculty of a companion assistant. Answer the user's message "
    "helpfully and concisely from general knowledge and any context provided. This is "
    "provisional reasoning, so do not claim certainty. If you genuinely cannot say "
    "anything useful, reply with nothing at all. Reply in the same language as the "
    "user's message. Output only the answer, with no preamble."
)


class LlmReasoner:
    """Proposes a provisional answer to a query via a language model."""

    def __init__(self, model: LanguageModel) -> None:
        self._model = model

    def infer(
        self, query: str, context: tuple[RecalledMemory, ...] = ()
    ) -> Inference | None:
        text = query.strip()
        if not text:
            return None
        try:
            answer = self._model.complete(self._prompt(text, context)).strip()
        except Exception:  # noqa: BLE001 - the external-provider boundary
            return None  # provider failure -> no inference, never a crash (§37)
        return Inference(answer=answer) if answer else None

    @staticmethod
    def _prompt(query: str, context: tuple[RecalledMemory, ...]) -> str:
        prompt = f"{_INSTRUCTIONS}\n\nUser's message: {query}"
        if context:
            remembered = "; ".join(memory.content for memory in context[:3])
            prompt += f"\n\nContext I remember (may or may not be relevant): {remembered}"
        return prompt
