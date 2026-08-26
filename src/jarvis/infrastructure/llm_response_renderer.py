"""LlmResponseRenderer: voice Jarvis's reply in the companion's language (Vision §40).

Given a reply the core has already decided, ask a `LanguageModel` to rephrase it in the
SAME language as the companion's message, naturally and warmly. It depends only on the
`LanguageModel` Protocol, so any provider (or a test stub) plugs in unchanged.

Strictly presentation (§38): the instruction pins the model to *rephrase only* —
preserve every fact, number, and quoted string, add nothing. If the model errors or
returns nothing usable, the original reply is returned unchanged (honest fallback, §37),
so the voice can never swallow or distort what Jarvis actually concluded.
"""

from __future__ import annotations

from jarvis.infrastructure.language_model import LanguageModel

_INSTRUCTIONS = (
    "You are the voice of an assistant. Rephrase the assistant's reply in the SAME "
    "LANGUAGE as the user's message, sounding natural and warm. Preserve the meaning "
    "EXACTLY: do not add, remove, or change any fact, number, name, or text inside "
    "quotation marks. Respond with ONLY the rephrased reply, nothing else."
)


class LlmResponseRenderer:
    """Rephrases a decided reply into the companion's language via a language model."""

    def __init__(self, model: LanguageModel) -> None:
        self._model = model

    def phrase(self, reply: str, like: str) -> str:
        text = reply.strip()
        if not text:
            return reply
        prompt = (
            f"{_INSTRUCTIONS}\n\nUser's message: {like}\n\nAssistant's reply: {text}"
        )
        try:
            rendered = self._model.complete(prompt).strip()
        except Exception:  # noqa: BLE001 - presentation must never break the reply
            return reply
        return rendered or reply
